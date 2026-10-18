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
        self._idx = 0

    def sort(self, *args, **kwargs):
        return self

    def batch_size(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._idx]
        self._idx += 1
        return item

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
                if "$addToSet" in update:
                    for k, v in update["$addToSet"].items():
                        arr = list(d.get(k) or [])
                        items_to_add = v["$each"] if isinstance(v, dict) and "$each" in v else [v]
                        for item in items_to_add:
                            if item not in arr:
                                arr.append(item)
                        d[k] = arr
                if "$pull" in update:
                    for k, v in update["$pull"].items():
                        arr = list(d.get(k) or [])
                        d[k] = [x for x in arr if x != v]
                return MagicMock(modified_count=1)
        if upsert:
            new_doc = dict(filt)
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$addToSet" in update:
                for k, v in update["$addToSet"].items():
                    arr = list(new_doc.get(k) or [])
                    if v not in arr:
                        arr.append(v)
                    new_doc[k] = arr
            self.docs.append(new_doc)
            return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    async def delete_one(self, filt):
        for i, d in enumerate(self.docs):
            if self._match(d, filt):
                self.docs.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

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
                if "$in" in v:
                    if isinstance(val, list):
                        if not any(item in v["$in"] for item in val):
                            return False
                    elif val not in v["$in"]:
                        return False
                if "$nin" in v and val in v["$nin"]:
                    return False
                if "$gte" in v and (val is None or val < v["$gte"]):
                    return False
            else:
                if isinstance(val, list):
                    if v != val and v not in val:
                        return False
                elif val != v:
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


# ══════════════════════════════════════════════════════════════════
#  🧪 تست‌های جامع بخش ۱ تا ۵ (فاز ۵: Educational Group, Filtering, Staging, Conflicts, Duplicate Sessions)
# ══════════════════════════════════════════════════════════════════

def test_section1_ai_name_suggestion_vs_verified_separation():
    """بخش ۱: پیشنهاد هوش مصنوعی از روی نام هرگز نباید بدون تأیید، فیلد قطعی را تغییر دهد و برای نام‌های مشترک/ناقص باید unknown برگرداند."""
    import asyncio

    # ۱) نام‌های مشخص پسرانه و دخترانه
    sug_male = Database.suggest_educational_group_from_name("محمدرضا کریمی")
    assert sug_male["ai_suggested_group"] == "male"
    assert sug_male["ai_confidence"] >= 0.85

    sug_female = Database.suggest_educational_group_from_name("فاطمه زهرا حسینی")
    assert sug_female["ai_suggested_group"] == "female"
    assert sug_female["ai_confidence"] >= 0.85

    # ۲) نام‌های مشترک، تک‌کلمه‌ای مبهم یا ناقص ← باید unknown باشد
    for amb_name in ("متین رضایی", "الهام؟", "ماهان", "دکتر", "A.R", ""):
        sug_amb = Database.suggest_educational_group_from_name(amb_name)
        assert sug_amb["ai_suggested_group"] == "unknown", f"Expected unknown for {amb_name}"
        assert sug_amb["ai_confidence"] == 0.0

    # ۳) Backfill کاربران قدیمی هرگز فیلد قطعی (educational_group / group_verified) را بدون تأیید پر نمی‌کند
    async def _run():
        db_inst = Database.__new__(Database)
        db_inst._user_cache = {}
        db_inst._user_cache_ttl = 60.0
        db_inst.users = _FakeCollection([
            {"user_id": 501, "name": "امیرحسین علوی", "group": "1", "approved": True},
            {"user_id": 502, "name": "متین محمدی", "group": "2", "approved": True},
            {"user_id": 503, "name": "سارا رضایی", "group": "1", "approved": True, "educational_group": "female", "group_verified": True, "group_source": "user_confirmed"},
        ])
        db_inst.educational_group_logs = _FakeCollection([])
        db_inst.educational_group_logs.insert_one = AsyncMock()

        res = await db_inst.backfill_legacy_users_educational_group(dry_run=False)
        assert res["ok"] is True
        assert res["already_verified"] == 1
        assert res["suggested_male"] == 1
        assert res["ambiguous_unknown"] == 1

        u501 = await db_inst.get_user(501, use_cache=False)
        assert u501["ai_suggested_group"] == "male"
        # قانون طلایی: بدون تأیید کاربر/ادمین، وضعیت قطعی همچنان unknown و group_verified=False می‌ماند
        assert u501["educational_group"] == "unknown"
        assert u501["group_verified"] is False
        info_501 = Database.extract_user_educational_group_info(u501)
        assert info_501["needs_confirmation"] is True

        # حالا کاربر ۵۰۱ تأیید می‌کند
        await db_inst.set_user_educational_group(501, "male", source="user_confirmed", verified=True, actor_id=501)
        u501_after = await db_inst.get_user(501, use_cache=False)
        info_after = Database.extract_user_educational_group_info(u501_after)
        assert info_after["educational_group"] == "male"
        assert info_after["group_verified"] is True
        assert info_after["needs_confirmation"] is False

    asyncio.run(_run())


