"""🌊 QBANK-W6 — lesson-level taxonomy independent of content-admin sessions."""
from __future__ import annotations

import pytest

from question_bank.contracts import (
    BASIC_SCIENCE_SUBJECTS,
    QBANK_LESSON_TERM,
    default_exam_bucket_topic,
    normalize_basic_science_lesson,
)


class TestLessonCatalog:
    def test_fifteen_subjects(self):
        assert len(BASIC_SCIENCE_SUBJECTS) == 15
        assert "آناتومی" in BASIC_SCIENCE_SUBJECTS
        assert "انقلاب و اندیشه اسلامی" in BASIC_SCIENCE_SUBJECTS
        assert QBANK_LESSON_TERM == "بانک سؤال"

    def test_ocr_aliases(self):
        assert normalize_basic_science_lesson("فیزیولوژِی") == "فیزیولوژی"
        assert normalize_basic_science_lesson("اپیدمولوژی") == "اپیدمیولوژی"
        assert normalize_basic_science_lesson("ایمونولوژِی") == "ایمونولوژی"
        assert normalize_basic_science_lesson("باکتری‌شناسی") == "باکتری شناسی"

    def test_bucket_topic_from_session(self):
        assert default_exam_bucket_topic(exam_session="shahrivar", exam_year="1404") == "شهریور ۱۴۰۴"
        assert default_exam_bucket_topic(exam_session="esfand", exam_year="1403") == "اسفند ۱۴۰۳"
        assert default_exam_bucket_topic(topic="شهریور ۱۴۰۴") == "شهریور ۱۴۰۴"
        # explicit topic wins
        assert default_exam_bucket_topic(
            exam_session="shahrivar", exam_year="1404", topic="آناتومی سر و گردن"
        ) == "آناتومی سر و گردن"


class TestEnsureTaxonomyUnit:
    """In-memory fake DB exercising ensure_taxonomy_for_import without Mongo."""

    @pytest.mark.asyncio
    async def test_auto_creates_lesson_and_bucket(self):
        bson = pytest.importorskip("bson")
        ObjectId = bson.ObjectId

        class FakeColl:
            def __init__(self):
                self.docs = []

            async def find_one(self, q, *a, **k):
                for d in self.docs:
                    if self._match(d, q):
                        return dict(d)
                return None

            def find(self, q=None, *a, **k):
                q = q or {}
                matched = [dict(d) for d in self.docs if self._match(d, q)]
                class C:
                    def __init__(self, rows): self.rows = rows
                    def sort(self, *a, **k): return self
                    def limit(self, n): self.rows = self.rows[:n]; return self
                    async def to_list(self, n): return self.rows[:n]
                    def __aiter__(self):
                        async def gen():
                            for r in self.rows: yield r
                        return gen()
                return C(matched)

            async def count_documents(self, q):
                return sum(1 for d in self.docs if self._match(d, q))

            async def insert_one(self, doc):
                doc = dict(doc)
                doc.setdefault("_id", ObjectId())
                self.docs.append(doc)
                class R: 
                    def __init__(self, i): self.inserted_id = i
                return R(doc["_id"])

            def _match(self, doc, q):
                if not q: return True
                if "$or" in q:
                    base = {k: v for k, v in q.items() if k != "$or"}
                    if base and not self._match(doc, base):
                        return False
                    return any(self._match(doc, branch) for branch in q["$or"])
                for k, v in q.items():
                    if isinstance(v, dict) and "$exists" in v:
                        exists = k in doc
                        if v["$exists"] and not exists: return False
                        if not v["$exists"] and exists: return False
                        continue
                    if doc.get(k) != v:
                        return False
                return True

        class FakeDB:
            def __init__(self):
                self.bs_lessons = FakeColl()
                self.bs_sessions = FakeColl()
                self.questions = FakeColl()

        from question_bank.service import QuestionBankService
        db = FakeDB()
        svc = QuestionBankService(db)
        tax = await svc.ensure_taxonomy_for_import(
            lesson="فیزیولوژِی", exam_year="1404", exam_session="shahrivar",
        )
        assert tax["lesson"] == "فیزیولوژی"
        assert tax["topic"] == "شهریور ۱۴۰۴"
        assert tax["term"] == "بانک سؤال"
        assert tax["lesson_id"] and tax["topic_id"]
        # second call reuses
        tax2 = await svc.ensure_taxonomy_for_import(
            lesson="فیزیولوژی", exam_year="1404", exam_session="shahrivar",
        )
        assert tax2["lesson_id"] == tax["lesson_id"]
        assert tax2["topic_id"] == tax["topic_id"]
        # another subject gets own lesson, same bucket name under it
        tax3 = await svc.ensure_taxonomy_for_import(
            lesson="آناتومی", exam_year="1404", exam_session="shahrivar",
        )
        assert tax3["lesson"] == "آناتومی"
        assert tax3["topic"] == "شهریور ۱۴۰۴"
        assert tax3["lesson_id"] != tax["lesson_id"]
