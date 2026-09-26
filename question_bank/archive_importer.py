"""High-level reusable archive → OCR → import-JSON pipeline (QBANK-W5).

This is the durable entry point for every future exam:
  Esfand 1403, Shahrivar 1404, Shahrivar 1405, … — same code path.
  Year/session are CLI/API arguments (or inferred from filenames), never
  hard-coded branches.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .archive_extract import prepare_source
from .contracts import QuestionDomainError, clean_text
from .exam_meta import build_exam_metadata
from .ocr_pipeline import (
    build_import_document,
    ocr_available,
    parse_answer_key_text,
    quality_report,
    run_ocr_on_inventory,
)


def run_archive_pipeline(
    source: str | Path,
    *,
    work_dir: str | Path,
    output_json: str | Path | None = None,
    report_path: str | Path | None = None,
    exam_year: str | None = None,
    exam_session: str | None = None,
    exam_type: str = "basic_sciences",
    exam_track: str | None = None,
    title: str | None = None,
    content_source: str = "konkoor_sarasari",
    answer_key_file: str | Path | None = None,
    answer_key_text: str | None = None,
) -> dict[str, Any]:
    """Extract → inventory → OCR → schema 1.0 JSON + quality report."""
    source_s = str(source)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    meta = build_exam_metadata(
        title=title,
        exam_type=exam_type,
        year=exam_year,
        session=exam_session,
        source_file=Path(source_s).name,
        exam_track=exam_track,
    )
    # If CLI omitted year/session, inference from path already ran inside build.

    inventory = prepare_source(source, work / "src")
    inv_dict = inventory.to_dict()

    answer_key: dict[int, int] = {}
    if answer_key_file:
        answer_key.update(parse_answer_key_text(Path(answer_key_file).read_text(encoding="utf-8")))
    if answer_key_text:
        answer_key.update(parse_answer_key_text(answer_key_text))

    engine = ocr_available()
    if not engine.get("ready") and inventory.total_images:
        raise QuestionDomainError(
            "ocr_engine_unavailable",
            "برای OCR محلی tesseract + pillow + pytesseract لازم است "
            f"(tesseract={engine.get('tesseract')}, pillow={engine.get('pillow')}, "
            f"pytesseract={engine.get('pytesseract')})",
            503,
        )

    progress_log: list[str] = []

    def _cb(done: int, total: int, path: str) -> None:
        if done == 1 or done == total or done % 25 == 0:
            progress_log.append(f"{done}/{total}")

    questions = run_ocr_on_inventory(
        inventory.assets,
        exam_year=meta.get("year"),
        exam_session=meta.get("session"),
        exam_session_label=meta.get("session_label"),
        exam_track=meta.get("exam_track"),
        answer_key=answer_key or None,
        content_source=content_source,
        progress_cb=_cb,
    )

    # Cross-validate answer key numbers vs detected pages (global numbering optional)
    mismatches = 0
    if answer_key:
        pages = {q.page for q in questions}
        for num, opt in answer_key.items():
            if num not in pages:
                mismatches += 1
            elif not 0 <= int(opt) < 4:
                mismatches += 1

    document = build_import_document(
        questions,
        meta=meta,
        file_name=Path(source_s).name,
    )
    report = quality_report(questions, inv_dict)
    report["answer_key_mismatches"] = mismatches
    report["answer_key_entries"] = len(answer_key)
    report["exam"] = meta
    report["ocr_engine"] = engine
    report["progress"] = progress_log

    out_json = Path(output_json) if output_json else work / "import_questions.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    out_report = Path(report_path) if report_path else work / "import_report.json"
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Also a markdown human report
    md_path = out_report.with_suffix(".md")
    md_path.write_text(_render_md_report(report, meta), encoding="utf-8")

    return {
        "ok": True,
        "exam": meta,
        "inventory": {
            "total_files": inventory.total_files,
            "total_images": inventory.total_images,
            "total_pdfs": inventory.total_pdfs,
            "subjects": inventory.subjects,
            "errors": inventory.errors[:50],
        },
        "report": report,
        "json_path": str(out_json),
        "report_path": str(out_report),
        "report_md_path": str(md_path),
        "question_count": len(questions),
    }


def _render_md_report(report: dict, meta: dict) -> str:
    title = clean_text((meta or {}).get("title")) or "Exam Import"
    lines = [
        f"# QBank Import Report — {title}",
        "",
        f"- **exam_id:** `{meta.get('exam_id')}`",
        f"- **year:** {meta.get('year')}",
        f"- **session:** {meta.get('session')} ({meta.get('session_label')})",
        f"- **track:** {meta.get('exam_track')}",
        "",
        "## Counts",
        f"- Total source files: {report.get('total_source_files')}",
        f"- Total images: {report.get('total_images')}",
        f"- Detected questions: {report.get('detected_questions')}",
        f"- Successfully parsed (stem+4 options): {report.get('successfully_parsed')}",
        f"- Needs review: {report.get('needs_review')}",
        f"- Missing answer: {report.get('missing_answer')}",
        f"- OCR low confidence: {report.get('ocr_low_confidence')}",
        f"- Duplicate questions: {report.get('duplicate_questions')}",
        f"- Duplicate images: {report.get('duplicate_images')}",
        f"- Invalid options: {report.get('invalid_options')}",
        f"- Answer-key entries: {report.get('answer_key_entries')}",
        f"- Answer-key mismatches: {report.get('answer_key_mismatches')}",
        "",
        "## By subject",
    ]
    for subj, n in sorted((report.get("by_subject") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"- {subj}: {n}")
    lines += [
        "",
        "## Policy",
        "- No fabricated stems, options, or answers were written.",
        "- Rows without an official answer key have `correct_option: null` and must be reviewed.",
        "- Source screenshots are referenced via `image.required=true` for later attach.",
        "",
    ]
    return "\n".join(lines) + "\n"
