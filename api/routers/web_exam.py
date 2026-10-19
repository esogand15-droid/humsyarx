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

import functools
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import get_question_access_user
from api.routers import questions as q_router
from api.routers.web_library import _web_user
from api.routers.web_student import current_student
from question_bank import QuestionDomainError

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
    detail: dict = {"code": code, "message": message}
    # ⚠️ `details` حمل می‌شود، نه دور ریخته: مثلاً `active_exam_exists`
    # خودِ آزمون فعال را در `details["exam"]` می‌فرستد و کلاینت بدون آن
    # نمی‌تواند «ادامه بده» را پیشنهاد کند. (پیش‌تر همین‌جا گم می‌شد.)
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        detail.update(details)
    return HTTPException(status_code=status, detail=detail)


def _domain_errors(fn):
    """خطای دامنه در هر اندپوینت آزمون **یک‌جا** به HTTP تبدیل می‌شود.

    چرا دکوراتور: پیش از این هر هندلر `try/except` تکراری داشت و دو
    هندلر (`mock_session`، `mock_review`) جا افتاده بودند → ۵۰۰ به‌جای ۴۰۴.
    یک نقطهٔ تبدیل، یک رفتار.
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except HTTPException:
            raise
        except QuestionDomainError as exc:
            raise _domain(exc)

    return wrapper


# ─────────────────────────────────────────────────────────────
#  📚 تاکسونومی
# ─────────────────────────────────────────────────────────────
@router.get("/exam/lessons")
@_domain_errors
async def lessons(user: dict = Depends(current_student)):
    """درس‌ها و شمار سؤال هر درس — همان داده‌ای که مینی‌اپ می‌بیند."""
    web = await _student(user)
    return await q_router.get_lessons(user=web)


@router.get("/exam/topics/{lesson}")
@_domain_errors
async def topics(lesson: str, user: dict = Depends(current_student)):
    web = await _student(user)
    return await q_router.get_topics(lesson=lesson, user=web)


# ─────────────────────────────────────────────────────────────
#  🎯 تمرین
# ─────────────────────────────────────────────────────────────
@router.get("/exam/next")
@_domain_errors
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
@_domain_errors
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
@_domain_errors
async def stats(user: dict = Depends(current_student)):
    """آمار واقعی از `question_progress` — هیچ عددی در کلاینت ساخته نمی‌شود."""
    web = await _student(user)
    return await q_router.practice_stats(user=web)


@router.get("/exam/history")
@_domain_errors
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


# ═════════════════════════════════════════════════════════════════
#  P5.2 — آزمون زمان‌دار
# ═════════════════════════════════════════════════════════════════
#
#  همان `ExamService` موجود (`question_bank/exam.py`) که مینی‌اپ استفاده
#  می‌کند: نمونه‌برداری، مهلت، انقضا، ثبت پاسخ و کارنامه همه همان‌جاست.
#  این‌جا فقط: ورود وب، همان گیت، و یک اندپوینت **خواندنی** برای بازبینی.
#
#  قاعدهٔ امنیتی که حفظ می‌شود: در جریان آزمون هیچ پاسخ صحیحی به کلاینت
#  نمی‌رود. `ExamService.answer` فقط `{accepted, progress, ...}` می‌دهد و
#  پاسخ صحیح هر سؤال تازه در کارنامهٔ **بعد از پایان** دیده می‌شود.


class MockExamStart(BaseModel):
    lesson: str = ""
    topic: str | None = None
    lesson_id: str | None = None
    topic_id: str | None = None
    count: int = Field(ge=5, le=100)
    minutes: int = Field(ge=0, le=180)
    allow_smaller: bool = False


async def _mock_gate(user: dict) -> dict:
    """گیت آزمون: `question_bank` + `mock_exam` — همان دو شرطی که مینی‌اپ دارد.

    بدون این، کسی که پلنش `mock_exam` ندارد می‌توانست از مسیر وب آزمون
    بسازد؛ یعنی یک راه دور زدن پلن. عمداً همان `require_feature` صدا زده
    می‌شود، نه یک بررسی دستی.
    """
    web = await _student(user)
    try:
        from api.auth import require_feature  # همان کارخانهٔ گیت موجود

        await require_feature("mock_exam")(user=web)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        logger.warning("web_exam_mock_gate_failed err=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="policy_unavailable")
    return web


@router.post("/exam/mock/preview")
@_domain_errors
async def mock_preview(body: MockExamStart, user: dict = Depends(current_student)):
    """چند سؤال در این محدوده هست؟ پیش از شروع، تا کاربر ۲۰ سؤال نخواهد
    وقتی بانک ۷ سؤال دارد."""
    web = await _mock_gate(user)
    taxonomy = await q_router._request_taxonomy(
        web, body.lesson_id, body.topic_id, body.lesson or None, body.topic
    )
    return await q_router.exam_domain.preview(
        user=web, taxonomy=taxonomy, requested_count=body.count,
        minutes=body.minutes, output_mode="app",
    )


@router.post("/exam/mock/start")
@_domain_errors
async def mock_start(body: MockExamStart, user: dict = Depends(current_student)):
    """شروع آزمون. اگر آزمون فعالی داشته باشد، ۴۰۹ `active_exam_exists`
    با خودِ آزمون در `detail.exam` برمی‌گردد (قرارداد `ExamService`)."""
    web = await _mock_gate(user)
    taxonomy = await q_router._request_taxonomy(
        web, body.lesson_id, body.topic_id, body.lesson or None, body.topic
    )
    return await q_router.exam_domain.create(
        user=web, taxonomy=taxonomy, requested_count=body.count,
        minutes=body.minutes, output_mode="app", allow_smaller=body.allow_smaller,
    )


@router.get("/exam/mock/active")
async def mock_active(user: dict = Depends(current_student)):
    """آزمون فعال، اگر هست. کلاینت با این تصمیم می‌گیرد «ادامه» بدهد."""
    web = await _mock_gate(user)
    return {"exam": await q_router.exam_domain.active(user=web)}


# ⚠️ ترتیب مسیر مهم است: این مسیر ثابت باید **پیش از** `/exam/mock/{session_id}`
# تعریف شود، وگرنه FastAPI آن را به‌عنوان شناسهٔ آزمون می‌گیرد.
@router.get("/exam/mock/history")
async def mock_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_student),
):
    web = await _mock_gate(user)
    return await q_router.exam_domain.history(user=web, skip=skip, limit=limit)


@router.get("/exam/mock/{session_id}")
@_domain_errors
async def mock_session(session_id: str, user: dict = Depends(current_student)):
    """خلاصهٔ یک آزمون (وضعیت، مهلت، شمار پاسخ) — برای بازیابی صفحه پس از رفرش."""
    web = await _mock_gate(user)
    session = await q_router.exam_domain.load(session_id, int(web["id"]))
    return q_router.exam_domain.summary(session)


@router.get("/exam/mock/{session_id}/next")
@_domain_errors
async def mock_next(session_id: str, user: dict = Depends(current_student)):
    """سؤال جاری. اگر مهلت تمام شده یا همه پاسخ داده شده باشند:
    `{finished: true, ...summary}` — حالت عادی، نه خطا."""
    web = await _mock_gate(user)
    return await q_router.exam_domain.next_question(session_id=session_id, user=web)


class MockAnswer(BaseModel):
    selected: int = Field(ge=0, le=3)


@router.post("/exam/mock/{session_id}/answer")
@_domain_errors
async def mock_answer(session_id: str, body: MockAnswer, user: dict = Depends(current_student)):
    """ثبت پاسخ. پاسخ صحیح **برنمی‌گردد** — همان قرارداد آزمون."""
    web = await _mock_gate(user)
    return await q_router.exam_domain.answer(
        session_id=session_id, user=web, selected=body.selected
    )


@router.post("/exam/mock/{session_id}/abandon")
@_domain_errors
async def mock_abandon(session_id: str, user: dict = Depends(current_student)):
    web = await _mock_gate(user)
    return await q_router.exam_domain.abandon(session_id=session_id, user=web)


@router.get("/exam/mock/{session_id}/review")
@_domain_errors
async def mock_review(session_id: str, user: dict = Depends(current_student)):
    """بازبینی آزمون **بعد از پایان**.

    چرا این اندپوینت تازه است: `ExamService` کارنامهٔ خلاصه می‌دهد ولی
    بازبینی سؤال‌به‌سؤال (چه زدم، چه بود) را نه — و در مینی‌اپ هم فقط
    خلاصه دیده می‌شود. این‌جا همان دادهٔ موجودِ سند آزمون (`answers`) با
    صورت سؤال‌ها ترکیب می‌شود؛ **هیچ نوشتنی** ندارد.

    قفل امنیتی: اگر وضعیت آزمون `active` باشد، ۴۰۹ می‌دهد. یعنی پاسخ‌های
    صحیح فقط برای آزمونی برمی‌گردد که تمام شده (یا منقضی/رها شده).
    """
    web = await _mock_gate(user)
    session = await q_router.exam_domain.load(session_id, int(web["id"]))
    summary = q_router.exam_domain.summary(session)
    if summary["status"] == "active":
        raise HTTPException(
            status_code=409,
            detail={"code": "exam_still_active", "message": "این آزمون هنوز تمام نشده است"},
        )

    answers = list(session.get("answers") or [])
    review = []
    try:
        from question_bank.contracts import public_question

        for a in answers:
            qid = str(a.get("question_id") or "")
            item = {
                "question_id": qid,
                "selected": int(a.get("selected") or 0),
                # پاسخ صحیح از **سند آزمون** خوانده می‌شود، نه از سؤال فعلی:
                # اگر سؤال بعداً ویرایش شود، کارنامهٔ تاریخی عوض نمی‌شود.
                "correct_answer": int(a.get("correct_answer") or 0),
                "is_correct": bool(a.get("is_correct")),
                "answered_at": str(a.get("answered_at") or ""),
            }
            doc = await q_router.db.get_question_by_id(qid) if qid else None
            if doc:
                pub = public_question(doc, reveal=True)  # مجاز: آزمون تمام شده است
                item["question"] = pub.get("question", "")
                item["options"] = pub.get("options", [])
                item["topic"] = pub.get("topic", "")
                item["explanation"] = pub.get("explanation", "")
                item["image_url"] = (
                    f"/api/web/exam/image/{qid}" if pub.get("image_url") else None
                )
            review.append(item)
    except Exception as exc:  # pragma: no cover
        logger.warning("web_exam_review_failed sid=%s err=%s", session_id, type(exc).__name__)
        raise HTTPException(status_code=503, detail="review_unavailable")

    return {**summary, "review": review, "total_questions": len(session.get("question_ids") or [])}
