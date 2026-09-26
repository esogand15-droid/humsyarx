"""🌊 QBANK-W5 — archive import pipeline + exam session metadata (no MongoDB)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from question_bank.contracts import (
    EXAM_SESSIONS,
    QuestionDomainError,
    canonical_exam_session,
    public_question,
    validate_question_payload,
)
from question_bank.exam_meta import (
    build_exam_metadata,
    infer_exam_session_from_filename,
    session_label,
)
from question_bank.importer import infer_exam_session_from_filename as importer_infer_session
from question_bank.ocr_pipeline import (
    normalize_persian_display,
    parse_answer_key_text,
    _split_stem_options,
    build_import_document,
    quality_report,
    ParsedQuestion,
)


class TestExamSessionContracts:
    def test_sessions_catalog(self):
        assert "shahrivar" in EXAM_SESSIONS and "esfand" in EXAM_SESSIONS
        assert EXAM_SESSIONS["shahrivar"] == "شهریور"

    def test_canonical_session(self):
        assert canonical_exam_session("shahrivar") == "shahrivar"
        assert canonical_exam_session("شهریور") == "shahrivar"
        assert canonical_exam_session("Esfand") == "esfand"
        assert canonical_exam_session("") is None
        assert canonical_exam_session(None) is None

    def test_invalid_session_strict(self):
        with pytest.raises(QuestionDomainError) as exc:
            canonical_exam_session("not-a-real-session", strict=True)
        assert exc.value.code == "invalid_exam_session"

    def test_infer_from_filename_generic(self):
        assert infer_exam_session_from_filename("علوم_پایه_شهریور_1404.rar") == "shahrivar"
        assert infer_exam_session_from_filename("esfand-1403.zip") == "esfand"
        assert infer_exam_session_from_filename("shahrivar 1405") == "shahrivar"
        assert importer_infer_session("بانک اسفند ۱۴۰۳") == "esfand"
        # No hard-coded year branch: unknown path → None
        assert infer_exam_session_from_filename("random_bank.json") is None

    def test_session_label(self):
        assert session_label("shahrivar", "1404") == "شهریور ۱۴۰۴"
        assert session_label("esfand", "1403") == "اسفند ۱۴۰۳"

    def test_build_metadata_data_driven(self):
        m1 = build_exam_metadata(year="1404", session="shahrivar", source_file="x.rar")
        assert m1["year"] == "1404" and m1["session"] == "shahrivar"
        assert "شهریور" in (m1["session_label"] or "")
        assert "1404" in m1["exam_id"] and "shahrivar" in m1["exam_id"]
        # Future year — same function, no code change
        m2 = build_exam_metadata(year="1405", session="esfand")
        assert m2["year"] == "1405" and m2["session"] == "esfand"
        # Inference from filename only
        m3 = build_exam_metadata(source_file="konkoor_shahrivar_1402.rar")
        assert m3["year"] == "1402" and m3["session"] == "shahrivar"


class TestValidateMissingAnswer:
    def _payload(self, **over):
        base = {
            "question": "کدام گزینه دربارهٔ غشای سلولی صحیح است؟ " + "x" * 12,
            "options": ["الف", "ب", "ج", "د"],
            "correct_answer": 2,
            "explanation": "توضیح",
        }
        base.update(over)
        return base

    def test_missing_answer_rejected_by_default(self):
        with pytest.raises(QuestionDomainError):
            validate_question_payload(self._payload(correct_answer=None))

    def test_missing_answer_allowed_flag(self):
        out = validate_question_payload(
            self._payload(correct_answer=None), allow_missing_answer=True,
        )
        assert out["correct_answer"] is None
        assert out["answer_missing"] is True
        assert out["content_hash"]


class TestOcrHelpers:
    def test_normalize_persian(self):
        assert "ی" in normalize_persian_display("يک")
        assert "ک" in normalize_persian_display("كتاب")

    def test_split_stem_options_mediofast_shape(self):
        lines = [
            "کدامیک از گزینه‌های زیر غلط است؟",
            "گزینه اول درست‌نما",
            "گزینه دوم",
            "گزینه سوم",
            "گزینه چهارم",
        ]
        stem, opts, errors = _split_stem_options(lines)
        assert stem and "غلط" in stem
        assert len(opts) == 4
        assert not any(e.startswith("expected_4") for e in errors)

    def test_split_incomplete_marked(self):
        stem, opts, errors = _split_stem_options(["فقط یک خط"])
        assert "options_missing" in errors

    def test_answer_key_parser_no_guess(self):
        text = """
        1 الف
        2-B
        3) ج
        12 → د
        nonsense line
        """
        mapping = parse_answer_key_text(text)
        assert mapping[1] == 0
        assert mapping[2] == 1
        assert mapping[3] == 2
        assert mapping[12] == 3
        assert 99 not in mapping

    def test_build_import_document_schema(self):
        q = ParsedQuestion(
            external_id="T-0001", page=1, lesson="آناتومی", topic="آزمون جامع",
            question="متن سؤال کافی برای اعتبار " + "x" * 8,
            options=["ا", "ب", "ج", "د"], correct_option=None, explanation=None,
            exam_year="1404", exam_year_source="inferred_from_filename",
            content_source="konkoor_sarasari",
            image={"required": True, "description": "src", "page": 1, "position": "full"},
            confidence={"question": 0.8, "options": 0.8, "answer": 0.0, "classification": 0.5},
            errors=["answer_not_in_source"], source_path="/tmp/a.png",
            exam_session="shahrivar", exam_session_label="شهریور ۱۴۰۴", exam_track="medicine",
        )
        doc = build_import_document([q], meta=build_exam_metadata(year="1404", session="shahrivar"))
        assert doc["schema_version"] == "1.0"
        assert doc["questions"][0]["correct_option"] is None
        assert doc["questions"][0]["exam_session"] == "shahrivar"
        assert doc["source"]["exam_year"] == "1404"

    def test_quality_report_counts(self):
        qs = [
            ParsedQuestion(
                external_id="a", page=1, lesson="X", topic="t", question="q" * 12,
                options=["1", "2", "3", "4"], correct_option=None, explanation=None,
                exam_year="1404", exam_year_source="x", content_source="konkoor_sarasari",
                image={}, confidence={"question": 0.9}, errors=["answer_not_in_source"],
                source_path="p",
            )
        ]
        rep = quality_report(qs, {"total_files": 1, "total_images": 1, "errors": []})
        assert rep["detected_questions"] == 1
        assert rep["missing_answer"] == 1
        assert rep["successfully_parsed"] == 1


class TestPublicQuestionSession:
    def test_session_exposed(self):
        doc = {
            "_id": "abc", "question": "متن", "options": ["ا", "ب", "ج", "د"],
            "difficulty": "medium", "exam_year": "1404",
            "exam_session": "shahrivar", "content_source": "konkoor_sarasari",
            "provenance": {"exam_track": "medicine"},
        }
        out = public_question(doc)
        assert out["exam_session"] == "shahrivar"
        assert out["exam_session_label"] and "شهریور" in out["exam_session_label"]


class TestArchiveExtractUnit:
    def test_inventory_on_temp_images(self, tmp_path):
        from PIL import Image
        from question_bank.archive_extract import inventory_tree

        sub = tmp_path / "exam" / "فیزیولوژی"
        sub.mkdir(parents=True)
        for i in range(3):
            Image.new("RGB", (40, 20), color=(i * 40, 10, 10)).save(sub / f"q{i+1}.png")
        inv = inventory_tree(tmp_path / "exam")
        assert inv.total_images == 3
        assert inv.subjects.get("فیزیولوژی") == 3
        assert inv.assets[0].sha256 and inv.assets[0].index == 1
