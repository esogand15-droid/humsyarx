"""Archive discovery + extraction for QBank imports (RAR/ZIP/folder).

Reusable across years/sessions: no hard-coded exam names. Callers pass a path;
this module returns a stable inventory of image/PDF assets ordered for OCR.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .contracts import QuestionDomainError, clean_text

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"}
PDF_SUFFIXES = {".pdf"}
ARCHIVE_SUFFIXES = {".rar", ".zip", ".7z"}

_UNRAR_CANDIDATES = ("unrar", "/usr/local/bin/unrar", "/usr/bin/unrar")
_7Z_CANDIDATES = ("7z", "7za", "/usr/bin/7z")


@dataclass
class SourceAsset:
    path: str
    relative_path: str
    subject: str
    order_key: str
    index: int
    size: int
    sha256: str
    mime_hint: str
    kind: str  # image | pdf | other


@dataclass
class ArchiveInventory:
    root: str
    source_archive: str | None
    subjects: dict[str, int]
    assets: list[SourceAsset] = field(default_factory=list)
    total_files: int = 0
    total_images: int = 0
    total_pdfs: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "source_archive": self.source_archive,
            "subjects": dict(self.subjects),
            "total_files": self.total_files,
            "total_images": self.total_images,
            "total_pdfs": self.total_pdfs,
            "errors": list(self.errors),
            "assets": [asdict(a) for a in self.assets],
        }


def _which(candidates: Iterable[str]) -> str | None:
    for name in candidates:
        path = shutil.which(name) if "/" not in name else (name if Path(name).exists() else None)
        if path:
            return path
    return None


def _file_sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _natural_key(text: str) -> list:
    text = clean_text(text).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    parts = re.split(r"(\d+)", text)
    key: list = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.casefold())
    return key


def extract_archive(archive_path: str | Path, dest_dir: str | Path) -> Path:
    """Extract RAR/ZIP/7z into dest_dir. Returns the extraction root."""
    archive = Path(archive_path).expanduser().resolve()
    dest = Path(dest_dir).expanduser().resolve()
    if not archive.is_file():
        raise QuestionDomainError("archive_not_found", f"آرشیو پیدا نشد: {archive}", 404)
    dest.mkdir(parents=True, exist_ok=True)
    suffix = archive.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        return dest
    if suffix == ".rar":
        unrar = _which(_UNRAR_CANDIDATES)
        if not unrar:
            # Fallback: Python rarfile if tool is on PATH later
            try:
                import rarfile  # type: ignore
                rarfile.UNRAR_TOOL = _which(_UNRAR_CANDIDATES) or "unrar"
                with rarfile.RarFile(archive) as rf:
                    for info in rf.infolist():
                        if info.is_dir():
                            continue
                        parts = [p for p in info.filename.replace("\\", "/").split("/") if p and p != ".."]
                        target = dest.joinpath(*parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with rf.open(info) as src, target.open("wb") as out:
                            out.write(src.read())
                return dest
            except Exception as exc:  # noqa: BLE001
                raise QuestionDomainError(
                    "unrar_unavailable",
                    "برای استخراج RAR به ابزار unrar نیاز است (apt/unrar یا RARLab).",
                    503,
                ) from exc
        result = subprocess.run(
            [unrar, "x", "-o+", "-y", str(archive), str(dest) + "/"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode not in (0,):
            # unrar sometimes returns 0 with warnings; non-zero is real failure
            if not any(dest.rglob("*")):
                raise QuestionDomainError(
                    "extract_failed",
                    f"استخراج RAR ناموفق بود: {(result.stderr or result.stdout or '')[:300]}",
                    500,
                )
        return dest
    if suffix == ".7z":
        seven = _which(_7Z_CANDIDATES)
        if not seven:
            raise QuestionDomainError("sevenzip_unavailable", "ابزار 7z برای این آرشیو نصب نیست", 503)
        result = subprocess.run(
            [seven, "x", f"-o{dest}", "-y", str(archive)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0 and not any(dest.rglob("*")):
            raise QuestionDomainError("extract_failed", "استخراج 7z ناموفق بود", 500)
        return dest
    raise QuestionDomainError("unsupported_archive", f"فرمت آرشیو پشتیبانی نمی‌شود: {suffix}", 415)


def _detect_content_root(extracted: Path) -> Path:
    """If extraction has a single top-level directory, use it as exam root."""
    children = [p for p in extracted.iterdir() if not p.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extracted


def _subject_of(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return "unknown"
    parts = rel.parts
    if len(parts) >= 2:
        return clean_text(parts[0]) or "unknown"
    # Files directly under content root: use the folder name itself when it
    # looks like a subject folder (not a bare dump of mixed images).
    name = clean_text(root.name)
    if name and name.lower() not in {"extracted", "src", "single", "out", "work", "images", "img"}:
        return name
    return "general"


def inventory_tree(root: str | Path, *, source_archive: str | None = None) -> ArchiveInventory:
    """Walk a folder (already extracted) and build a deterministic asset list."""
    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise QuestionDomainError("inventory_root_missing", f"مسیر منبع وجود ندارد: {base}", 404)
    content_root = _detect_content_root(base) if base.is_dir() else base.parent
    inv = ArchiveInventory(root=str(content_root), source_archive=source_archive, subjects={})
    files = sorted(
        (p for p in content_root.rglob("*") if p.is_file() and not p.name.startswith(".")),
        key=lambda p: (_subject_of(p, content_root), _natural_key(p.name), str(p).casefold()),
    )
    # Dedup by sha256 keep first path
    seen_hash: dict[str, str] = {}
    index = 0
    for path in files:
        suffix = path.suffix.lower()
        try:
            size = path.stat().st_size
        except OSError:
            inv.errors.append(f"stat_failed:{path}")
            continue
        if size <= 0:
            inv.errors.append(f"empty_file:{path}")
            continue
        try:
            digest = _file_sha256(path)
        except OSError:
            inv.errors.append(f"hash_failed:{path}")
            continue
        inv.total_files += 1
        if digest in seen_hash:
            inv.errors.append(f"duplicate_bytes:{path}=={seen_hash[digest]}")
            # still count but skip adding second asset? Keep both references with same hash
        else:
            seen_hash[digest] = str(path)
        if suffix in IMAGE_SUFFIXES:
            kind = "image"
            inv.total_images += 1
            mime = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif", ".tif": "image/tiff",
                ".tiff": "image/tiff", ".bmp": "image/bmp",
            }.get(suffix, "application/octet-stream")
        elif suffix in PDF_SUFFIXES:
            kind = "pdf"
            inv.total_pdfs += 1
            mime = "application/pdf"
        else:
            kind = "other"
            mime = "application/octet-stream"
        if kind == "other":
            continue
        subject = _subject_of(path, content_root)
        inv.subjects[subject] = inv.subjects.get(subject, 0) + 1
        index += 1
        try:
            rel = str(path.relative_to(content_root))
        except ValueError:
            rel = path.name
        inv.assets.append(SourceAsset(
            path=str(path), relative_path=rel, subject=subject,
            order_key=path.name, index=index, size=size, sha256=digest,
            mime_hint=mime, kind=kind,
        ))
    return inv


def prepare_source(source: str | Path, work_dir: str | Path) -> ArchiveInventory:
    """Accept archive or folder; extract if needed; return inventory."""
    src = Path(source).expanduser().resolve()
    work = Path(work_dir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        return inventory_tree(src, source_archive=None)
    if src.is_file() and src.suffix.lower() in ARCHIVE_SUFFIXES:
        extract_dir = work / "extracted"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        extract_archive(src, extract_dir)
        return inventory_tree(extract_dir, source_archive=str(src))
    if src.is_file() and src.suffix.lower() in IMAGE_SUFFIXES | PDF_SUFFIXES:
        # Single file — wrap as tiny tree
        single = work / "single"
        single.mkdir(parents=True, exist_ok=True)
        target = single / src.name
        shutil.copy2(src, target)
        return inventory_tree(single, source_archive=str(src))
    raise QuestionDomainError("unsupported_source", "منبع باید پوشه، RAR/ZIP/7z یا تصویر/PDF باشد", 415)
