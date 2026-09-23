"""🌊 QBANK-W2 — regression tests: extraction prompt + taxonomy injection.

Runs without MongoDB (FakeDB mimics the motor find/sort/to_list chain).
"""
import asyncio
import json

from question_bank.importer import (
    IMPORT_SCHEMA_VERSION, PROMPT_PATH, QuestionImportService,
)


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, n):
        return self._docs[:n]


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *args, **kwargs):
        return _FakeCursor(self._docs)


class _FakeDB:
    def __init__(self, lessons, sessions):
        self.bs_lessons = _FakeCollection(lessons)
        self.bs_sessions = _FakeCollection(sessions)


def _svc(lessons=None, sessions=None):
    svc = QuestionImportService.__new__(QuestionImportService)
    svc.db = _FakeDB(lessons or [], sessions or [])
    return svc


class TestPromptContent:
    """پرامپت باید هر ۴ بند §۶ + قوانین §۱۵.۱ را پوشش دهد."""

    def _text(self):
        return PROMPT_PATH.read_text(encoding="utf-8")

    def test_new_schema_fields_present(self):
        text = self._text()
        for token in ("exam_year", "exam_year_source", "explicit_in_text",
                      "not_found", "content_source", "image.page",
                      "image.position"):
            assert token in text, token

    def test_no_guess_year_rule(self):
        text = self._text()
        assert "حدس نزن" in text or "حدس نزنید" in text
        assert "سال چاپ" in text  # سال چاپ ≠ سال آزمون

    def test_two_digit_conversion_rule(self):
        text = self._text()
        assert "۹۷" in text and "1397" in text

    def test_jame_per_question_detection(self):
        text = self._text()
        assert "جامع" in text
        assert "عیناً" in text  # نام‌ها عیناً از مرجع

    def test_content_source_null_default(self):
        text = self._text()
        assert "همیشه null" in text

    def test_schema_version_still_1_0(self):
        assert IMPORT_SCHEMA_VERSION == "1.0"
        assert '"schema_version": "1.0"' in self._text()


class TestParseAcceptsNewKeys:
    def test_row_with_w2_fields_parses(self):
        payload = {
            "schema_version": "1.0",
            "source": {"title": "t"},
            "questions": [{
                "external_id": "Q1", "page": 3,
                "lesson": "بیوشیمی", "topic": "x",
                "exam_year": "1402", "exam_year_source": "explicit_in_text",
                "content_source": None,
                "image": {"required": True, "description": "d",
                          "page": 3, "position": "بالا"},
            }],
        }
        data, fingerprint = QuestionImportService.parse(
            json.dumps(payload).encode("utf-8"), "f.json")
        assert len(fingerprint) == 64
        assert data["questions"][0]["exam_year"] == "1402"
        assert data["source"]["file_name"] == "f.json"


class TestTaxonomyInjection:
    def test_reference_lists_lessons_and_topics(self):
        lessons = [{"_id": "L1", "name": "بیوشیمی", "term": "ترم ۱"}]
        sessions = [{"_id": "T1", "lesson_id": "L1", "topic": "آنزیم‌ها"}]
        out = asyncio.run(_svc(lessons, sessions).prompt())
        assert out["schema_version"] == "1.0"
        assert "درس: بیوشیمی" in out["prompt"]
        assert "مبحث: آنزیم‌ها" in out["prompt"]

    def test_empty_db_serves_base_prompt(self):
        out = asyncio.run(_svc().prompt())
        base = PROMPT_PATH.read_text(encoding="utf-8")
        assert out["prompt"] == base
