# -*- coding: utf-8 -*-
"""🌀 موج v3 — پل «داده‌های من» برای مینی‌اپ تلگرام.

چرا این فایل؟
──────────────
سه بلوک از پروتوتایپ («ادامهٔ مطالعه»، «یادداشت‌ها»، «هدف هفتگی») قبلاً
ساخته نشدند چون داده‌شان فقط از راه **سشن وب** (`/api/web/...` با کوکی)
در دسترس بود و مینی‌اپ تلگرام با `X-Init-Data` احراز هویت می‌شود.
نتیجه: یا باید همان بلوک‌ها را با دادهٔ ساختگی می‌ساختیم (ممنوع) یا
دادهٔ واقعی را به مینی‌اپ می‌رساندیم. اینجا راه دوم را انتخاب کردیم.

چه چیزی ساخته می‌شود؟
  GET /api/me/continue-reading   → آخرین فایل‌های نیمه‌خوانده (reading_progress)
  GET /api/me/notes              → فایل‌هایی که روی آن‌ها خط/یادداشت کشیده شده
  GET /api/me/weekly-goal        → هدف هفتگی + پیشرفت واقعی از فعالیت ثبت‌شده
  PUT /api/me/weekly-goal        → تعیین هدف (روز یا دقیقه) توسط خودِ کاربر

قواعد ایمنی (هم‌راستا با بقیهٔ پروژه):
  • فقط **خواندن** از کالکشن‌های موجود؛ هیچ کالکشن/اندیس تازه‌ای جز یک
    فیلد کوچک روی `users` (هدف هفتگی) اضافه نمی‌شود.
  • هر پاسخ با `uid` همین کاربر فیلتر می‌شود؛ هیچ ورودی‌ای از کلاینت
    به‌عنوان uid پذیرفته نمی‌شود.
  • اگر کالکشنی نبود یا دیتابیس در دسترس نبود، پاسخ خالی (`items: []`)
    برمی‌گردد نه 500 — داشبورد باید در هر حال باز شود.
  • هیچ محتوای فایلی از تلگرام به مرورگر لو نمی‌رود؛ فقط نام/نوع/درصد.

نصب: `app.include_router(me_bridge.router, prefix="/api/me", tags=["me"])`
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_current_user
from database import db
from time_utils import now_utc

logger = logging.getLogger(__name__)

router = APIRouter()

#: دامنه‌های مجاز فایل — همان دو دامنه‌ای که ریدر وب می‌شناسد
SCOPES = ("res", "ref")

#: بازهٔ هدف‌گیری: سقف منطقی برای جلوگیری از مقدار بی‌معنا
MIN_GOAL = 1
MAX_GOAL = 60


def _coll(name: str):
    """دسترسی به کالکشن بدون دست‌زدن به لایهٔ db/core (فقط خواندن)."""
    return db.users.database[name]


def _uid(user: dict) -> int:
    try:
        return int(user.get("id") or user.get("uid") or 0)
    except (TypeError, ValueError):
        return 0


def _tehran_today() -> "datetime.date":
    return (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).date()


@router.get("/continue-reading")
async def continue_reading(user: dict = Depends(get_current_user)):
    """آخرین فایل‌های نیمه‌خواندهٔ همین کاربر.

    شکل هر آیتم عیناً همان قرارداد `/api/web/library/continue` است تا
    مینی‌اپ و پنل وب یک زبان داشته باشند:
        {scope, id, name, kind, page, total, percent, updated_at}
    """
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")

    items: list[dict] = []
    try:
        docs = [
            d
            async for d in _coll("reading_progress")
            .find({"uid": uid})
            .sort("updated_at", -1)
            .limit(6)
        ]
    except Exception as exc:  # pragma: no cover - وابسته به دیتابیس
        logger.info("me_continue_failed uid=%s err=%s", uid, type(exc).__name__)
        return {"items": []}

    for doc in docs:
        total = int(doc.get("total") or 0)
        page = int(doc.get("page") or 0)
        percent = max(0, min(100, int(round(100 * page / total)))) if total > 0 else 0

        items.append(
            {
                "scope": str(doc.get("scope") or "res"),
                "id": str(doc.get("file_id") or ""),
                "name": str(doc.get("name") or doc.get("file_name") or "").strip() or "فایل درسی",
                "kind": str(doc.get("kind") or "other"),
                "page": page,
                "total": total,
                "percent": percent,
                "updated_at": str(doc.get("updated_at") or ""),
            }
        )

    return {"items": items}


@router.get("/notes")
async def notes(user: dict = Depends(get_current_user)):
    """فایل‌هایی که کاربر روی آن‌ها خط/یادداشت کشیده است (کالکشن web_ink_pages)."""
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")

    grouped: dict[tuple[str, str], dict] = {}
    try:
        async for doc in _coll("web_ink_pages").find({"uid": uid}).sort("updated_at", -1).limit(200):
            scope = str(doc.get("scope") or "")
            fid = str(doc.get("file_id") or "")
            if scope not in SCOPES or not fid:
                continue

            key = (scope, fid)
            row = grouped.setdefault(
                key,
                {
                    "scope": scope,
                    "id": fid,
                    "name": str(doc.get("file_name") or "").strip(),
                    "pages": 0,
                    "strokes": 0,
                    "last_page": 1,
                    "updated_at": "",
                },
            )
            row["pages"] += 1
            row["strokes"] += int(doc.get("count") or 0)

            stamp = str(doc.get("updated_at") or "")
            if stamp >= row["updated_at"]:
                row["updated_at"] = stamp
                row["last_page"] = int(doc.get("page") or 1)
    except Exception as exc:  # pragma: no cover
        logger.info("me_notes_failed uid=%s err=%s", uid, type(exc).__name__)
        return {"items": []}

    items = [
        {**grouped[key], "name": grouped[key]["name"] or "فایل درسی"}
        for key in sorted(grouped, key=lambda k: grouped[k]["updated_at"], reverse=True)[:12]
    ]
    return {"items": items}


@router.get("/weekly-goal")
async def weekly_goal(user: dict = Depends(get_current_user)):
    """هدف هفتگی + پیشرفت واقعی این هفته.

    هدف از پروفایل کاربر خوانده می‌شود (`weekly_goal_days`، پیش‌فرض ۵ روز).
    پیشرفت از فعالیت ثبت‌شدهٔ ۷ روز گذشته (`weekly_activity`) — همان منبعی
    که نمودار داشبورد استفاده می‌کند؛ پس هیچ عدد ساختگی‌ای وجود ندارد.
    """
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")

    db_user = user.get("_db") if isinstance(user.get("_db"), dict) else {}
    try:
        goal = int(db_user.get("weekly_goal_days") or 5)
    except (TypeError, ValueError):
        goal = 5
    goal = max(MIN_GOAL, min(MAX_GOAL, goal))

    active_days = 0
    total_actions = 0
    try:
        data = await db.weekly_activity(uid)
        for row in data or []:
            count = int(row.get("count") or 0) if isinstance(row, dict) else int((row or [0, 0])[1] or 0)
            total_actions += count
            if count > 0:
                active_days += 1
    except Exception as exc:  # pragma: no cover
        logger.info("me_weekly_failed uid=%s err=%s", uid, type(exc).__name__)

    return {
        "goal_days": goal,
        "active_days": active_days,
        "total_actions": total_actions,
        "percent": max(0, min(100, int(round(100 * active_days / goal)))) if goal else 0,
        "today": str(_tehran_today()),
    }


class GoalBody(BaseModel):
    """فقط یک عدد کوچک — هیچ چیز دیگری از کلاینت نوشته نمی‌شود."""
    goal_days: int = Field(..., ge=MIN_GOAL, le=MAX_GOAL)


@router.put("/weekly-goal")
async def set_weekly_goal(body: GoalBody, user: dict = Depends(get_current_user)):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        await db.users.update_one(
            {"uid": uid},
            {"$set": {"weekly_goal_days": int(body.goal_days), "weekly_goal_set_at": now_utc()}},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("me_weekly_goal_save_failed uid=%s err=%s", uid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="goal_unavailable")

    return {"ok": True, "goal_days": int(body.goal_days)}
