"""Secure schedule and grade management endpoints."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from pydantic import BaseModel, Field

from api.auth import get_content_admin_user
from api.routers.admin_panel import _audit
from database import db
from grade_utils import normalize_grade


router = APIRouter()

ScheduleType = Literal[
    "class",
    "exam",
    "makeup",
]

ScheduleGroup = Literal[
    "1",
    "2",
    "هر دو",
]

FlexType = Literal[
    "fixed",
    "flexible",
]


def _clean(
    value,
    max_length: int = 200,
) -> str:
    text = " ".join(
        str(value or "").split()
    )

    return text[:max_length]


def _valid_date(
    value: str,
) -> str:
    try:
        datetime.strptime(
            value,
            "%Y-%m-%d",
        )

    except (
        TypeError,
        ValueError,
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "تاریخ باید با فرمت "
                "YYYY-MM-DD باشد"
            ),
        )

    return value


def _valid_time(
    value: str,
) -> str:
    value = (
        value or ""
    ).strip()

    if not value:
        return ""

    try:
        datetime.strptime(
            value,
            "%H:%M",
        )

    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                "ساعت باید با فرمت "
                "HH:MM باشد"
            ),
        )

    return value


def _schedule_document(
    item: dict,
) -> dict:
    return {
        "id": str(
            item.get("_id", "")
        ),

        "type": item.get(
            "type",
            "",
        ),

        "lesson": item.get(
            "lesson",
            "",
        ),

        "teacher": item.get(
            "teacher",
            "",
        ),

        "date": item.get(
            "date",
            "",
        ),

        "time": item.get(
            "time",
            "",
        ),

        "location": item.get(
            "location",
            "",
        ),

        "group": (
            item.get("group")
            or "هر دو"
        ),

        "note": (
            item.get("notes")
            or item.get("note", "")
        ),

        "flex_type": (
            item.get("flex_type")
            or "fixed"
        ),

        "flex_note": item.get(
            "flex_note",
            "",
        ),
    }


class ScheduleCreate(BaseModel):
    type: ScheduleType

    lesson: str = Field(
        min_length=2,
        max_length=100,
    )

    teacher: str = Field(
        default="",
        max_length=100,
    )

    date: str = Field(
        min_length=10,
        max_length=10,
    )

    time: str = Field(
        default="",
        max_length=5,
    )

    group: ScheduleGroup = "هر دو"

    location: str = Field(
        default="",
        max_length=100,
    )

    note: str = Field(
        default="",
        max_length=500,
    )

    flex_type: FlexType = "fixed"


class ScheduleUpdate(BaseModel):
    lesson: str = Field(
        min_length=2,
        max_length=100,
    )

    teacher: str = Field(
        default="",
        max_length=100,
    )

    date: str = Field(
        min_length=10,
        max_length=10,
    )

    time: str = Field(
        default="",
        max_length=5,
    )

    group: ScheduleGroup = "هر دو"

    location: str = Field(
        default="",
        max_length=100,
    )

    note: str = Field(
        default="",
        max_length=500,
    )

    flex_type: FlexType = "fixed"


class FlexChange(BaseModel):
    date: str = Field(
        min_length=10,
        max_length=10,
    )

    time: str = Field(
        min_length=5,
        max_length=5,
    )

    note: str = Field(
        default="",
        max_length=500,
    )


@router.get("/schedule")
async def schedule_list(
    stype: ScheduleType | None = Query(
        default=None
    ),

    admin=Depends(
        get_content_admin_user
    ),
):
    items = await db.get_schedules(
        stype=stype,
        upcoming=False,
    )

    if not isinstance(items, list):
        items = []

    return {
        "schedule": [
            _schedule_document(item)
            for item in items
            if isinstance(item, dict)
        ],
    }


@router.post("/schedule")
async def schedule_create(
    body: ScheduleCreate,
    admin=Depends(get_content_admin_user),
):
    date = _valid_date(body.date)
    time = _valid_time(body.time)
    lesson = _clean(body.lesson, 100)
    teacher = _clean(body.teacher, 100)
    location = _clean(body.location, 100)
    note = str(body.note or "").strip()[:500]
    group = db.normalize_group(body.group) or "هر دو"
    schedule_id = await db.add_schedule(
        stype=body.type, lesson=lesson, teacher=teacher, date=date, time=time,
        location=location, notes=note, group=group, flex_type=body.flex_type)
    item = await db.get_schedule_by_id(str(schedule_id)) or {
        "_id": schedule_id, "type": body.type, "lesson": lesson,
        "teacher": teacher, "date": date, "time": time,
        "location": location, "notes": note, "group": group,
    }
    notice = await db.schedule_notify_event(item, "created")
    await _audit(
        admin, "ایجاد برنامه آموزشی", "Schedules", severity="INFO",
        target_id=str(schedule_id), target_type="schedule", target_label=lesson,
        after={"type": body.type, "date": date, "group": group,
               "notified": notice.get("notified", 0)},
        tags=["برنامه", body.type, "پنل_وب"],
    )
    return {"ok": True, "id": str(schedule_id),
            "notified": notice.get("notified", 0)}


@router.patch("/schedule/{schedule_id}")
async def schedule_update(
    schedule_id: str, body: ScheduleUpdate,
    admin=Depends(get_content_admin_user),
):
    date = _valid_date(body.date)
    time = _valid_time(body.time)
    old = await db.get_schedule_by_id(schedule_id)
    if not old:
        raise HTTPException(status_code=404, detail="برنامه پیدا نشد")
    group = db.normalize_group(body.group) or "هر دو"
    ok = await db.update_schedule_full(
        schedule_id, _clean(body.lesson, 100), _clean(body.teacher, 100),
        date, time, _clean(body.location, 100),
        str(body.note or "").strip()[:500], group, body.flex_type)
    if not ok:
        raise HTTPException(status_code=404, detail="برنامه پیدا نشد")
    item = await db.get_schedule_by_id(schedule_id) or {
        **old, "lesson": _clean(body.lesson, 100),
        "teacher": _clean(body.teacher, 100), "date": date, "time": time,
        "location": _clean(body.location, 100), "notes": str(body.note or "").strip()[:500],
        "group": group, "flex_type": body.flex_type,
    }
    notice = await db.schedule_notify_event(item, "updated")
    await _audit(
        admin, "ویرایش برنامه آموزشی", "Schedules", severity="WARNING",
        target_id=schedule_id, target_type="schedule", target_label=item.get("lesson", ""),
        before={"lesson": old.get("lesson"), "date": old.get("date"),
                "time": old.get("time"), "group": old.get("group")},
        after={"lesson": item.get("lesson"), "date": date, "time": time,
               "group": group, "notified": notice.get("notified", 0)},
        tags=["برنامه", old.get("type", ""), "پنل_وب"],
    )
    return {"ok": True, "notified": notice.get("notified", 0)}


@router.delete("/schedule/{schedule_id}")
async def schedule_delete(
    schedule_id: str, admin=Depends(get_content_admin_user),
):
    old = await db.get_schedule_by_id(schedule_id)
    if not old:
        raise HTTPException(status_code=404, detail="برنامه پیدا نشد")
    await db.delete_schedule(schedule_id)
    notice = await db.schedule_notify_event(old, "cancelled")
    await _audit(
        admin, "حذف و لغو برنامه آموزشی", "Schedules", severity="HIGH",
        target_id=schedule_id, target_type="schedule", target_label=old.get("lesson", ""),
        before={"type": old.get("type"), "date": old.get("date"), "group": old.get("group")},
        after={"deleted": True, "notified": notice.get("notified", 0)},
        tags=["برنامه", "لغو", old.get("type", ""), "پنل_وب"],
    )
    return {"ok": True, "notified": notice.get("notified", 0)}


@router.get(
    "/schedule/flexible"
)
async def flexible_schedule_list(
    admin=Depends(
        get_content_admin_user
    ),
):
    items = await db.get_schedules(
        upcoming=True
    )

    if not isinstance(items, list):
        items = []

    return {
        "items": [
            _schedule_document(item)
            for item in items
            if (
                isinstance(item, dict)
                and item.get(
                    "flex_type"
                ) == "flexible"
            )
        ],
    }


@router.post("/schedule/{schedule_id}/flex-change")
async def flexible_schedule_change(
    schedule_id: str, body: FlexChange,
    admin=Depends(get_content_admin_user),
):
    date = _valid_date(body.date)
    time = _valid_time(body.time)
    schedule = await db.get_schedule_by_id(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="برنامه پیدا نشد")
    if schedule.get("flex_type") != "flexible":
        raise HTTPException(status_code=422, detail="این برنامه منعطف نیست")
    ok = await db.update_schedule_time(schedule_id, date, time,
                                       str(body.note or "").strip()[:500])
    if not ok:
        raise HTTPException(status_code=500, detail="تغییر زمان ذخیره نشد")
    item = {**schedule, "date": date, "time": time,
            "flex_note": str(body.note or "").strip()[:500]}
    notice = await db.schedule_notify_event(item, "time_changed")
    await _audit(
        admin, "اعلام تغییر زمان برنامه", "Schedules", severity="WARNING",
        target_id=schedule_id, target_type="schedule", target_label=schedule.get("lesson", ""),
        before={"date": schedule.get("date"), "time": schedule.get("time")},
        after={"date": date, "time": time,
               "notified": notice.get("notified", 0)},
        tags=["برنامه", "تغییر_زمان", schedule.get("type", ""), "پنل_وب"],
    )
    return {"ok": True, "notified": notice.get("notified", 0)}


class GradeEntry(BaseModel):
    user_id: int = Field(
        gt=0
    )

    score: float = Field(
        ge=0,
        le=20,
    )


class GradeBulkCreate(BaseModel):
    entries: list[GradeEntry] = Field(
        min_length=1,
        max_length=500,
    )

    lesson: str = Field(
        min_length=2,
        max_length=100,
    )

    exam_title: str = Field(
        min_length=2,
        max_length=100,
    )

    exam_date: str = Field(
        min_length=10,
        max_length=10,
    )


class GradeUpdate(BaseModel):
    score: float = Field(
        ge=0,
        le=20,
    )


@router.post("/grades/bulk")
async def grades_bulk_create(
    body: GradeBulkCreate,

    admin=Depends(
        get_content_admin_user
    ),
):
    exam_date = _valid_date(
        body.exam_date
    )

    lesson = _clean(
        body.lesson,
        100,
    )

    exam_title = _clean(
        body.exam_title,
        100,
    )

    user_ids = [
        entry.user_id
        for entry in body.entries
    ]

    if (
        len(user_ids)
        != len(set(user_ids))
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "هر دانشجو فقط یک بار "
                "باید در لیست باشد"
            ),
        )

    users = await db.users.find(
        {
            "user_id": {
                "$in": user_ids,
            },

            "approved": True,
        },
        {
            "user_id": 1,
        },
    ).to_list(
        len(user_ids)
    )

    valid_ids = {
        int(user["user_id"])
        for user in users
        if user.get("user_id")
    }

    if any(
        user_id not in valid_ids
        for user_id in user_ids
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "یک یا چند دانشجو "
                "معتبر یا تأییدشده نیستند"
            ),
        )

    saved = await db.grade_bulk_upsert(
        entries=[
            entry.model_dump()
            for entry in body.entries
        ],

        lesson=lesson,

        exam_title=exam_title,

        exam_date=exam_date,

        entered_by=admin["id"],
    )

    notified = 0

    try:
        collection = (
            db.client["medicalbot"]
            ["bot_notifications"]
        )

        safe_lesson = escape(
            lesson
        )

        safe_title = escape(
            exam_title
        )

        documents = [
            {
                "type":
                    "grade_notif",

                "chat_id":
                    item["student_id"],

                "text": (
                    "📊 <b>نمره‌ی جدید "
                    "ثبت شد</b>"

                    f"\n📚 "
                    f"{safe_lesson} — "
                    f"{safe_title}"

                    f"\n🎯 نمره: "
                    f"{item['score']}/20"
                ),

                "sent":
                    False,

                "created_at":
                    datetime.now()
                    .isoformat(),
            }

            for item in saved
        ]

        if documents:
            await collection.insert_many(
                documents
            )

        notified = len(documents)

        # 🔔 موج ۴.۹۰ — اینباکس مینی‌اپ (نمره → تب کارنامه)
        from urllib.parse import quote as _qq3
        await db.inbox_add_many([
            {'user_id': item['student_id'], 'type': 'grade',
             'title': "📊 نمره‌ی جدید ثبت شد",
             'body': (f"📚 {lesson} — {exam_title}\n"
                      f"🎯 نمره: {item['score']}/20"),
             'link': '/grades?hl=' + _qq3(str(lesson or ''))}
            for item in saved if item.get('student_id')
        ])

    except Exception:
        notified = 0

    await _audit(
        admin, "ثبت گروهی نمره", "Grades", severity="WARNING",
        target_type="grades", target_label=f"{len(saved)} دانشجو",
        after={"lesson": lesson, "exam_title": exam_title,
               "updated": len(saved), "notified": notified},
        tags=["نمرات", "ثبت_گروهی", "پنل_وب"],
    )
    return {
        "ok": True,
        "updated": len(saved),
        "notified": notified,
    }


@router.get("/grades/recent")
async def grades_recent(
    skip: int = Query(
        default=0,
        ge=0,
    ),

    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),

    intake: str | None = Query(
        default=None,
        max_length=50,
    ),

    admin=Depends(
        get_content_admin_user
    ),
):
    records = (
        await db.grade_list_recent(
            skip=skip,
            limit=limit,
            intake=intake,
        )
    )

    if not isinstance(records, list):
        records = []

    total = (
        await db.grade_count_recent(
            intake=intake
        )
    )

    user_ids = list({
        item.get("student_id")
        for item in records
        if item.get("student_id")
    })

    if user_ids:
        users = await db.users.find(
            {
                "user_id": {
                    "$in": user_ids,
                }
            },
            {
                "user_id": 1,
                "name": 1,
                "student_id": 1,
            },
        ).to_list(
            len(user_ids)
        )

    else:
        users = []

    users_by_id = {
        item.get("user_id"): item
        for item in users
    }

    result = []

    for record in records:
        grade = normalize_grade(
            record
        )

        if grade is None:
            continue

        user_id = record.get(
            "student_id"
        )

        student = users_by_id.get(
            user_id,
            {},
        )

        result.append({
            **grade,

            "student_id":
                user_id,

            "student_name": (
                student.get("name")
                or f"#{user_id}"
            ),

            "student_number":
                student.get(
                    "student_id",
                    "",
                ),
        })

    return {
        "total": max(
            0,
            int(total or 0),
        ),

        "grades": result,
    }


@router.get(
    "/grades/find-student"
)
async def grades_find_student(
    query: str = Query(
        min_length=2,
        max_length=100,
    ),

    admin=Depends(
        get_content_admin_user
    ),
):
    users = await db.search_users(
        query.strip()
    )

    return {
        "students": [
            {
                "id":
                    user.get("user_id"),

                "name":
                    user.get("name", ""),

                "student_id":
                    user.get(
                        "student_id",
                        "",
                    ),

                "group":
                    user.get(
                        "group",
                        "",
                    ),

                "intake":
                    user.get(
                        "intake",
                        "",
                    ),
            }

            for user in users

            if (
                user.get("approved")
                and user.get("user_id")
            )
        ],
    }


@router.patch("/grades/{grade_id}")
async def grade_update(
    grade_id: str, body: GradeUpdate,
    admin=Depends(get_content_admin_user),
):
    old = await db.grade_get(grade_id)
    if not old:
        raise HTTPException(status_code=404, detail="نمره پیدا نشد")
    ok = await db.grade_update_score(grade_id, body.score, admin["id"])
    if not ok:
        raise HTTPException(status_code=500, detail="اصلاح نمره انجام نشد")
    uid = old.get("student_id")
    if uid:
        await db.notify_user(
            uid, "grade", title="📊 نمره‌ات اصلاح شد",
            body=(f"📚 {old.get('lesson','')} — {old.get('exam_title','')}\n"
                  f"🎯 نمره جدید: {body.score}/20"),
            link="/grades", dm=(
                f"📊 <b>نمره‌ات اصلاح شد</b>\n\n"
                f"📚 {old.get('lesson','')} — {old.get('exam_title','')}\n"
                f"🎯 نمره جدید: <b>{body.score}/20</b>"),
        )
    await _audit(
        admin, "اصلاح نمره دانشجو", "Grades", severity="HIGH",
        target_id=grade_id, target_type="grade", target_label=str(uid or ""),
        before={"score": old.get("score")}, after={"score": body.score},
        tags=["نمرات", "اصلاح", "پنل_وب"],
    )
    return {"ok": True, "score": body.score}


@router.delete("/grades/{grade_id}")
async def grade_delete(
    grade_id: str, admin=Depends(get_content_admin_user),
):
    old = await db.grade_get(grade_id)
    if not old:
        raise HTTPException(status_code=404, detail="نمره پیدا نشد")
    ok = await db.grade_delete(grade_id)
    if not ok:
        raise HTTPException(status_code=500, detail="حذف نمره انجام نشد")
    uid = old.get("student_id")
    if uid:
        await db.notify_user(
            uid, "grade", title="📊 یک نمره از کارنامه حذف شد",
            body=f"📚 {old.get('lesson','')} — {old.get('exam_title','')}",
            link="/grades", dm=(
                f"📊 <b>یک نمره از کارنامه‌ات حذف شد</b>\n\n"
                f"📚 {old.get('lesson','')} — {old.get('exam_title','')}"),
        )
    await _audit(
        admin, "حذف نمره دانشجو", "Grades", severity="HIGH",
        target_id=grade_id, target_type="grade", target_label=str(uid or ""),
        before={"lesson": old.get("lesson"), "exam_title": old.get("exam_title"),
                "score": old.get("score")}, after={"deleted": True},
        tags=["نمرات", "حذف", "پنل_وب"],
    )
    return {"ok": True}
