"""
🧪 تست‌های جامع بخش ۲: سیستم انتخاب گروه درس‌به‌درس در بخش «برنامه»
- تست قانون اکثریت و قانون تساوی (۱۰ از ۱۰، ۷ به ۳، ۵ به ۵ با واحد نابرابر/برابر، و بدون انتخاب)
- تست ساخت برنامه شخصی‌سازی‌شده از ترکیب دو گروه + fallback برای کاربران بدون انتخاب + تداخل ساعتی
- تست ارسال خودکار پیام یادآوری پایان امتحانات ترم فقط یک بار در هر ترم برای هر دانشجو + کاتالوگ اعلانات
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from database import DB as Database


def test_notif_catalog_includes_course_selection():
    """اعلان یادآوری انتخاب واحد ترم جدید باید در کاتالوگ اعلانات با پیش‌فرض روشن ثبت شده باشد."""
    keys = [k for k, *_ in Database.NOTIF_CATALOG]
    assert "course_selection" in keys
    assert "course_selection" in Database.NOTIF_TYPES
    assert Database.DEFAULT_NOTIF_FALLBACK.get("course_selection") is True


def test_majority_group_10_of_10():
    """حالت ۱۰ از ۱۰ درس در یک گروه."""
    selections_g1 = [{"lesson": f"درس {i}", "group": "1", "credit": 2.0} for i in range(10)]
    res1 = Database.compute_majority_group(selections_g1, fallback_group="2")
    assert res1["computed_group"] == "1"
    assert res1["group1_courses"] == 10
    assert res1["group2_courses"] == 0
    assert res1["tie_broken_by"] == "course_count_majority"

    selections_g2 = [{"lesson": f"درس {i}", "group": "2", "credit": 2.0} for i in range(10)]
    res2 = Database.compute_majority_group(selections_g2, fallback_group="1")
    assert res2["computed_group"] == "2"
    assert res2["group1_courses"] == 0
    assert res2["group2_courses"] == 10
    assert res2["tie_broken_by"] == "course_count_majority"


def test_majority_group_7_to_3():
    """حالت ۷ درس از یک گروه و ۳ درس از گروه دیگر."""
    selections = (
        [{"lesson": f"درس الف {i}", "group": "1", "credit": 2.0} for i in range(3)]
        + [{"lesson": f"درس ب {i}", "group": "2", "credit": 1.0} for i in range(7)]
    )
    res = Database.compute_majority_group(selections, fallback_group="1")
    assert res["computed_group"] == "2"
    assert res["group1_courses"] == 3
    assert res["group2_courses"] == 7
    assert res["tie_broken_by"] == "course_count_majority"


def test_majority_group_5_to_5_tie_broken_by_credits():
    """حالت تساوی ۵ به ۵ در تعداد درس‌ها: گروهی که مجموع واحدهای بیشتری دارد برنده می‌شود."""
    selections = (
        [{"lesson": f"درس سنگین {i}", "group": "1", "credit": 3.0} for i in range(5)]  # 15 واحد
        + [{"lesson": f"درس سبک {i}", "group": "2", "credit": 2.0} for i in range(5)]  # 10 واحد
    )
    res = Database.compute_majority_group(selections, fallback_group="2")
    assert res["computed_group"] == "1"
    assert res["group1_courses"] == 5
    assert res["group2_courses"] == 5
    assert res["group1_credits"] == 15.0
    assert res["group2_credits"] == 10.0
    assert res["tie_broken_by"] == "credit_tiebreaker"


def test_majority_group_5_to_5_exact_tie_keeps_previous_group():
    """حالت تساوی ۵ به ۵ هم در تعداد درس‌ها و هم در مجموع واحدها: گروه قبلی/ثبت‌نام دانشجو حفظ می‌شود."""
    selections = (
        [{"lesson": f"درس الف {i}", "group": "1", "credit": 2.0} for i in range(5)]
        + [{"lesson": f"درس ب {i}", "group": "2", "credit": 2.0} for i in range(5)]
    )
    res_keep_1 = Database.compute_majority_group(selections, fallback_group="1")
    assert res_keep_1["computed_group"] == "1"
    assert res_keep_1["tie_broken_by"] == "fallback_tiebreaker"

    res_keep_2 = Database.compute_majority_group(selections, fallback_group="2")
    assert res_keep_2["computed_group"] == "2"
    assert res_keep_2["tie_broken_by"] == "fallback_tiebreaker"


def test_majority_group_no_selection_fallback():
    """حالت بدون انتخاب (۰ درس): گروه قبلی/ثبت‌نام دانشجو حفظ می‌شود."""
    res1 = Database.compute_majority_group([], fallback_group="1")
    assert res1["computed_group"] == "1"
    assert res1["total_selected"] == 0
    assert res1["tie_broken_by"] == "no_selection"

    res2 = Database.compute_majority_group([], fallback_group="2")
    assert res2["computed_group"] == "2"
    assert res2["total_selected"] == 0
    assert res2["tie_broken_by"] == "no_selection"


def test_detect_schedule_conflicts():
    """تشخیص تداخل ساعتی دو درس انتخابی در یک روز."""
    items = [
        {
            "type": "class",
            "lesson": "فارماکولوژی",
            "group": "1",
            "date": "2026-10-18",
            "time": "08:00",
            "end_time": "10:00",
        },
        {
            "type": "class",
            "lesson": "پاتولوژی",
            "group": "2",
            "date": "2026-10-18",
            "time": "09:00",
            "end_time": "10:00",
        },
        {
            "type": "class",
            "lesson": "فیزیولوژی",
            "group": "1",
            "date": "2026-10-18",
            "time": "10:00",
            "end_time": "12:00",
        },
    ]
    conflicts = Database.detect_schedule_conflicts(items)
    assert len(conflicts) == 1
    assert conflicts[0]["lesson_a"] == "فارماکولوژی"
    assert conflicts[0]["lesson_b"] == "پاتولوژی"


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self._docs[:length] if length else self._docs)


class _FakeCollection:
    def __init__(self, initial=None):
        self.docs = list(initial or [])

    def find(self, query=None, projection=None):
        q = query or {}
        matched = [d for d in self.docs if self._match(d, q)]
        return _FakeCursor(matched)

    async def find_one(self, query=None):
        q = query or {}
        for d in self.docs:
            if self._match(d, q):
                return dict(d)
        return None

    async def update_one(self, filt, update, upsert=False):
        for d in self.docs:
            if self._match(d, filt):
                if "$set" in update:
                    d.update(update["$set"])
                if "$setOnInsert" in update:
                    for k, v in update["$setOnInsert"].items():
                        d.setdefault(k, v)
                return MagicMock(modified_count=1)
        if upsert:
            new_doc = dict(filt)
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            if "$set" in update:
                new_doc.update(update["$set"])
            self.docs.append(new_doc)
            return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    async def update_many(self, filt, update):
        cnt = 0
        for d in self.docs:
            if self._match(d, filt):
                if "$set" in update:
                    d.update(update["$set"])
                cnt += 1
        return MagicMock(modified_count=cnt)

    async def delete_many(self, filt):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not self._match(d, filt)]
        return MagicMock(deleted_count=before - len(self.docs))

    async def count_documents(self, filt):
        return sum(1 for d in self.docs if self._match(d, filt or {}))

    async def distinct(self, field, filt=None):
        vals = set()
        for d in self.docs:
            if self._match(d, filt or {}) and field in d:
                vals.add(d[field])
        return list(vals)

    @staticmethod
    def _get_val(doc, key):
        if key in doc:
            return True, doc[key]
        if "." in key:
            cur = doc
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return False, None
            return True, cur
        return False, None

    @classmethod
    def _match(cls, doc, query):
        for k, v in (query or {}).items():
            if k == "$or":
                if not any(cls._match(doc, sub) for sub in v):
                    return False
                continue
            exists, val = cls._get_val(doc, k)
            if isinstance(v, dict):
                if "$exists" in v:
                    if bool(v["$exists"]) != exists:
                        return False
                if "$ne" in v and val == v["$ne"]:
                    return False
                if "$in" in v and val not in v["$in"]:
                    return False
                if "$nin" in v and val in v["$nin"]:
                    return False
                if "$gte" in v and (val is None or val < v["$gte"]):
                    return False
            else:
                if val != v:
                    return False
        return True


def test_personalized_schedule_combined_groups_and_fallback():
    """تست ساخت برنامه شخصی‌سازی‌شده از ترکیب گروه ۱ و گروه ۲ + fallback برای دانشجوی بدون انتخاب."""
    import asyncio

    async def _run():
        db_inst = Database.__new__(Database)
        db_inst._settings_cache = None
        db_inst._settings_cache_at = 0.0
        db_inst._settings_cache_ttl = 60.0
        db_inst._settings_lock = asyncio.Lock()
        db_inst._user_cache = {}
        db_inst._user_cache_ttl = 60.0
        db_inst.settings = _FakeCollection([{"_id": "global", "current_academic_term": "1404-2"}])
        db_inst.users = _FakeCollection([
            {"user_id": 101, "name": "سارا", "group": "1", "registered_group": "1", "approved": True},
            {"user_id": 102, "name": "علی", "group": "2", "registered_group": "2", "approved": True},
        ])
        db_inst.course_offerings = _FakeCollection([])
        db_inst.course_selections = _FakeCollection([])
        db_inst.schedule_templates = _FakeCollection([])
        db_inst.schedules = _FakeCollection([
            {"_id": "s1", "type": "class", "lesson": "فارماکولوژی", "teacher": "دکتر رضایی", "group": "1", "date": "2099-05-10", "time": "08:00", "end_time": "10:00", "credit": 3.0},
            {"_id": "s2", "type": "class", "lesson": "فارماکولوژی", "teacher": "دکتر کریمی", "group": "2", "date": "2099-05-11", "time": "10:00", "end_time": "12:00", "credit": 3.0},
            {"_id": "s3", "type": "class", "lesson": "پاتولوژی", "teacher": "دکتر علوی", "group": "1", "date": "2099-05-12", "time": "08:00", "end_time": "10:00", "credit": 2.0},
            {"_id": "s4", "type": "class", "lesson": "پاتولوژی", "teacher": "دکتر حسینی", "group": "2", "date": "2099-05-12", "time": "13:00", "end_time": "15:00", "credit": 2.0},
            {"_id": "s5", "type": "class", "lesson": "اخلاق پزشکی", "teacher": "دکتر محمدی", "group": "هر دو", "date": "2099-05-13", "time": "15:00", "end_time": "17:00", "credit": 1.0},
        ])

        # ۱) کاربر ۱۰۲ هنوز انتخاب واحد وارد نکرده ← fallback به گروه ۲
        fallback_res = await db_inst.get_personalized_schedules(102, stype="class", upcoming=True)
        assert fallback_res["has_custom_selection"] is False
        assert fallback_res["computed_group"] == "2"
        fallback_ids = {it["_id"] for it in fallback_res["items"]}
        assert fallback_ids == {"s2", "s4", "s5"}

        # ۲) کاربر ۱۰۱ فارماکولوژی را با گروه ۲ (۳ واحد) و پاتولوژی را با گروه ۱ (۲ واحد) برمی‌دارد
        # چون ۱ درس گروه ۱ و ۱ درس گروه ۲ دارد (تساوی ۱ به ۱)، اما واحد گروه ۲ بیشتر است (۳ > ۲) ← گروه محاسبه‌شده = ۲
        save_res = await db_inst.save_student_course_selections(
            101,
            [
                {"lesson": "فارماکولوژی", "group": "2"},
                {"lesson": "پاتولوژی", "group": "1"},
            ],
            term="1404-2",
        )
        assert save_res["ok"] is True
        assert save_res["computed_group"] == "2"
        assert save_res["majority"]["tie_broken_by"] == "credit_tiebreaker"

        # بررسی ذخیره در پروفایل کاربر
        updated_u101 = await db_inst.get_user(101)
        assert updated_u101["computed_group"] == "2"
        assert updated_u101["group"] == "2"
        assert updated_u101["registered_group"] == "1"

        # ۳) بررسی برنامه شخصی‌سازی‌شده کاربر ۱۰۱ (ترکیب s2 از گروه ۲ + s3 از گروه ۱ + s5 مشترک)
        pers_res = await db_inst.get_personalized_schedules(101, stype="class", upcoming=True)
        assert pers_res["has_custom_selection"] is True
        pers_ids = {it["_id"] for it in pers_res["items"]}
        assert pers_ids == {"s2", "s3", "s5"}
        assert pers_res["unselected_lessons"] == []

        # ۴) حالت انتخاب ناقص (فقط فارماکولوژی انتخاب شده و پاتولوژی انتخاب نشده)
        await db_inst.save_student_course_selections(
            101,
            [{"lesson": "فارماکولوژی", "group": "1"}],
            term="1404-2",
        )
        partial_res = await db_inst.get_personalized_schedules(101, stype="class", upcoming=True)
        partial_ids = {it["_id"] for it in partial_res["items"]}
        # پاتولوژی نباید نمایش داده شود، و در unselected_lessons لیست شود
        assert partial_ids == {"s1", "s5"}
        assert partial_res["unselected_lessons"] == ["پاتولوژی"]

    asyncio.run(_run())


def test_single_group_course_auto_selected():
    """درس تک‌گروهی (فقط گروه ۱ بدون گروه ۲) باید single_group=True و auto_selected_group='1' داشته باشد."""
    import asyncio

    async def _run():
        db_inst = Database.__new__(Database)
        db_inst._settings_cache = None
        db_inst._settings_cache_at = 0.0
        db_inst._settings_cache_ttl = 60.0
        db_inst._settings_lock = asyncio.Lock()
        db_inst.settings = _FakeCollection([{"_id": "global", "current_academic_term": "1404-2"}])
        db_inst.course_offerings = _FakeCollection([])
        db_inst.schedule_templates = _FakeCollection([])
        db_inst.schedules = _FakeCollection([
            {"_id": "s1", "type": "class", "lesson": "ژنتیک", "teacher": "دکتر نادری", "group": "1", "date": "2099-05-10", "time": "08:00", "end_time": "10:00", "credit": 2.0},
        ])
        offerings = await db_inst.get_term_course_offerings("1404-2")
        assert len(offerings) == 1
        assert offerings[0]["lesson"] == "ژنتیک"
        assert offerings[0]["single_group"] is True
        assert offerings[0]["auto_selected_group"] == "1"

    asyncio.run(_run())


def test_auto_term_course_selection_reminder_once_per_term():
    """تست ارسال خودکار پیام پایان امتحانات ترم فقط یک بار برای هر دانشجو در هر ترم."""
    import asyncio

    async def _run():
        db_inst = Database.__new__(Database)
        db_inst._settings_cache = None
        db_inst._settings_cache_at = 0.0
        db_inst._settings_cache_ttl = 60.0
        db_inst._settings_lock = asyncio.Lock()
        db_inst._user_cache = {}
        db_inst._user_cache_ttl = 60.0
        db_inst.settings = _FakeCollection([
            {
                "_id": "global",
                "current_academic_term": "1404-2",
                "term_exams_end_date": "2020-01-01",
            },
        ])
        db_inst.users = _FakeCollection([
            # دانشجو ۱: هنوز انتخاب واحد نزده و پیام نگرفته ← باید پیام بگیرد
            {"user_id": 201, "name": "مینا", "group": "1", "approved": True, "suspended": False, "blocked_bot": False},
            # دانشجو ۲: قبلاً انتخاب واحدش را وارد کرده ← نباید پیام بگیرد
            {"user_id": 202, "name": "رضا", "group": "2", "approved": True, "suspended": False, "blocked_bot": False},
            # دانشجو ۳: اعلان course_selection را خاموش کرده ← نباید پیام بگیرد
            {
                "user_id": 203,
                "name": "کاوه",
                "group": "1",
                "approved": True,
                "suspended": False,
                "blocked_bot": False,
                "notification_settings": {"course_selection": False},
            },
        ])
        db_inst.course_selections = _FakeCollection([
            {"user_id": 202, "term": "1404-2", "lesson": "آناتومی", "group": "2", "archived": False},
        ])
        db_inst.inbox_add = AsyncMock()

        fake_bot = MagicMock()
        fake_bot.send_message = AsyncMock()

        # اجرای اول: فقط دانشجو ۲۰۱ باید پیام را دریافت کند
        res1 = await db_inst.run_term_course_selection_reminder(fake_bot, force=False)
        assert res1["triggered"] is True
        assert res1["sent"] == 1
        assert res1["skipped_has_selection"] == 1
        assert fake_bot.send_message.call_count == 1
        sent_call = fake_bot.send_message.call_args
        assert sent_call.kwargs["chat_id"] == 201
        assert "امتحانات تموم شد" in sent_call.kwargs["text"]

        # اجرای دوم در همان ترم: هیچ پیامی نباید دوباره ارسال شود (فقط یک بار در هر ترم)
        res2 = await db_inst.run_term_course_selection_reminder(fake_bot, force=False)
        assert res2["triggered"] is True
        assert res2["sent"] == 0
        assert res2["skipped_already_reminded"] >= 1
        assert fake_bot.send_message.call_count == 1

    asyncio.run(_run())
