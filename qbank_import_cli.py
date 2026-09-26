#!/usr/bin/env python3
"""CLI: reusable QBank archive import (OCR → schema 1.0 JSON).

Examples:
  python qbank_import_cli.py extract --source shahrivar-1404.rar --work /tmp/q1 \\
      --exam-year 1404 --session shahrivar --exam-type basic_sciences

  python qbank_import_cli.py extract --source ./esfand-1403/ --work /tmp/q2 \\
      --exam-year 1403 --session esfand

  # Same pipeline for any future year — no Core code change:
  python qbank_import_cli.py extract --source ./shahrivar-1405.rar --work /tmp/q3 \\
      --exam-year 1405 --session shahrivar

Optional answer key (never invent answers):
  python qbank_import_cli.py extract --source archive.rar --work /tmp/q \\
      --exam-year 1404 --session shahrivar --answer-key answers.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HUMSYAR QBank archive → OCR → import JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="Extract archive, OCR images, write import JSON")
    p.add_argument("--source", "--file", dest="source", required=True,
                   help="RAR/ZIP/7z archive or folder of images")
    p.add_argument("--work", required=True, help="Working directory for extraction + outputs")
    p.add_argument("--output", help="Path for import JSON (default: WORK/import_questions.json)")
    p.add_argument("--report", help="Path for JSON report (default: WORK/import_report.json)")
    p.add_argument("--exam-year", dest="exam_year", default=None)
    p.add_argument("--session", dest="exam_session", default=None,
                   help="shahrivar|esfand|ordibehesht|mehr|… (data-driven)")
    p.add_argument("--exam-type", default="basic_sciences")
    p.add_argument("--exam-track", default="medicine", help="medicine|dentistry")
    p.add_argument("--title", default=None)
    p.add_argument("--content-source", default="konkoor_sarasari",
                   help="hamsyar|konkoor_sarasari|sib_sabz|prognoz|other")
    p.add_argument("--answer-key", dest="answer_key_file", default=None,
                   help="Optional plain-text answer key (never invent answers)")

    p2 = sub.add_parser("ocr-status", help="Check local OCR dependencies")
    p3 = sub.add_parser("sessions", help="List supported exam session keys")

    args = parser.parse_args(argv)

    if args.cmd == "ocr-status":
        # Direct submodule import avoids pulling Motor/bson via package __init__.
        from question_bank.ocr_pipeline import ocr_available
        print(json.dumps(ocr_available(), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "sessions":
        from question_bank.contracts import EXAM_SESSIONS
        print(json.dumps(EXAM_SESSIONS, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "extract":
        # Import leaf modules first so extract works on OCR-only hosts.
        from question_bank.archive_importer import run_archive_pipeline
        from question_bank.contracts import QuestionDomainError
        try:
            result = run_archive_pipeline(
                args.source,
                work_dir=args.work,
                output_json=args.output,
                report_path=args.report,
                exam_year=args.exam_year,
                exam_session=args.exam_session,
                exam_type=args.exam_type,
                exam_track=args.exam_track,
                title=args.title,
                content_source=args.content_source,
                answer_key_file=args.answer_key_file,
            )
        except QuestionDomainError as exc:
            print(json.dumps({"ok": False, "code": exc.code, "message": exc.message},
                             ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2),
                  file=sys.stderr)
            return 1
        # Compact stdout summary
        summary = {
            "ok": True,
            "exam": result.get("exam"),
            "question_count": result.get("question_count"),
            "inventory": result.get("inventory"),
            "report_highlights": {
                k: result["report"].get(k)
                for k in (
                    "detected_questions", "successfully_parsed", "needs_review",
                    "missing_answer", "ocr_low_confidence", "invalid_options",
                    "duplicate_questions", "answer_key_entries",
                )
            },
            "json_path": result.get("json_path"),
            "report_path": result.get("report_path"),
            "report_md_path": result.get("report_md_path"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
