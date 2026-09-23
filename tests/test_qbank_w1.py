"""🌊 QBANK-W1 — regression tests: exam_year + content_source + exam_track.

Runs without MongoDB: pure contracts, query composition and importer inference.
"""
import pytest

from question_bank import (
    CONTENT_SOURCE_DEFAULT, CONTENT_SOURCES, EXAM_TRACKS,
    canonical_content_source, canonical_exam_track, canonical_exam_year,
    infer_exam_track_from_filename, infer_exam_year_from_filename,
)
from question_bank.contracts import QuestionDomainError, validate_question_payload
from question_bank.service import QuestionBankService


def _payload(**over):
    base = {
        "question": "کدام گزینه دربارهٔ غشای سلولی صحیح است؟ " + "x" * 12,
        "options": ["الف", "ب", "ج", "د"],
        "correct_answer": 2,
        "explanation": "توضیح کافی برای عبور از حد",
    }
    base.update(over)
    return base


class TestExamYear:
    def test_accepts_valid_year(self):
        out = validate_question_payload(_payload(exam_year="1402"))
        assert out["exam_year"] == "1402"
        assert out["exam_year_confidence"] == "extracted"

    def test_farsi_digits_normalized(self):
        out = validate_question_payload(_payload(exam_year="۱۴۰۲"))
        assert out["exam_year"] == "1402"

    def test_empty_becomes_unknown(self):
        out = validate_question_payload(_payload())
        assert out["exam_year"] is None
        assert out["exam_year_confidence"] == "unknown"

    @pytest.mark.parametrize("bad", ["97", "1299", "1431", "20ab", "1402-1403"])
    def test_out_of_range_rejected(self, bad):
        with pytest.raises(QuestionDomainError) as exc:
            canonical_exam_year(bad)
        assert exc.value.code == "invalid_exam_year"


class TestContentSource:
    def test_five_sources_defined(self):
        assert set(CONTENT_SOURCES) == {
            "hamsyar", "konkoor_sarasari", "sib_sabz", "prognoz", "other"}
        assert CONTENT_SOURCE_DEFAULT == "hamsyar"

    def test_default_on_empty(self):
        out = validate_question_payload(_payload())
        assert out["content_source"] == "hamsyar"
        assert out["content_source_label_fa"] == CONTENT_SOURCES["hamsyar"]

    def test_unknown_rejected(self):
        with pytest.raises(QuestionDomainError) as exc:
            canonical_content_source("nope")
        assert exc.value.code == "invalid_content_source"


class TestExamTrack:
    def test_two_tracks_only(self):
        assert set(EXAM_TRACKS) == {"medicine", "dentistry"}

    def test_defaults_to_medicine(self):
        assert canonical_exam_track(None) == "medicine"
        assert canonical_exam_track("") == "medicine"

    def test_unknown_falls_back_to_medicine(self):
        # track فقط متادیتای ممیزی است (§۱۵.۲)؛ مقدار ناشناس به پزشکی برمی‌گردد.
        assert canonical_exam_track("pharmacy") == "medicine"


def _flatten(query):
    """همه‌ی شرط‌های درختی کوئری را به فهرست تخت تبدیل می‌کند."""
    found = []
    stack = [query]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("$and", "$or"):
                    stack.extend(value)
                else:
                    found.append({key: value})
        elif isinstance(node, list):
            stack.extend(node)
    return found


class TestEligibleQuery:
    def _svc(self):
        return QuestionBankService.__new__(QuestionBankService)

    def test_no_filters_matches_legacy(self):
        svc = self._svc()
        q = svc.eligible_query({"lesson_id": "L1"}, intakes=[""])
        flat = _flatten(q)
        assert not [c for c in flat if "exam_year" in c or "content_source" in c]
        assert {"lesson_id": "L1"} in flat  # taxonomy دست‌نخورده

    def test_year_range_clause(self):
        svc = self._svc()
        q = svc.eligible_query({"lesson_id": "L1"}, intakes=[""],
                               exam_year_from="۱۴۰۰", exam_year_to="1402")
        assert {"exam_year": {"$gte": "1400", "$lte": "1402"}} in _flatten(q)

    def test_reversed_range_rejected(self):
        svc = self._svc()
        with pytest.raises(QuestionDomainError) as exc:
            svc.eligible_query({"lesson_id": "L1"}, intakes=[""],
                               exam_year_from="1402", exam_year_to="1400")
        assert exc.value.code == "invalid_exam_year_range"

    def test_multi_source_clause(self):
        svc = self._svc()
        q = svc.eligible_query({"lesson_id": "L1"}, intakes=[""],
                               content_source=["konkoor_sarasari", "other"])
        assert {"content_source": {"$in": ["konkoor_sarasari", "other"]}} in _flatten(q)

    def test_bad_source_rejected(self):
        svc = self._svc()
        with pytest.raises(QuestionDomainError) as exc:
            svc.eligible_query({"lesson_id": "L1"}, intakes=[None],
                               content_source=["nope"])
        assert exc.value.code == "invalid_content_source"


class TestFilenameInference:
    @pytest.mark.parametrize("name, expected", [
        ("Azmoon-Jame-OloomPaye-Pezeshki1402-[konkur.in].pdf", "1402"),
        ("آزمون-جامع-۱۴۰۱-پزشکی.pdf", "1401"),
        ("Azmun-OlumPaye-Pezeshki-Azar97-[konkur.in].pdf", None),  # ۲رقمی: نامشخص
        ("notes.pdf", None),
    ])
    def test_year(self, name, expected):
        assert infer_exam_year_from_filename(name) == expected

    @pytest.mark.parametrize("name, expected", [
        ("_@Olumpaye99_علوم_پایه_دندانپزشکی_+_پاسخ_1.rar", "dentistry"),
        ("Dentistry-Basic-Sciences-1401.pdf", "dentistry"),
        ("Azmoon-Jame-OloomPaye-Pezeshki1402.pdf", "medicine"),
    ])
    def test_track(self, name, expected):
        assert infer_exam_track_from_filename(name) == expected
