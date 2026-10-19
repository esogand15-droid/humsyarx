# -*- coding: utf-8 -*-
"""❓ موج P5 — تمرین بانک سؤال در وب.

اصل، مثل موج‌های قبل: **هیچ منطق سؤالی دوباره ساخته نمی‌شود.** همهٔ
قواعد (نمونه‌برداری از سؤال حل‌نشده، محدودهٔ ورودی، پاسخ‌نامه،
ثبت پیشرفت، آمار) در `question_bank` و روتر `api/routers/questions.py`
هست که ربات و مینی‌اپ هم از همان استفاده می‌کنند. این فایل فقط:

  ۱) همان هندلرها را با کاربرِ وب صدا می‌زند (نه با initData تلگرام).
  ۲) گیت اشتراک را با همان `get_question_access_user` اجرا می‌کند.
  ۳) تصویر سؤال را برای مرورگر پروکسی می‌کند (توکن تلگرام لو نمی‌رود).

اندپوینت‌های تازه (همه زیر /api/web):
    GET  /exam/lessons                 فهرست درس‌ها با شمار سؤال
    GET  /exam/topics/{lesson}         مبحث‌های یک درس
    GET  /exam/next?lesson&topic       سؤال بعدی حل‌نشده + پیشرفت
    POST /exam/answer                  پاسخ → درست/غلط + توضیح
    GET  /exam/stats                   آمار تمرین کاربر
    GET  /exam/history?limit           تاریخچهٔ پاسخ‌ها
    GET  /exam/image/{qid}             تصویر سؤال (پروکسی سرور به سرور)

نصب: در api/main.py
    from api.routers import web_exam
    app.include_router(web_exam.router, prefix="/api/web", tags=["web-exam"])
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import get_question_access_user
from api.routers import questions as q_router
from api.routers.web_library import _web_user
from api.routers.web_student import current_student

logger = logging.getLogger(__name__)

router = APIRouter()


async def _student(user: dict) -> dict:
    """کاربر وب → شکل مورد انتظار بانک سؤال، با همان گیت اشتراک.

    `get_question_access_user` یک وابستگی FastAPI است، ولی تابع خالص هم
    هست؛ مستقیم صدا زدنش یعنی **همان** قانون دسترسی اجرا می‌شود، نه یک
    نسخهٔ موازی که دیر یا زود عقب می‌ماند.
    """
    web = _web_user(user)
    try:
        return await get_question_access_user(user=web)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - پالیسی موقتاً در دسترس نیست
        logger.warning("web_exam_gate_failed err=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="policy_unavailable")


def _domain(exc: Exception) -> HTTPException:
    """خطای دامنهٔ بانک سؤال → پاسخ HTTP با کد ماشین‌خوان."""
    status = int(getattr(exc, "status_code", 0) or 400)
    code = str(getattr(exc, "code", "") or "question_error")
    message = str(getattr(exc, "message", "") or getattr(exc, "detail", "") or "")
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# ─────────────────────────────────────────────────────────────
#  📚 تاکسونومی
# ─────────────────────────────────────────────────────────────
@router.get("/exam/lessons")
async def lessons(user: dict = Depends(current_student)):
    """درس‌ها و شمار سؤال هر درس — همان داده‌ای که مینی‌اپ می‌بیند."""
    web = await _student(user)
    try:
        return await q_router.get_lessons(user=web)
    except HTTPException:
        raise
    except Exception as exc:
        from question_bank import QuestionDomainError  # نوع مشترک

        if isinstance(exc, QuestionDomainError):
            raise _domain(exc)
        raise


@router.get("/exam/topics/{lesson}")
async def topics(lesson: str, user: dict = Depends(current_student)):
    web = await _student(user)
    return await q_router.get_topics(lesson=lesson, user=web)


# ─────────────────────────────────────────────────────────────
#  🎯 تمرین
# ─────────────────────────────────────────────────────────────
@router.get("/exam/next")
async def next_question(
    lesson: str | None = Query(None, max_length=100),
    topic: str | None = Query(None, max_length=100),
    lesson_id: str | None = Query(None),
    topic_id: str | None = Query(None),
    user: dict = Depends(current_student),
):
    """سؤال بعدی **حل‌نشده** در همان محدوده.

    اگر چیزی نماند، `question: null` با `progress.exhausted: true` می‌آید —
    حالت عادی است، نه خطا. کلاینت خودش پیام «این بخش را تمام کردی» را
    نشان می‌دهد؛ هیچ سؤال تکراری هم پشت سر هم نمی‌آید چون سرور فقط
    حل‌نشده‌ها را برمی‌گرداند.
    """
    web = await _student(user)
    return await q_router.practice(
        user=web,
        lesson_id=lesson_id,
        topic_id=topic_id,
        lesson=lesson,
        topic=topic,
        exclude=None,
        exam_year_from=None,
        exam_year_to=None,
        content_source=None,
    )


class AnswerBody(BaseModel):
    question_id: str = Field(min_length=24, max_length=24)
    selected: int = Field(ge=0, le=3)


@router.post("/exam/answer")
async def answer(body: AnswerBody, user: dict = Depends(current_student)):
    """پاسخ به سؤال → درست/غلط + پاسخ صحیح + توضیح.

    `correct_answer` و `explanation` فقط **بعد از** پاسخ برمی‌گردند؛ همان
    قراردادی که مینی‌اپ دارد. یعنی قبل از پاسخ، پاسخ صحیح در مرورگر نیست.
    """
    web = await _student(user)
    payload = q_router.AnswerInput(question_id=body.question_id, selected=body.selected)
    out = await q_router.answer(body=payload, user=web)
    # تصویر سؤال در پاسخ هم لازم است (بالای توضیح) — همان مسیر وب می‌شود
    q = out.get("question") if isinstance(out, dict) else None
    if isinstance(q, dict) and q.get("image_url"):
        q["image_url"] = f"/api/web/exam/image/{q.get('id')}"
    return out


# ─────────────────────────────────────────────────────────────
#  📊 آمار و تاریخچه
# ─────────────────────────────────────────────────────────────
@router.get("/exam/stats")
async def stats(user: dict = Depends(current_student)):
    """آمار واقعی از `question_progress` — هیچ عددی در کلاینت ساخته نمی‌شود."""
    web = await _student(user)
    return await q_router.practice_stats(user=web)


@router.get("/exam/history")
async def history(
    limit: int = Query(20, ge=1, le=100),
    after: str | None = Query(None, max_length=32),
    user: dict = Depends(current_student),
):
    web = await _student(user)
    return await q_router.answer_history(user=web, skip=0, limit=limit, after=after)


# ─────────────────────────────────────────────────────────────
#  🖼 تصویر سؤال
# ─────────────────────────────────────────────────────────────
@router.get("/exam/image/{qid}")
async def image(qid: str, user: dict = Depends(current_student)):
    """پروکسی تصویر سؤال.

    چرا پروکسی و نه آدرس تلگرام: `file_id` تلگرام با توکن ربات کار می‌کند.
    مرورگر فقط بایت تصویر را از دامنهٔ خودمان می‌گیرد؛ توکن هیچ‌وقت به
    کلاینت نمی‌رسد و دسترسی هم داخل همان هندلر بررسی می‌شود.
    """
    web = await _student(user)
    return await q_router.question_image(qid=qid, user=web)
