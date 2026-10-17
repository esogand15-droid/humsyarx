"""Class and exam schedule endpoints."""

from typing import Any, Literal, Mapping

from fastapi import APIRouter, Depends, Query, Response

from api.auth import get_current_user, require_perm
from database import db
from time_utils import parse_gregorian_date
from utils import now_tehran


router = APIRouter()

ScheduleType = Literal[
    "class",
    "exam",
    "makeup",
]


def _text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _format_schedule(
    item: Mapping[str, Any] | None,
) -> dict | None:
    if not isinstance(item, Mapping):
        return None

    schedule_type = _text(
        item.get("type")
    )

    raw_date = _text(
        item.get("date")
    )

    document = {
        "id": _text(
            item.get("_id")
        ),

        "type": schedule_type,

        "lesson": _text(
            item.get("lesson")
        ),

        "teacher": _text(
            item.get("teacher")
        ),

        "date": raw_date,

        "time": _text(
            item.get("time")
        ),

        "location": _text(
            item.get("location")
        ),

        # رکوردهای جدید از notes و بعضی
        # رکوردهای قدیمی از note استفاده می‌کنند.
        "note": _text(
            item.get("notes")
            or item.get("note")
        ),

        "group": _text(
            item.get("group")
        ),

        "flex_type": (
            _text(
                item.get("flex_type")
            )
            or "fixed"
        ),

        "flex_note": _text(
            item.get("flex_note")
        ),

        "days_left": None,
    }

    if (
        schedule_type == "exam"
        and raw_date
    ):
        try:
            exam_date = parse_gregorian_date(raw_date)

            document["days_left"] = max(
                0,
                (
                    exam_date
                    - now_tehran().date()
                ).days,
            )

        except (
            TypeError,
            ValueError,
        ):
            document["days_left"] = None

    return document


def _serialize(
    items: Any,
) -> list[dict]:
    result = []

    if not isinstance(items, list):
        return result

    for item in items:
        formatted = _format_schedule(
            item
        )

        if formatted is not None:
            result.append(formatted)

    return result


@router.get("")
async def get_schedule(
    user=Depends(get_current_user),

    stype: ScheduleType | None = Query(
        default=None
    ),
):
    personalized = await db.get_personalized_schedules(
        user["id"],
        stype=stype,
        upcoming=True,
    )
    items = personalized.get("items") or []
    eff_group = personalized.get("computed_group") or _text(user["_db"].get("group")) or "1"

    return {
        "schedule": _serialize(items),
        "group": eff_group,
        "computed_group": eff_group,
        "registered_group": personalized.get("registered_group") or eff_group,
        "has_custom_selection": bool(personalized.get("has_custom_selection")),
        "selected_count": int(personalized.get("selected_count") or 0),
        "total_offered_count": int(personalized.get("total_offered_count") or 0),
        "unselected_lessons": personalized.get("unselected_lessons") or [],
        "majority": personalized.get("majority") or {},
        "conflicts": personalized.get("conflicts") or [],
        "term": personalized.get("term") or "",
    }


@router.get("/course-selections")
async def get_course_selections_ep(
    user=Depends(get_current_user),
    term: str | None = Query(default=None),
):
    """🎓 دریافت لیست درس‌های ارائه‌شده ترم جاری + انتخاب‌های درس‌به‌درس دانشجو و گروه اکثریت."""
    return await db.get_student_course_selections(user["id"], term=term)


@router.post("/course-selections")
async def save_course_selections_ep(
    body: dict,
    user=Depends(get_current_user),
):
    """🎓 ذخیره انتخاب‌های درس‌به‌درس دانشجو + محاسبه خودکار گروه اکثریت و به‌روزرسانی پروفایل."""
    selections = body.get("selections") if isinstance(body, dict) else []
    term = body.get("term") if isinstance(body, dict) else None
    if not isinstance(selections, list):
        from fastapi import HTTPException
        raise HTTPException(422, "فرمت انتخاب واحد معتبر نیست")
    res = await db.save_student_course_selections(user["id"], selections, term=term)
    try:
        db_user = user.get("_db") or {}
        name = db_user.get("name") or str(user["id"])
        await db.log_action(
            user["id"], name, "student",
            "ثبت انتخاب واحد درس‌به‌درس", "Schedule", category="academic", severity="INFO",
            target_id=str(user["id"]), target_type="user", target_label=name,
            after={
                "term": res.get("term"),
                "selected_count": res.get("selected_count"),
                "computed_group": res.get("computed_group"),
                "tie_broken_by": (res.get("majority") or {}).get("tie_broken_by"),
            },
        )
    except Exception:
        pass
    return res