def test_section2_central_educational_group_filtering_and_non_destructive_mismatch():
    """بخش ۲: فیلتر مرکزی کلاس‌ها براساس گروه آموزشی (آقایان/بانوان/مشترک) + عدم حذف خودکار انتخاب‌های قبلی هنگام تغییر گروه آموزشی."""
    import asyncio

    async def _run():
        db_inst = Database.__new__(Database)
        db_inst._settings_cache = None
        db_inst._settings_cache_at = 0.0
        db_inst._settings_cache_ttl = 60.0
        db_inst._settings_lock = asyncio.Lock()
        db_inst._user_cache = {}
        db_inst._user_cache_ttl = 60.0
        db_inst.settings = _FakeCollection([{"_id": "global", "current_academic_term": "1405-1"}])
        db_inst.users = _FakeCollection([
            {"user_id": 601, "name": "علی رضایی", "group": "1", "registered_group": "1", "educational_group": "male", "group_verified": True, "approved": True},
            {"user_id": 602, "name": "زهرا حسینی", "group": "1", "registered_group": "1", "educational_group": "female", "group_verified": True, "approved": True},
            {"user_id": 603, "name": "متین کاظمی", "group": "1", "registered_group": "1", "educational_group": "unknown", "group_verified": False, "approved": True},
        ])
        db_inst.course_offerings = _FakeCollection([
            # درس مشترک با دو گروه
            {"_id": "o1", "term": "1405-1", "lesson": "بافت شناسی نظری", "course_code": "98261047", "group": "1", "educational_group": "mixed", "teacher": "دکتر جعفری", "credit": 2.0},
            {"_id": "o2", "term": "1405-1", "lesson": "بافت شناسی نظری", "course_code": "98261047", "group": "2", "educational_group": "mixed", "teacher": "دکتر موسوی", "credit": 2.0},
            # درس تفکیک‌شده: گروه ۲ ویژه آقایان، گروه ۱ ویژه بانوان
            {"_id": "o3", "term": "1405-1", "lesson": "آئین زندگی(اخلاق کاربردی)", "course_code": "98331048", "group": "2", "educational_group": "male_only", "teacher": "استاد مردانه", "credit": 2.0},
            {"_id": "o4", "term": "1405-1", "lesson": "آئین زندگی(اخلاق کاربردی)", "course_code": "98331048", "group": "1", "educational_group": "female_only", "teacher": "استاد بانوان", "credit": 2.0},
            # تربیت بدنی ۲: گروه ۳ ویژه آقایان، گروه ۱ ویژه بانوان
            {"_id": "o5", "term": "1405-1", "lesson": "تربیت بدنی 2", "course_code": "98331025", "group": "3", "educational_group": "male_only", "teacher": "مربی آقایان", "credit": 1.0},
            {"_id": "o6", "term": "1405-1", "lesson": "تربیت بدنی 2", "course_code": "98331025", "group": "1", "educational_group": "female_only", "teacher": "مربی بانوان", "credit": 1.0},
        ])
        db_inst.schedule_templates = _FakeCollection([])
        db_inst.schedules = _FakeCollection([])
        db_inst.course_selections = _FakeCollection([])
        db_inst.educational_group_logs = _FakeCollection([])
        db_inst.educational_group_logs.insert_one = AsyncMock()

        # ۱) دانشجوی آقا (601): در آئین زندگی فقط گروه ۲ (male_only) و در تربیت بدنی ۲ فقط گروه ۳ (male_only) را می‌بیند
        male_state = await db_inst.get_student_course_selections(601, term="1405-1")
        male_off_map = {o["lesson"]: o for o in male_state["offerings"]}
        assert [g["group"] for g in male_off_map["آئین زندگی(اخلاق کاربردی)"]["groups"]] == ["2"]
        assert [g["group"] for g in male_off_map["تربیت بدنی 2"]["groups"]] == ["3"]
        assert [g["group"] for g in male_off_map["بافت شناسی نظری"]["groups"]] == ["1", "2"]

        # ۲) دانشجوی خانم (602): در آئین زندگی فقط گروه ۱ (female_only) و در تربیت بدنی ۲ فقط گروه ۱ (female_only) را می‌بیند
        female_state = await db_inst.get_student_course_selections(602, term="1405-1")
        female_off_map = {o["lesson"]: o for o in female_state["offerings"]}
        assert [g["group"] for g in female_off_map["آئین زندگی(اخلاق کاربردی)"]["groups"]] == ["1"]
        assert [g["group"] for g in female_off_map["تربیت بدنی 2"]["groups"]] == ["1"]

        # ۳) دانشجوی unknown (603): کلاس‌های تفکیک‌شده را بدون تأیید نمی‌بیند و needs_educational_group_confirmation=True می‌گیرد
        unk_state = await db_inst.get_student_course_selections(603, term="1405-1")
        assert unk_state["needs_educational_group_confirmation"] is True
        unk_lessons = {o["lesson"] for o in unk_state["offerings"]}
        assert "بافت شناسی نظری" in unk_lessons
        assert "آئین زندگی(اخلاق کاربردی)" not in unk_lessons

        # ۴) دانشجوی ۶۰۱ انتخاب واحد خود را ذخیره می‌کند (شامل گروه ۳ تربیت بدنی ۲)
        await db_inst.save_student_course_selections(
            601,
            [
                {"lesson": "بافت شناسی نظری", "group": "1"},
                {"lesson": "آئین زندگی(اخلاق کاربردی)", "group": "2"},
                {"lesson": "تربیت بدنی 2", "group": "3"},
            ],
            term="1405-1",
        )
        # حالا اگر گروه آموزشی ۶۰۱ به female تغییر کند، انتخاب قبلی او نباید حذف شود بلکه باید علامت‌گذاری شود!
        await db_inst.set_user_educational_group(601, "female", source="user_confirmed", verified=True)
        flagged = await db_inst.flag_mismatched_student_selections(601, "female", term="1405-1")
        assert flagged == 2  # آئین زندگی گروه ۲ و تربیت بدنی گروه ۳
        after_state = await db_inst.get_student_course_selections(601, term="1405-1")
        assert len(after_state["selections"]) == 3  # هیچ انتخابی خودکار حذف نشده!
        assert len(after_state["mismatched_selections"]) == 2

    asyncio.run(_run())


