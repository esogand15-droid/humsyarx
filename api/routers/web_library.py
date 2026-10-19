# -*- coding: utf-8 -*-
"""📚 موج P2 — کتابخانهٔ وب دانشجو.

اصل طراحی این فایل: **هیچ منطق محتوایی تازه‌ای ساخته نمی‌شود.**
همهٔ پاسخ‌ها از همان هندلرهای موجود مینی‌اپ
(`api/routers/resources.py` و `api/routers/references.py`) گرفته
می‌شوند، فقط با یک لایهٔ احراز هویت وب روی آن‌ها:

    session وب (api/routers/web_student.py)
        → get_resource_access_user  (گیت اشتراک، همان قانون ربات)
        → resources.terms / lessons / sessions / files
        → references.subjects / books / files

چرا این‌طور؟
  ۱) قواعد «دامنهٔ دید» (intake) و «جلسهٔ جایگزین‌شده» (fork) فقط
     یک‌جا در `db/*` و همان هندلرها زندگی می‌کنند؛ کپی‌کردنشان یعنی
     دو منبع حقیقت که دیر یا زود از هم جدا می‌شوند.
  ۲) هر فیلدی که به کلاینت می‌رسد، همان فیلدی است که مینی‌اپ می‌گیرد؛
     هیچ فیلد جدیدی اختراع نمی‌شود.
  ۳) اگر فردا قانون دسترسی عوض شود، وب و مینی‌اپ **با هم** عوض می‌شوند.

این موج فقط «خواندن» است: فهرست ترم/درس/جلسه/فایل و مرجع‌ها.
دریافت فایل (رلهٔ سرور) کار P3 است؛ عمداً دکمهٔ دانلودِ بی‌عمل
ساخته نمی‌شود.

نصب: دو خط در api/main.py

    from api.routers import web_library
    app.include_router(web_library.router, prefix="/api/web", tags=["web-library"])
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth import get_references_access_user, get_resource_access_user
from api.routers import references as ref_router
from api.routers import resources as res_router
from api.routers.web_student import current_student

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────
#  🧰 کمکی‌ها
# ─────────────────────────────────────────────────────────────
def _web_user(user: dict) -> dict:
    """سند کاربر دیتابیس → شکل مورد انتظار هندلرهای موجود.

    `api/auth.get_current_user` همان جا هم `{"id": ..., "_db": doc}`
    می‌سازد؛ این‌جا همان قرارداد بازسازی می‌شود تا هندلرها بدون تغییر
    کار کنند (به‌خصوص `_viewer_intake` که به `_db.intake` نیاز دارد).
    """
    uid = int(user.get("user_id") or user.get("id") or 0)
    return {**user, "id": uid, "_db": user}


async def _gate(kind: str, user: dict) -> dict:
    """گیت اشتراک — همان تابعی که مینی‌اپ استفاده می‌کند.

    خطای ۴۰۲/۴۰۳ عیناً به کلاینت می‌رسد تا UI با کد ماشین‌خوان
    (`SUB_REQUIRED` / `feature_disabled` / `policy_unavailable`) تصمیم
    بگیرد، نه با تطبیق متن فارسی.
    """
    gate = get_references_access_user if kind == "references" else get_resource_access_user
    return await gate(user=user)


async def _safe_gate(kind: str, user: dict) -> dict:
    """مثل `_gate` ولی خطا را به «اجازه ندارم» تبدیل می‌کند (برای /state)."""
    try:
        await _gate(kind, user)
        return {"allowed": True, "code": None, "message": ""}
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return {
            "allowed": False,
            "code": str(detail.get("code") or (exc.detail if isinstance(exc.detail, str) else "forbidden")),
            "message": str(detail.get("message") or ""),
            "status": exc.status_code,
        }
    except Exception as exc:  # pragma: no cover - پالیسی موقتاً در دسترس نیست
        logger.warning("web_library_gate_failed kind=%s err=%s", kind, type(exc).__name__)
        return {"allowed": False, "code": "policy_unavailable", "message": "", "status": 503}


def _guard_intake_error(exc: HTTPException) -> HTTPException:
    """۴۰۳ «برای ورودی شما نیست» را به کد ماشین‌خوان تبدیل می‌کند.

    هندلرهای موجود متن فارسی برمی‌گردانند؛ کلاینت وب نباید روی متن
    تکیه کند، پس این‌جا کد اضافه می‌شود و پیام اصلی حفظ می‌شود.
    """
    if exc.status_code == 403:
        message = exc.detail if isinstance(exc.detail, str) else "forbidden"
        return HTTPException(status_code=403, detail={"code": "not_in_scope", "message": message})
    return exc


# ─────────────────────────────────────────────────────────────
#  🔌 اندپوینت‌ها — همه read-only
# ─────────────────────────────────────────────────────────────
@router.get("/library/state")
async def library_state(request: Request, user: dict = Depends(current_student)):
    """وضعیت دو بخش کتابخانه برای همین کاربر.

    یک درخواست، دو بخش: «منابع» و «مرجع» گیت‌های مستقل دارند
    (`resources` و `references`)، پس UI می‌تواند تب‌ها را درست
    فعال/غیرفعال کند بدون اینکه دو بار خطا بخورد.
    """
    web = _web_user(user)
    resources = await _safe_gate("resources", web)
    references = await _safe_gate("references", web)
    return {
        "resources": resources,
        "references": references,
        "intake": str(user.get("intake") or ""),
        "group": str(user.get("group") or ""),
    }


@router.get("/library/terms")
async def library_terms(request: Request, user: dict = Depends(current_student)):
    web = _web_user(user)
    await _gate("resources", web)
    try:
        return await res_router.terms(user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)


@router.get("/library/lessons/{term}")
async def library_lessons(term: str, request: Request, user: dict = Depends(current_student)):
    web = _web_user(user)
    await _gate("resources", web)
    try:
        return await res_router.lessons(term=term, user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)


@router.get("/library/sessions/{lesson_id}")
async def library_sessions(lesson_id: str, request: Request, user: dict = Depends(current_student)):
    web = _web_user(user)
    await _gate("resources", web)
    try:
        return await res_router.sessions(lesson_id=lesson_id, user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)


@router.get("/library/files/{session_id}")
async def library_files(session_id: str, request: Request, user: dict = Depends(current_student)):
    web = _web_user(user)
    await _gate("resources", web)
    try:
        return await res_router.files(session_id=session_id, user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)


@router.get("/library/search")
async def library_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    user: dict = Depends(current_student),
):
    web = _web_user(user)
    await _gate("resources", web)
    try:
        return await res_router.search(q=q, user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)


@router.get("/library/subjects")
async def library_subjects(request: Request, user: dict = Depends(current_student)):
    web = _web_user(user)
    await _gate("references", web)
    try:
        return await ref_router.subjects(user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)


@router.get("/library/books/{subject_id}")
async def library_books(subject_id: str, request: Request, user: dict = Depends(current_student)):
    web = _web_user(user)
    await _gate("references", web)
    try:
        return await ref_router.books(subject_id=subject_id, user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)


@router.get("/library/book-files/{book_id}")
async def library_book_files(book_id: str, request: Request, user: dict = Depends(current_student)):
    web = _web_user(user)
    await _gate("references", web)
    try:
        return await ref_router.files(book_id=book_id, user=web)
    except HTTPException as exc:
        raise _guard_intake_error(exc)
