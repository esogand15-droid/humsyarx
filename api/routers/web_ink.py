# -*- coding: utf-8 -*-
"""🖋 موج P4 — قلم، حاشیه‌نویسی و دفتر یادداشت.

قرارداد اصلی: **استروک، نه تصویر.** کلاینت فقط «خط» می‌فرستد و سرور آن را
می‌ذخیره می‌کند؛ رندر دوباره روی canvas انجام می‌شود. چرا:

- حجم: یک خط ۱۰۰ نقطه‌ای ≈ ۱٫۵KB، اما اسکرین‌شات همان خط ≈ ۳۰۰KB.
- کیفیت: هنگام زوم، خط دوباره با اندازهٔ واقعی کشیده می‌شود، پیکسلی نمی‌شود.
- مالکیت: مشتری فایل PDF را نمی‌گیرد و تصویری هم از آن نمی‌سازد.

مختصات **نرمال‌شده** است (۰..۱ نسبت به عرض/ارتفاع صفحه). یعنی همان خط روی
گوشی ۳۹۰px و آیپد ۱۰۲۴px و در هر سطح زوم، دقیقاً سر جای خودش می‌نشیند.

کالکشن تازه: `web_ink_pages`
    {_id: "<uid>:<scope>:<file_id>:<page>", uid, scope, file_id, page,
     strokes: [...], count, updated_at}

یک سند برای هر صفحه. ذخیره = جایگزینی کامل استروک‌های همان صفحه (idempotent)،
پس تکرار/تلاش دوباره در شبکهٔ ضعیف، خط تکراری نمی‌سازد.

اندپوینت‌ها (همه زیر /api/web):
    GET    /ink/{scope}/{file_id}/{page}   → خطوط همان صفحه
    PUT    /ink/{scope}/{file_id}/{page}   → ذخیرهٔ خطوط همان صفحه
    DELETE /ink/{scope}/{file_id}/{page}   → پاک‌کردن همان صفحه
    GET    /ink/summary/{scope}/{file_id}  → شمار خطوط هر صفحه (برای دفتر)
    GET    /ink/notes                      → فهرست یادداشت‌ها (صفحهٔ /me/notes)

نصب: در api/main.py
    from api.routers import web_ink
    app.include_router(web_ink.router, prefix="/api/web", tags=["web-ink"])
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api.routers.web_library import _gate, _web_user
from api.routers.web_reader import SCOPES, _item, _public
from api.routers.web_student import current_student
from database import db
from time_utils import now_utc

logger = logging.getLogger(__name__)

router = APIRouter()

# سقف‌ها: عددی بزرگ‌تر از این‌ها یعنی کلاینت خراب است، نه کاربر پرکار.
MAX_STROKES = 400
MAX_POINTS = 2000
MAX_PAGE = 2000
TOOLS = ("pen", "highlighter")


def _coll(name: str):
    return db.users.database[name]


def _key(uid: int, scope: str, file_id: str, page: int) -> str:
    return f"{int(uid)}:{scope}:{file_id}:{int(page)}"


def _doc_prefix(uid: int, scope: str, file_id: str) -> str:
    return f"{int(uid)}:{scope}:{file_id}:"


class Stroke(BaseModel):
    """یک خط. مختصات نرمال‌شده و ضخامت به‌صورت کسری از عرض صفحه."""

    tool: str = Field(default="pen", max_length=16)
    color: str = Field(default="#1740B8", max_length=9)
    width: float = Field(default=0.0035, gt=0, lt=0.2)
    points: list[list[float]] = Field(default_factory=list)

    @field_validator("tool")
    @classmethod
    def _tool_ok(cls, v: str) -> str:
        return v if v in TOOLS else "pen"

    @field_validator("points")
    @classmethod
    def _points_ok(cls, v: list[list[float]]) -> list[list[float]]:
        if len(v) > MAX_POINTS:
            raise ValueError("stroke_too_long")
        out = []
        for p in v:
            if len(p) != 2:
                raise ValueError("point_shape")
            x, y = float(p[0]), float(p[1])
            # مختصات بیرون از کادر صفحه بریده می‌شود، نه اینکه دور ریخته شود
            out.append([min(1.0, max(0.0, x)), min(1.0, max(0.0, y))])
        return out


class InkBody(BaseModel):
    strokes: list[Stroke] = Field(default_factory=list)

    @field_validator("strokes")
    @classmethod
    def _limit(cls, v: list[Stroke]) -> list[Stroke]:
        if len(v) > MAX_STROKES:
            raise ValueError("too_many_strokes")
        return v


def _page_ok(page: int) -> int:
    if page < 1 or page > MAX_PAGE:
        raise HTTPException(status_code=422, detail="page_invalid")
    return int(page)


async def _guard(scope: str, file_id: str, user: dict) -> dict:
    """اجازهٔ نوشتن/خواندن حاشیه‌نویسی = همان اجازهٔ خواندن خود فایل.

    عمداً از همان `_gate` و همان واکشی سند استفاده می‌شود که ریدر؛ وگرنه
    دو مسیر اجازهٔ جدا از هم می‌ساختیم و یکی از آن‌ها دیر یا زود عقب می‌ماند.
    """
    if scope not in SCOPES:
        raise HTTPException(status_code=422, detail="scope_invalid")
    web = _web_user(user)
    await _gate("references" if scope == "ref" else "resources", web)
    item = await _item(scope, file_id)
    if not item:
        raise HTTPException(status_code=404, detail="file_not_found")
    return item


@router.get("/ink/summary/{scope}/{file_id}")
async def summary(scope: str, file_id: str, user: dict = Depends(current_student)):
    """شمار خطوط هر صفحه — برای پنل «دفتر» کنار ریدر و پرش به صفحه."""
    if scope not in SCOPES:
        raise HTTPException(status_code=422, detail="scope_invalid")
    uid = int(user["user_id"])
    try:
        cur = _coll("web_ink_pages").find(
            {"scope": scope, "file_id": file_id, "uid": uid}, {"page": 1, "count": 1}
        )
        docs = [d async for d in cur]
    except Exception as exc:  # pragma: no cover
        logger.warning("ink_summary_failed uid=%s err=%s", uid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="ink_unavailable")
    pages = sorted(
        ({"page": int(d.get("page") or 0), "count": int(d.get("count") or 0)} for d in docs),
        key=lambda x: x["page"],
    )
    return {"pages": pages, "total": sum(p["count"] for p in pages)}


@router.get("/ink/notes")
async def notes(user: dict = Depends(current_student)):
    """همهٔ فایل‌هایی که این کاربر روی آن‌ها خط کشیده — برای صفحهٔ «دفتر من».

    نام فایل از منبع اصلی خوانده می‌شود؛ اگر فایل حذف شده باشد ردیف با
    `available: false` می‌آید نه اینکه کل فهرست بشکند.
    """
    uid = int(user["user_id"])
    try:
        cur = _coll("web_ink_pages").find({"uid": uid}).sort("updated_at", -1).limit(200)
        docs = [d async for d in cur]
    except Exception as exc:  # pragma: no cover
        logger.warning("ink_notes_failed uid=%s err=%s", uid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="ink_unavailable")

    grouped: dict[tuple[str, str], dict] = {}
    for d in docs:
        scope = str(d.get("scope") or "")
        fid = str(d.get("file_id") or "")
        if scope not in SCOPES or not fid:
            continue
        key = (scope, fid)
        g = grouped.setdefault(
            key,
            {"scope": scope, "id": fid, "pages": 0, "strokes": 0, "last_page": 1, "updated_at": ""},
        )
        count = int(d.get("count") or 0)
        g["pages"] += 1
        g["strokes"] += count
        ts = str(d.get("updated_at") or "")
        if ts >= g["updated_at"]:
            g["updated_at"] = ts
            g["last_page"] = int(d.get("page") or 1)

    items = []
    for (scope, fid) in sorted(grouped, key=lambda k: grouped[k]["updated_at"], reverse=True)[:30]:
        g = grouped[(scope, fid)]
        try:
            item = await _item(scope, fid)
        except Exception:
            item = None
        if not item:
            items.append({**g, "name": "فایل حذف‌شده", "kind": "other", "available": False})
            continue
        meta = _public(item)
        items.append({**g, "name": meta["name"], "kind": meta["kind"], "available": True})
    return {"items": items}


# ─────────────────────────────────────────────────────────────
#  🌊 خطوط یک صفحه
# ─────────────────────────────────────────────────────────────
@router.get("/ink/{scope}/{file_id}/{page}")
async def get_page(scope: str, file_id: str, page: int, user: dict = Depends(current_student)):
    _page_ok(page)
    uid = int(user["user_id"])
    try:
        doc = await _coll("web_ink_pages").find_one({"_id": _key(uid, scope, file_id, page)})
    except Exception as exc:  # pragma: no cover
        logger.warning("ink_read_failed uid=%s err=%s", uid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="ink_unavailable")
    if not doc:
        return {"strokes": [], "updated_at": None}
    return {"strokes": list(doc.get("strokes") or []), "updated_at": str(doc.get("updated_at") or "")}


@router.put("/ink/{scope}/{file_id}/{page}")
async def put_page(scope: str, file_id: str, page: int, body: InkBody,
                   user: dict = Depends(current_student)):
    """جایگزینی کامل خطوط همان صفحه (idempotent)."""
    _page_ok(page)
    await _guard(scope, file_id, user)
    uid = int(user["user_id"])
    strokes = [s.model_dump() for s in body.strokes]
    now = now_utc()
    try:
        await _coll("web_ink_pages").update_one(
            {"_id": _key(uid, scope, file_id, page)},
            {
                "$set": {
                    "uid": uid,
                    "scope": scope,
                    "file_id": file_id,
                    "page": int(page),
                    "strokes": strokes,
                    "count": len(strokes),
                    "updated_at": now,
                }
            },
            upsert=True,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("ink_write_failed uid=%s err=%s", uid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="ink_unavailable")
    return {"ok": True, "count": len(strokes), "updated_at": str(now)}


@router.delete("/ink/{scope}/{file_id}/{page}")
async def delete_page(scope: str, file_id: str, page: int, user: dict = Depends(current_student)):
    _page_ok(page)
    uid = int(user["user_id"])
    try:
        await _coll("web_ink_pages").delete_one({"_id": _key(uid, scope, file_id, page)})
    except Exception as exc:  # pragma: no cover
        logger.warning("ink_delete_failed uid=%s err=%s", uid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="ink_unavailable")
    return {"ok": True}