def test_section3_multi_image_reconciliation_and_staging_publish_rollback():
    """بخش ۳: تطبیق هوشمند چند تصویر انتخاب واحد (آقایان و بانوان)، جلوگیری از تکرار، حفظ دروس تفکیک‌شده، و انتشار/بازگردانی Transactional در Staging."""
    import asyncio

    # شبیه‌سازی دقیق استخراج از تصویر انتخاب واحد آقایان (مانند image-3.png) و تصویر انتخاب واحد بانوان
    boys_image_rows = [
        {"course_code": "98261047", "course_name": "بافت شناسی نظری", "group_code": "1", "credit": 2, "educational_group": "male_only", "source_image": "boys_portal.png"},
        {"course_code": "98261043", "course_name": "فیزیولوژی 1 نظری", "group_code": "1", "credit": 2, "educational_group": "male_only", "source_image": "boys_portal.png"},
        {"course_code": "98331048", "course_name": "آئین زندگی(اخلاق کاربردی)", "group_code": "2", "credit": 2, "educational_group": "male_only", "source_image": "boys_portal.png"},
        {"course_code": "98331025", "course_name": "تربیت بدنی 2", "group_code": "3", "credit": 1, "educational_group": "male_only", "source_image": "boys_portal.png"},
    ]
    girls_image_rows = [
        {"course_code": "98261047", "course_name": "بافت شناسی نظری", "group_code": "1", "credit": 2, "educational_group": "female_only", "source_image": "girls_portal.png"},
        {"course_code": "98261043", "course_name": "فیزیولوژی 1 نظری", "group_code": "1", "credit": 2, "educational_group": "female_only", "source_image": "girls_portal.png"},
        {"course_code": "98331048", "course_name": "آئین زندگی(اخلاق کاربردی)", "group_code": "1", "credit": 2, "educational_group": "female_only", "source_image": "girls_portal.png"},
        {"course_code": "98331025", "course_name": "تربیت بدنی 2", "group_code": "1", "credit": 1, "educational_group": "female_only", "source_image": "girls_portal.png"},
    ]

    reconciled = Database.reconcile_staged_course_extractions(
        boys_image_rows + girls_image_rows,
        academic_term="1405-1",
    )
    summary = reconciled["summary"]
    assert summary["raw_count"] == 8
    # ۲ درس مشترک ادغام می‌شوند (۲ ردیف) + ۲ درس تفکیک‌شده برای هر جنس جدا می‌مانند (۴ ردیف) = مجموعاً ۶ ردیف یکتا!
    assert summary["staged_count"] == 6
    assert summary["merged_shared_count"] == 2
    assert summary["distinct_gender_count"] == 4

    by_code_grp = {(it["course_code"], it["group_code"]): it for it in reconciled["items"]}
    # بافت‌شناسی گروه ۱ باید به عنوان مشترک (mixed) تشخیص داده شده باشد
    assert by_code_grp[("98261047", "1")]["educational_group"] == "mixed"
    assert by_code_grp[("98261047", "1")]["merge_status"] == "merged_shared"
    # آئین زندگی گروه ۲ (آقایان) و گروه ۱ (بانوان) باید جدا مانده باشند
    assert by_code_grp[("98331048", "2")]["educational_group"] == "male_only"
    assert by_code_grp[("98331048", "1")]["educational_group"] == "female_only"
    # تربیت بدنی ۲ گروه ۳ (آقایان) و گروه ۱ (بانوان) باید جدا مانده باشند
    assert by_code_grp[("98331025", "3")]["educational_group"] == "male_only"
    assert by_code_grp[("98331025", "1")]["educational_group"] == "female_only"

    # تست چرخه کامل Staging -> Edit -> Publish -> Rollback
    async def _run_staging():
        db_inst = Database.__new__(Database)
        db_inst._settings_cache = None
        db_inst._settings_cache_at = 0.0
        db_inst._settings_cache_ttl = 60.0
        db_inst._settings_lock = asyncio.Lock()
        db_inst.settings = _FakeCollection([{"_id": "global", "current_academic_term": "1405-1"}])
        db_inst.course_offerings = _FakeCollection([])
        db_inst.schedule_templates = _FakeCollection([])
        db_inst.course_import_staging = _FakeCollection([])
        db_inst.course_import_staging.insert_one = AsyncMock(side_effect=lambda d: db_inst.course_import_staging.docs.append(dict(d)))
        db_inst.course_offerings.insert_one = AsyncMock(side_effect=lambda d: db_inst.course_offerings.docs.append(dict(d)))
        db_inst.schedule_templates.insert_one = AsyncMock(side_effect=lambda d: db_inst.schedule_templates.docs.append(dict(d)))

        batch = await db_inst.create_course_import_staging_batch(
            raw_items=boys_image_rows + girls_image_rows,
            academic_term="1405-1",
            source_images=["boys_portal.png", "girls_portal.png"],
            created_by=1,
        )
        assert batch["status"] == "staged"
        # قبل از انتشار، دیتابیس اصلی کاملاً خالی است
        assert len(db_inst.course_offerings.docs) == 0

        # ویرایش نام استاد یکی از ردیف‌ها در Staging توسط ادمین
        first_item_id = batch["items"][0]["item_id"]
        edited_batch = await db_inst.update_course_import_staging_item(
            batch["batch_id"], first_item_id, {"instructor_name": "دکتر شریفی"}, actor_id=1
        )
        assert edited_batch["items"][0]["instructor_name"] == "دکتر شریفی"

        # انتشار بسته Staging
        pub_res = await db_inst.publish_course_import_staging_batch(batch["batch_id"], actor_id=1)
        assert pub_res["ok"] is True
        assert pub_res["published_offerings"] == 6
        assert len(db_inst.course_offerings.docs) == 6

        # بازگردانی (Rollback) بسته منتشرشده
        rb_res = await db_inst.rollback_course_import_staging_batch(batch["batch_id"], actor_id=1)
        assert rb_res["ok"] is True
        assert len(db_inst.course_offerings.docs) == 0

    asyncio.run(_run_staging())