@router.get("/exams")
async def get_exams(
    user=Depends(get_current_user),

    days: int = Query(
        default=30,
        ge=1,
        le=365,
    ),
):
    group = _text(
        user["_db"].get("group")
    )

    exams = await db.upcoming_exams(
        days,
        group=group,
    )

    return {
        "exams": _serialize(exams),
    }


def _ical_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ical(items: list, cal_name: str = "HumsYar") -> str:
    """🌊 W8/UX-05 — ساخت تقویم iCal (UTC، بدون وابستگی خارجی)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tehran = ZoneInfo("Asia/Tehran")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//HumsYar//Schedule//FA",
        f"X-WR-CALNAME:{_ical_escape(cal_name)}",
    ]
    for it in items or []:
        try:
            day = parse_gregorian_date(str(it.get("date") or ""))
        except (TypeError, ValueError):
            continue
        hm = str(it.get("time") or "").strip()
        try:
            hh, mm = hm.split(":")
            start = datetime(day.year, day.month, day.day,
                             int(hh), int(mm), tzinfo=tehran)
        except (ValueError, AttributeError):
            continue  # بدون ساعت عینی، رویداد تقویمی نمی‌سازیم
        ehm = str(it.get("end_time") or "").strip()
        try:
            eh, em = ehm.split(":")
            end = datetime(day.year, day.month, day.day,
                           int(eh), int(em), tzinfo=tehran)
            if end <= start:
                raise ValueError
        except (ValueError, AttributeError):
            from datetime import timedelta
            end = start + timedelta(minutes=90)
        kind = {"class": "کلاس", "exam": "آزمون", "makeup": "جبرانی"}.get(
            str(it.get("type") or ""), "")
        summary = f"{kind} {it.get('lesson') or ''}".strip()
        desc = " / ".join(x for x in (
            str(it.get("teacher") or ""),
            str(it.get("notes") or it.get("note") or "")) if x)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{it.get('_id', '')}@humsyar",
            f"DTSTART:{start.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{_ical_escape(summary)}",
            f"LOCATION:{_ical_escape(it.get('location') or '')}",
            f"DESCRIPTION:{_ical_escape(desc)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@router.get("/ical")
async def get_ical(
    user=Depends(get_current_user),
    days: int = Query(default=90, ge=1, le=365),
    stype: ScheduleType | None = Query(default=None),
):
    """🌊 W8/UX-05 — خروجی iCal برنامه‌ی شخصی‌سازی‌شده کاربر (۹۰ روز آینده)."""
    from datetime import timedelta
    personalized = await db.get_personalized_schedules(user["id"], stype=stype, upcoming=True)
    items = personalized.get("items") or []
    cutoff = (now_tehran().date() + timedelta(days=days)).isoformat()
    items = [it for it in (items or [])
             if str(it.get("date") or "") <= cutoff]
    body = build_ical(items)
    return Response(
        content=body.encode("utf-8"), media_type="text/calendar",
        headers={"Content-Disposition":
                 "attachment; filename=humsyar-schedule.ics"})


@router.get("/conflicts")
async def get_conflicts(
    user=Depends(require_perm("schedules.manage")),
    group: str = Query(default="هر دو"),
    date: str = Query(default=""),
):
    """🌊 W8/UX-05 — همه‌ی جفت‌های متداخل یک روز (بازبینی ادمین)."""
    if not date:
        date = now_tehran().strftime("%Y-%m-%d")
    try:
        parse_gregorian_date(date)
    except (TypeError, ValueError):
        from fastapi import HTTPException
        raise HTTPException(422, "فرمت تاریخ YYYY-MM-DD")
    from database import db as _db

    cur = await _db.schedules.find(
        {"date": date, "is_weekly": {"$ne": True}}).to_list(200)
    pairs = []
    seen = set()
    for s in cur or []:
        g = (s.get("group") or "هر دو").strip()
        if group != "هر دو" and g != "هر دو" and g != group:
            continue
        for c in await _db.schedule_find_conflicts(
                g, date, s.get("time") or "", s.get("end_time") or "",
                exclude_id=str(s.get("_id"))):
            key = tuple(sorted((str(s.get("_id")), c["id"])))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"a": {"id": str(s.get("_id")),
                                "lesson": s.get("lesson", ""),
                                "time": s.get("time", ""),
                                "group": g}, "b": c})
    return {"date": date, "group": group, "conflicts": pairs}
