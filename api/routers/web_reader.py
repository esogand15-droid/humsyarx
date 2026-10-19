# -*- coding: utf-8 -*-
"""📖 موج P3 — ریدر: خواندن و پخش داخل مرورگر، به‌علاوهٔ پیشرفت مطالعه.

اصل: **هیچ رلهٔ تازه‌ای ساخته نمی‌شود.** سیستم از قبل یک پراکسی
سمت‌سرور با پشتیبانی Range دارد (`api/telegram_send.proxy_telegram_preview`)
که مینی‌اپ هم از آن استفاده می‌کند:

    GET /api/resources/preview-url/{id}   → آدرس امضاشدهٔ ۱۰ دقیقه‌ای
    GET /api/resources/preview/{id}       → استریم بایت‌ها (Range)

پس این فایل فقط دو کار می‌کند:
  ۱) همان آدرس امضاشده را برای کاربر وب صادر می‌کند (با احراز هویت وب).
  ۲) پیشرفت مطالعه (`reading_progress`) را نگه می‌دارد.

چرا این مهم است: توکن تلگرام هرگز به مرورگر نمی‌رسد، فایل از سرور خود
هامزیار عبور می‌کند (بدون نیاز به VPN) و هر درخواست بایت، دوباره گیت
`core/access.py` و دامنهٔ دید را رد می‌کند — چون بازبینی داخل خودِ
`preview` انجام می‌شود، نه یک‌بار در ابتدا.

کالکشن تازه: `reading_progress`
    {_id: "<uid>:<scope>:<file_id>", uid, scope, file_id,
     page, total, position, kind, updated_at}
یک __id یکتا یعنی آپسِرت idempotent است و دو تب هم‌زمان، رکورد تکراری نمی‌سازد.

نصب: در api/main.py
    from api.routers import web_reader
    app.include_router(web_reader.router, prefix="/api/web", tags=["web-reader"])
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.routers import references as ref_router
from api.routers import resources as res_router
from api.routers.web_library import _gate, _web_user
from api.routers.web_student import current_student
from database import db
from time_utils import now_utc

logger = logging.getLogger(__name__)

router = APIRouter()

SCOPES = ("res", "ref")


def _coll(name: str):
    return db.users.database[name]


def _key(uid: int, scope: str, file_id: str) -> str:
    return f"{int(uid)}:{scope}:{file_id}"


def _kind(mime: str, ext: str) -> str:
    """نوع محتوا برای انتخاب رندرر — همان دسته‌بندی مینی‌اپ، نه بیشتر."""
    m = (mime or "").lower()
    e = (ext or "").lower().lstrip(".")
    if m == "application/pdf" or e == "pdf":
        return "pdf"
    if m.startswith("video/") or e in {"mp4", "webm", "mkv", "mov", "m4v"}:
        return "video"
    if m.startswith("audio/") or e in {"mp3", "ogg", "oga", "wav", "m4a", "flac"}:
        return "audio"
    if m.startswith("image/") or e in {"jpg", "jpeg", "png", "gif", "webp"}:
        return "image"
    return "other"


async def _item(scope: str, file_id: str) -> dict | None:
    """سند فایل از همان جایی که مینی‌اپ می‌خواند."""
    if scope == "ref":
        return await db.ref_get_file(file_id)
    return await db.bs_get_content_item(file_id)


def _public(item: dict) -> dict:
    name = (str(item.get("display_file_name") or item.get("name") or "").strip()
            or str(item.get("description") or "").strip() or "فایل آموزشی")
    return {
        "id": str(item.get("_id") or ""),
        "name": name,
        "mime": str(item.get("mime_type") or ""),
        "size": int(item.get("file_size") or 0),
        "kind": _kind(str(item.get("mime_type") or ""), str(item.get("file_extension") or "")),
    }


# ─────────────────────────────────────────────────────────────
#  🔗 آدرس نمایش
# ─────────────────────────────────────────────────────────────
@router.get("/library/view-url/{scope}/{file_id}")
async def view_url(scope: str, file_id: str, request: Request, user: dict = Depends(current_student)):
    """آدرس امضاشدهٔ ریدر برای یک فایل.

    پاسخ همیشه ۲۰۰ است و خودش می‌گوید «قابل خواندن هست یا نه»:
        {available: true,  url, kind, mime, name, size, expires_in}
        {available: false, reason, kind, name}

    چرا ۲۰۰ و نه خطا: «این نوع فایل پیش‌نمایش ندارد» یک حالت عادی UI
    است، نه نقص. خطا فقط برای دسترسی/ورودی/نشست می‌ماند (۴۰۱/۴۰۳/۴۰۲).
    """
    if scope not in SCOPES:
        raise HTTPException(status_code=422, detail="scope_invalid")
    web = _web_user(user)
    await _gate("references" if scope == "ref" else "resources", web)

    item = await _item(scope, file_id)
    if not item:
        raise HTTPException(status_code=404, detail="file_not_found")
    meta = _public(item)

    try:
        if scope == "ref":
            out = await ref_router.preview_url(file_id=file_id, user=web)
        else:
            out = await res_router.preview_url(content_id=file_id, user=web)
    except HTTPException as exc:
        # ۴۱۵ = نوع فایل قابل پیش‌نمایش نیست (قانون خود مینی‌اپ)
        if exc.status_code == 415:
            return {**meta, "available": False, "reason": "not_previewable"}
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="file_not_found")
        if exc.status_code == 403:
            raise HTTPException(status_code=403, detail={"code": "not_in_scope",
                                                         "message": str(exc.detail)})
        raise

    return {**meta, "available": True, "url": out.get("url", ""), "expires_in": 600}


# ─────────────────────────────────────────────────────────────
#  📈 پیشرفت مطالعه
# ─────────────────────────────────────────────────────────────
class ProgressBody(BaseModel):
    page: int = Field(default=0, ge=0, le=100000)
    total: int = Field(default=0, ge=0, le=100000)
    position: float = Field(default=0.0, ge=0.0)
    kind: str = Field(default="pdf", max_length=16)


@router.get("/library/progress/{scope}/{file_id}")
async def get_progress(scope: str, file_id: str, user: dict = Depends(current_student)):
    if scope not in SCOPES:
        raise HTTPException(status_code=422, detail="scope_invalid")
    uid = int(user["user_id"])
    doc = await _coll("reading_progress").find_one({"_id": _key(uid, scope, file_id)})
    if not doc:
        return {"page": 0, "total": 0, "position": 0.0, "updated_at": None}
    return {
        "page": int(doc.get("page") or 0),
        "total": int(doc.get("total") or 0),
        "position": float(doc.get("position") or 0.0),
        "updated_at": str(doc.get("updated_at") or ""),
    }


@router.put("/library/progress/{scope}/{file_id}")
async def put_progress(scope: str, file_id: str, body: ProgressBody,
                       user: dict = Depends(current_student)):
    """ذخیرهٔ نقطهٔ توقف. آپسِرت است؛ تکرار درخواست، رکورد تکراری نمی‌سازد."""
    if scope not in SCOPES:
        raise HTTPException(status_code=422, detail="scope_invalid")
    uid = int(user["user_id"])
    now = now_utc()
    try:
        await _coll("reading_progress").update_one(
            {"_id": _key(uid, scope, file_id)},
            {
                "$set": {
                    "uid": uid,
                    "scope": scope,
                    "file_id": file_id,
                    "page": int(body.page),
                    "total": int(body.total),
                    "position": float(body.position),
                    "kind": str(body.kind)[:16],
                    "updated_at": now,
                }
            },
            upsert=True,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("progress_save_failed uid=%s err=%s", uid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="progress_unavailable")
    return {"ok": True}


@router.get("/library/continue")
async def continue_reading(user: dict = Depends(current_student)):
    """آخرین چیزهایی که کاربر نیمه‌کاره گذاشته — برای کارت «ادامهٔ مطالعه».

    نام فایل از همان منبع اصلی خوانده می‌شود؛ اگر فایل بعد از آن حذف شده
    باشد، ردیف با `available: false` برمی‌گردد نه اینکه کرش کند.
    """
    uid = int(user["user_id"])
    try:
        docs = [d async for d in _coll("reading_progress")
                .find({"uid": uid})
                .sort("updated_at", -1)]
    except Exception as exc:  # pragma: no cover
        logger.info("continue_failed err=%s", type(exc).__name__)
        return {"items": []}

    items = []
    for d in docs[:8]:
        scope = str(d.get("scope") or "res")
        fid = str(d.get("file_id") or "")
        try:
            item = await _item(scope, fid)
        except Exception:
            item = None
        if not item:
            continue
        meta = _public(item)
        page, total = int(d.get("page") or 0), int(d.get("total") or 0)
        percent = int(round(100 * page / total)) if total > 0 else 0
        items.append({
            "scope": scope,
            "id": fid,
            "name": meta["name"],
            "kind": str(d.get("kind") or meta["kind"]),
            "page": page,
            "total": total,
            "position": float(d.get("position") or 0.0),
            "percent": max(0, min(100, percent)),
            "updated_at": str(d.get("updated_at") or ""),
        })
        if len(items) >= 5:
            break
    return {"items": items}