def test_section4_false_conflict_elimination():
    """بخش ۴: رفع تمام عوامل تداخل زمانی کاذب (مرز ساعت‌ها، کلاس در برابر امتحان، آقایان در برابر بانوان، ترم متفاوت، و جابه‌جایی تک‌جلسه‌ای)."""
    items = [
        # ۱) دو کلاس پشت‌سرهم (۰۸:۰۰ تا ۱۰:۰۰ و ۱۰:۰۰ تا ۱۲:۰۰) ← نباید تداخل داشته باشند
        {"type": "class", "lesson": "آناتومی", "group": "1", "educational_group": "mixed", "term": "1405-1", "weekday": 0, "time": "08:00", "end_time": "10:00"},
        {"type": "class", "lesson": "فیزیولوژی", "group": "1", "educational_group": "mixed", "term": "1405-1", "weekday": 0, "time": "10:00", "end_time": "12:00"},
        # ۲) امتحان در همان ساعت ۰۸:۰۰ تا ۱۰:۰۰ ← نباید با کلاس هفتگی تداخل بخورد
        {"type": "exam", "lesson": "بیوشیمی", "group": "1", "educational_group": "mixed", "term": "1405-1", "date": "2026-10-17", "time": "08:00", "end_time": "10:00"},
        # ۳) کلاس ویژه آقایان (۰۸:۰۰ تا ۱۰:۰۰) و کلاس ویژه بانوان (۰۸:۰۰ تا ۱۰:۰۰) ← نباید با هم تداخل بخورند
        {"type": "class", "lesson": "تربیت بدنی آقایان", "group": "3", "educational_group": "male_only", "term": "1405-1", "weekday": 1, "time": "08:00", "end_time": "10:00"},
        {"type": "class", "lesson": "تربیت بدنی بانوان", "group": "1", "educational_group": "female_only", "term": "1405-1", "weekday": 1, "time": "08:00", "end_time": "10:00"},
        # ۴) کلاس از ترم قبلی (1404-2) در همان ساعت ۰۸:۰۰ شنبه ← نباید با ترم 1405-1 تداخل بخورد
        {"type": "class", "lesson": "درس ترم قبل", "group": "1", "educational_group": "mixed", "term": "1404-2", "weekday": 0, "time": "08:00", "end_time": "10:00"},
        # ۵) کلاس آرشیوشده در همان ساعت ۰۸:۰۰ شنبه ← نباید تداخل بخورد
        {"type": "class", "lesson": "درس آرشیوشده", "group": "1", "educational_group": "mixed", "term": "1405-1", "weekday": 0, "time": "08:00", "end_time": "10:00", "archived": True},
    ]
    conflicts = Database.detect_schedule_conflicts(items, active_term="1405-1")
    assert conflicts == []


