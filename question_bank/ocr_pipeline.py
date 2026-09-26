"""OCR + question segmentation for screenshot/PDF-style medical QBank sources.

Design rules (non-negotiable):
- Never invent stem, options, or answers.
- Missing / low-confidence fields → errors + needs_review signals.
- correct_option stays null unless an explicit answer key is supplied separately.
- Persian normalization is display-safe (ي/ک digits) without destroying meaning.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .contracts import clean_text, normalized_question_text

# Optional heavy deps — imported lazily so runtime image stays light unless OCR runs.
_PIL = None
_PYTESS = None

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_TO_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

_BUTTON_NOISE = re.compile(
    r"(ثبت\s*و\s*مشاهده\s*پاسخ\s*صحیح|مشاهده\s*پاسخ\s*صحیح|MedioFast|"
    r"www\.[a-z0-9.\-]+|https?://\S+)",
    re.IGNORECASE,
)
_OPTION_BULLET = re.compile(
    r"^\s*(?:[a-dA-D]|[آاببپپتتجج]|[۱-۴1-4]|[①②③④])[\s\)\]\.\-_:،]+"
)
_QUESTION_NUM = re.compile(
    r"^\s*(?:سؤال|سوال|Q)?\s*([0-9۰-۹]{1,4})\s*[\-\.|\:\)]\s*"
)


@dataclass
class OcrPageResult:
    path: str
    subject: str
    page_index: int
    raw_text: str
    lines: list[str]
    confidence: float
    engine: str
    errors: list[str] = field(default_factory=list)


@dataclass
class ParsedQuestion:
    external_id: str
    page: int
    lesson: str | None
    topic: str | None
    question: str | None
    options: list[str] | None
    correct_option: int | None
    explanation: str | None
    exam_year: str | None
    exam_year_source: str
    content_source: str | None
    image: dict
    confidence: dict
    errors: list[str]
    source_path: str
    source_sha256: str | None = None
    exam_session: str | None = None
    exam_session_label: str | None = None
    exam_track: str | None = None

    def to_import_row(self) -> dict:
        return {
            "external_id": self.external_id,
            "page": self.page,
            "lesson": self.lesson,
            "topic": self.topic,
            "difficulty": None,
            "question": self.question,
            "options": self.options,
            "correct_option": self.correct_option,
            "explanation": self.explanation,
            "exam_year": self.exam_year,
            "exam_year_source": self.exam_year_source,
            "exam_session": self.exam_session,
            "exam_session_label": self.exam_session_label,
            "exam_track": self.exam_track,
            "content_source": self.content_source,
            "image": self.image,
            "confidence": self.confidence,
            "errors": list(self.errors),
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
        }


def ocr_available() -> dict:
    """Report whether local OCR can run (never raises)."""
    tess = shutil.which("tesseract")
    try:
        from PIL import Image  # noqa: F401
        pil_ok = True
    except Exception:
        pil_ok = False
    try:
        import pytesseract  # noqa: F401
        pt_ok = True
    except Exception:
        pt_ok = False
    langs = []
    if tess:
        import subprocess
        try:
            out = subprocess.run(
                [tess, "--list-langs"], capture_output=True, text=True, check=False,
            )
            langs = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip() and "list" not in ln.lower()]
        except Exception:
            langs = []
    return {
        "tesseract": bool(tess),
        "pillow": pil_ok,
        "pytesseract": pt_ok,
        "langs": langs,
        "ready": bool(tess and pil_ok and pt_ok),
    }


def _load_deps():
    global _PIL, _PYTESS
    if _PIL is None:
        from PIL import Image, ImageOps, ImageFilter
        _PIL = (Image, ImageOps, ImageFilter)
    if _PYTESS is None:
        import pytesseract
        _PYTESS = pytesseract
    return _PIL, _PYTESS


def normalize_persian_display(text: str) -> str:
    """Safe orthography normalization for storage/display."""
    if not text:
        return ""
    # Arabic yeh/kaf → Persian; keep digits as-is mixed (medical often Latin).
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("ة", "ه")
    text = text.replace("\u200c", "\u200c")  # keep ZWNJ
    text = text.replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _preprocess_for_ocr(path: Path):
    (Image, ImageOps, ImageFilter), _ = _load_deps()
    im = Image.open(path)
    if im.mode == "RGBA":
        # Dark UI screenshots: composite on black to preserve light glyphs, then invert.
        bg = Image.new("RGB", im.size, (0, 0, 0))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    gray = ImageOps.grayscale(im)
    # Heuristic: if mean is dark, invert (white-on-dark UI).
    stat = gray.resize((64, 64)).getdata()
    mean = sum(stat) / max(1, len(list(stat)) if False else 64 * 64)
    # recomputed properly
    pixels = list(gray.getdata())
    mean = sum(pixels) / max(1, len(pixels))
    if mean < 90:
        gray = ImageOps.invert(gray)
    # Upscale thin UI text
    scale = 3 if max(gray.size) < 2000 else 2
    gray = gray.resize((gray.width * scale, gray.height * scale), Image.LANCZOS)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)
    return gray


def ocr_image(path: str | Path, *, lang: str = "fas+eng") -> OcrPageResult:
    path = Path(path)
    status = ocr_available()
    if not status["ready"]:
        return OcrPageResult(
            path=str(path), subject="", page_index=0, raw_text="", lines=[],
            confidence=0.0, engine="none",
            errors=["ocr_engine_unavailable: tesseract+pillow+pytesseract required"],
        )
    _, pytesseract = _load_deps()
    errors: list[str] = []
    try:
        image = _preprocess_for_ocr(path)
    except Exception as exc:  # noqa: BLE001
        return OcrPageResult(
            path=str(path), subject="", page_index=0, raw_text="", lines=[],
            confidence=0.0, engine="tesseract",
            errors=[f"image_open_failed:{type(exc).__name__}"],
        )
    try:
        data = pytesseract.image_to_data(
            image, lang=lang, config="--psm 6", output_type=pytesseract.Output.DICT,
        )
        confs = [float(c) for c in data.get("conf", []) if str(c) not in {"-1", ""}]
        conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        text = pytesseract.image_to_string(image, lang=lang, config="--psm 6")
    except Exception as exc:  # noqa: BLE001
        return OcrPageResult(
            path=str(path), subject="", page_index=0, raw_text="", lines=[],
            confidence=0.0, engine="tesseract",
            errors=[f"ocr_failed:{type(exc).__name__}:{exc}"],
        )
    text = normalize_persian_display(text)
    text = _BUTTON_NOISE.sub(" ", text)
    lines = [normalize_persian_display(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not _BUTTON_NOISE.search(ln)]
    if conf < 0.45:
        errors.append("ocr_low_confidence")
    if len(" ".join(lines)) < 8:
        errors.append("ocr_empty_or_too_short")
    return OcrPageResult(
        path=str(path), subject="", page_index=0, raw_text="\n".join(lines),
        lines=lines, confidence=round(conf, 3), engine="tesseract", errors=errors,
    )


def _is_probably_short_option(line: str) -> bool:
    """Heuristic: short lines without '?' are option-like (EN anatomy labels etc.)."""
    s = line.strip()
    if not s or "?" in s or "؟" in s:
        return False
    if len(s) <= 48:
        return True
    # Multi-word but still option-like if no verb-ish Persian question markers
    if len(s) <= 80 and not re.search(r"(کدام|چیست|میباشد|می‌باشد|است\?|غلط|صحیح)", s):
        # mostly latin short phrase
        latin = sum(1 for ch in s if "A" <= ch <= "Z" or "a" <= ch <= "z")
        if latin >= max(3, len(s) // 3):
            return True
    return False


def _split_stem_options(lines: list[str]) -> tuple[str | None, list[str], list[str]]:
    """Split OCR lines into stem + up to 4 options. Never pads with invented text."""
    errors: list[str] = []
    if not lines:
        return None, [], ["no_ocr_lines"]
    # Drop pure noise lines
    cleaned = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if _BUTTON_NOISE.search(s):
            continue
        if s in {"○", "●", "•", "◦", "〇"}:
            continue
        # Strip bidi marks / empty RTL leftovers
        s = s.replace("\u200e", "").replace("\u200f", "").replace("\u202a", "").replace("\u202c", "").strip()
        if not s or s in {"-", "—", "_"}:
            continue
        cleaned.append(s)
    if not cleaned:
        return None, [], ["no_usable_lines"]

    # Strategy A: bullet-prefixed option lines.
    bullet_idx = [i for i, ln in enumerate(cleaned) if _OPTION_BULLET.match(ln)]
    if bullet_idx and bullet_idx[0] > 0:
        stem = " ".join(cleaned[: bullet_idx[0]]).strip()
        opts = [_OPTION_BULLET.sub("", cleaned[i]).strip() for i in bullet_idx]
        opts = [o for o in opts if o]
    else:
        # MedioFast pattern: stem may span 1+ lines; trailing short lines are options.
        # Prefer last 4 as options when total >= 5.
        if len(cleaned) >= 5:
            stem = " ".join(cleaned[:-4]).strip()
            opts = cleaned[-4:]
        elif len(cleaned) == 4:
            # If first line looks like a question and the rest are short options → 1+3 (incomplete)
            # If ALL four look like short options and none has '?', could be OCR-lost stem.
            first_is_q = ("?" in cleaned[0] or "؟" in cleaned[0] or len(cleaned[0]) >= 24
                          or bool(re.search(r"کدام|چیست|میباشد|غلط|صحیح", cleaned[0])))
            rest_opts = all(_is_probably_short_option(x) for x in cleaned[1:])
            if first_is_q and rest_opts:
                stem = cleaned[0]
                opts = cleaned[1:]
                errors.append("option_count_uncertain_3")
            elif all(_is_probably_short_option(x) for x in cleaned):
                # English-only option list with stem OCR-failed on same block — keep as 4 opts, empty stem error
                stem = None
                opts = cleaned
                errors.append("stem_missing_options_only")
            else:
                stem = cleaned[0]
                opts = cleaned[1:]
                errors.append("option_count_uncertain_3")
        elif len(cleaned) == 1:
            stem = cleaned[0]
            opts = []
            errors.append("options_missing")
        else:
            stem = cleaned[0]
            opts = cleaned[1:]
            errors.append(f"option_count_{len(opts)}")

    stem = normalize_persian_display(stem) if stem else None
    opts = [normalize_persian_display(o) for o in opts if normalize_persian_display(o)]
    # Dedup empty
    opts = [o for o in opts if o]
    if stem and len(stem) < 8:
        errors.append("stem_too_short")
    if not stem:
        errors.append("stem_missing")
    if len(opts) != 4:
        errors.append(f"expected_4_options_got_{len(opts)}")
    else:
        norms = [normalized_question_text(o) for o in opts]
        if len(set(n for n in norms if n)) != 4:
            errors.append("duplicate_options")
    return stem, opts, errors


def parse_answer_key_text(text: str) -> dict[int, int]:
    """Parse explicit answer-key text → {question_number: correct_index0}.

    Accepts lines like:
      1 الف   |  1-A  |  12) ج  |  ۱ → ب
    Returns only confidently parsed pairs. Never guesses medical answers.
    """
    mapping: dict[int, int] = {}
    if not text:
        return mapping
    letter_map = {
        "a": 0, "b": 1, "c": 2, "d": 3,
        "الف": 0, "ب": 1, "ج": 2, "د": 3,
        "آ": 0, "ا": 0,
        "1": 0, "2": 1, "3": 2, "4": 3,
        "۱": 0, "۲": 1, "۳": 2, "۴": 3,
    }
    text = text.translate(_FA_DIGITS)
    patterns = [
        re.compile(
            r"(?m)(?:^|\s)(\d{1,4})\s*[\-\.|\:\)\=]\s*([A-Da-d]|الف|ب|ج|د|آ|ا|۱|۲|۳|۴|1|2|3|4)\b"
        ),
        re.compile(
            r"(?m)(?:سؤال|سوال|Q)?\s*(\d{1,4})\s*[\:\-\.\)→➡︎=>]*\s*([A-Da-d]|الف|ب|ج|د)\b"
        ),
    ]
    for pat in patterns:
        for match in pat.finditer(text):
            num = int(match.group(1))
            raw = match.group(2).strip()
            key = raw.casefold() if raw.isascii() else raw
            if key in letter_map:
                mapping[num] = letter_map[key]
            elif raw in letter_map:
                mapping[num] = letter_map[raw]
    return mapping


def page_to_question(
    page: OcrPageResult,
    *,
    subject: str,
    page_index: int,
    sha256: str | None = None,
    exam_year: str | None = None,
    exam_session: str | None = None,
    exam_session_label: str | None = None,
    exam_track: str | None = None,
    answer_key: dict[int, int] | None = None,
    content_source: str | None = "konkoor_sarasari",
    default_topic: str | None = None,
) -> ParsedQuestion:
    stem, opts, parse_errors = _split_stem_options(page.lines)
    errors = list(page.errors) + list(parse_errors)
    # Always keep the source image reference — admin can re-OCR / attach later.
    image = {
        "required": True,
        "description": f"اسکرین منبع سؤال — {subject} — صفحه/فایل {page_index}",
        "page": page_index,
        "position": "full",
    }
    q_conf = max(0.0, min(1.0, page.confidence))
    opt_conf = q_conf if opts and len(opts) == 4 else min(q_conf, 0.4)
    correct = None
    ans_conf = 0.0
    if answer_key and page_index in answer_key:
        correct = int(answer_key[page_index])
        if not 0 <= correct < 4:
            errors.append("answer_key_out_of_range")
            correct = None
        else:
            ans_conf = 0.95
    else:
        errors.append("answer_not_in_source")
        ans_conf = 0.0

    # Confidence gates aligned with importer thresholds
    if q_conf < 0.75:
        errors.append("confidence_question_below_threshold")
    if opt_conf < 0.75:
        errors.append("confidence_options_below_threshold")
    if correct is None or ans_conf < 0.70:
        errors.append("confidence_answer_below_threshold")

    topic = default_topic or (exam_session_label or "آزمون جامع")
    lesson = clean_text(subject) or None
    # Fix common OCR diacritic noise in folder subjects already handled by caller.

    external_id = f"{clean_text(subject) or 'SUBJ'}-{page_index:04d}"
    if sha256:
        external_id = f"{external_id}-{sha256[:8]}"

    return ParsedQuestion(
        external_id=external_id,
        page=page_index,
        lesson=lesson,
        topic=topic,
        question=stem,
        options=opts if opts else None,
        correct_option=correct,
        explanation=None,
        exam_year=exam_year,
        exam_year_source="inferred_from_filename" if exam_year else "not_found",
        content_source=content_source,
        image=image,
        confidence={
            "question": round(q_conf, 3),
            "options": round(opt_conf, 3),
            "answer": round(ans_conf, 3),
            "classification": 0.5 if lesson else 0.2,
        },
        errors=sorted(set(e for e in errors if e)),
        source_path=page.path,
        source_sha256=sha256,
        exam_session=exam_session,
        exam_session_label=exam_session_label,
        exam_track=exam_track,
    )


def run_ocr_on_inventory(
    assets: list,
    *,
    exam_year: str | None = None,
    exam_session: str | None = None,
    exam_session_label: str | None = None,
    exam_track: str | None = None,
    answer_key: dict[int, int] | None = None,
    content_source: str | None = "konkoor_sarasari",
    progress_cb: Callable[[int, int, str], None] | None = None,
    subject_page_counters: bool = True,
) -> list[ParsedQuestion]:
    """OCR every image asset. PDFs are listed as errors (convert externally)."""
    results: list[ParsedQuestion] = []
    # Global page counter AND per-subject counters for stable external ids.
    global_page = 0
    per_subject: dict[str, int] = {}
    images = [a for a in assets if getattr(a, "kind", None) == "image" or (isinstance(a, dict) and a.get("kind") == "image")]
    total = len(images)
    for i, asset in enumerate(images):
        path = asset.path if not isinstance(asset, dict) else asset["path"]
        subject = asset.subject if not isinstance(asset, dict) else asset.get("subject", "unknown")
        sha = asset.sha256 if not isinstance(asset, dict) else asset.get("sha256")
        if subject_page_counters:
            per_subject[subject] = per_subject.get(subject, 0) + 1
            page_index = per_subject[subject]
        else:
            global_page += 1
            page_index = global_page
        # Answer key is global exam numbering when provided; also try subject-local.
        local_key = answer_key
        if progress_cb:
            progress_cb(i + 1, total, path)
        page = ocr_image(path)
        page.subject = subject
        page.page_index = page_index
        q = page_to_question(
            page,
            subject=subject,
            page_index=page_index,
            sha256=sha,
            exam_year=exam_year,
            exam_session=exam_session,
            exam_session_label=exam_session_label,
            exam_track=exam_track,
            answer_key=local_key,
            content_source=content_source,
            default_topic=exam_session_label or "آزمون جامع",
        )
        results.append(q)
    return results


def build_import_document(
    questions: list[ParsedQuestion],
    *,
    meta: dict | None = None,
    file_name: str | None = None,
) -> dict:
    """Build schema_version 1.0 document compatible with QuestionImportService."""
    rows = []
    for q in questions:
        row = q.to_import_row()
        # Import schema historically expects options list; keep nulls honest.
        rows.append(row)
    source = {
        "title": (meta or {}).get("title"),
        "file_name": file_name or (meta or {}).get("source_file"),
        "page_count": len(rows),
        "exam_id": (meta or {}).get("exam_id"),
        "exam_year": (meta or {}).get("year"),
        "exam_session": (meta or {}).get("session"),
        "exam_session_label": (meta or {}).get("session_label"),
        "exam_type": (meta or {}).get("exam_type"),
        "exam_track": (meta or {}).get("exam_track"),
    }
    return {
        "schema_version": "1.0",
        "source": source,
        "exam": meta or {},
        "questions": rows,
    }


def quality_report(questions: list[ParsedQuestion], inventory: dict | None = None) -> dict:
    total = len(questions)
    def count(pred):
        return sum(1 for q in questions if pred(q))

    parsed_ok = count(lambda q: q.question and q.options and len(q.options) == 4)
    needs_review = count(lambda q: bool(q.errors))
    missing_answer = count(lambda q: q.correct_option is None)
    low_ocr = count(lambda q: "ocr_low_confidence" in q.errors or (q.confidence or {}).get("question", 0) < 0.75)
    invalid_options = count(lambda q: not q.options or len(q.options) != 4)
    # duplicate by normalized stem
    seen = {}
    dup = 0
    for q in questions:
        if not q.question:
            continue
        key = normalized_question_text(q.question)
        if key in seen:
            dup += 1
        else:
            seen[key] = q.external_id
    by_subject: dict[str, int] = {}
    for q in questions:
        by_subject[q.lesson or "unknown"] = by_subject.get(q.lesson or "unknown", 0) + 1
    return {
        "total_source_files": (inventory or {}).get("total_files"),
        "total_images": (inventory or {}).get("total_images"),
        "detected_questions": total,
        "successfully_parsed": parsed_ok,
        "needs_review": needs_review,
        "missing_answer": missing_answer,
        "ocr_low_confidence": low_ocr,
        "duplicate_questions": dup,
        "duplicate_images": sum(1 for e in (inventory or {}).get("errors", []) if str(e).startswith("duplicate_bytes")),
        "invalid_options": invalid_options,
        "answer_key_mismatches": 0,  # filled by caller when key present
        "by_subject": by_subject,
    }