def test_section5_admin_and_student_session_count_consistency():
    """بخش ۵: بررسی یکپارچگی جلسات برای ادمین محتوا و دانشجوی عادی (عدم نمایش هم‌زمان base + fork در نمای دانشجویی یا ادمین)."""
    import asyncio
    from bson import ObjectId

    async def _run():
        db_inst = Database.__new__(Database)
        lid = str(ObjectId())
        base_sid = ObjectId()
        fork_sid = ObjectId()

        db_inst.bs_lessons = _FakeCollection([
            {"_id": ObjectId(lid), "name": "زبان انگلیسی پیش ۲", "term": "ترم ۱", "intake": ""},
        ])
        db_inst.bs_sessions = _FakeCollection([
            {"_id": base_sid, "lesson_id": lid, "title": "جلسه اول", "sort_order": 1, "intake": "", "fork_of": None},
            {"_id": fork_sid, "lesson_id": lid, "title": "جلسه اول (ویرایش بهمن ۱۴۰۴)", "sort_order": 2, "intake": "بهمن ۱۴۰۴", "fork_of": str(base_sid)},
        ])

        # ۱) دانشجوی عادی ورودی بهمن ۱۴۰۴ ← فقط ۱ جلسه (نسخه fork) را می‌بیند
        student_sessions = await db_inst.bs_get_sessions_effective(lid, intake="بهمن ۱۴۰۴")
        assert len(student_sessions) == 1
        assert student_sessions[0]["_id"] == fork_sid

        # ۲) ادمین محتوا در نمای دانشجویی بدون فیلتر ورودی (intake=None) ← باز هم فقط ۱ جلسه می‌بیند (بدون تکرار base + fork!)
        admin_student_view = await db_inst.bs_get_sessions_effective(lid, intake=None)
        assert len(admin_student_view) == 1
        assert admin_student_view[0]["_id"] == base_sid

    asyncio.run(_run())


def test_rbac_unification_menus_and_stores_sync():
    """تست جامع Phase F: همگام‌سازی کامل دوطرفه بین «🎓 ادمین‌های محتوا» و «🛡 سطوح دسترسی ادمین»،
    منبع حقیقت واحد (user_roles + admin_roles + users.role)، رفع تداخل تاریخی content_admin/content_scoped و باطل‌سازی کش."""
    import asyncio

    async def _run():
        db_inst = Database.__new__(Database)
        db_inst._user_cache = {}
        db_inst._user_cache_ttl = 60.0
        db_inst.perm_catalog = _FakeCollection([])
        db_inst.roles = _FakeCollection([])
        db_inst.user_roles = _FakeCollection([])
        db_inst.admin_roles = _FakeCollection([])
        await db_inst.seed_system_roles()
        db_inst.users = _FakeCollection([
            {"user_id": 501, "name": "سما دمیری", "role": "student", "approved": True},
            {"user_id": 502, "name": "حورا چگینی", "role": "student", "approved": True},
            {"user_id": 503, "name": "مائده اسماعیلی", "role": "student", "approved": True},
        ])

        # ۱) اعطای نقش از منوی «🎓 ادمین‌های محتوا» (grant_content_admin) به کاربر ۵۰۱
        await db_inst.grant_content_admin(501, added_by=1)
        ca_list = await db_inst.get_content_admins()
        ar_list = await db_inst.get_all_admin_roles()
        u501 = await db_inst.get_user(501)
        assert any(a["user_id"] == 501 and a["content_role"] == "content_admin" for a in ca_list)
        assert any(r["_id"] == 501 and r["role"] == "content_admin" for r in ar_list)
        assert u501["role"] == "content_admin"
        assert await db_inst.is_content_admin(501) is True
        assert await db_inst.get_content_scope(501) == {"kind": "global", "intake": None}
        assert await db_inst.has_role(501, "content_admin") is True
        assert await db_inst.check_permission(501, "content.manage") is True

        # ۲) اعطای مجدد (Idempotency) ← نباید رکورد تکراری ایجاد شود
        await db_inst.grant_content_admin(501, added_by=1)
        ca_list_again = await db_inst.get_content_admins()
        assert sum(1 for a in ca_list_again if a["user_id"] == 501) == 1

        # ۳) اعطای نقش «📅 ادمین محتوای ورودی خاص» از منوی «🛡 سطوح دسترسی ادمین» به کاربر ۵۰۲
        await db_inst.add_admin_role(502, "content_scoped", added_by=1, scope_intake="bahman_1404")
        ca_list = await db_inst.get_content_admins()
        ar_list = await db_inst.get_all_admin_roles()
        ca_502 = next(a for a in ca_list if a["user_id"] == 502)
        ar_502 = next(r for r in ar_list if r["_id"] == 502)
        assert ca_502["content_role"] == "content_scoped"
        assert ca_502["scope_intake"] == "bahman_1404"
        assert "ادمین محتوای ورودی خاص" in ca_502["role_label"]
        assert ar_502["role"] == "content_scoped"
        assert ar_502["scope_intake"] == "bahman_1404"
        assert await db_inst.is_content_admin(502) is True
        assert await db_inst.get_content_scope(502) == {"kind": "scoped", "intake": "bahman_1404"}
        assert await db_inst.has_role(502, "content_scoped") is True

        # ۴) تغییر سطح همان کاربر ۵۰۲ از ورودی‌خاص به ادمین ارشد محتوا (جایگزینی متقابل بدون تداخل برچسب)
        await db_inst.add_admin_role(502, "content_admin", added_by=1)
        ar_502_after = await db_inst.get_admin_role(502)
        ur_502_after = await db_inst.get_user_roles(502)
        assert ar_502_after["role"] == "content_admin"
        assert ar_502_after.get("scope_intake") is None
        assert "content_scoped" not in ur_502_after["keys"]
        assert await db_inst.get_content_scope(502) == {"kind": "global", "intake": None}

        # ۵) لغو نقش از منوی «🎓 ادمین‌های محتوا» (revoke_content_admin) برای کاربر ۵۰۱
        await db_inst.revoke_content_admin(501, actor_id=1)
        ca_list = await db_inst.get_content_admins()
        ar_list = await db_inst.get_all_admin_roles()
        u501_after = await db_inst.get_user(501)
        assert not any(a["user_id"] == 501 for a in ca_list)
        assert not any(r["_id"] == 501 for r in ar_list)
        assert u501_after["role"] == "student"
        assert await db_inst.is_content_admin(501) is False
        assert await db_inst.get_content_scope(501) is None

        # ۶) لغو نقش از منوی «🛡 سطوح دسترسی ادمین» (remove_admin_role) برای کاربر ۵۰۲
        await db_inst.remove_admin_role(502)
        ca_list = await db_inst.get_content_admins()
        ar_list = await db_inst.get_all_admin_roles()
        u502_after = await db_inst.get_user(502)
        assert not any(a["user_id"] == 502 for a in ca_list)
        assert not any(r["_id"] == 502 for r in ar_list)
        assert u502_after["role"] == "student"
        assert await db_inst.is_content_admin(502) is False
        assert await db_inst.get_content_scope(502) is None

        # ۷) شبیه‌سازی رکورد تاریخی متناقض (مشاهده‌شده در image-2.png: هم‌زمان content_scoped + content_admin با scope_intake)
        # و اجرای خودترمیم rbac_migrate_users
        db_inst.users.docs.append({"user_id": 504, "name": "سیده یاسمن هاشمی", "role": "content_admin", "approved": True})
        db_inst.user_roles.docs.append({
            "_id": 504,
            "roles": ["content_scoped", "content_admin"],
            "scope_intake": "bahman_1404",
        })
        db_inst.admin_roles.docs.append({
            "_id": 504,
            "role": "content_admin",
            "roles": ["content_scoped", "content_admin"],
            "scope_intake": "bahman_1404",
        })
        await db_inst.rbac_migrate_users()
        ar_504 = await db_inst.get_admin_role(504)
        ur_504 = await db_inst.get_user_roles(504)
        assert ur_504["keys"] == ["content_scoped"]
        assert ar_504["role"] == "content_scoped"
        assert ar_504["scope_intake"] == "bahman_1404"
        assert await db_inst.get_content_scope(504) == {"kind": "scoped", "intake": "bahman_1404"}

    asyncio.run(_run())


