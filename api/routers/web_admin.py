# -*- coding: utf-8 -*-
"""
🖥️ موج WA + WA2 — Web Admin Control Center API

احراز هویت مستقل دسکتاپ: OTP تلگرامی → سشن HttpOnly (۱۲ ساعته).
هیچ منطق کسب‌وکاری تکرار نمی‌شود: همان user/RBAC/audit/db موجود.
- مالک (ADMIN_ID) یا دارای هر مجوز RBAC یا ادمین محتوا ⇒ اجازه‌ی ورود وب.
- دسترسی به هر endpoint همچنان permission-based است (require_perm/owner).

🌊 WA2 (افزایشی — هیچ endpoint/رفتار قبلی حذف یا تغییر نکرده):
  WA2.1 Content Command Center : /content/tree + duplicate + bulk sessions/items
  WA2.2 Exams Admin            : /exams CRUD (schedules type=exam) + /exams/stats
  WA2.3 Settings Center        : /settings/center (GET/PATCH + meta)
  WA2.4 Bulk + Saved Filters   : tickets/questions bulk + /saved-filters
  WA2.5 Global Quick Search    : /search
  WA2.6 Analytics              : /wa-analytics (stats.view)
  WA2.7 Attention + Activity   : /attention + /activity
  WA2.8 User 360               : /users/{uid}/360
  WA2.9 Hardening              : محدودسازی bulk کاربران به مجوز + audit همه‌ی اکشن‌ها
"""
import asyncio
import csv
import hashlib
import io
import json
import re
import secrets
import time
from datetime import datetime, timedelta, date, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from api.auth import (
    ADMIN_ID, _hash_token, get_current_user, get_content_admin_user,
    get_content_global_user, new_session_token, resolve_content_intake,
    resolve_web_session, WA_SESSION_COOKIE, WA_SESSION_TTL_H,
)
from database import db
from api.routers import admin_panel as owner_api
from api.routers import subscription_management as subscription_api
from api.routers import ai_management as ai_admin_api
from api.routers import content_admin as content_api
from api.routers import academic_admin as academic_api
from api.routers import rbac as rbac_api
from api.routers import resources as resources_api
import backup as backup_service
from request_context import current_request_id

router = APIRouter()

OTP_TTL_MIN = 5
OTP_MAX_ATTEMPTS = 5
OTP_RL_COUNT = 5          # حداکثر درخواست کد
OTP_RL_WINDOW = 600       # در ۱۰ دقیقه

# rate-limit ساده‌ی درون‌حافظه‌ای per-identifier (گره Railway تک‌نمونه‌ای)
_otp_rl: dict = {}

TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']
CONTENT_TYPES = ['video', 'ppt', 'pdf', 'note', 'test', 'voice']


def _now() -> str:
    return datetime.now().isoformat()


def _oid(v):
    try:
        return ObjectId(str(v))
    except Exception:
        return None


async def _has_admin_access(uid: int) -> bool:
    """مالک یا دارای هر مجوز RBAC یا ادمین محتوا."""
    if uid == ADMIN_ID:
        return True
    try:
        if await db.is_content_admin(uid):
            return True
    except Exception:
        pass
    try:
        if await db.get_user_perms(uid):
            return True
    except Exception:
        pass
    return False


async def _resolve_user(identifier: str):
    """آیدی عددی یا یوزرنیم تلگرام → سند کاربر (بدون نشت وجود/عدم وجود)."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    if ident.lstrip("-").isdigit():
        return await db.get_user(int(ident))
    uname = ident.lstrip("@").lower()
    return await db.users.find_one({"username": {"$regex": f"^{uname}$", "$options": "i"}})


async def _guard_any_admin(user=Depends(get_current_user)) -> dict:
    """گیت مشترک endpointهای وب‌ادمین: احراز هویت + حداقل یک سطح ادمین."""
    if not await _has_admin_access(user["id"]):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _perm(permission: str):
    """🛡 WA2 — گیت مجوز برای اکشن‌های مدیریتی وب (تصمیم فقط با Permission).

    بای‌پس مالک/ادمین میراثی داخل db.has_permission اعمال می‌شود؛ در غیر
    این صورت 403 دقیقاً مثل بقیه‌ی سطح ادمین."""
    async def _guard(user=Depends(get_current_user)) -> dict:
        try:
            if await db.has_permission(user["id"], permission):
                return user
        except Exception:
            pass
        raise HTTPException(status_code=403, detail="forbidden")
    _guard.__name__ = f"wa_perm_{permission.replace('.', '_')}"
    return _guard


def _perm_any(*permissions: str):
    """عبور با داشتن حداقل یکی از مجوزها؛ owner bypass داخل DB باقی می‌ماند."""
    async def _guard(user=Depends(get_current_user)) -> dict:
        for permission in permissions:
            try:
                if await db.has_permission(user["id"], permission):
                    return user
            except Exception:
                continue
        raise HTTPException(status_code=403, detail="forbidden")
    _guard.__name__ = "wa_perm_any_" + "_or_".join(
        p.replace('.', '_') for p in permissions)
    return _guard


async def _audit(actor_uid: int, action: str, *, severity: str = "INFO",
                 target_id: str = "", target_type: str = "",
                 target_label: str = "", tags=None,
                 before: dict = None, after: dict = None):
    # 🌊 موج Audit-Diff — before/after افزودنی: db.log_action از همیشه
    # changes را می‌ساخت؛ حالا روتر وب‌ادمین هم آن را پاس می‌دهد تا
    # کشوی Diff «قبل/بعد» داده‌ی واقعی داشته باشد.
    try:
        u = await db.get_user(actor_uid)
        await db.log_action(
            actor_uid, (u or {}).get("name", str(actor_uid)),
            await db.get_actor_role_label(actor_uid),
            action, "WebAdmin", category="admin", severity=severity,
            target_id=str(target_id), target_type=target_type,
            target_label=target_label, tags=tags or [],
            before=before, after=after,
        )
    except Exception:
        pass


class RequestCode(BaseModel):
    identifier: str


class VerifyCode(BaseModel):
    identifier: str
    code: str


class BulkBody(BaseModel):
    action: str            # approve | suspend | unsuspend | set_intake
    ids: list[int]
    value: Optional[str] = None     # WA2.4 — مقدار جانبی (مثل intake)


@router.post("/auth/request-code")
async def request_code(body: RequestCode, request: Request):
    """ارسال کد ورود ۶ رقمی از طریق ربات تلگرام (بدون نشت وجود حساب)."""
    ident = (body.identifier or "").strip()[:64]
    # ── rate limit ── (WA2.9: شناسه + IP هر دو در کلید لحاظ می‌شوند)
    ip = ""
    try:
        ip = (request.client.host if getattr(request, "client", None) else "") or ""
    except Exception:
        ip = ""
    rl_key = f"{ident}|{ip}"
    now = time.time()
    hits = [t for t in _otp_rl.get(rl_key, []) if now - t < OTP_RL_WINDOW]
    if len(hits) >= OTP_RL_COUNT:
        raise HTTPException(status_code=429,
                            detail="تعداد درخواست زیاد است؛ چند دقیقه دیگر تلاش کنید.")
    hits.append(now)
    _otp_rl[rl_key] = hits

    user = await _resolve_user(ident)
    if user and user.get("approved") and not user.get("suspended"):
        uid = int(user.get("user_id"))
        if await _has_admin_access(uid):
            code = f"{secrets.randbelow(900000) + 100000}"
            exp = (datetime.utcnow() + timedelta(minutes=OTP_TTL_MIN)).isoformat()
            await db.web_admin_otps.delete_many({"uid": uid})
            await db.web_admin_otps.insert_one({
                "uid": uid,
                "code_hash": hashlib.sha256(code.encode()).hexdigest(),
                "expires_at": exp, "attempts": 0, "created_at": _now(),
            })
            # ارسال از صف outbox موجود ربات (همان الگوی admin_panel._notify)
            await db.client["medicalbot"]["bot_notifications"].insert_one({
                "type": "web_admin_otp", "chat_id": uid,
                "text": (f"🔐 <b>کد ورود به پنل مدیریت هامزیار</b>\n\n"
                         f"کد: <code>{code}</code>\n"
                         f"⏳ اعتبار: {OTP_TTL_MIN} دقیقه\n\n"
                         f"اگر شما درخواست نداده‌اید، این پیام را نادیده بگیرید."),
                "sent": False, "created_at": _now(),
            })
            await _audit(uid, "درخواست کد ورود پنل وب", tags=["ورود_وب", "otp"])
    # پاسخ یکسان always (ضد account-enumeration)
    return {"ok": True,
            "message": "اگر این حساب ادمین باشد، کد ورود در تلگرام برایتان ارسال شد."}


@router.post("/auth/verify")
async def verify_code(body: VerifyCode, response: Response):
    user = await _resolve_user(body.identifier)
    if not user:
        raise HTTPException(status_code=401, detail="کد یا شناسه نامعتبر است.")
    uid = int(user.get("user_id"))
    otp = await db.web_admin_otps.find_one({"uid": uid})
    if not otp or otp.get("expires_at", "") < _now():
        raise HTTPException(status_code=401, detail="کد منقضی شده؛ دوباره درخواست بدهید.")
    if (otp.get("attempts") or 0) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="تلاش‌های ناموفق زیاد بود؛ دوباره درخواست کد بدهید.")
    ok = hashlib.sha256((body.code or "").strip().encode()).hexdigest() == otp.get("code_hash")
    if not ok:
        await db.web_admin_otps.update_one({"uid": uid}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=401, detail="کد نامعتبر است.")
    if not await _has_admin_access(uid):
        raise HTTPException(status_code=403, detail="forbidden")

    await db.web_admin_otps.delete_many({"uid": uid})
    token = new_session_token()
    await db.web_admin_sessions.insert_one({
        "_id": _hash_token(token), "uid": uid,
        "created_at": _now(),
        "expires_at": (datetime.utcnow() + timedelta(hours=WA_SESSION_TTL_H)).isoformat(),
        "revoked": False,
    })
    response.set_cookie(
        WA_SESSION_COOKIE, token,
        max_age=WA_SESSION_TTL_H * 3600,
        httponly=True, secure=True, samesite="lax", path="/",
    )
    await _audit(uid, "ورود موفق به پنل وب", tags=["ورود_وب"])
    return {"ok": True, "id": uid, "name": user.get("name", "")}


@router.get("/me")
async def me(user=Depends(_guard_any_admin)):
    uid = user["id"]
    perms = sorted(await db.get_user_perms(uid))
    return {
        "id": uid,
        "name": (user.get("_db") or {}).get("name", ""),
        "nickname": (user.get("_db") or {}).get("nickname"),
        "username": (user.get("_db") or {}).get("username", ""),
        "is_owner": uid == ADMIN_ID,
        "is_content_admin": await db.is_content_admin(uid),
        "role_label": await db.get_actor_role_label(uid),
        "perms": perms,
    }


@router.post("/auth/logout")
async def logout(request: Request, response: Response, user=Depends(_guard_any_admin)):
    sess = await resolve_web_session(request.cookies.get(WA_SESSION_COOKIE, ""))
    if sess:
        await db.web_admin_sessions.update_one(
            {"_id": sess["_id"]}, {"$set": {"revoked": True, "revoked_at": _now()}})
    response.delete_cookie(WA_SESSION_COOKIE, path="/")
    await _audit(user["id"], "خروج از پنل وب", tags=["خروج_وب"])
    return {"ok": True}


@router.get("/overview")
async def overview(user=Depends(_guard_any_admin)):
    """KPIهای role-aware؛ هیچ شمارش خارج از effective permissions query نمی‌شود."""
    uid = user["id"]
    perms = await db.get_user_perms(uid)
    allow = lambda *keys: uid == ADMIN_ID or any(k in perms for k in keys)
    jobs = {}
    if allow("users.view", "users.manage", "stats.view"):
        jobs["total_users"] = db.users.count_documents({})
    if allow("users.manage"):
        jobs["pending_users"] = db.users.count_documents({"approved": False, "suspended": {"$ne": True}})
    if allow("subscription.manage"):
        jobs["pending_payments"] = db.sub_payment_count_all("pending")
        jobs["sub_stats"] = db.sub_stats()
    if allow("questions.review", "questions.review_scoped"):
        jobs["pending_questions"] = db.questions.count_documents({"approved": False})
    if allow("tickets.reply", "tickets.manage"):
        jobs["open_tickets"] = db.tickets.count_documents({"status": "open"})
    if allow("reports.review"):
        jobs["open_reports"] = db.content_reports.count_documents({"status": {"$in": ["new", "pending", "reviewing"]}})
    keys = list(jobs)
    values = await asyncio.gather(*(jobs[k] for k in keys), return_exceptions=True)
    data = {k: (None if isinstance(v, Exception) else v) for k, v in zip(keys, values)}
    sub_stats = data.pop("sub_stats", None) or {}
    if allow("subscription.manage"):
        data["active_subs"] = sub_stats.get("active", 0)
        data["expiring_soon"] = sub_stats.get("expiring", 0)
    return data


_SMART_USER_RAW_FIELDS = {
    "name": "name", "nickname": "nickname", "username": "username",
    "student_id": "student_id", "intake": "intake", "group": "group",
    "total_answers": "total_answers", "correct_answers": "correct_answers",
    "streak": "streak_current", "ai_usage": "ai_total_usage",
    "registered_at": "registered_at", "last_active": "last_active",
}
_SMART_OPS = {"eq": "$eq", "ne": "$ne", "gt": "$gt", "gte": "$gte", "lt": "$lt", "lte": "$lte"}


async def _compile_user_smart_query(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        tree = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(422, "ساختار فیلتر هوشمند معتبر نیست")
    state = {"nodes": 0, "leaves": 0}
    now = datetime.now()

    async def compile_node(node, depth=0):
        if depth > 3 or not isinstance(node, dict):
            raise HTTPException(422, "عمق فیلتر هوشمند بیشتر از حد مجاز است")
        state["nodes"] += 1
        if state["nodes"] > 40:
            raise HTTPException(422, "ساختار فیلتر هوشمند بیش از حد پیچیده است")
        if "conditions" in node:
            logic = str(node.get("logic") or "and").lower()
            if logic not in ("and", "or"):
                raise HTTPException(422, "منطق گروه باید AND یا OR باشد")
            conditions = node.get("conditions") or []
            if not conditions:
                raise HTTPException(422, "گروه شرط خالی است")
            compiled = [await compile_node(child, depth + 1) for child in conditions]
            return {"$and" if logic == "and" else "$or": compiled}
        state["leaves"] += 1
        if state["leaves"] > 30:
            raise HTTPException(422, "حداکثر ۳۰ شرط در فیلتر هوشمند مجاز است")
        field, op, value = node.get("field"), node.get("op", "eq"), node.get("value")
        if field in _SMART_USER_RAW_FIELDS:
            db_field = _SMART_USER_RAW_FIELDS[field]
            if op == "contains":
                text = str(value or "").strip()
                if not text: raise HTTPException(422, "مقدار جست‌وجوی شرط خالی است")
                return {db_field: {"$regex": re.escape(text), "$options": "i"}}
            if op == "in":
                values = value if isinstance(value, list) else [part.strip() for part in str(value or "").split(",") if part.strip()]
                return {db_field: {"$in": values[:100]}}
            mongo_op = _SMART_OPS.get(op)
            if not mongo_op: raise HTTPException(422, "عملگر فیلتر هوشمند پشتیبانی نمی‌شود")
            if field in ("total_answers", "correct_answers", "streak", "ai_usage"):
                try: value = float(value)
                except (TypeError, ValueError): raise HTTPException(422, "مقدار عددی شرط نامعتبر است")
            if field == "group": value = db.normalize_group(value)
            return {db_field: value} if op == "eq" else {db_field: {mongo_op: value}}
        if field == "status":
            mapping = {
                "active": {"approved": True, "suspended": {"$ne": True}},
                "pending": {"approved": False, "suspended": {"$ne": True}},
                "suspended": {"suspended": True},
            }
            if op not in ("eq", "ne") or value not in mapping:
                raise HTTPException(422, "شرط وضعیت نامعتبر است")
            if op == "eq": return mapping[value]
            return {"$nor": [mapping[value]]}
        if field == "accuracy":
            try: threshold = float(value)
            except (TypeError, ValueError): raise HTTPException(422, "آستانه دقت نامعتبر است")
            if op not in _SMART_OPS: raise HTTPException(422, "عملگر دقت نامعتبر است")
            accuracy_expr = {"$cond": [
                {"$gt": [{"$ifNull": ["$total_answers", 0]}, 0]},
                {"$multiply": [{"$divide": [{"$ifNull": ["$correct_answers", 0]},
                                               {"$ifNull": ["$total_answers", 1]}]}, 100]}, 0]}
            return {"$expr": {_SMART_OPS[op]: [accuracy_expr, threshold]}}
        if field == "inactive_days":
            try: days = max(0, min(3650, int(value)))
            except (TypeError, ValueError): raise HTTPException(422, "تعداد روز عدم فعالیت نامعتبر است")
            cutoff = (now - timedelta(days=days)).isoformat()
            clause = {"$or": [{"last_active": {"$lt": cutoff}}, {"last_active": {"$exists": False}}, {"last_active": ""}]}
            return clause if op in ("gte", "gt", "eq") else {"$nor": [clause]}
        if field == "subscription_days_left":
            try: days = max(0, min(3650, int(value)))
            except (TypeError, ValueError): raise HTTPException(422, "روز باقی‌مانده اشتراک نامعتبر است")
            end_filter = {"$gte": now.isoformat()}
            cutoff = (now + timedelta(days=days)).isoformat()
            if op in ("lte", "lt", "eq"): end_filter["$lte"] = cutoff
            elif op in ("gt", "gte"): end_filter["$gt"] = cutoff
            else: raise HTTPException(422, "عملگر اشتراک نامعتبر است")
            ids = await db.subscriptions.distinct("_id", {"status": "active", "end_date": end_filter})
            return {"user_id": {"$in": ids}}
        if field == "open_tickets":
            ids = await db.tickets.distinct("user_id", {"status": "open"})
            truthy = str(value).lower() in ("1", "true", "yes") or value is True
            return {"user_id": {"$in" if truthy else "$nin": ids}}
        if field == "role":
            ids = await db.user_ids_by_role(str(value or "").strip(), limit=100000)
            return {"user_id": {"$in": ids}}
        if field == "exam_count":
            try: threshold = max(0, int(value))
            except (TypeError, ValueError): raise HTTPException(422, "تعداد آزمون نامعتبر است")
            mongo_op = _SMART_OPS.get(op)
            if not mongo_op: raise HTTPException(422, "عملگر تعداد آزمون نامعتبر است")
            grouped = await db.exam_sessions.aggregate([
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$match": {"count": {mongo_op: threshold}}}, {"$project": {"_id": 1}},
            ]).to_list(100000)
            return {"user_id": {"$in": [row.get("_id") for row in grouped if row.get("_id") is not None]}}
        raise HTTPException(422, "فیلد فیلتر هوشمند پشتیبانی نمی‌شود")

    return await compile_node(tree)


@router.get("/users")
async def users_table(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    q: str | None = Query(None),
    intake: str | None = Query(None),
    group: str | None = Query(None),
    status: str | None = Query(None),   # pending | suspended | active
    role: str | None = Query(None, max_length=80),
    activity: str | None = Query(None, pattern="^(never|inactive_14|inactive_30)$"),
    accuracy_max: float | None = Query(None, ge=0, le=100),
    sub_expiring_days: int | None = Query(None, ge=1, le=365),
    has_open_ticket: bool | None = Query(None),
    smart: str | None = Query(None, max_length=8000),
    sort_by: str = Query("registered_at", pattern="^(registered_at|last_active|name|total_answers|correct_answers|streak_current|ai_total_usage)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user=Depends(_perm_any("users.view", "users.manage")),
):
    """جدول حرفه‌ای کاربران با pagination/filter/sort کاملاً سرورساید.

    enrichmentهای نقش، اشتراک، تیکت و تعداد آزمون برای همان صفحه به‌شکل
    batch خوانده می‌شوند؛ هیچ query به‌ازای هر ردیف و هیچ full dataset fetch
    در پاسخ وجود ندارد.
    """
    filt = db.build_user_search_query(q) if q else {}
    smart = smart if isinstance(smart, str) else None
    smart_filter = await _compile_user_smart_query(smart)
    if smart_filter:
        filt = {"$and": [filt, smart_filter]} if filt else {"$and": [smart_filter]}
    if intake:
        filt["intake"] = intake
    if group:
        filt["group"] = db.normalize_group(group)
    if status == "pending":
        filt["approved"] = False
    elif status == "suspended":
        filt["suspended"] = True
    elif status == "active":
        filt["approved"] = True
        filt["suspended"] = {"$ne": True}
    if role:
        role_ids = await db.user_ids_by_role(role, limit=100000)
        # users.role فقط mirror سازگاری است؛ user_ids_by_role هر سه منبع را
        # deduplicate می‌کند و منطق RBAC موازی نمی‌سازد.
        filt["user_id"] = {"$in": role_ids}
    now = datetime.now()
    if activity == "never":
        filt["$and"] = filt.get("$and", []) + [{"$or": [
            {"last_active": {"$exists": False}}, {"last_active": None},
            {"last_active": ""},
        ]}]
    elif activity in ("inactive_14", "inactive_30"):
        days = 14 if activity == "inactive_14" else 30
        cutoff = (now - timedelta(days=days)).isoformat()
        filt["$and"] = filt.get("$and", []) + [{"$or": [
            {"last_active": {"$lt": cutoff}}, {"last_active": {"$exists": False}},
        ]}]
    if accuracy_max is not None:
        filt["$expr"] = {"$lte": [
            {"$cond": [
                {"$gt": [{"$ifNull": ["$total_answers", 0]}, 0]},
                {"$multiply": [
                    {"$divide": [
                        {"$ifNull": ["$correct_answers", 0]},
                        {"$ifNull": ["$total_answers", 1]},
                    ]}, 100,
                ]},
                0,
            ]},
            accuracy_max,
        ]}
    if sub_expiring_days is not None:
        sub_ids = await db.subscriptions.distinct("_id", {
            "status": "active", "end_date": {
                "$gte": now.isoformat(),
                "$lte": (now + timedelta(days=sub_expiring_days)).isoformat(),
            },
        })
        existing_ids = (filt.get("user_id") or {}).get("$in")
        filt["user_id"] = {"$in": ([i for i in sub_ids if i in set(existing_ids)]
                                      if existing_ids is not None else sub_ids)}
    if has_open_ticket is not None:
        ticket_ids = await db.tickets.distinct("user_id", {"status": "open"})
        existing_ids = (filt.get("user_id") or {}).get("$in")
        if has_open_ticket:
            filt["user_id"] = {"$in": ([i for i in ticket_ids if i in set(existing_ids)]
                                          if existing_ids is not None else ticket_ids)}
        elif existing_ids is not None:
            ticket_set = set(ticket_ids)
            filt["user_id"] = {"$in": [i for i in existing_ids if i not in ticket_set]}
        else:
            filt["user_id"] = {"$nin": ticket_ids}

    total = await db.users.count_documents(filt)
    projection = {
        "user_id": 1, "name": 1, "nickname": 1, "username": 1, "student_id": 1,
        "group": 1, "intake": 1, "role": 1, "approved": 1, "suspended": 1,
        "registered_at": 1, "last_active": 1, "total_answers": 1,
        "correct_answers": 1, "prestige_rank": 1, "prestige_div": 1,
        "streak_current": 1, "ai_total_usage": 1,
    }
    docs = await (db.users.find(filt, projection)
                  .sort(sort_by, 1 if sort_dir == "asc" else -1)
                  .skip((page - 1) * per_page).limit(per_page).to_list(per_page))
    ids = [u.get("user_id") for u in docs if u.get("user_id") is not None]
    if ids:
        role_docs, sub_docs, open_docs, exam_counts = await asyncio.gather(
            db.user_roles.find({"_id": {"$in": ids}}, {"roles": 1, "scope_intake": 1}).to_list(per_page),
            db.subscriptions.find({"_id": {"$in": ids}}, {
                "status": 1, "plan_name": 1, "end_date": 1,
            }).to_list(per_page),
            db.tickets.find({"user_id": {"$in": ids}, "status": "open"}, {"user_id": 1}).to_list(500),
            db.exam_sessions.aggregate([
                {"$match": {"user_id": {"$in": ids}}},
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
            ]).to_list(per_page),
        )
    else:
        role_docs, sub_docs, open_docs, exam_counts = [], [], [], []
    role_map = {r.get("_id"): r for r in role_docs}
    sub_map = {s.get("_id"): s for s in sub_docs}
    open_set = {t.get("user_id") for t in open_docs}
    exam_map = {e.get("_id"): int(e.get("count") or 0) for e in exam_counts}

    rows = []
    for u in docs:
        uid = u.get("user_id")
        total_answers = int(u.get("total_answers") or 0)
        correct = int(u.get("correct_answers") or 0)
        sub = sub_map.get(uid) or {}
        days_left = None
        if sub.get("status") == "active" and sub.get("end_date"):
            try:
                days_left = max(0, (datetime.fromisoformat(sub["end_date"]) - now).days)
            except (TypeError, ValueError):
                days_left = None
        roles = list((role_map.get(uid) or {}).get("roles") or [])
        if not roles and u.get("role") not in (None, "", "student"):
            roles = [u.get("role")]
        rows.append({
            "id": uid, "name": u.get("name", ""), "nickname": u.get("nickname"),
            "username": u.get("username", ""), "display_name": db.display_name_of(u),
            "student_id": u.get("student_id", ""), "group": u.get("group", ""),
            "intake": u.get("intake", ""), "role": u.get("role", "student"),
            "roles": roles, "role_scope": (role_map.get(uid) or {}).get("scope_intake"),
            "approved": u.get("approved", False), "suspended": u.get("suspended", False),
            "registered_at": (u.get("registered_at") or "")[:16],
            "last_active": (u.get("last_active") or "")[:16],
            "total_answers": total_answers, "correct_answers": correct,
            "accuracy": round(correct * 100 / total_answers, 1) if total_answers else 0,
            "rank": u.get("prestige_rank", ""), "div": u.get("prestige_div", ""),
            "streak": int(u.get("streak_current") or 0),
            "ai_usage": int(u.get("ai_total_usage") or 0),
            "exam_count": exam_map.get(uid, 0), "has_open_ticket": uid in open_set,
            "subscription": {
                "status": sub.get("status", ""), "plan": sub.get("plan_name", ""),
                "end_date": (sub.get("end_date") or "")[:10], "days_left": days_left,
            } if sub else None,
        })
    return {
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "users": rows,
    }


@router.get("/exports/users.csv")
async def export_users_csv(
    q: str | None = Query(None), intake: str | None = Query(None),
    group: str | None = Query(None), status: str | None = Query(None),
    role: str | None = Query(None), activity: str | None = Query(None),
    accuracy_max: float | None = Query(None, ge=0, le=100),
    sub_expiring_days: int | None = Query(None, ge=1, le=365),
    has_open_ticket: bool | None = Query(None), smart: str | None = Query(None, max_length=8000),
    sort_by: str = Query("registered_at"), sort_dir: str = Query("desc"),
    user=Depends(_perm_any("users.view", "users.manage")),
):
    """CSV streaming برای dataset بزرگ؛ مرورگر هرگز همه کاربران را در RAM نمی‌گیرد."""
    smart = smart if isinstance(smart, str) else None
    allowed_sort = {"registered_at", "last_active", "name", "total_answers", "correct_answers", "streak_current", "ai_total_usage"}
    if sort_by not in allowed_sort or sort_dir not in ("asc", "desc"):
        raise HTTPException(422, "مرتب‌سازی نامعتبر است")
    if activity not in (None, "", "never", "inactive_14", "inactive_30"):
        raise HTTPException(422, "فیلتر فعالیت نامعتبر است")
    await _audit(user["id"], "خروجی CSV کاربران", severity="HIGH",
                 target_type="export", target_label="users.csv",
                 after={"filtered": bool(any([q, intake, group, status, role, activity,
                                                accuracy_max is not None, sub_expiring_days,
                                                has_open_ticket is not None, smart]))},
                 tags=["خروجی", "کاربران", "پنل_وب"])
    columns = ["telegram_id", "name", "nickname", "username", "student_id", "intake", "group",
               "status", "roles", "subscription", "subscription_end", "accuracy", "total_answers",
               "exam_count", "ai_usage", "streak", "rank", "last_active", "registered_at"]

    def safe(value):
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text

    async def stream():
        buf = io.StringIO(); writer = csv.writer(buf)
        writer.writerow(columns)
        yield "\ufeff" + buf.getvalue(); buf.seek(0); buf.truncate(0)
        page = 1
        while True:
            result = await users_table(
                page=page, per_page=100, q=q, intake=intake, group=group, status=status,
                role=role, activity=activity, accuracy_max=accuracy_max,
                sub_expiring_days=sub_expiring_days, has_open_ticket=has_open_ticket, smart=smart,
                sort_by=sort_by, sort_dir=sort_dir, user=user,
            )
            rows = result.get("users") or []
            for row in rows:
                sub = row.get("subscription") or {}
                writer.writerow([safe(v) for v in [
                    row.get("id"), row.get("name"), row.get("nickname"), row.get("username"),
                    row.get("student_id"), row.get("intake"), row.get("group"),
                    "suspended" if row.get("suspended") else "active" if row.get("approved") else "pending",
                    "|".join(row.get("roles") or []), sub.get("status"), sub.get("end_date"),
                    row.get("accuracy"), row.get("total_answers"), row.get("exam_count"),
                    row.get("ai_usage"), row.get("streak"),
                    " / ".join(x for x in [row.get("rank"), row.get("div")] if x),
                    row.get("last_active"), row.get("registered_at"),
                ]])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
            if page >= int(result.get("pages") or 1) or not rows:
                break
            page += 1

    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=humsyar-users.csv"})


@router.post("/users/bulk")
async def users_bulk(body: BulkBody, user=Depends(_guard_any_admin)):
    """اکشن گروهی کاربران با گزارش success/failed/skipped و سقف ۱۰۰.

    تغییر نقش از همان تابع RBAC و پیام از همان outbox موجود استفاده می‌کند؛
    این endpoint orchestration وب است، نه business logic موازی.
    """
    action_perm = {
        "approve": "users.manage", "set_intake": "users.manage",
        "set_group": "users.manage", "add_role": "users.manage",
        "remove_role": "users.manage", "suspend": "users.suspend",
        "unsuspend": "users.suspend", "message": "users.message", "block": "users.delete",
    }
    need = action_perm.get(body.action)
    if not need:
        raise HTTPException(400, "اکشن نامعتبر است.")
    actor = user["id"]
    if not await db.has_permission(actor, need):
        raise HTTPException(403, "forbidden")
    ids = list(dict.fromkeys(
        int(i) for i in (body.ids or [])
        if isinstance(i, (int, str)) and str(i).isdigit()
    ))[:100]
    if not ids:
        raise HTTPException(400, "لیست کاربران خالی است.")
    succeeded, skipped, failed = [], [], []
    value = (body.value or "").strip()
    if body.action in ("set_intake", "set_group", "add_role", "remove_role", "message", "block") and not value:
        raise HTTPException(422, "مقدار عملیات گروهی الزامی است")
    if body.action in ("add_role", "remove_role") and not await db.get_role(value):
        raise HTTPException(422, "نقش ناشناخته است")

    for uid in ids:
        if uid == ADMIN_ID and body.action in ("suspend", "remove_role", "block"):
            skipped.append({"id": uid, "reason": "owner_protected"})
            continue
        target = await db.get_user(uid)
        if not target:
            skipped.append({"id": uid, "reason": "user_not_found"})
            continue
        try:
            if body.action == "approve":
                if target.get("approved") and not target.get("suspended"):
                    skipped.append({"id": uid, "reason": "already_approved"}); continue
                await db.update_user(uid, {"approved": True, "suspended": False})
                await db.inbox_add(uid, 'account', "✅ حسابت تأیید شد!",
                    "اکنون به تمام بخش‌های هامزیار دسترسی داری — خوش اومدی! 🎓", link='/')
            elif body.action == "suspend":
                if target.get("suspended"):
                    skipped.append({"id": uid, "reason": "already_suspended"}); continue
                await db.update_user(uid, {"suspended": True, "approved": False})
            elif body.action == "unsuspend":
                if not target.get("suspended"):
                    skipped.append({"id": uid, "reason": "not_suspended"}); continue
                await db.update_user(uid, {"suspended": False, "approved": True})
            elif body.action == "set_intake":
                if (target.get("intake") or "") == value:
                    skipped.append({"id": uid, "reason": "unchanged"}); continue
                await db.update_user(uid, {"intake": value})
            elif body.action == "set_group":
                normalized = db.normalize_group(value)
                if (target.get("group") or "") == normalized:
                    skipped.append({"id": uid, "reason": "unchanged"}); continue
                await db.update_user(uid, {"group": normalized})
            elif body.action in ("add_role", "remove_role"):
                info = await db.get_user_roles(uid)
                has_role = value in info.get("keys", [])
                if (body.action == "add_role" and has_role) or (body.action == "remove_role" and not has_role):
                    skipped.append({"id": uid, "reason": "unchanged"}); continue
                payload = rbac_api.AssignBody(
                    add=[value] if body.action == "add_role" else [],
                    remove=[value] if body.action == "remove_role" else [],
                )
                await rbac_api.assign_roles(uid=uid, body=payload, user=user)
            elif body.action == "message":
                await wa_user_message(uid=uid, body=DmIn(text=value), user=user)
            elif body.action == "block":
                await wa_user_action(uid=uid, body=UserActionIn(action="block", reason=value), user=user)
            succeeded.append(uid)
        except HTTPException as exc:
            failed.append({"id": uid, "error": str(exc.detail or "operation_failed")[:160]})
        except Exception:
            failed.append({"id": uid, "error": "operation_failed"})

    labels = {
        "approve": "تأیید گروهی", "suspend": "تعلیق گروهی",
        "unsuspend": "رفع تعلیق گروهی", "set_intake": "تغییر ورودی گروهی",
        "set_group": "تغییر گروه گروهی", "add_role": "افزودن نقش گروهی",
        "remove_role": "حذف نقش گروهی", "message": "پیام گروهی انتخابی",
        "block": "مسدودسازی گروهی",
    }
    await _audit(
        actor, f"{labels[body.action]} کاربران ({len(succeeded)} موفق)",
        severity="CRITICAL" if body.action == "block" else "HIGH" if body.action in ("suspend", "remove_role") else "INFO",
        target_type="user_batch", target_label=f"{len(ids)} کاربر",
        after={"action": body.action, "requested": len(ids),
               "succeeded": len(succeeded), "failed": len(failed), "skipped": len(skipped)},
        tags=["bulk_users", "پنل_وب"],
    )
    return {"ok": not failed, "done": len(succeeded), "succeeded": succeeded,
            "failed": failed, "skipped": skipped}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.7 — «نیازمند اقدام» + فید فعالیت واقعی
# ══════════════════════════════════════════════════════════════════

@router.get("/attention")
async def attention(user=Depends(_guard_any_admin)):
    """صف‌های اقدام permission-aware؛ شمارش خارج از دسترسی حتی برگردانده نمی‌شود."""
    perms = await db.get_user_perms(user["id"])
    allow = lambda *keys: user["id"] == ADMIN_ID or any(k in perms for k in keys)
    jobs, time_jobs = {}, {}
    async def latest_at(collection, query, *fields):
        docs = await collection.find(query).sort(fields[0], -1).limit(1).to_list(1)
        row = docs[0] if docs else {}
        return next((row.get(field) for field in fields if row.get(field)), None)
    if allow("users.view", "users.manage"):
        query = {"approved": False, "suspended": {"$ne": True}}
        jobs["users"] = db.users.count_documents(query)
        time_jobs["users"] = latest_at(db.users, query, "registered_at")
    if allow("subscription.manage"):
        query = {"status": "pending"}
        jobs["payments"] = db.sub_payment_count_all("pending")
        time_jobs["payments"] = latest_at(db.sub_payments, query, "submitted_at", "created_at")
    if allow("questions.review", "questions.review_scoped"):
        query = {"approved": False}
        jobs["questions"] = db.questions.count_documents(query)
        time_jobs["questions"] = latest_at(db.questions, query, "created_at")
    if allow("tickets.reply", "tickets.manage"):
        query = {"status": "open"}
        jobs["tickets"] = db.tickets.count_documents(query)
        time_jobs["tickets"] = latest_at(db.tickets, query, "created_at")
    if allow("reports.review"):
        query = {"status": {"$in": ["new", "pending", "reviewing"]}}
        jobs["reports"] = db.content_reports.count_documents(query)
        time_jobs["reports"] = latest_at(db.content_reports, query, "created_at")
    if allow("notifications.manage", "system.manage"):
        async def failed_jobs_metric(kind):
            runs = await db.get_recent_notif_runs(limit=20)
            failed = [run for run in runs if int(run.get("failed") or 0) > 0]
            return len(failed) if kind == "count" else ((failed[0].get("started_at") or failed[0].get("created_at")) if failed else None)
        jobs["failed_jobs"] = failed_jobs_metric("count")
        time_jobs["failed_jobs"] = failed_jobs_metric("time")
    keys = list(jobs)
    values, time_values = await asyncio.gather(
        asyncio.gather(*(jobs[k] for k in keys), return_exceptions=True),
        asyncio.gather(*(time_jobs[k] for k in keys), return_exceptions=True))
    counts = {k: (0 if isinstance(v, Exception) else int(v or 0)) for k, v in zip(keys, values)}
    timestamps = {k: (None if isinstance(v, Exception) else v) for k, v in zip(keys, time_values)}
    meta = {
        "payments": ("🧾", "رسید پرداخت در انتظار بررسی", "/subscriptions?tab=payments", "warning"),
        "tickets": ("🎫", "تیکت بدون پاسخ", "/tickets?status=open", "warning"),
        "questions": ("🧪", "سؤال در انتظار بازبینی", "/questions?status=pending", "warning"),
        "users": ("🧑‍🎓", "کاربر در انتظار تأیید", "/users?status=pending", "warning"),
        "reports": ("🚩", "گزارش محتوا/سؤال در انتظار", "/content?tab=reports", "warning"),
        "failed_jobs": ("⚙️", "اجرای اعلان دارای خطا", "/system", "critical"),
    }
    checked_at = _now()
    items = [{"key": k, "icon": meta[k][0], "label": meta[k][1],
              "count": counts.get(k, 0), "go": meta[k][2], "severity": meta[k][3],
              "timestamp": timestamps.get(k), "urgent": counts.get(k, 0) > 0}
             for k in meta if k in counts]
    backup = None
    if allow("backup.manage", "settings.manage", "system.manage"):
        last_run = await db.get_setting("auto_backup_last_run", None)
        enabled = bool(await db.get_setting("auto_backup_enabled", False))
        backup = {"last_run": last_run, "enabled": enabled}
        stale = not enabled or not last_run
        if enabled and last_run:
            try: stale = datetime.fromisoformat(last_run) < datetime.now() - timedelta(hours=48)
            except (TypeError, ValueError): stale = True
        if stale:
            items.append({"key": "backup_issue", "icon": "💾",
                          "label": "پشتیبان‌گیری نیازمند بررسی است", "count": 1,
                          "go": "/system", "severity": "critical",
                          "timestamp": last_run or checked_at, "urgent": True})
    return {"items": items, "backup": backup, "checked_at": checked_at}


@router.get("/activity")
async def activity(limit: int = Query(40, ge=1, le=100),
                   user=Depends(_guard_any_admin)):
    """🕓 جریان فعالیت واقعی از audit_logs — با متادیتای کامل برای View Context."""
    logs = await db.get_recent_logs(limit=limit)
    out = []
    for l in logs:
        actor = l.get("actor") or {}
        out.append({
            "id": str(l.get("_id", "")),
            "at": (l.get("timestamp") or "")[:16].replace("T", " "),
            "actor_id": actor.get("id"),
            "actor_name": actor.get("name", ""),
            "actor_role": actor.get("role", ""),
            "action": l.get("action", ""),
            "module": l.get("module", ""),
            "severity": l.get("severity", "INFO"),
            "target_type": l.get("target_type", ""),
            "target_id": l.get("target_id", ""),
            "target_label": l.get("target_label", ""),
            "tags": l.get("tags") or [],
        })
    return {"items": out}


@router.get("/dashboard-bundle")
async def dashboard_bundle(user=Depends(_guard_any_admin)):
    """یک round-trip برای صفحه اصلی؛ بخش‌های اختیاری permission-aware هستند."""
    uid = user["id"]
    perms = await db.get_user_perms(uid)
    base, attn = await asyncio.gather(overview(user=user), attention(user=user))
    insights = None
    feed = []
    owner_stats = None
    if uid == ADMIN_ID or "stats.view" in perms:
        try:
            insights = await db.admin_insights()
        except Exception:
            insights = None
    if uid == ADMIN_ID or "audit.view" in perms:
        try:
            feed = (await activity(limit=30, user=user)).get("items", [])
        except Exception:
            feed = []
    if uid == ADMIN_ID:
        try:
            owner_stats = await owner_api.stats(admin=user)
        except Exception:
            owner_stats = None
    return {"overview": base, "attention": attn, "activity": feed,
            "insights": insights, "stats": owner_stats}


# ══════════════════════════════════════════════════════════════════
# 👑 W24/W28 — Operations Hub: My Work, Alerts, Data Quality
# ══════════════════════════════════════════════════════════════════

async def _oldest_time(collection, query: dict, *fields):
    docs = await collection.find(query).sort(fields[0], 1).limit(1).to_list(1)
    row = docs[0] if docs else {}
    return next((row.get(field) for field in fields if row.get(field)), None)


@router.get("/operations/my-work")
async def wa_my_work(user=Depends(_guard_any_admin)):
    """صف کار واقعی مدیر جاری؛ هیچ task یا SLA ساختگی تولید نمی‌شود."""
    uid = user["id"]
    perms = await db.get_user_perms(uid)
    allow = lambda *keys: uid == ADMIN_ID or any(key in perms for key in keys)
    jobs, times, meta = {}, {}, {}
    if allow("tickets.reply", "tickets.manage"):
        query = {"assignee_id": uid, "status": {"$ne": "closed"}}
        jobs["assigned_tickets"] = db.tickets.count_documents(query)
        times["assigned_tickets"] = _oldest_time(db.tickets, query, "created_at")
        meta["assigned_tickets"] = ("🎫", "تیکت‌های تخصیص‌یافته به من", "/tickets?assignee=" + str(uid), "high")
    if allow("questions.review", "questions.review_scoped"):
        scope = await _question_scope_context(user)
        query = {"approved": False}
        if scope.get("kind") == "scoped": query["intake"] = scope.get("intake") or ""
        jobs["question_reviews"] = db.questions.count_documents(query)
        times["question_reviews"] = _oldest_time(db.questions, query, "created_at")
        meta["question_reviews"] = ("🧪", "سؤال‌های منتظر بازبینی", "/questions?status=pending", "normal")
    if allow("reports.review"):
        query = {"status": {"$in": ["new", "pending", "reviewing"]}}
        jobs["content_reports"] = db.content_reports.count_documents(query)
        times["content_reports"] = _oldest_time(db.content_reports, query, "created_at")
        meta["content_reports"] = ("🚩", "گزارش‌های محتوا", "/content?tab=reports", "normal")
    if allow("subscription.manage"):
        query = {"status": "pending"}
        jobs["payment_reviews"] = db.sub_payments.count_documents(query)
        times["payment_reviews"] = _oldest_time(db.sub_payments, query, "submitted_at", "created_at")
        meta["payment_reviews"] = ("🧾", "رسیدهای منتظر بررسی", "/subscriptions?tab=payments", "high")
    if allow("users.manage"):
        query = {"approved": False, "suspended": {"$ne": True}}
        jobs["user_approvals"] = db.users.count_documents(query)
        times["user_approvals"] = _oldest_time(db.users, query, "registered_at")
        meta["user_approvals"] = ("👤", "ثبت‌نام‌های منتظر تأیید", "/users?status=pending", "normal")
    keys = list(jobs)
    counts, oldest = await asyncio.gather(
        asyncio.gather(*(jobs[key] for key in keys), return_exceptions=True),
        asyncio.gather(*(times[key] for key in keys), return_exceptions=True),
    ) if keys else ([], [])
    tasks = []
    for key, count_value, time_value in zip(keys, counts, oldest):
        count = 0 if isinstance(count_value, Exception) else int(count_value or 0)
        at = None if isinstance(time_value, Exception) else time_value
        icon, label, go, urgency = meta[key]
        tasks.append({"key": key, "icon": icon, "label": label, "count": count,
                      "oldest_at": at, "go": go, "urgency": urgency,
                      "empty": count == 0})
    tasks.sort(key=lambda item: ({"high": 0, "normal": 1}.get(item["urgency"], 2),
                                 0 if item["count"] else 1, item.get("oldest_at") or ""))
    return {"tasks": tasks, "checked_at": _now()}


@router.get("/operations/alerts")
async def wa_alert_center(user=Depends(_guard_any_admin)):
    data = await attention(user=user)
    alerts = [item for item in data.get("items", []) if int(item.get("count") or 0) > 0]
    alerts.sort(key=lambda item: (0 if item.get("severity") == "critical" else 1,
                                  item.get("timestamp") or ""))
    return {"alerts": alerts, "checked_at": data.get("checked_at")}


_QUALITY_META = {
    "users_missing_intake": ("warning", "کاربر تأییدشده بدون ورودی", "تکمیل ورودی فقط پس از بررسی پرونده"),
    "invalid_role_refs": ("critical", "ارجاع به نقش نامعتبر", "بازبینی تخصیص نقش و حذف reference نامعتبر"),
    "orphan_sessions": ("critical", "جلسه بدون درس والد", "اتصال به درس معتبر یا حذف با تأیید"),
    "orphan_files": ("critical", "فایل بدون جلسه والد", "اتصال به جلسه معتبر یا حذف با تأیید"),
    "malformed_questions": ("warning", "رکورد سؤال ناقص", "اصلاح فیلدهای الزامی پیش از استفاده"),
    "files_missing_metadata": ("info", "فایل آموزشی با متادیتای ناقص", "تکمیل نام/نوع/توضیح"),
}


def _quality_simple_query(kind: str):
    return {
        "users_missing_intake": (db.users, {"approved": True, "$or": [
            {"intake": {"$exists": False}}, {"intake": None}, {"intake": ""}]}),
        "malformed_questions": (db.questions, {"$or": [
            {"question": {"$exists": False}}, {"question": ""},
            {"lesson": {"$exists": False}}, {"lesson": ""},
            {"options": {"$exists": False}}, {"options.1": {"$exists": False}},
            {"correct_answer": {"$exists": False}}]}),
        "files_missing_metadata": (db.bs_content, {"$or": [
            {"type": {"$exists": False}}, {"type": ""},
            {"description": {"$exists": False}}, {"description": ""}]}),
    }.get(kind)


async def _quality_invalid_roles(skip=0, limit=30, count_only=False):
    valid = [role.get("_id") for role in await db.list_roles() if role.get("_id")]
    pipeline = [
        {"$unwind": "$roles"}, {"$match": {"roles": {"$nin": valid}}},
        {"$group": {"_id": "$_id", "invalid": {"$addToSet": "$roles"}}},
    ]
    if count_only:
        pipeline.append({"$count": "count"})
        return await db.user_roles.aggregate(pipeline).to_list(1)
    pipeline.extend([{"$sort": {"_id": 1}}, {"$skip": skip}, {"$limit": limit}])
    return await db.user_roles.aggregate(pipeline).to_list(limit)


async def _quality_orphans(child, parent, parent_field: str, skip=0, limit=30, count_only=False):
    pipeline = [
        {"$addFields": {"_parent_oid": {"$convert": {
            "input": f"${parent_field}", "to": "objectId", "onError": None, "onNull": None}}}},
        {"$lookup": {"from": parent.name, "localField": "_parent_oid", "foreignField": "_id", "as": "_parent"}},
        {"$match": {"_parent.0": {"$exists": False}}},
    ]
    if count_only:
        pipeline.append({"$count": "count"})
        return await child.aggregate(pipeline).to_list(1)
    pipeline.extend([{"$project": {"_parent": 0, "_parent_oid": 0}}, {"$sort": {"_id": 1}},
                     {"$skip": skip}, {"$limit": limit}])
    return await child.aggregate(pipeline).to_list(limit)


async def _quality_count(kind: str):
    simple = _quality_simple_query(kind)
    if simple:
        collection, query = simple
        return await collection.count_documents(query)
    if kind == "invalid_role_refs":
        rows = await _quality_invalid_roles(count_only=True)
    elif kind == "orphan_sessions":
        rows = await _quality_orphans(db.bs_sessions, db.bs_lessons, "lesson_id", count_only=True)
    elif kind == "orphan_files":
        rows = await _quality_orphans(db.bs_content, db.bs_sessions, "session_id", count_only=True)
    else:
        return 0
    return int(rows[0].get("count") or 0) if rows else 0


@router.get("/operations/data-quality")
async def wa_data_quality(user=Depends(_perm("system.manage"))):
    kinds = list(_QUALITY_META)
    values = await asyncio.gather(*(_quality_count(kind) for kind in kinds), return_exceptions=True)
    items = []
    for kind, value in zip(kinds, values):
        severity, label, suggestion = _QUALITY_META[kind]
        items.append({"kind": kind, "severity": severity, "label": label,
                      "suggestion": suggestion,
                      "count": None if isinstance(value, Exception) else int(value or 0),
                      "available": not isinstance(value, Exception)})
    return {"items": items, "checked_at": _now(), "read_only": True}


@router.get("/operations/data-quality/{kind}")
async def wa_data_quality_items(
    kind: str, skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
    user=Depends(_perm("system.manage")),
):
    if kind not in _QUALITY_META:
        raise HTTPException(404, "نوع بررسی کیفیت داده پیدا نشد")
    total = await _quality_count(kind)
    simple = _quality_simple_query(kind)
    if simple:
        collection, query = simple
        docs = await collection.find(query).sort("_id", 1).skip(skip).limit(limit).to_list(limit)
    elif kind == "invalid_role_refs":
        docs = await _quality_invalid_roles(skip, limit)
    elif kind == "orphan_sessions":
        docs = await _quality_orphans(db.bs_sessions, db.bs_lessons, "lesson_id", skip, limit)
    else:
        docs = await _quality_orphans(db.bs_content, db.bs_sessions, "session_id", skip, limit)
    severity, label, suggestion = _QUALITY_META[kind]
    def shape(doc):
        return {"id": str(doc.get("_id", "")),
                "label": doc.get("name") or doc.get("question") or doc.get("topic") or doc.get("description") or str(doc.get("_id", "")),
                "reason": label, "severity": severity, "suggestion": suggestion,
                "metadata": {key: doc.get(key) for key in
                             ("user_id", "intake", "lesson_id", "session_id", "roles", "invalid", "type", "source")
                             if doc.get(key) is not None}}
    return {"items": [shape(doc) for doc in docs], "total": total, "skip": skip, "limit": limit,
            "read_only": True}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.5 — جست‌وجوی سراسری سریع (Command Palette)
# ══════════════════════════════════════════════════════════════════

@router.get("/search")
async def global_quick_search(q: str = Query(..., min_length=2, max_length=80),
                              user=Depends(_guard_any_admin)):
    """جست‌وجوی سراسری permission-aware در موجودیت‌های واقعی سامانه."""
    query = " ".join(q.split())[:80]
    rx = {"$regex": re.escape(query), "$options": "i"}
    uid = user["id"]
    perms = await db.get_user_perms(uid)
    allow = lambda *keys: uid == ADMIN_ID or any(k in perms for k in keys)
    res = {"users": [], "tickets": [], "questions": [], "content": [],
           "exams": [], "grades": [], "roles": [], "broadcasts": [],
           "payments": [], "subscriptions": [], "notifications": [], "audit": []}

    if allow("users.view", "users.manage"):
        try:
            us = await db.users.find(db.build_user_search_query(query)).sort("registered_at", -1).limit(6).to_list(6)
            res["users"] = [{"id": u.get("user_id"), "name": u.get("name", ""),
                "student_id": u.get("student_id", ""), "intake": u.get("intake", ""),
                "username": u.get("username", "")} for u in us]
        except Exception:
            pass
    if allow("tickets.reply", "tickets.manage"):
        try:
            ts = await db.tickets.find({"$or": [{"subject": rx}, {"user_name": rx}]}).sort("created_at", -1).limit(5).to_list(5)
            res["tickets"] = [{"id": t.get("ticket_id"), "subject": t.get("subject", ""),
                "status": t.get("status", ""), "user_name": t.get("user_name", "")} for t in ts]
        except Exception:
            pass
    if allow("questions.review", "questions.review_scoped"):
        try:
            scope = await _question_scope_context(user)
            qf = {"question": rx}
            if scope.get("kind") == "scoped": qf["intake"] = scope.get("intake") or ""
            qs = await db.questions.find(qf).sort("created_at", -1).limit(5).to_list(5)
            res["questions"] = [{"id": str(x.get("_id", "")), "text": (x.get("question", "") or "")[:90],
                "lesson": x.get("lesson", ""), "topic": x.get("topic", ""),
                "approved": bool(x.get("approved"))} for x in qs]
        except Exception:
            pass
    if allow("content.manage", "content.scoped"):
        try:
            scope = await db.get_content_scope(uid)
            intake = scope.get("intake") if scope and scope.get("kind") == "scoped" else None
            rs = await db.search_resources(query, intake=intake)
            res["content"] = [{"title": r.get("title") or r.get("description") or "",
                "type": r.get("type", ""), "path": r.get("path", "")} for r in (rs or [])[:5]]
        except Exception:
            pass
    if allow("schedules.manage"):
        try:
            docs = await db.schedules.find({"type": "exam", "$or": [
                {"lesson": rx}, {"teacher": rx}, {"location": rx}]}).sort("date", -1).limit(5).to_list(5)
            res["exams"] = [{"id": str(x.get("_id", "")), "lesson": x.get("lesson", ""),
                "date": x.get("date", ""), "group": db.normalize_group(x.get("group")) or "هر دو"} for x in docs]
        except Exception:
            pass
    if allow("grades.manage", "grades.scoped"):
        try:
            gf = {"$or": [{"lesson": rx}, {"exam_title": rx}]}
            if query.isdigit(): gf["$or"].append({"student_id": int(query)})
            if await db.has_permission(uid, "grades.scoped") and not await db.has_permission(uid, "grades.manage"):
                scope = await db.get_scoped_intake(uid)
                scoped_ids = await db.users.distinct("user_id", {"intake": scope}) if scope else []
                gf["student_id"] = {"$in": scoped_ids}
            docs = await db.grades.find(gf).sort("exam_date", -1).limit(5).to_list(5)
            res["grades"] = [{"id": str(row.get("_id", "")), "student_id": row.get("student_id"),
                              "lesson": row.get("lesson", ""), "exam_title": row.get("exam_title", ""),
                              "score": row.get("score"), "exam_date": row.get("exam_date", "")} for row in docs]
        except Exception:
            pass
    if allow("roles.manage"):
        try:
            docs = await db.roles.find({"$or": [{"label": rx}, {"_id": rx}]}).sort("priority", 1).limit(5).to_list(5)
            res["roles"] = [{"id": row.get("_id"), "label": row.get("label", ""),
                             "active": row.get("active", True), "permissions": len(row.get("perms") or [])} for row in docs]
        except Exception:
            pass
    if allow("broadcast.send"):
        try:
            docs = await db.bot_notifs.find({"type": "broadcast", "text": rx}).sort("created_at", -1).limit(20).to_list(20)
            seen = set()
            for row in docs:
                key = (row.get("text", ""), row.get("created_at", ""))
                if key in seen: continue
                seen.add(key)
                res["broadcasts"].append({"id": str(row.get("_id", "")), "text": (row.get("text") or "")[:90],
                                          "created_at": row.get("created_at", ""), "correlation_id": row.get("correlation_id")})
                if len(res["broadcasts"]) >= 5: break
        except Exception:
            pass
    if allow("subscription.manage"):
        try:
            pays = await db.sub_payments.find({"$or": [{"plan_name": rx}, {"discount_code": rx}]}).sort("submitted_at", -1).limit(5).to_list(5)
            res["payments"] = [{"id": str(x.get("_id", "")), "user_id": x.get("user_id"),
                "plan": x.get("plan_name", ""), "status": x.get("status", ""),
                "amount": x.get("final_price", x.get("price", 0))} for x in pays]
            subs = await db.subscriptions.find({"plan_name": rx}).sort("end_date", -1).limit(5).to_list(5)
            res["subscriptions"] = [{"user_id": x.get("_id"), "plan": x.get("plan_name", ""),
                "status": x.get("status", ""), "end_date": x.get("end_date", "")} for x in subs]
        except Exception:
            pass
    if allow("notifications.manage", "broadcast.send"):
        try:
            notes = await db.bot_notifs.find({"text": rx}).sort("created_at", -1).limit(5).to_list(5)
            res["notifications"] = [{"id": str(x.get("_id", "")), "type": x.get("type", ""),
                "text": (x.get("text", "") or "")[:90], "sent": bool(x.get("sent"))} for x in notes]
        except Exception:
            pass
    if allow("audit.view"):
        try:
            al = await db.audit_logs.find({"$or": [{"action": rx}, {"actor.name": rx},
                {"target.label": rx}]}).sort("timestamp", -1).limit(5).to_list(5)
            res["audit"] = [{"id": str(a.get("_id", "")), "action": a.get("action", ""),
                "actor": (a.get("actor") or {}).get("name", ""),
                "at": (a.get("timestamp") or "")[:16].replace("T", " ")} for a in al]
        except Exception:
            pass
    return {"q": query, **res}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.4 — فیلترهای ذخیره‌شده + اکشن گروهی تیکت/سؤال
# ══════════════════════════════════════════════════════════════════

SAVED_VIEW_SCOPE_PERMS = {
    "users": ("users.view", "users.manage"),
    "questions": ("questions.review", "questions.review_scoped"),
    "content": ("content.manage", "content.scoped"),
    "audit": ("audit.view",), "payments": ("subscription.manage",),
    "subscriptions": ("subscription.manage",),
    "tickets": ("tickets.reply", "tickets.manage"),
    "reports": ("reports.review",), "grades": ("grades.manage", "grades.scoped"),
    "broadcast_segment": ("broadcast.send",), "broadcast_draft": ("broadcast.send",),
    "exams": ("schedules.manage",),
}


async def _saved_view_scope_allowed(user: dict, scope: str) -> bool:
    if scope not in SAVED_VIEW_SCOPE_PERMS:
        return False
    if user["id"] == ADMIN_ID:
        return True
    for permission in SAVED_VIEW_SCOPE_PERMS[scope]:
        if await db.has_permission(user["id"], permission):
            return True
    return False


class SavedFilterIn(BaseModel):
    name: str
    scope: str
    filters: dict = {}
    columns: list[str] = []
    sort: dict = {}
    shared: bool = False


class SavedFilterPatch(BaseModel):
    name: Optional[str] = None
    filters: Optional[dict] = None
    columns: Optional[list[str]] = None
    sort: Optional[dict] = None
    shared: Optional[bool] = None


@router.get("/saved-filters")
async def saved_filters_list(scope: str | None = Query(None),
                             user=Depends(_guard_any_admin)):
    """Saved Views شخصی + اشتراکی، فقط در scope مجاز همان مدیر."""
    if scope and not await _saved_view_scope_allowed(user, scope):
        raise HTTPException(403, "forbidden")
    query = {"$or": [{"owner": user["id"]}, {"shared": True}]}
    if scope:
        query["scope"] = scope
    else:
        allowed_scopes = [key for key in SAVED_VIEW_SCOPE_PERMS
                          if await _saved_view_scope_allowed(user, key)]
        query["scope"] = {"$in": allowed_scopes}
    docs = await db.wa_saved_filters.find(query).sort("updated_at", -1).limit(80).to_list(80)
    owner_ids = list({d.get("owner") for d in docs if d.get("owner") is not None})
    owners = await db.users.find({"user_id": {"$in": owner_ids}}, {"user_id": 1, "name": 1}).to_list(len(owner_ids) or 1)
    owner_map = {u.get("user_id"): u.get("name", "") for u in owners}
    return {"filters": [{
        "id": str(d.get("_id", "")), "name": d.get("name", ""),
        "scope": d.get("scope", ""), "filters": d.get("filters") or {},
        "columns": d.get("columns") or [], "sort": d.get("sort") or {},
        "shared": bool(d.get("shared")), "owner": d.get("owner"),
        "owner_name": owner_map.get(d.get("owner"), ""),
        "editable": d.get("owner") == user["id"],
        "created_at": (d.get("created_at") or "")[:16],
        "updated_at": (d.get("updated_at") or d.get("created_at") or "")[:16],
    } for d in docs if d.get("owner") == user["id"] or d.get("shared")]}


@router.post("/saved-filters")
async def saved_filters_add(body: SavedFilterIn, user=Depends(_guard_any_admin)):
    name = (body.name or "").strip()[:60]
    if not name:
        raise HTTPException(422, "نام نما الزامی است")
    if not await _saved_view_scope_allowed(user, body.scope):
        raise HTTPException(403, "forbidden")
    uid = user["id"]
    if await db.wa_saved_filters.count_documents({"owner": uid}) >= 50:
        raise HTTPException(422, "حداکثر ۵۰ نمای ذخیره‌شده می‌توانید داشته باشید")
    now = _now()
    doc = {"owner": uid, "name": name, "scope": body.scope,
           "filters": body.filters or {}, "columns": list(dict.fromkeys(body.columns or []))[:80],
           "sort": body.sort or {}, "shared": bool(body.shared),
           "created_at": now, "updated_at": now}
    r = await db.wa_saved_filters.insert_one(doc)
    return {"ok": True, "id": str(getattr(r, "inserted_id", "") or "")}


@router.put("/saved-filters/{fid}")
async def saved_filters_update(fid: str, body: SavedFilterPatch,
                               user=Depends(_guard_any_admin)):
    oid = _oid(fid)
    query = {"owner": user["id"], "_id": oid if oid else fid}
    old = await db.wa_saved_filters.find_one(query)
    if not old:
        raise HTTPException(404, "نمای ذخیره‌شده پیدا نشد")
    if not await _saved_view_scope_allowed(user, old.get("scope", "")):
        raise HTTPException(403, "forbidden")
    changes = {}
    if body.name is not None:
        name = body.name.strip()[:60]
        if not name: raise HTTPException(422, "نام نما الزامی است")
        changes["name"] = name
    if body.filters is not None: changes["filters"] = body.filters
    if body.columns is not None: changes["columns"] = list(dict.fromkeys(body.columns))[:80]
    if body.sort is not None: changes["sort"] = body.sort
    if body.shared is not None: changes["shared"] = bool(body.shared)
    if not changes: raise HTTPException(422, "تغییری ارسال نشده است")
    changes["updated_at"] = _now()
    await db.wa_saved_filters.update_one(query, {"$set": changes})
    return {"ok": True, "changed": list(changes)}


@router.delete("/saved-filters/{fid}")
async def saved_filters_del(fid: str, user=Depends(_guard_any_admin)):
    """فقط صاحب فیلتر می‌تواند آن را حذف کند."""
    oid = _oid(fid)
    q = {"owner": user["id"]}
    if oid:
        q["_id"] = oid
    else:
        q["_id"] = fid
    r = await db.wa_saved_filters.delete_many(q)
    if not getattr(r, "deleted_count", 0):
        raise HTTPException(404, "فیلتر یافت نشد")
    return {"ok": True}


async def _require_object_permission(user: dict, target_type: str):
    perm_map = {
        "user": ("users.view", "users.manage"), "question": ("questions.review", "questions.review_scoped"),
        "ticket": ("tickets.reply", "tickets.manage"), "payment": ("subscription.manage",),
        "subscription": ("subscription.manage",), "role": ("roles.manage",),
        "notification": ("notifications.manage",), "broadcast": ("broadcast.send",),
        "setting": ("settings.manage",), "exam": ("schedules.manage",), "grade": ("grades.manage", "grades.scoped"),
    }
    required = perm_map.get(target_type)
    if not required: raise HTTPException(422, "نوع object پشتیبانی نمی‌شود")
    if user["id"] == ADMIN_ID: return
    if not any([await db.has_permission(user["id"], permission) for permission in required]):
        raise HTTPException(403, "forbidden")


@router.get("/objects/{target_type}/{target_id}")
async def wa_object_summary(target_type: str, target_id: str, user=Depends(_guard_any_admin)):
    """Universal object summary: identity/status/metadata/relations از persisted data."""
    await _require_object_permission(user, target_type)
    relations, actions = [], []
    if target_type == "user":
        if not target_id.isdigit(): raise HTTPException(422, "شناسه کاربر نامعتبر است")
        doc = await db.get_user(int(target_id))
        if not doc: raise HTTPException(404, "کاربر پیدا نشد")
        identity = {"id": doc.get("user_id"), "label": db.display_name_of(doc), "type": "user"}
        status = "suspended" if doc.get("suspended") else "active" if doc.get("approved") else "pending"
        metadata = {key: doc.get(key) for key in ("username", "student_id", "intake", "group", "registered_at", "last_active")}
        ticket_count, question_count = await asyncio.gather(
            db.tickets.count_documents({"user_id": int(target_id)}),
            db.questions.count_documents({"creator_id": int(target_id)}))
        relations = [{"type": "ticket", "label": "تیکت‌ها", "count": ticket_count, "go": f"/tickets?q={target_id}"},
                     {"type": "question", "label": "سؤال‌های طراحی‌شده", "count": question_count, "go": f"/questions?author={target_id}"}]
        actions = ["edit", "message"]
    elif target_type == "question":
        doc = await db.get_question_by_id(target_id)
        if not doc: raise HTTPException(404, "سؤال پیدا نشد")
        scope = await _question_scope_context(user)
        if scope.get("kind") == "scoped" and (doc.get("intake") or "") != (scope.get("intake") or ""):
            raise HTTPException(403, "intake_out_of_scope")
        identity = {"id": target_id, "label": (doc.get("question") or "")[:120], "type": "question"}
        status = "approved" if doc.get("approved") else "pending"
        metadata = {key: doc.get(key) for key in ("lesson", "topic", "difficulty", "source", "intake", "attempt_count", "correct_count", "report_count")}
        if doc.get("creator_id"):
            relations.append({"type": "user", "label": doc.get("creator_name") or "طراح", "id": doc.get("creator_id"), "go": f"/users?q={doc.get('creator_id')}"})
        actions = [] if doc.get("approved") else ["edit", "approve", "reject"]
    elif target_type == "ticket":
        if not target_id.isdigit(): raise HTTPException(422, "شناسه تیکت نامعتبر است")
        doc = await db.ticket_get(int(target_id))
        if not doc: raise HTTPException(404, "تیکت پیدا نشد")
        identity = {"id": int(target_id), "label": doc.get("subject") or f"تیکت {target_id}", "type": "ticket"}
        status = doc.get("status", "open")
        metadata = {key: doc.get(key) for key in ("priority", "assignee_name", "created_at", "last_reply_at", "tags")}
        if doc.get("user_id"):
            relations.append({"type": "user", "label": doc.get("user_name") or "کاربر", "id": doc.get("user_id"), "go": f"/users?q={doc.get('user_id')}"})
        actions = ["reply", "close"] if status != "closed" else ["reopen"]
    elif target_type == "role":
        doc = await db.get_role(target_id)
        if not doc: raise HTTPException(404, "نقش پیدا نشد")
        identity = {"id": target_id, "label": doc.get("label") or target_id, "type": "role"}
        status = "active" if doc.get("active", True) else "disabled"
        metadata = {"description": doc.get("description") or doc.get("desc"), "permissions": doc.get("perms") or [], "system": bool(doc.get("system"))}
        relations = [{"type": "user", "label": "اعضای نقش", "count": len(await db.user_ids_by_role(target_id, limit=100000)), "go": f"/users?role={target_id}"}]
        actions = [] if doc.get("system") else ["edit", "clone", "toggle", "delete"]
    elif target_type in ("payment", "subscription"):
        uid = int(target_id) if target_id.isdigit() else None
        if target_type == "payment":
            oid = _oid(target_id); doc = await db.sub_payments.find_one({"_id": oid if oid else target_id})
            uid = (doc or {}).get("user_id")
        else:
            doc = await db.sub_get(uid) if uid is not None else None
        if not doc: raise HTTPException(404, "رکورد اشتراک پیدا نشد")
        identity = {"id": target_id, "label": doc.get("plan_name") or f"اشتراک {target_id}", "type": target_type}
        status = doc.get("status", "")
        metadata = {key: doc.get(key) for key in ("amount", "final_price", "submitted_at", "start_date", "end_date", "discount_code")}
        if uid is not None: relations.append({"type": "user", "label": "دارنده", "id": uid, "go": f"/users?q={uid}"})
        actions = ["approve", "reject"] if target_type == "payment" and status == "pending" else []
    else:
        raise HTTPException(422, "خلاصه این نوع object هنوز پشتیبانی نمی‌شود")
    return {"identity": identity, "status": status, "metadata": metadata,
            "relations": relations, "available_actions": actions}


@router.get("/audit/correlation/{correlation_id}")
async def wa_correlation_chain(correlation_id: str, user=Depends(_perm("audit.view"))):
    correlation_id = correlation_id.strip()[:120]
    if not correlation_id: raise HTTPException(422, "Correlation ID الزامی است")
    audits, outbox = await asyncio.gather(
        db.audit_logs.find({"correlation_id": correlation_id}).sort("timestamp", 1).limit(100).to_list(100),
        db.bot_notifs.find({"correlation_id": correlation_id}).sort("created_at", 1).limit(100).to_list(100),
    )
    events = [{"id": f"audit:{row.get('_id')}", "stage": "audit", "title": row.get("action") or "Audit",
               "status": row.get("severity", "INFO"), "at": row.get("timestamp"),
               "metadata": {"module": row.get("module"), "target": row.get("target") or {}}} for row in audits]
    events.extend({"id": f"outbox:{row.get('_id')}", "stage": "outbox",
                   "title": row.get("type") or "Outbox",
                   "status": "failed" if row.get("failed") else "sent" if row.get("sent") else "scheduled" if row.get("send_at") else "queued",
                   "at": row.get("sent_at") or row.get("created_at"),
                   "metadata": {"chat_id": row.get("chat_id"), "send_at": row.get("send_at")}}
                  for row in outbox)
    events.sort(key=lambda event: event.get("at") or "")
    return {"correlation_id": correlation_id, "events": events,
            "counts": {"audit": len(audits), "outbox": len(outbox)},
            "complete": bool(events)}


@router.get("/history/{target_type}/{target_id}")
async def object_history(
    target_type: str, target_id: str,
    limit: int = Query(30, ge=1, le=100),
    user=Depends(_guard_any_admin),
):
    """Timeline/diff عمومی objectها بر پایه audit مشترک، با RBAC هر domain."""
    await _require_object_permission(user, target_type)
    if target_type == "question":
        item = await db.get_question_by_id(target_id)
        if not item:
            raise HTTPException(404, "سؤال پیدا نشد")
        scope = await _question_scope_context(user)
        if scope.get("kind") == "scoped" and (item.get("intake") or "") != (scope.get("intake") or ""):
            raise HTTPException(403, "intake_out_of_scope")
    elif target_type == "user" and (not target_id.isdigit() or not await db.get_user(int(target_id))):
        raise HTTPException(404, "کاربر پیدا نشد")
    elif target_type == "ticket" and (not target_id.isdigit() or not await db.ticket_get(int(target_id))):
        raise HTTPException(404, "تیکت پیدا نشد")
    docs = await db.audit_logs.find({"$or": [
        {"target.type": target_type, "target.id": target_id},
        {"target_type": target_type, "target_id": target_id},
    ]}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"items": [{
        "id": str(d.get("_id", "")), "title": d.get("action", ""),
        "actor": (d.get("actor") or {}).get("name", ""),
        "actor_role": (d.get("actor") or {}).get("role", ""),
        "at": (d.get("timestamp") or "")[:16].replace("T", " "),
        "description": d.get("details", ""), "severity": d.get("severity", "INFO"),
        "changes": d.get("changes") or [], "correlation_id": d.get("correlation_id"),
    } for d in docs], "target_type": target_type, "target_id": target_id}


class TicketsBulk(BaseModel):
    action: str           # close | reopen
    ids: list[int]


@router.post("/tickets/bulk")
async def tickets_bulk(body: TicketsBulk, user=Depends(_perm("tickets.manage"))):
    """⚡ اکشن گروهی تیکت (سقف ۱۰۰) — با همان متدهای موجود db."""
    ids = [int(i) for i in (body.ids or []) if isinstance(i, (int, str)) and str(i).isdigit()][:100]
    if not ids:
        raise HTTPException(400, "لیست تیکت‌ها خالی است")
    if body.action not in ("close", "reopen"):
        raise HTTPException(422, "اکشن گروهی نامعتبر است")
    succeeded, skipped, failed = [], [], []
    for tid in ids:
        try:
            t = await db.ticket_get(tid)
            if not t:
                skipped.append({"id": tid, "reason": "ticket_not_found"}); continue
            if body.action == "close":
                if t.get("status") == "closed":
                    skipped.append({"id": tid, "reason": "already_closed"}); continue
                await db.ticket_close(tid)
            else:
                if t.get("status") != "closed":
                    skipped.append({"id": tid, "reason": "already_open"}); continue
                await db.ticket_reopen(tid)
            succeeded.append(tid)
        except Exception:
            failed.append({"id": tid, "error": "operation_failed"})
    fa = {"close": "بستن گروهی", "reopen": "بازگشایی گروهی"}
    await _audit(user["id"], f"{fa[body.action]} تیکت ({len(succeeded)} مورد)",
                 severity="INFO", target_type="ticket_batch", target_label=f"{len(ids)} تیکت",
                 after={"action": body.action, "succeeded": len(succeeded),
                        "skipped": len(skipped), "failed": len(failed)},
                 tags=["bulk_tickets", "پنل_وب"])
    return {"ok": not failed, "done": len(succeeded), "succeeded": succeeded,
            "skipped": skipped, "failed": failed}


async def _question_scope_context(user: dict) -> dict:
    """Scope مستقل مجوز بازبینی سؤال؛ به content.manage وابسته نیست."""
    if await db.has_permission(user["id"], "questions.review"):
        return {"kind": "global", "intake": None}
    if await db.has_permission(user["id"], "questions.review_scoped"):
        scope = await db.get_scoped_intake(user["id"])
        if not scope:
            info = await db.get_user_roles(user["id"])
            scope = info.get("scope_intake")
        if scope:
            return {"kind": "scoped", "intake": scope}
    raise HTTPException(403, "question_scope_missing")


async def _question_admin(user: dict) -> dict:
    ctx = dict(user)
    ctx["_scope"] = await _question_scope_context(user)
    return ctx


@router.get("/questions")
async def wa_questions_list(
    status: str = Query("pending", pattern="^(pending|approved|all)$"),
    intake: Optional[str] = Query(None, max_length=80),
    q: Optional[str] = Query(None, max_length=120),
    lesson: Optional[str] = Query(None, max_length=100),
    topic: Optional[str] = Query(None, max_length=100),
    difficulty: Optional[str] = Query(None, pattern="^(easy|medium|hard)$"),
    source: Optional[str] = Query(None, max_length=40),
    author: Optional[str] = Query(None, max_length=100),
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
    sort_by: str = Query("created_at", pattern="^(created_at|attempt_count|correct_count|difficulty)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    """Question workspace سرورساید برای 10k+ سؤال، بدون تغییر endpoint قدیمی pending."""
    author = author if isinstance(author, str) else None
    date_from = date_from if isinstance(date_from, str) else None
    date_to = date_to if isinstance(date_to, str) else None
    scope = await _question_scope_context(user)
    if scope.get("kind") == "scoped":
        iv = scope.get("intake") or ""
        if intake not in (None, "", iv):
            raise HTTPException(403, "intake_out_of_scope")
    else:
        iv = intake or ""
    filt = {"intake": iv}
    if status == "pending":
        filt["approved"] = False
    elif status == "approved":
        filt["approved"] = True
    if lesson:
        filt["lesson"] = lesson
    if topic:
        filt["topic"] = topic
    if difficulty:
        filt["difficulty"] = difficulty
    if source:
        filt["source"] = source
    if author and author.strip():
        author_value = author.strip()
        if author_value.isdigit():
            filt["creator_id"] = int(author_value)
        else:
            filt["creator_name"] = {"$regex": re.escape(author_value), "$options": "i"}
    if date_from or date_to:
        created = {}
        if date_from: created["$gte"] = date_from[:10]
        if date_to: created["$lte"] = date_to[:10] + "T23:59:59.999999"
        filt["created_at"] = created
    if q and q.strip():
        term = q.strip()
        rx = {"$regex": re.escape(term), "$options": "i"}
        options = [{"question": rx}, {"lesson": rx}, {"topic": rx}, {"creator_name": rx}]
        oid = _oid(term)
        if oid: options.append({"_id": oid})
        filt["$or"] = options
    total = await db.questions.count_documents(filt)
    docs = await (db.questions.find(filt)
                  .sort(sort_by, 1 if sort_dir == "asc" else -1)
                  .skip(skip).limit(limit).to_list(limit))
    rows = []
    for d in docs:
        attempts = int(d.get("attempt_count") or 0)
        correct = int(d.get("correct_count") or 0)
        rows.append({
            "id": str(d.get("_id", "")), "lesson": d.get("lesson", ""),
            "topic": d.get("topic", ""), "difficulty": d.get("difficulty", ""),
            "question": d.get("question", ""), "options": d.get("options", []),
            "correct": d.get("correct_answer", 0), "explanation": d.get("explanation", ""),
            "creator_id": d.get("creator_id"), "creator_name": d.get("creator_name", ""),
            "created_at": (d.get("created_at") or "")[:16], "updated_at": (d.get("updated_at") or "")[:16],
            "intake": d.get("intake", ""), "source": d.get("source", "bot"),
            "approved": bool(d.get("approved")), "attempts": attempts,
            "accuracy": round(correct * 100 / attempts, 1) if attempts else 0,
            "reports": int(d.get("report_count") or 0),
        })
    return {"questions": rows, "total": total, "skip": skip, "limit": limit,
            "pages": (total + limit - 1) // limit, "status": status, "intake": iv}


@router.get("/exports/questions.csv")
async def export_questions_csv(
    status: str = Query("pending", pattern="^(pending|approved|all)$"),
    intake: Optional[str] = Query(None), q: Optional[str] = Query(None),
    lesson: Optional[str] = Query(None), topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None), source: Optional[str] = Query(None),
    author: Optional[str] = Query(None), date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at|attempt_count|correct_count|difficulty)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    """خروجی سؤال با همان scope/filter/sort جدول؛ داده در مرورگر تجمیع نمی‌شود."""
    await _audit(user["id"], "خروجی CSV سؤال‌ها", severity="HIGH",
                 target_type="export", target_label="questions.csv",
                 tags=["خروجی", "سؤال", "پنل_وب"])
    columns = ["id", "question", "lesson", "topic", "difficulty", "status", "intake",
               "creator_id", "creator_name", "source", "attempts", "accuracy", "created_at"]
    def safe(value):
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text
    async def stream():
        buf = io.StringIO(); writer = csv.writer(buf); writer.writerow(columns)
        yield "\ufeff" + buf.getvalue(); buf.seek(0); buf.truncate(0)
        skip = 0
        while True:
            result = await wa_questions_list(
                status=status, intake=intake, q=q, lesson=lesson, topic=topic,
                difficulty=difficulty, source=source, author=author,
                date_from=date_from, date_to=date_to, skip=skip, limit=100, sort_by=sort_by, sort_dir=sort_dir, user=user)
            rows = result.get("questions") or []
            for row in rows:
                writer.writerow([safe(v) for v in [row.get("id"), row.get("question"),
                    row.get("lesson"), row.get("topic"), row.get("difficulty"),
                    "approved" if row.get("approved") else "pending", row.get("intake"),
                    row.get("creator_id"), row.get("creator_name"), row.get("source"),
                    row.get("attempts"), row.get("accuracy"), row.get("created_at")]])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
            skip += len(rows)
            if not rows or skip >= int(result.get("total") or 0): break
    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=humsyar-questions.csv"})


@router.get("/questions/intakes")
async def wa_question_intakes(
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    return await content_api.content_intakes(admin=await _question_admin(user))


@router.get("/questions/pending")
async def wa_questions_pending(
    intake: Optional[str] = Query(None),
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    return await content_api.pending_questions(
        intake=intake, admin=await _question_admin(user))


@router.post("/questions/{qid}/approve")
async def wa_question_approve(
    qid: str,
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    return await content_api.approve_question(qid=qid, admin=await _question_admin(user))


@router.post("/questions/{qid}/reject")
async def wa_question_reject(
    qid: str,
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    return await content_api.reject_question(qid=qid, admin=await _question_admin(user))


@router.patch("/questions/{qid}")
async def wa_question_patch(
    qid: str, body: content_api.QuestionPatch,
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    return await content_api.patch_question(
        qid=qid, body=body, admin=await _question_admin(user))


@router.post("/questions/bulk-import")
async def wa_questions_import(
    body: content_api.QuestionImportBody,
    intake: Optional[str] = Query(None),
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    return await content_api.bulk_import_questions(
        body=body, intake=intake, admin=await _question_admin(user))


class QuestionsBulk(BaseModel):
    action: str           # approve | reject | metadata
    ids: list[str]
    patch: Optional[dict] = None


@router.post("/questions/bulk")
async def questions_bulk(
    body: QuestionsBulk,
    user=Depends(_perm_any("questions.review", "questions.review_scoped")),
):
    """⚡ تأیید/رد گروهی سؤال‌های پیشنهادی — معناشناسی دقیقاً مثل مسیر تکی:
    approve → db.approve_question ؛ reject → db.delete_question + اطلاع به طراح (outbox)."""
    ids = [str(i) for i in (body.ids or [])][:100]
    if not ids:
        raise HTTPException(400, "لیست سؤال‌ها خالی است")
    if body.action not in ("approve", "reject", "metadata"):
        raise HTTPException(400, "اکشن نامعتبر است")
    patch_body = None
    if body.action == "metadata":
        allowed = {key: value for key, value in (body.patch or {}).items()
                   if key in ("lesson", "topic", "difficulty") and value not in (None, "")}
        if not allowed: raise HTTPException(422, "حداقل یک metadata معتبر لازم است")
        try: patch_body = content_api.QuestionPatch(**allowed)
        except Exception: raise HTTPException(422, "metadata سؤال معتبر نیست")
    succeeded, skipped, failed = [], [], []
    scope = await _question_scope_context(user)
    question_admin = dict(user); question_admin["_scope"] = scope
    for qid in ids:
        try:
            q = await db.get_question_by_id(qid)
            if not q:
                skipped.append({"id": qid, "reason": "question_not_found"}); continue
            if q.get("approved"):
                skipped.append({"id": qid, "reason": "already_approved"}); continue
            # scope مستقل permission سؤال؛ نقش سفارشی مجبور به content.manage نیست.
            if (scope.get("kind") == "scoped"
                    and (q.get("intake") or "") != (scope.get("intake") or "")):
                skipped.append({"id": qid, "reason": "intake_out_of_scope"}); continue
            if body.action == "approve":
                # approve_question منبع واحد پاداش + اعلان طراح است.
                await db.approve_question(qid)
            elif body.action == "metadata":
                await content_api.patch_question(qid=qid, body=patch_body, admin=question_admin)
            else:
                await db.delete_question(qid)
                if q.get("source") == "webapp" and q.get("creator_id"):
                    await db.notify_user(
                        q["creator_id"], "question_rejected",
                        title="❌ سؤالت رد شد",
                        body=f"📚 {q.get('lesson','')} — {q.get('topic','')}",
                        link="/learn/my-questions",
                        dm=(f"❌ <b>سؤالت رد شد</b>\n\n"
                            f"📚 {q.get('lesson','')} — {q.get('topic','')}"),
                    )
            succeeded.append(qid)
        except Exception:
            failed.append({"id": qid, "error": "operation_failed"})
    fa = {"approve": "تأیید گروهی", "reject": "رد گروهی", "metadata": "ویرایش گروهی metadata"}
    await _audit(user["id"], f"{fa[body.action]} سؤال‌ها ({len(succeeded)} مورد)",
                 severity="INFO", target_type="question_batch", target_label=f"{len(ids)} سؤال",
                 after={"action": body.action, "requested": len(ids),
                        "patch_fields": list((body.patch or {}).keys()) if body.action == "metadata" else [],
                        "succeeded": len(succeeded), "skipped": len(skipped), "failed": len(failed)},
                 tags=["bulk_questions", "پنل_وب"])
    return {"ok": not failed, "done": len(succeeded), "succeeded": succeeded,
            "skipped": skipped, "failed": failed}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.3 — مرکز کنترل تنظیمات (+ Last-Modified-By/At)
# ══════════════════════════════════════════════════════════════════

# (key, label, توضیح, نوع, perm, severity-لاگ)
_SETTINGS_CATALOG = [
    ("general", [
        ("maintenance_mode", "حالت تعمیر و نگهداشت",
         "وقتی روشن است، ربات برای کاربران عادی پیام تعمیرات نشان می‌دهد",
         "bool", "settings.manage", "CRITICAL"),
        ("maintenance_text", "متن حالت تعمیر",
         "متن نمایشی به کاربران هنگام حالت تعمیر (حداکثر ۴۰۰ کاراکتر)",
         "text", "settings.manage", "HIGH"),
        ("require_student_id", "الزام شماره دانشجویی",
         "ثبت‌نام بدون شماره دانشجویی ممکن نمی‌شود",
         "bool", "settings.manage", "HIGH"),
    ]),
    ("logs", [
        ("log_group_admin", "گروه لاگ مدیریت",
         "آیدی عددی گروه تلگرام لاگ‌های مدیریتی (عدد منفی؛ خالی=حذف)",
         "group", "settings.manage", "HIGH"),
        ("log_group_content", "گروه لاگ محتوا",
         "آیدی عددی گروه تلگرام لاگ‌های محتوایی (عدد منفی؛ خالی=حذف)",
         "group", "settings.manage", "HIGH"),
    ]),
    ("donation", [
        ("donation_enabled", "بخش حمایت مالی",
         "نمایش دکمه‌ی حمایت مالی در ربات/مینی‌اپ",
         "bool", "settings.manage", "HIGH"),
        ("donation_link", "لینک حمایت مالی",
         "آدرس صفحه‌ی حمایت (با http/https؛ خالی=حذف)",
         "link", "settings.manage", "HIGH"),
    ]),
    ("backup", [
        ("auto_backup_enabled", "بکاپ خودکار روزانه",
         "هر روز در ساعت مشخص‌شده نسخه‌ی پشتیبان ساخته می‌شود",
         "bool", "backup.manage", "HIGH"),
        ("auto_backup_hour", "ساعت بکاپ خودکار",
         "ساعت اجرا به‌وقت تهران (۰ تا ۲۳)",
         "hour", "backup.manage", "HIGH"),
        ("auto_backup_last_run", "آخرین اجرای بکاپ",
         "فقط نمایشی — توسط جاب بکاپ به‌روزرسانی می‌شود",
         "readonly", "backup.manage", "INFO"),
    ]),
]


@router.get("/settings/center")
async def settings_center(
    user=Depends(_perm_any("settings.manage", "notifications.manage", "backup.manage")),
):
    """⚙️ نمای دسته‌بندی‌شده‌ی تنظیمات + متا (آخرین تغییردهنده/زمان)."""
    meta_docs = await db.settings_meta.find({}).to_list(200)
    meta = {str(m.get("_id")): m for m in meta_docs}
    notif_defaults = await db.get_notif_defaults()

    cats = []
    for cat_key, rows in _SETTINGS_CATALOG:
        items = []
        for key, label, desc, typ, perm, sev in rows:
            if not await db.has_permission(user["id"], perm):
                continue
            val = await db.get_setting(key, None)
            m = meta.get(key) or {}
            items.append({
                "key": key, "label": label, "desc": desc, "type": typ,
                "value": val,
                "updated_by": m.get("by_name", ""), "updated_at": m.get("at", "")[:16],
            })
        if items:
            cats.append({"key": cat_key, "items": items})

    # 🔔 پیش‌فرض اعلان‌ها — همان کلیدهای get_notif_defaults (بدون توقف ربات)
    notif_items = []
    notif_labels = {}
    try:
        for row in db.NOTIF_CATALOG:
            notif_labels[row[0]] = row[1]
    except Exception:
        pass
    if await db.has_permission(user["id"], "notifications.manage"):
        for k in sorted(notif_defaults.keys()):
            m = meta.get(f"notif_default:{k}") or {}
            notif_items.append({
                "key": f"notif_default:{k}", "label": notif_labels.get(k, k),
                "desc": "پیش‌فرض این دسته اعلان برای کاربران جدید",
                "type": "bool", "value": bool(notif_defaults.get(k)),
                "updated_by": m.get("by_name", ""), "updated_at": m.get("at", "")[:16],
            })
        cats.append({"key": "notif", "items": notif_items})
    return {"categories": cats}


class SettingPatch(BaseModel):
    value: object = None


@router.patch("/settings/center/{key}")
async def settings_center_patch(key: str, body: SettingPatch,
                                user=Depends(_guard_any_admin)):
    """✏️ تغییر یک تنظیم — همان کنوانسیون مقداردهی پنل وب موجود + متا + audit.
    مقادیر با همان کلیدهای bot_settings نوشته می‌شوند ⇒ ربات/مینی‌اپ بی‌وقفه
    همان رفتار قبلی را می‌خوانند."""
    uid = user["id"]
    is_notif = key.startswith("notif_default:")
    need = "notifications.manage" if is_notif else None
    if not is_notif:
        row = next((r for _, rows in _SETTINGS_CATALOG for r in rows if r[0] == key), None)
        if not row:
            raise HTTPException(404, "تنظیم ناشناخته")
        if row[3] == "readonly":
            raise HTTPException(422, "این تنظیم فقط‌خواندنی است")
        need = row[4]
    if not await db.has_permission(uid, need):
        raise HTTPException(403, "forbidden")

    val = body.value
    if is_notif:
        ntype = key.split(":", 1)[1]
        try:
            known = {r[0] for r in db.NOTIF_CATALOG}
            if ntype not in known:
                raise HTTPException(404, "دسته‌ی اعلان ناشناخته")
        except HTTPException:
            raise
        except Exception:
            pass
        old = bool((await db.get_notif_defaults()).get(ntype))
        await db.set_notif_default(ntype, bool(val))
        label = ntype
        sev = "INFO"
        before, after = old, bool(val)
    else:
        _, label, _desc, typ, _perm_key, sev = row
        old = await db.get_setting(key, None)
        if typ == "bool":
            val = bool(val)
        elif typ == "text":
            val = str(val or "").strip()
            if len(val) > 400:
                raise HTTPException(422, "متن نباید بیشتر از ۴۰۰ کاراکتر باشد")
        elif typ == "group":
            if val in (None, ""):
                val = None
            else:
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(422, "آیدی گروه باید عدد باشد")
                if val >= 0:
                    raise HTTPException(422, "آیدی گروه باید عدد منفی باشد (مثل -1001234567890)")
        elif typ == "link":
            val = (str(val or "").strip()) or None
            if val and not (val.startswith("http://") or val.startswith("https://")):
                raise HTTPException(422, "لینک باید با http:// یا https:// شروع شود")
            if val and len(val) > 300:
                raise HTTPException(422, "لینک نباید بیشتر از ۳۰۰ کاراکتر باشد")
        elif typ == "hour":
            try:
                val = int(val)
            except (TypeError, ValueError):
                raise HTTPException(422, "ساعت باید عدد باشد")
            if not 0 <= val <= 23:
                raise HTTPException(422, "ساعت بکاپ باید بین ۰ تا ۲۳ باشد")
        await db.set_setting(key, val)
        before, after = old, val

    # متا: آخرین تغییردهنده/زمان (Last Modified By/At)
    udb = user.get("_db") or {}
    await db.settings_meta.update_one(
        {"_id": key},
        {"$set": {"by": uid, "by_name": udb.get("name", str(uid)), "at": _now()}},
        upsert=True)
    await _audit(uid, f"تغییر تنظیم «{label}»", severity=sev if not is_notif else "INFO",
                 before={label: before}, after={label: after},
                 tags=["تنظیمات", "پنل_وب", f"setting:{key}"])
    return {"ok": True, "key": key, "before": before, "after": after}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.2 — مدیریت آزمون‌ها (schedules type=exam + آمار exam_sessions)
# ══════════════════════════════════════════════════════════════════

def _exam_status(doc: dict) -> str:
    """scheduled | active | finished — مشتق از date/time (میلادی ISO همان سیستم)."""
    try:
        d = date.fromisoformat((doc.get("date") or "")[:10])
    except Exception:
        return "scheduled"
    today = date.today()
    if d > today:
        return "scheduled"
    if d == today:
        return "active"
    return "finished"


_STATUS_FA = {"scheduled": "زمان‌بندی‌شده", "active": "در حال برگزاری", "finished": "برگزارشده"}


def _exam_row(doc: dict) -> dict:
    st = _exam_status(doc)
    return {
        "id": str(doc.get("_id", "")),
        "lesson": doc.get("lesson", ""), "teacher": doc.get("teacher", ""),
        "date": doc.get("date", ""), "time": doc.get("time", ""),
        "location": doc.get("location", ""), "notes": doc.get("notes", ""),
        "group": db.normalize_group(doc.get("group", "هر دو")) or "هر دو",
        "status": st, "status_fa": _STATUS_FA[st],
        "reminded": doc.get("notified_days") or [],
    }


@router.get("/exams")
async def exams_list(status: str | None = Query(None),
                     user=Depends(_perm("schedules.manage"))):
    """📝 لیست آزمون‌ها (type='exam' در schedules) + وضعیت مشتق‌شده."""
    docs = await db.schedules.find({"type": "exam"}).sort("date", -1).to_list(200)
    rows = [_exam_row(d) for d in docs]
    if status in _STATUS_FA:
        rows = [r for r in rows if r["status"] == status]
    counts = {k: 0 for k in _STATUS_FA}
    for r in [_exam_row(d) for d in docs]:
        counts[r["status"]] += 1
    return {"exams": rows, "counts": counts}


class ExamIn(BaseModel):
    lesson: str
    date: str
    time: str = ""
    teacher: str = ""
    location: str = ""
    notes: str = ""
    group: str = "هر دو"


def _valid_exam_fields(body) -> tuple:
    lesson = (body.lesson or "").strip()
    if not (1 <= len(lesson) <= 80):
        raise HTTPException(422, "عنوان درس/آزمون الزامی است (حداکثر ۸۰ کاراکتر)")
    d = (body.date or "").strip()
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise HTTPException(422, "تاریخ باید به فرمت YYYY-MM-DD باشد")
    t = (body.time or "").strip()
    if t:
        try:
            datetime.strptime(t, "%H:%M")
        except (TypeError, ValueError):
            raise HTTPException(422, "ساعت باید به فرمت HH:MM باشد")
    grp = db.normalize_group(body.group or "هر دو") or "هر دو"
    if grp not in ("هر دو", "1", "2"):
        grp = "هر دو"
    return lesson, d, t, grp


@router.post("/exams")
async def exams_create(body: ExamIn, user=Depends(_perm("schedules.manage"))):
    """➕ ایجاد آزمون — دقیقاً با همان db.add_schedule(type='exam') مسیر ربات."""
    lesson, d, t, grp = _valid_exam_fields(body)
    teacher = (body.teacher or "").strip()[:80]
    location = (body.location or "").strip()[:80]
    notes = (body.notes or "").strip()[:300]
    sid = await db.add_schedule("exam", lesson, teacher, d, t, location,
                                notes=notes, group=grp)
    item = await db.get_schedule_by_id(str(sid)) or {
        "_id": sid, "type": "exam", "lesson": lesson, "teacher": teacher,
        "date": d, "time": t, "location": location, "notes": notes, "group": grp,
    }
    notice = await db.schedule_notify_event(item, "created")
    await _audit(user["id"], "ایجاد آزمون جدید", severity="INFO",
                 target_id=str(sid), target_type="exam", target_label=lesson,
                 after={"تاریخ": d, "گروه": grp,
                        "اطلاع‌رسانی": notice.get("notified", 0)},
                 tags=["امتحان", "پنل_وب"])
    return {"ok": True, "id": str(sid),
            "notified": notice.get("notified", 0)}


@router.patch("/exams/{sid}")
async def exams_update(sid: str, body: ExamIn,
                       user=Depends(_perm("schedules.manage"))):
    lesson, d, t, grp = _valid_exam_fields(body)
    old = await db.get_schedule_by_id(sid)
    if not old or old.get("type") != "exam":
        raise HTTPException(404, "آزمون یافت نشد")
    teacher = (body.teacher or "").strip()[:80]
    location = (body.location or "").strip()[:80]
    notes = (body.notes or "").strip()[:300]
    ok = await db.update_schedule_full(sid, lesson, teacher, d, t, location,
                                       notes, grp)
    if not ok:
        raise HTTPException(500, "به‌روزرسانی ناموفق بود")
    item = await db.get_schedule_by_id(sid) or {
        **old, "lesson": lesson, "teacher": teacher, "date": d, "time": t,
        "location": location, "notes": notes, "group": grp,
    }
    notice = await db.schedule_notify_event(item, "updated")
    await _audit(user["id"], "ویرایش آزمون", severity="WARNING",
                 target_id=sid, target_type="exam", target_label=lesson,
                 before={"عنوان": old.get("lesson"), "تاریخ": old.get("date"),
                         "گروه": old.get("group")},
                 after={"عنوان": lesson, "تاریخ": d, "گروه": grp,
                        "اطلاع‌رسانی": notice.get("notified", 0)},
                 tags=["امتحان", "پنل_وب"])
    return {"ok": True, "notified": notice.get("notified", 0)}


@router.delete("/exams/{sid}")
async def exams_delete(sid: str, user=Depends(_perm("schedules.manage"))):
    old = await db.get_schedule_by_id(sid)
    if not old or old.get("type") != "exam":
        raise HTTPException(404, "آزمون یافت نشد")
    await db.delete_schedule(sid)
    notice = await db.schedule_notify_event(old, "cancelled")
    await _audit(user["id"], "حذف آزمون", severity="HIGH",
                 target_id=sid, target_type="exam",
                 target_label=old.get("lesson", ""),
                 before={"تاریخ": old.get("date"), "گروه": old.get("group")},
                 after={"حذف": True, "اطلاع‌رسانی": notice.get("notified", 0)},
                 tags=["امتحان", "لغو", "پنل_وب"])
    return {"ok": True, "notified": notice.get("notified", 0)}


@router.get("/exams/stats")
async def exams_stats(user=Depends(_perm("schedules.manage"))):
    """📊 آمار آزمون‌های تمرینی (exam_sessions) — خواندنی و دفاعی."""
    out = {"total_runs": 0, "finished": 0, "avg_pct": None,
           "runs_7d": 0, "questions_total": 0}
    try:
        out["total_runs"] = await db.exam_sessions.count_documents({})
        out["finished"] = await db.exam_sessions.count_documents({"status": "finished"})
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        out["runs_7d"] = await db.exam_sessions.count_documents(
            {"started_at": {"$gte": week_ago}})
        # میانگین درصد — نمونه‌ی ۵۰۰تایی اخیر (بدون aggregate سنگین)
        rows = await db.exam_sessions.find({"status": "finished"}).limit(500).to_list(500)
        pcts = []
        for r in rows:
            tot = r.get("total") or r.get("count") or 0
            cor = r.get("correct") or 0
            if tot:
                try:
                    pcts.append(round(cor * 100.0 / tot, 1))
                except Exception:
                    pass
        if pcts:
            out["avg_pct"] = round(sum(pcts) / len(pcts), 1)
    except Exception:
        pass
    try:
        out["questions_total"] = await db.questions.count_documents({"approved": True})
    except Exception:
        pass
    return out


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.1 — Content Command Center (درخت ترم→درس→جلسه+نشان fork)
# ══════════════════════════════════════════════════════════════════

@router.get("/content/tree")
async def content_tree(intake: Optional[str] = Query(None),
                       admin=Depends(get_content_admin_user)):
    """🌳 درخت مؤثر محتوا برای یک ورودی — ۳ کوئری ثابت (بدون N+1):
    پایه‌ی سراسری + overrideهای همان ورودی، با نشان 🌐/⭐/🏷 روی هر جلسه."""
    iv = resolve_content_intake(admin, intake)  # '' یا کد ورودی (scope-enforced)
    actor_scope = admin.get("_scope") or {"kind": "global", "intake": None}
    scoped_view = actor_scope.get("kind") == "scoped"
    scope_intakes = ["", iv] if iv else [""]

    # 🌊 WA3-fix — داکیومنت‌های پیش از موج C1 ممکن است فیلد intake نداشته
    # باشند؛ با $or آن‌ها را هم می‌آوریم (معادل '' سراسری تلقی می‌شوند).
    lessons = await db.bs_lessons.find({
        "term": {"$in": TERMS},
        "$or": [{"intake": {"$in": scope_intakes}}, {"intake": {"$exists": False}},
                {"intake": None}],
    }).to_list(400)
    lesson_ids = [str(l.get("_id")) for l in lessons]
    sessions = await db.bs_sessions.find(
        {"lesson_id": {"$in": lesson_ids}}).to_list(2000) if lesson_ids else []
    if iv:
        sessions = [s for s in sessions if (s.get("intake") or "") in ("", iv)
                    or not s.get("fork_of")]
    else:
        sessions = [s for s in sessions if (s.get("intake") or "") == ""
                    and not s.get("fork_of")]
    sess_ids = [str(s.get("_id")) for s in sessions]
    counts = {}
    if sess_ids:
        for c in await db.bs_content.find(
                {"session_id": {"$in": sess_ids}}).to_list(5000):
            cid = c.get("session_id", "")
            slot = counts.setdefault(cid, {"n": 0, "types": {}})
            slot["n"] += 1
            t = c.get("type", "?")
            slot["types"][t] = slot["types"].get(t, 0) + 1

    intake_labels = {}
    try:
        for i in await db.get_all_intakes():
            if i.get("active", True):
                intake_labels[i.get("code", "")] = i.get("label", "")
    except Exception:
        pass
    if scoped_view:
        intake_labels = {iv: intake_labels.get(iv, iv)} if iv else {}

    tree = []
    for term in TERMS:
        # 🌊 WA3-fix — order/number ممکن است در داکیومنت legacy مفقود یا
        # None باشند؛ مقایسه‌ی None با int پایتون TypeError می‌دهد (ریشه‌ی 500).
        t_lessons = sorted([l for l in lessons if l.get("term") == term],
                           key=lambda x: (x.get("order") or 0))
        trow = {"term": term, "lessons": []}
        for l in t_lessons:
            lid = str(l.get("_id"))
            l_sessions = sorted([s for s in sessions if s.get("lesson_id") == lid],
                                key=lambda x: ((x.get("number") or 0), str(x.get("_id"))))
            srows = []
            for s in l_sessions:
                sid = str(s.get("_id"))
                s_intake = s.get("intake") or ""
                s_intake_effective = s_intake if s_intake else (l.get("intake") or "")
                fork_of = s.get("fork_of") or ""
                srows.append({
                    "id": sid, "number": s.get("number") or 0,
                    "topic": s.get("topic", ""), "teacher": s.get("teacher", ""),
                    "intake": s_intake_effective,
                    "intake_label": intake_labels.get(s_intake_effective, ""),
                    "kind": ("fork" if fork_of else
                             ("exclusive" if s_intake_effective else "global")),
                    "fork_of": fork_of,
                    "readonly": bool(scoped_view and s_intake_effective != iv),
                    "content_count": counts.get(sid, {}).get("n", 0),
                    "types": counts.get(sid, {}).get("types", {}),
                })
            trow["lessons"].append({
                "id": lid, "name": l.get("name", ""), "teacher": l.get("teacher", ""),
                "intake": l.get("intake") or "",
                "readonly": bool(scoped_view and (l.get("intake") or "") != iv),
                "sessions": srows, "session_count": len(srows),
                "content_count": sum(r["content_count"] for r in srows),
            })
        tree.append(trow)
    return {"intake": iv, "scope_kind": actor_scope.get("kind", "global"),
            "tree": tree,
            "intakes": [{"code": c, "label": l} for c, l in intake_labels.items()]}


async def _student_preview_context(user_id: int, admin: dict):
    target = await db.get_user(user_id)
    if not target or not target.get("approved") or target.get("suspended"):
        raise HTTPException(404, "دانشجوی فعال پیدا نشد")
    if await _has_admin_access(user_id):
        raise HTTPException(422, "برای پیش‌نمایش باید حساب دانشجو انتخاب شود")
    intake = target.get("intake") or ""
    scope = admin.get("_scope") or await db.get_content_scope(admin["id"])
    if scope and scope.get("kind") == "scoped" and intake != (scope.get("intake") or ""):
        raise HTTPException(403, "intake_out_of_scope")
    return {"id": user_id, "_db": target}, target


@router.get("/content/student-preview/students")
async def wa_student_preview_students(q: str = Query(..., min_length=2, max_length=100),
                                      admin=Depends(get_content_admin_user)):
    query = db.build_user_search_query(q.strip())
    query["approved"] = True; query["suspended"] = {"$ne": True}
    scope = admin.get("_scope") or await db.get_content_scope(admin["id"])
    if scope and scope.get("kind") == "scoped": query["intake"] = scope.get("intake") or ""
    docs = await db.users.find(query, {"user_id": 1, "name": 1, "nickname": 1,
        "student_id": 1, "username": 1, "intake": 1, "group": 1, "role": 1}).sort("name", 1).limit(20).to_list(20)
    return {"students": [{"id": row.get("user_id"), "name": db.display_name_of(row),
                           "student_id": row.get("student_id", ""), "username": row.get("username", ""),
                           "intake": row.get("intake", ""), "group": row.get("group", "")}
                          for row in docs if row.get("role", "student") == "student"]}


@router.get("/content/student-preview")
async def wa_student_preview(user_id: int = Query(...), admin=Depends(get_content_admin_user)):
    context, target = await _student_preview_context(user_id, admin)
    terms = await resources_api.terms(user=context)
    return {"student": {"id": user_id, "name": db.display_name_of(target),
                         "intake": target.get("intake", ""), "group": target.get("group", "")},
            "terms": terms.get("terms") or [], "resolver": "mini_app_resources"}


@router.get("/content/student-preview/lessons")
async def wa_student_preview_lessons(user_id: int, term: str = Query(..., max_length=100),
                                     admin=Depends(get_content_admin_user)):
    context, _ = await _student_preview_context(user_id, admin)
    return await resources_api.lessons(term=term, user=context)


@router.get("/content/student-preview/sessions")
async def wa_student_preview_sessions(user_id: int, lesson_id: str = Query(..., max_length=80),
                                      admin=Depends(get_content_admin_user)):
    context, _ = await _student_preview_context(user_id, admin)
    return await resources_api.sessions(lesson_id=lesson_id, user=context)


@router.get("/content/student-preview/files")
async def wa_student_preview_files(user_id: int, session_id: str = Query(..., max_length=80),
                                   admin=Depends(get_content_admin_user)):
    context, _ = await _student_preview_context(user_id, admin)
    return await resources_api.files(session_id=session_id, user=context)


@router.get("/content/impact/{target_type}/{target_id}")
async def wa_content_impact(
    target_type: str, target_id: str, admin=Depends(get_content_admin_user),
):
    if target_type == "lesson":
        item = await db.bs_get_lesson(target_id)
        intake = (item or {}).get("intake") or ""
        session_ids = [str(row.get("_id")) for row in await db.bs_sessions.find({"lesson_id": target_id}, {"_id": 1}).to_list(10000)]
        sessions = len(session_ids)
        files = await db.bs_content.count_documents({"session_id": {"$in": session_ids}}) if session_ids else 0
    elif target_type == "session":
        item = await db.bs_get_session(target_id)
        intake = await db.session_intake(target_id) if item else ""
        sessions = 1 if item else 0
        files = await db.bs_content.count_documents({"session_id": target_id}) if item else 0
    elif target_type == "content_item":
        item = await db.bs_get_content_item(target_id)
        intake = await db.content_intake(target_id) if item else ""
        sessions, files = 0, 1 if item else 0
    else:
        raise HTTPException(422, "نوع محتوا برای تحلیل اثر پشتیبانی نمی‌شود")
    if not item:
        raise HTTPException(404, "محتوا پیدا نشد")
    if not await db.can_access_intake(admin["id"], intake):
        raise HTTPException(403, "intake_out_of_scope")
    user_query = {"approved": True, "suspended": {"$ne": True}}
    if intake: user_query["intake"] = intake
    affected_users = await db.users.count_documents(user_query)
    return {"target_type": target_type, "target_id": target_id, "intake": intake,
            "affected_users": affected_users, "affected_sessions": sessions,
            "affected_files": files, "visibility": "potential",
            "explanation": "تعداد کاربران فعالی که این scope بالقوه برایشان قابل مشاهده است؛ سیاست اشتراک ممکن است دسترسی نهایی را محدود کند."}


@router.get("/content/history")
async def content_history(
    target_id: str = Query(..., min_length=1, max_length=80),
    target_type: str = Query(..., pattern="^(lesson|session|content_item|reference_subject|reference_book|reference_file|qbank_file)$"),
    limit: int = Query(20, ge=1, le=50),
    admin=Depends(get_content_admin_user),
):
    if target_type == "lesson":
        item = await db.bs_get_lesson(target_id); item_intake = (item or {}).get("intake") or ""
    elif target_type == "session":
        item = await db.bs_get_session(target_id); item_intake = await db.session_intake(target_id)
    elif target_type == "content_item":
        item = await db.bs_get_content_item(target_id); item_intake = await db.content_intake(target_id)
    elif target_type == "reference_subject":
        item = await db.ref_get_subject(target_id); item_intake = (item or {}).get("intake") or ""
    elif target_type == "reference_book":
        item = await db.ref_get_book(target_id); item_intake = await db.ref_book_intake(target_id)
    elif target_type == "reference_file":
        item = await db.ref_get_file(target_id); item_intake = await db.ref_file_intake(target_id)
    else:
        item = await db.get_qbank_file(target_id); item_intake = (item or {}).get("intake") or ""
    if not item:
        raise HTTPException(404, "محتوا پیدا نشد")
    scope = admin.get("_scope") or await db.get_content_scope(admin["id"])
    if scope and scope.get("kind") == "scoped" and item_intake not in ("", scope.get("intake") or ""):
        raise HTTPException(403, "intake_out_of_scope")
    docs = await db.audit_logs.find({"$or": [
        {"target.id": target_id}, {"target_id": target_id},
    ]}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"items": [{
        "id": str(d.get("_id", "")), "title": d.get("action", ""),
        "actor": (d.get("actor") or {}).get("name", ""),
        "at": (d.get("timestamp") or "")[:16].replace("T", " "),
        "description": d.get("details", ""), "severity": d.get("severity", "INFO"),
    } for d in docs]}


@router.post("/content/sessions/{sid}/duplicate")
async def content_session_duplicate(sid: str,
                                    admin=Depends(get_content_global_user)):
    """📄➜📄 کلون جلسه — شماره‌ی بعدی همان درس؛ کپی فایل‌ها با notif_sent=True
    (کلون «محتوای جدید» نیست ⇒ دوباره اعلان منابع نمی‌شورد)."""
    base = await db.bs_get_session(sid)
    if not base:
        raise HTTPException(404, "جلسه یافت نشد")
    lid = base.get("lesson_id", "")
    eff_intake = await db.session_intake(sid)
    sibs = await db.bs_sessions.find({"lesson_id": lid}).to_list(500)
    next_num = max([0] + [s.get("number", 0) or 0 for s in sibs]) + 1
    doc = {"lesson_id": lid, "number": next_num,
           "topic": (base.get("topic", "") or "")[:120],
           "teacher": base.get("teacher", ""),
           "intake": eff_intake, "duplicated_from": sid,
           "created_at": _now()}
    r = await db.bs_sessions.insert_one(doc)
    new_sid = str(getattr(r, "inserted_id", "") or "")
    copied = 0
    for c in (await db.bs_get_content(sid)):
        await db.bs_content.insert_one({
            "session_id": new_sid, "type": c.get("type", "pdf"),
            "file_id": c.get("file_id", ""), "description": c.get("description", ""),
            "extra_info": c.get("extra_info", ""), "order": c.get("order", 0),
            "uploaded_at": _now(), "downloads": 0, "notif_sent": True,
        })
        copied += 1
    await _audit(admin["id"], "کلون جلسه (همراه فایل‌ها)", severity="INFO",
                 target_id=new_sid, target_type="session",
                 target_label=base.get("topic", ""), tags=["کلون_جلسه", "پنل_وب"])
    return {"ok": True, "id": new_sid, "number": next_num, "copied": copied}


class SessionsBulk(BaseModel):
    action: str                 # duplicate | delete | move
    ids: list[str]
    target_lesson: Optional[str] = None


@router.post("/content/sessions/bulk")
async def content_sessions_bulk(body: SessionsBulk,
                                admin=Depends(get_content_global_user)):
    """⚡ اکشن گروهی جلسات (سقف ۵۰) — فقط ادمین ارشد محتوا (ساختار سراسری)."""
    ids = [str(i) for i in (body.ids or [])][:50]
    if not ids:
        raise HTTPException(400, "لیست جلسات خالی است")
    done = 0
    if body.action == "delete":
        for sid in ids:
            # پاک‌سازی forkهای وابسته هم (جلوگیری از یتیم‌شدن)
            for f in await db.bs_sessions.find({"fork_of": sid}).to_list(50):
                await db.bs_delete_session(str(f.get("_id")))
            await db.bs_delete_session(sid)
            done += 1
    elif body.action == "duplicate":
        for sid in ids:
            try:
                r = await content_session_duplicate(sid, admin)
                if r.get("ok"):
                    done += 1
            except Exception:
                continue   # جلسه‌ی نامعتبر/خراب متوقف‌کننده‌ی بقیه نیست
    elif body.action == "move":
        tl = (body.target_lesson or "").strip()
        target = await db.bs_get_lesson(tl)
        if not target:
            raise HTTPException(404, "درس مقصد یافت نشد")
        siblings = await db.bs_sessions.find({"lesson_id": tl}).to_list(500)
        next_num = max([0] + [s.get("number", 0) or 0 for s in siblings])
        for sid in ids:
            s = await db.bs_get_session(sid)
            if not s or s.get("lesson_id") == tl:
                continue
            if s.get("fork_of"):
                continue  # fork را جابه‌جا نمی‌کنیم (به base گره خورده)
            next_num += 1
            await db.bs_update_session(sid, {"lesson_id": tl, "number": next_num,
                                             "intake": target.get("intake") or ""})
            done += 1
    else:
        raise HTTPException(400, "اکشن نامعتبر است")
    fa = {"delete": "حذف گروهی", "duplicate": "کلون گروهی", "move": "انتقال گروهی"}
    await _audit(admin["id"], f"{fa[body.action]} جلسات ({done} مورد)",
                 severity="HIGH" if body.action == "delete" else "INFO",
                 target_label=f"{done} جلسه", tags=["bulk_content", "پنل_وب"])
    return {"ok": True, "done": done}


class ItemsBulk(BaseModel):
    action: str                 # delete | move
    ids: list[str]
    target_session: Optional[str] = None


@router.post("/content/items/bulk")
async def content_items_bulk(body: ItemsBulk,
                             admin=Depends(get_content_global_user)):
    """⚡ اکشن گروهی آیتم‌های محتوا (سقف ۱۰۰): حذف | انتقال به جلسه‌ی دیگر."""
    ids = [str(i) for i in (body.ids or [])][:100]
    if not ids:
        raise HTTPException(400, "لیست آیتم‌ها خالی است")
    done = 0
    if body.action == "delete":
        for cid in ids:
            if await db.bs_get_content_item(cid):
                await db.bs_delete_content(cid)
                done += 1
    elif body.action == "move":
        ts = (body.target_session or "").strip()
        if not await db.bs_get_session(ts):
            raise HTTPException(404, "جلسه‌ی مقصد یافت نشد")
        order = await db.bs_content.count_documents({"session_id": ts})
        for cid in ids:
            c = await db.bs_get_content_item(cid)
            if not c or c.get("session_id") == ts:
                continue
            order += 1
            await db.bs_content.update_one({"_id": _oid(cid)},
                                           {"$set": {"session_id": ts, "order": order}})
            done += 1
    else:
        raise HTTPException(400, "اکشن نامعتبر است")
    await _audit(admin["id"],
                 f"{'حذف' if body.action == 'delete' else 'انتقال'} گروهی فایل‌ها ({done} مورد)",
                 severity="HIGH" if body.action == "delete" else "INFO",
                 target_label=f"{done} فایل", tags=["bulk_content", "پنل_وب"])
    return {"ok": True, "done": done}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.6 — تحلیل پیشرفته‌ی وب‌ادمین (بدون هیچ داده‌ی ساختگی)
# ══════════════════════════════════════════════════════════════════

@router.get("/wa-analytics")
async def wa_analytics(user=Depends(_perm("stats.view")),
                       days: int = Query(14, ge=1, le=90)):
    """📈 متحد از داشبوردهای آماری واقعی db + شمارش‌های زنده — فقط خواندنی.

    🌊 موج Analytics-Filters: پارامتر days (۷ تا ۹۰ روز) برای متریکهای
    بازه‌ای؛ دارندگان مجوز stats.deep علاوه‌بر snapshot، «bundle»‌ی کامل
    تحلیلی (KPI/سری روزانه/اکشن‌ها/ساعات اوج — همان منطق واحد db) می‌گیرند.
    """
    out = {}
    out["days"] = days
    for name, fn in (("users", getattr(db, "stats_dashboard_users", None)),
                     ("content", getattr(db, "stats_dashboard_content", None)),
                     ("questions", getattr(db, "stats_dashboard_questions", None)),
                     ("tickets", getattr(db, "stats_dashboard_tickets", None)),
                     ("notif", getattr(db, "stats_dashboard_notif", None))):
        if fn:
            try:
                out[name] = await fn()
            except Exception:
                out[name] = {}
    try:
        out["pulse"] = await db.activity_pulse()
    except Exception:
        out["pulse"] = {}
    try:
        out["sub"] = await db.sub_stats()
    except Exception:
        out["sub"] = {}
    try:
        out["new_resources_7d"] = await db.new_resources_count(7)
    except Exception:
        out["new_resources_7d"] = 0
    try:
        out["new_resources_in_range"] = await db.new_resources_count(days)
    except Exception:
        out["new_resources_in_range"] = 0
    try:
        out["active_today"] = await db.count_active_users_today()
    except Exception:
        out["active_today"] = 0
    # 🌊 تحلیل عمیق بازه‌ای — فقط با مجوز جداگانه (گیت دومرحله‌ای)
    deep = False
    try:
        deep = bool(await db.has_permission(user["id"], "stats.deep"))
    except Exception:
        deep = False
    if deep:
        try:
            out["bundle"] = await db.stats_analytics_bundle(days)
        except Exception:
            pass
    out["deep"] = deep
    return out


# 🌊 موج Parity-Final — مرکز هوش ربات در وب: منطق rule-based واحدِ
# db.admin_insights() (همان صفحه‌ی admin:insights ربات) بدون هیچ کپی‌خوانی.
@router.get("/wa-insights")
async def wa_insights(user=Depends(_perm("stats.view"))):
    try:
        return await db.admin_insights()
    except Exception:
        # جزئیات exception فقط در لاگ سرور می‌ماند؛ API متن داخلی/credential را لو نمی‌دهد.
        raise HTTPException(503, "insights_temporarily_unavailable")


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.7 — مدیریت اعلان‌ها: اجراها + تلاش مجدد (مشابه admin_panel ولی با مجوز)
# ══════════════════════════════════════════════════════════════════

@router.get("/notif/runs")
async def notif_runs(job_name: str | None = Query(None),
                     limit: int = Query(15, ge=1, le=50),
                     user=Depends(_perm("notifications.manage"))):
    runs = await db.get_recent_notif_runs(job_name=job_name, limit=limit)
    return {"runs": [{
        "id": str(r.get("_id", "")), "job_name": r.get("job_name", ""),
        "status": r.get("status", ""), "sent": r.get("sent", 0),
        "failed": r.get("failed", 0), "total": r.get("total", 0),
        "started_at": (r.get("started_at") or "")[:16].replace("T", " "),
        "finished_at": (r.get("finished_at") or "")[:16].replace("T", " ") if r.get("finished_at") else "",
    } for r in runs]}


@router.get("/notif/runs/{run_id}")
async def notif_run_detail(run_id: str, user=Depends(_perm("notifications.manage"))):
    oid = _oid(run_id)
    if not oid: raise HTTPException(422, "شناسه اجرای اعلان نامعتبر است")
    run = await db.notif_runs.find_one({"_id": oid})
    if not run: raise HTTPException(404, "اجرای اعلان پیدا نشد")
    failed = run.get("failed_targets_detailed") or [{"user_id": uid} for uid in (run.get("failed_user_ids") or [])]
    return {"run": {"id": run_id, "job_name": run.get("job_name", ""),
        "status": run.get("status", ""), "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"), "sent": int(run.get("sent") or 0),
        "failed": int(run.get("failed") or 0), "skipped": int(run.get("skipped") or 0),
        "total": int(run.get("total") or 0), "error": (run.get("error") or "")[:500],
        "message_preview": (run.get("message_text") or "")[:500],
        "correlation_id": run.get("correlation_id"),
        "failed_targets": [{"user_id": item.get("user_id"), "error": item.get("error") or "send_failed"}
                           for item in failed[:100]],
        "failed_targets_truncated": len(failed) > 100}}


@router.post("/notif/runs/{run_id}/retry")
async def notif_retry(run_id: str, user=Depends(_perm("notifications.manage"))):
    """🔁 صف دوباره‌ی گیرندگان ناموفق — همان الگوی admin_panel ولی permission-based."""
    targets = await db.get_failed_notif_details(run_id)
    if not targets:
        raise HTTPException(404, "موردی برای تلاش مجدد پیدا نشد")
    notif = db.client["medicalbot"]["bot_notifications"]
    n = 0
    for t in targets:
        if not t.get("message"):
            continue
        await notif.insert_one({"type": "notif_retry", "chat_id": t["user_id"],
                                "text": t["message"], "sent": False,
                                "created_at": _now(), "correlation_id": current_request_id.get()})
        n += 1
    await _audit(user["id"], f"تلاش مجدد ارسال اعلان ({n} گیرنده)",
                 severity="INFO", target_label=run_id, tags=["retry_notif", "پنل_وب"])
    return {"ok": True, "requeued": n}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA3 — پریتی کامل «مدیریت کاربران» (آینه‌ی دقیق رفتار پنل وب قبلی ولی
# permission-based؛ هیچ endpoint موجود تغییر نمی‌کند)
# ══════════════════════════════════════════════════════════════════

class DmIn(BaseModel):
    text: str


@router.post("/users/{uid}/message")
async def wa_user_message(uid: int, body: DmIn, user=Depends(_perm("users.message"))):
    """✉️ پیام مستقیم ادمین به کاربر — همان کانال outbox ربات."""
    text = (body.text or "").strip()
    if not (1 <= len(text) <= 1500):
        raise HTTPException(422, "متن پیام باید بین ۱ تا ۱۵۰۰ کاراکتر باشد")
    target = await db.get_user(uid)
    if not target:
        raise HTTPException(404, "کاربر یافت نشد")
    await db.client["medicalbot"]["bot_notifications"].insert_one({
        "type": f"admin_dm", "chat_id": uid,
        "text": f"📩 <b>پیام از پشتیبانی هامزیار</b>\n\n{text}",
        "sent": False, "created_at": _now()})
    await _audit(user["id"], "ارسال پیام مستقیم به کاربر", severity="INFO",
                 target_id=uid, target_type="user",
                 target_label=target.get("name", ""), tags=["dm_کاربر", "پنل_وب"])
    return {"ok": True}


class UserActionIn(BaseModel):
    action: str          # approve|reject|suspend|unsuspend|delete|block|unblock
    reason: str = ""


@router.post("/users/{uid}/action")
async def wa_user_action(uid: int, body: UserActionIn, user=Depends(_guard_any_admin)):
    """⚙️ اکشن‌های تکی کاربر — معناشناسی دقیقاً برابر پنل قبلی/ربات + آینه‌ی
    Inbox مینی‌اپ (سه کلاینت سینک می‌مانند)."""
    _PERM = {"approve": "users.manage", "reject": "users.manage",
             "suspend": "users.suspend", "unsuspend": "users.suspend",
             "delete": "users.delete", "block": "users.delete", "unblock": "users.delete"}
    need = _PERM.get(body.action)
    if not need:
        raise HTTPException(400, "اکشن نامعتبر است")
    actor = user["id"]
    if not await db.has_permission(actor, need):
        raise HTTPException(403, "forbidden")
    if uid == ADMIN_ID and body.action in ("suspend", "delete", "block", "reject"):
        raise HTTPException(403, "روی مالک سامانه قابل اعمال نیست")
    target = await db.get_user(uid)
    notif = db.client["medicalbot"]["bot_notifications"]

    if body.action == "unblock":
        ok = await db.unblock_user(uid)
        if not ok:
            raise HTTPException(404, "این کاربر در بلک‌لیست نیست")
        await _audit(actor, "رفع مسدودیت کاربر", severity="HIGH",
                     target_id=uid, target_type="user", tags=["آنبلاک_کاربر", "پنل_وب"])
        return {"ok": True}
    if not target:
        raise HTTPException(404, "کاربر یافت نشد")
    label = target.get("name", "")

    if body.action == "approve":
        await db.update_user(uid, {"approved": True})
        await notif.insert_one({"type": "user_approved", "chat_id": uid,
            "text": "✅ <b>حساب شما تأیید شد!</b>\n\nاکنون می‌توانید از هامزیار استفاده کنید.\n/start بزنید.",
            "sent": False, "created_at": _now()})
        await db.inbox_add(uid, 'account', "✅ حسابت تأیید شد!",
            "اکنون به تمام بخش‌های هامزیار دسترسی داری — خوش اومدی! 🎓", link='/')
        await _audit(actor, "تأیید حساب کاربر", target_id=uid, target_type="user",
                     target_label=label, tags=["تأیید_کاربر", "پنل_وب"])
    elif body.action == "reject":
        await db.users.delete_one({"user_id": uid})
        await _audit(actor, "رد درخواست عضویت", severity="WARNING", target_id=uid,
                     target_type="user", target_label=label, tags=["رد_کاربر", "پنل_وب"])
    elif body.action == "suspend":
        await db.update_user(uid, {"suspended": True, "approved": False})
        await notif.insert_one({"type": "user_suspended", "chat_id": uid,
            "text": "⚠️ دسترسی شما موقتاً تعلیق شد.", "sent": False, "created_at": _now()})
        await _audit(actor, "تعلیق حساب کاربر", severity="HIGH", target_id=uid,
                     target_type="user", target_label=label, tags=["تعلیق_کاربر", "پنل_وب"])
    elif body.action == "unsuspend":
        await db.update_user(uid, {"suspended": False, "approved": True})
        await _audit(actor, "رفع تعلیق حساب کاربر", target_id=uid, target_type="user",
                     target_label=label, tags=["رفع_تعلیق", "پنل_وب"])
    elif body.action == "delete":
        await notif.insert_one({"type": "user_deleted", "chat_id": uid,
            "text": "❌ حساب شما حذف شد.", "sent": False, "created_at": _now()})
        await db.delete_user(uid)
        await _audit(actor, "حذف حساب کاربر", severity="CRITICAL", target_id=uid,
                     target_type="user", target_label=label, tags=["حذف_کاربر", "پنل_وب"])
    elif body.action == "block":
        await db.block_user(uid, reason=body.reason or "",
                            blocked_by=actor, blocked_by_name=(user.get("_db") or {}).get("name", ""))
        try:
            await db.blacklist.update_one({"_id": uid}, {"$set": {"name": label}})
        except Exception:
            pass
        await notif.insert_one({"type": "user_blocked", "chat_id": uid,
            "text": "🚫 حساب شما مسدود شد و امکان ثبت‌نام مجدد ندارید.",
            "sent": False, "created_at": _now()})
        await _audit(actor, "مسدودسازی کاربر (بلک‌لیست)", severity="CRITICAL",
                     target_id=uid, target_type="user", target_label=label,
                     tags=["بلاک_کاربر", "پنل_وب"])
    return {"ok": True}


class WaUserPatch(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None
    group: Optional[str] = None
    intake: Optional[str] = None
    student_id: Optional[str] = None


@router.patch("/users/{uid}")
async def wa_user_patch(uid: int, body: WaUserPatch, user=Depends(_perm("users.manage"))):
    """✏️ ویرایش فیلدهای پروفایل — همان whitelist پنل قبلی + لقب از مسیر
    IdentityService (اعتبارسنجی/audit خودکار داخل db)."""
    old_doc = await db.get_user(uid)
    if not old_doc:
        raise HTTPException(404, "کاربر یافت نشد")
    updates = {}
    if body.name is not None:
        updates["name"] = body.name.strip()[:80]
    if body.group is not None:
        updates["group"] = db.normalize_group(body.group)
    if body.intake is not None:
        updates["intake"] = body.intake
    if body.student_id is not None:
        updates["student_id"] = body.student_id.strip()[:40]
    nick_note = ""
    if body.nickname is not None:
        ok, err, _info = await db.set_nickname(
            uid, body.nickname, changed_by=f"admin:{user['id']}", reason="پنل وب‌ادمین")
        if not ok:
            raise HTTPException(422, f"لقب نامعتبر: {err}")
        nick_note = " + لقب"
    # 🌊 موج Audit-Diff — اسنپ‌شات «قبل» پیش از update (مقادیر scalar تغییرناپذیرند)
    _LBL = {"name": "نام", "group": "گروه", "intake": "ورودی", "student_id": "شماره دانشجویی"}
    _before = {_LBL.get(k, k): old_doc.get(k) for k in updates}
    _after = {_LBL.get(k, k): updates[k] for k in updates}
    if updates:
        await db.update_user(uid, updates)
    if updates or body.nickname is not None:
        await _audit(user["id"], "ویرایش اطلاعات کاربر" + nick_note, severity="WARNING",
                     target_id=uid, target_type="user",
                     target_label=" / ".join(f"{k}: {v}" for k, v in updates.items())[:300],
                     before=_before or None, after=_after or None,
                     tags=["ویرایش_کاربر", "پنل_وب"])
    return {"ok": True, "changed": list(updates.keys()) + (["nickname"] if body.nickname is not None else [])}


@router.get("/blacklist")
async def wa_blacklist(user=Depends(_perm("users.view"))):
    """🚫 بلک‌لیست — همان شکل پنل قبلی."""
    items = await db.get_blacklist()
    return {"blacklist": [{
        "id": b.get("_id"), "name": b.get("name", ""),
        "blocked_by_name": b.get("blocked_by_name", ""),
        "blocked_at": str(b.get("blocked_at", ""))[:10]} for b in items]}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA3 — مرتب‌سازی محتوا (reorder) — همان متدهای db که ربات استفاده می‌کند
# ══════════════════════════════════════════════════════════════════

class ReorderIn(BaseModel):
    direction: str       # up | down


@router.post("/content/lessons/{lid}/reorder")
async def content_lesson_reorder(lid: str, body: ReorderIn,
                                 admin=Depends(get_content_admin_user)):
    lesson = await db.bs_get_lesson(lid)
    if not lesson:
        raise HTTPException(404, "درس یافت نشد")
    if not await db.can_access_intake(admin["id"], lesson.get("intake") or ""):
        raise HTTPException(403, "intake_out_of_scope")
    q = {"term": lesson.get("term", ""), "intake": lesson.get("intake") or ""}
    fn = db.reorder_up if body.direction == "up" else db.reorder_down
    ok = await fn("bs_lessons", lid, q)
    if ok:
        await _audit(admin["id"], "تغییر ترتیب درس علوم پایه", severity="INFO",
                     target_id=lid, target_type="lesson", target_label=lesson.get("name", ""),
                     after={"جهت": body.direction}, tags=["محتوا", "ترتیب", "پنل_وب"])
    return {"ok": bool(ok)}


@router.post("/content/sessions/{sid}/reorder")
async def content_session_reorder(sid: str, body: ReorderIn,
                                  admin=Depends(get_content_admin_user)):
    ses = await db.bs_get_session(sid)
    if not ses:
        raise HTTPException(404, "جلسه یافت نشد")
    if not await db.can_access_intake(admin["id"], await db.session_intake(sid)):
        raise HTTPException(403, "intake_out_of_scope")
    q = {"lesson_id": ses.get("lesson_id", "")}
    if ses.get("fork_of") or (ses.get("intake") or ""):
        q["intake"] = ses.get("intake") or ""
    else:
        # baseها هرگز با fork ورودی دیگر swap نمی‌شوند.
        q["fork_of"] = {"$in": [None, ""]}
        q["$or"] = [{"intake": ""}, {"intake": None},
                    {"intake": {"$exists": False}}]
    fn = db.reorder_up if body.direction == "up" else db.reorder_down
    ok = await fn("bs_sessions", sid, q)
    return {"ok": bool(ok)}


@router.post("/content/items/{cid}/reorder")
async def content_item_reorder(cid: str, body: ReorderIn,
                               admin=Depends(get_content_admin_user)):
    item = await db.bs_get_content_item(cid)
    if not item:
        raise HTTPException(404, "فایل یافت نشد")
    if not await db.can_access_intake(admin["id"], await db.content_intake(cid)):
        raise HTTPException(403, "intake_out_of_scope")
    sid = item.get("session_id", "")
    fn = db.reorder_content_up if body.direction == "up" else db.reorder_content_down
    ok = await fn(cid, sid)
    return {"ok": bool(ok)}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.8 — User 360 (کانتکست کامل بدون ترک صفحه)
# ══════════════════════════════════════════════════════════════════

@router.get("/users/{uid}/360")
async def user_360(uid: int, user=Depends(_perm("users.view"))):
    """👤 نمای ۳۶۰ درجه‌ی کاربر — پرونده + اشتراک + نقش‌ها + شمارش‌ها +
    آخرین تیکت‌ها + آخرین رویدادهای audit مرتبط، همه در یک پاسخ."""
    target = await db.get_user(uid)
    if not target:
        raise HTTPException(404, "کاربر یافت نشد")
    out = {
        "user": {
            "id": target.get("user_id"), "name": target.get("name", ""),
            "nickname": target.get("nickname"), "username": target.get("username", ""),
            "display_name": db.display_name_of(target),
            "student_id": target.get("student_id", ""),
            "intake": target.get("intake", ""), "group": target.get("group", ""),
            "role": target.get("role", "student"),
            "approved": target.get("approved", False),
            "suspended": target.get("suspended", False),
            "registered_at": (target.get("registered_at") or "")[:16],
            "last_active": (target.get("last_active") or "")[:16],
            "total_answers": target.get("total_answers", 0),
            "correct_answers": target.get("correct_answers", 0),
            "accuracy": round(
                int(target.get("correct_answers") or 0) * 100 /
                int(target.get("total_answers") or 1), 1
            ) if int(target.get("total_answers") or 0) else 0,
            "prestige_rank": target.get("prestige_rank", ""),
            "prestige_div": target.get("prestige_div", ""),
            "streak_current": target.get("streak_current", 0) or 0,
        },
        "subscription": None, "admin_role": None, "roles": [], "perms": [],
        "counts": {"tickets": 0, "grades": 0, "answers": 0, "questions": 0,
                   "exams": 0, "notifications": 0},
        "recent_tickets": [], "recent_audit": [], "recent_questions": [],
        "recent_exams": [], "recent_notifications": [], "prestige_history": [],
    }
    try:
        sub = await db.sub_get(uid)
        if sub:
            out["subscription"] = {
                "status": sub.get("status", ""), "plan": sub.get("plan_name", ""),
                "end_date": (sub.get("end_date", "") or "")[:10],
                "days_left": await db.sub_days_left(uid),
            }
    except Exception:
        pass
    try:
        ar = await db.get_admin_role(uid)
        if ar:
            out["admin_role"] = {"role": ar.get("role"), "scope": ar.get("scope_intake")}
        role_info = await db.get_user_roles(uid)
        out["roles"] = [{
            "key": r.get("_id"), "label": r.get("label", r.get("_id", "")),
            "active": r.get("active", True), "scope": role_info.get("scope_intake"),
        } for r in role_info.get("roles", [])]
    except Exception:
        pass
    try:
        out["perms"] = sorted(await db.get_user_perms(uid))
    except Exception:
        pass
    try:
        out["counts"]["tickets"] = await db.tickets.count_documents({"user_id": uid})
        out["recent_tickets"] = [{
            "id": t.get("ticket_id"), "subject": t.get("subject", ""),
            "status": t.get("status", ""),
            "at": (t.get("created_at", "") or "")[:10],
        } for t in await db.tickets.find({"user_id": uid}).sort("created_at", -1).limit(5).to_list(5)]
    except Exception:
        pass
    try:
        out["counts"]["grades"] = await db.grades.count_documents({"student_id": uid})
        out["counts"]["answers"] = await db.answers.count_documents({"user_id": uid})
        out["counts"]["questions"] = await db.questions.count_documents({"creator_id": uid})
        out["counts"]["exams"] = await db.exam_sessions.count_documents({"user_id": uid})
    except Exception:
        pass
    try:
        logs = await db.audit_logs.find({"$or": [
            {"actor.id": uid}, {"target.id": str(uid)}, {"target.id": uid},
            {"target_id": str(uid)}, {"target_id": uid},
        ]}).sort("timestamp", -1).limit(20).to_list(20)
        out["recent_audit"] = [{
            "id": str(l.get("_id", "")), "action": l.get("action", ""),
            "module": l.get("module", ""),
            "at": (l.get("timestamp") or "")[:16].replace("T", " "),
            "severity": l.get("severity", "INFO"),
            "relation": "actor" if (l.get("actor") or {}).get("id") == uid else "target",
            "changes": l.get("changes") or [],
            "correlation_id": l.get("correlation_id"),
        } for l in logs]
    except Exception:
        pass

    # 🌊 W-Admin — بخش‌های جدید User 360 (افزودنی؛ هر بخش جدا ضدخطا)
    try:  # 📊 تحصیلی — آخرین نمرات
        gdocs = await db.grades.find({"student_id": uid}).sort("exam_date", -1).limit(6).to_list(6)
        out["academic"] = {"grades_recent": [{
            "lesson": g.get("lesson", ""), "exam_title": g.get("exam_title", ""),
            "exam_date": g.get("exam_date", ""), "score": g.get("score", 0),
        } for g in gdocs]}
    except Exception:
        out.setdefault("academic", {"grades_recent": []})
    try:  # 🤖 هوشیار — از روی سند کاربر (بدون کوئری اضافه)
        today = datetime.now().strftime("%Y-%m-%d")
        out["ai"] = {
            "total_usage": target.get("ai_total_usage", 0) or 0,
            "today": (target.get("ai_usage_count", 0) or 0)
                     if target.get("ai_usage_date") == today else 0,
            "total_tokens": target.get("ai_total_tokens", 0) or 0,
            "banned": bool(target.get("ai_banned")),
        }
    except Exception:
        out.setdefault("ai", {})
    try:  # 🏆 افتخار — رنک/XP/استریک از سند کاربر
        dx = target.get("daily_xp") or {}
        out["prestige"] = {
            "rank": target.get("prestige_rank", ""), "div": target.get("prestige_div", ""),
            "prestige_xp": target.get("prestige_xp", 0) or 0,
            "effective_xp": target.get("effective_xp", 0) or 0,
            "weekly_xp": target.get("weekly_xp", 0) or 0,
            "monthly_xp": target.get("monthly_xp", 0) or 0,
            "streak_current": target.get("streak_current", 0) or 0,
            "streak_best": target.get("streak_best", 0) or 0,
            "daily_xp_amount": dx.get("amount", 0) or 0,
        }
    except Exception:
        out.setdefault("prestige", {})
    try:  # 🔔 اعلان‌ها — شمارش و آخرین آیتم‌ها
        un = await db.user_notifs.count_documents({"user_id": uid, "read": {"$ne": True}})
        tot = await db.user_notifs.count_documents({"user_id": uid})
        ndocs = await db.user_notifs.find({"user_id": uid}).sort("created_at", -1).limit(8).to_list(8)
        out["notifs"] = {"unread": un, "total": tot}
        out["counts"]["notifications"] = tot
        out["recent_notifications"] = [{
            "id": str(n.get("_id", "")), "type": n.get("type", ""),
            "title": n.get("title", ""), "body": n.get("body", ""),
            "read": bool(n.get("read")),
            "at": (n.get("created_at") or "")[:16].replace("T", " "),
        } for n in ndocs]
    except Exception:
        out.setdefault("notifs", {})
    try:
        qdocs = await db.questions.find({"creator_id": uid}).sort("created_at", -1).limit(8).to_list(8)
        out["recent_questions"] = [{
            "id": str(q.get("_id", "")), "question": (q.get("question") or "")[:180],
            "lesson": q.get("lesson", ""), "topic": q.get("topic", ""),
            "difficulty": q.get("difficulty", ""), "approved": bool(q.get("approved")),
            "attempts": int(q.get("attempt_count") or 0),
            "accuracy": round(int(q.get("correct_count") or 0) * 100 /
                              int(q.get("attempt_count") or 1), 1)
                        if int(q.get("attempt_count") or 0) else 0,
            "at": (q.get("created_at") or "")[:10],
        } for q in qdocs]
    except Exception:
        pass
    try:
        edocs = await db.exam_sessions.find({"user_id": uid}).sort("started_at", -1).limit(8).to_list(8)
        out["recent_exams"] = [{
            "id": str(e.get("session_id") or e.get("_id", "")),
            "lesson": e.get("lesson", ""), "topic": e.get("topic", ""),
            "status": e.get("status", "active"),
            "answered": int(e.get("answered") or 0), "correct": int(e.get("correct") or 0),
            "total": len(e.get("question_ids") or []),
            "percentage": round(int(e.get("correct") or 0) * 100 /
                                int(e.get("answered") or 1)) if int(e.get("answered") or 0) else 0,
            "started_at": (e.get("started_at") or "")[:16].replace("T", " "),
        } for e in edocs]
    except Exception:
        pass
    try:
        # منبع واحد domain: schema واقعی prestige_history با uid/type/detail/at.
        pdocs = await db.prestige_history_list(uid, limit=10)
        out["prestige_history"] = [{
            "id": f"{i}:{p.get('type', '')}:{p.get('at', '')}", "kind": p.get("type", ""),
            "title": p.get("title", "") or p.get("type", ""),
            "xp": int((p.get("detail") or {}).get("xp") or (p.get("detail") or {}).get("amount") or 0),
            "at": (p.get("at") or "")[:16].replace("T", " "),
        } for i, p in enumerate(pdocs)]
    except Exception:
        pass
    # Timeline واحد از eventهای واقعی و قابل‌ردیابی؛ هیچ event مصنوعی ساخته نمی‌شود.
    activity = []
    if target.get("registered_at"):
        activity.append({"id": "registration", "kind": "registration", "icon": "👤",
                         "title": "ثبت‌نام در هامزیار", "at": (target.get("registered_at") or "")[:16].replace("T", " "),
                         "go": f"/users?q={uid}"})
    try:
        adocs = await db.answers.find({"user_id": uid}).sort("answered_at", -1).limit(12).to_list(12)
        activity.extend({"id": f"answer:{a.get('_id')}", "kind": "answer", "icon": "🧪",
                         "title": "پاسخ صحیح به سؤال" if a.get("is_correct") else "پاسخ به سؤال",
                         "description": f"شناسه سؤال: {a.get('question_id', '')}",
                         "at": (a.get("answered_at") or "")[:16].replace("T", " "), "go": f"/questions?q={a.get('question_id', '')}"}
                        for a in adocs)
    except Exception:
        pass
    activity.extend({"id": f"exam:{e['id']}", "kind": "exam", "icon": "📝",
                     "title": f"آزمون {e.get('lesson') or 'سفارشی'}", "description": f"نتیجه {e.get('percentage', 0)}٪",
                     "at": e.get("started_at", ""), "go": "/exams?tab=grades"} for e in out.get("recent_exams", []))
    activity.extend({"id": f"ticket:{t['id']}", "kind": "ticket", "icon": "🎫",
                     "title": t.get("subject") or "تیکت پشتیبانی", "description": t.get("status", ""),
                     "at": t.get("at", ""), "go": f"/tickets?q={t['id']}"} for t in out.get("recent_tickets", []))
    activity.extend({"id": f"prestige:{p['id']}", "kind": "prestige", "icon": "🏆",
                     "title": p.get("title") or p.get("kind") or "رویداد Prestige",
                     "description": f"{p.get('xp', 0):+d} XP", "at": p.get("at", ""), "go": f"/users?q={uid}"}
                    for p in out.get("prestige_history", []))
    activity.extend({"id": f"audit:{a.get('id', i)}", "kind": "audit", "icon": "🧭",
                     "title": a.get("action") or "رویداد حسابرسی", "description": a.get("module", ""),
                     "at": a.get("at", ""), "go": f"/audit?target={uid}"}
                    for i, a in enumerate(out.get("recent_audit", [])))
    out["activity"] = sorted(activity, key=lambda event: event.get("at") or "", reverse=True)[:40]
    return out


# ══════════════════════════════════════════════════════════════════
# 🛡 موج RBAC-Execution — مسیرهای permission-based برای Web Admin
# routeهای owner قدیمی دست‌نخورده‌اند؛ این wrapperها همان business logic
# موجود را با guard دانه‌ای فراخوانی می‌کنند.
# ══════════════════════════════════════════════════════════════════

# ── RBAC helpers ──────────────────────────────────────────────────

@router.get("/rbac/intakes")
async def wa_rbac_intakes(user=Depends(_perm("users.manage"))):
    items = await db.get_all_intakes()
    return {"intakes": [
        {"code": i.get("code", ""), "label": i.get("label", i.get("code", "")),
         "active": i.get("active", True)}
        for i in items
    ]}


@router.get("/rbac/roles-picker")
async def wa_rbac_roles_picker(user=Depends(_perm("users.manage"))):
    """فهرست کمینه و فقط‌خواندنی نقش‌ها برای filter/bulk کاربر."""
    roles = await db.list_roles()
    return {"roles": [{
        "key": r.get("_id"), "label": r.get("label", r.get("_id", "")),
        "active": r.get("active", True),
    } for r in roles if r.get("active", True)]}


# ── Tickets ───────────────────────────────────────────────────────

@router.get("/tickets")
async def wa_tickets_list(
    status: Optional[str] = Query(None, pattern="^(open|answered|closed)$"),
    q: Optional[str] = Query(None, max_length=120),
    intake: Optional[str] = Query(None, max_length=80),
    priority: Optional[str] = Query(None, pattern="^(low|normal|high|urgent)$"),
    assignee_id: Optional[int] = Query(None), unanswered: Optional[bool] = Query(None),
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at|last_reply_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=100),
    user=Depends(_perm_any("tickets.reply", "tickets.manage")),
):
    """Support queue با search/filter/pagination سرورساید؛ legacy owner route حفظ شده."""
    q = q if isinstance(q, str) else None
    intake = intake if isinstance(intake, str) else None
    priority = priority if isinstance(priority, str) else None
    assignee_id = assignee_id if isinstance(assignee_id, int) else None
    unanswered = unanswered if isinstance(unanswered, bool) else None
    date_from = date_from if isinstance(date_from, str) else None
    date_to = date_to if isinstance(date_to, str) else None
    sort_by = sort_by if isinstance(sort_by, str) else "created_at"
    sort_dir = sort_dir if isinstance(sort_dir, str) else "desc"
    page = page if isinstance(page, int) else 1
    limit = limit if isinstance(limit, int) else 30
    return await owner_api.all_tickets(
        status=status, q=q, intake=intake, priority=priority,
        assignee_id=assignee_id, unanswered=unanswered,
        date_from=date_from, date_to=date_to, sort_by=sort_by, sort_dir=sort_dir,
        page=page, limit=limit, admin=user,
    )


@router.get("/exports/tickets.csv")
async def export_tickets_csv(
    status: Optional[str] = Query(None, pattern="^(open|answered|closed)$"),
    q: Optional[str] = Query(None), intake: Optional[str] = Query(None),
    priority: Optional[str] = Query(None, pattern="^(low|normal|high|urgent)$"),
    assignee_id: Optional[int] = Query(None), unanswered: Optional[bool] = Query(None),
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at|last_reply_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user=Depends(_perm_any("tickets.reply", "tickets.manage")),
):
    await _audit(user["id"], "خروجی CSV تیکت‌ها", severity="HIGH",
                 target_type="export", target_label="tickets.csv",
                 tags=["خروجی", "تیکت", "پنل_وب"])
    columns = ["id", "subject", "user_id", "user_name", "status", "priority",
               "assignee_id", "assignee_name", "reply_count", "created_at", "last_reply_at", "tags"]
    def safe(value):
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text
    async def stream():
        buf = io.StringIO(); writer = csv.writer(buf); writer.writerow(columns)
        yield "\ufeff" + buf.getvalue(); buf.seek(0); buf.truncate(0)
        page = 1
        while True:
            result = await owner_api.all_tickets(
                admin=user, status=status, q=q, intake=intake, priority=priority,
                assignee_id=assignee_id, unanswered=unanswered, date_from=date_from,
                date_to=date_to, sort_by=sort_by, sort_dir=sort_dir, page=page, limit=100)
            rows = result.get("tickets") or []
            for row in rows:
                writer.writerow([safe(v) for v in [row.get("id"), row.get("subject"), row.get("user_id"),
                    row.get("user_name"), row.get("status"), row.get("priority"), row.get("assignee_id"),
                    row.get("assignee_name"), row.get("reply_count"), row.get("created_at"),
                    row.get("last_reply_at"), "|".join(row.get("tags") or [])]])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
            if not rows or page >= int(result.get("pages") or 1): break
            page += 1
    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=humsyar-tickets.csv"})


@router.get("/tickets/assignees")
async def wa_ticket_assignees(user=Depends(_perm_any("tickets.reply", "tickets.manage"))):
    roles = await db.list_roles()
    role_keys = [r.get("_id") for r in roles
                 if r.get("active", True) and set(r.get("perms") or []) & {"tickets.reply", "tickets.manage"}]
    ids = {ADMIN_ID}
    for key in role_keys:
        ids.update(await db.user_ids_by_role(key, limit=100000))
    docs = await db.users.find({"user_id": {"$in": list(ids)}}, {
        "user_id": 1, "name": 1, "username": 1,
    }).sort("name", 1).to_list(100000)
    intakes = await db.get_all_intakes()
    return {"assignees": [{"id": u.get("user_id"), "name": u.get("name", ""),
                             "username": u.get("username", "")} for u in docs],
            "intakes": [{"code": i.get("code", ""), "label": i.get("label", i.get("code", ""))}
                        for i in intakes]}


@router.get("/tickets/{tid}")
async def wa_ticket_detail(
    tid: int,
    user=Depends(_perm_any("tickets.reply", "tickets.manage")),
):
    result = await owner_api.ticket_detail(tid=tid, admin=user)
    raw = await db.ticket_get(tid)
    ticket = result.get("ticket") or {}
    ticket.update({
        "priority": (raw or {}).get("priority", "normal"),
        "tags": (raw or {}).get("tags") or [],
        "assignee_id": (raw or {}).get("assignee_id"),
        "assignee_name": (raw or {}).get("assignee_name", ""),
        "internal_notes": [{
            "id": str(n.get("id") or i), "text": n.get("text", ""),
            "actor_id": n.get("actor_id"), "actor_name": n.get("actor_name", ""),
            "at": (n.get("at") or "")[:16].replace("T", " "),
        } for i, n in enumerate((raw or {}).get("internal_notes") or [])],
    })
    return result


class TicketMetaPatch(BaseModel):
    priority: Optional[str] = None
    tags: Optional[list[str]] = None
    assignee_id: Optional[int] = None


@router.patch("/tickets/{tid}/meta")
async def wa_ticket_meta(
    tid: int, body: TicketMetaPatch,
    user=Depends(_perm("tickets.manage")),
):
    ticket = await db.ticket_get(tid)
    if not ticket:
        raise HTTPException(404, "تیکت پیدا نشد")
    updates = {}
    if body.priority is not None:
        if body.priority not in ("low", "normal", "high", "urgent"):
            raise HTTPException(422, "اولویت نامعتبر است")
        updates["priority"] = body.priority
    if body.tags is not None:
        updates["tags"] = list(dict.fromkeys(
            str(tag).strip()[:30] for tag in body.tags if str(tag).strip()
        ))[:12]
    if "assignee_id" in body.model_fields_set:
        if body.assignee_id is None:
            updates.update({"assignee_id": None, "assignee_name": ""})
        else:
            assignee = await db.get_user(body.assignee_id)
            if not assignee or not await db.has_permission(body.assignee_id, "tickets.reply"):
                raise HTTPException(422, "مسئول انتخابی مجوز پاسخ‌گویی ندارد")
            updates.update({"assignee_id": body.assignee_id,
                            "assignee_name": assignee.get("name", str(body.assignee_id))})
    if not updates:
        raise HTTPException(422, "تغییری ارسال نشده است")
    before = {key: ticket.get(key) for key in updates}
    await db.tickets.update_one({"ticket_id": tid}, {"$set": updates})
    await _audit(user["id"], "ویرایش صف/متادیتای تیکت", severity="WARNING",
                 target_id=tid, target_type="ticket", target_label=ticket.get("subject", ""),
                 before=before, after=updates, tags=["تیکت", "متادیتا", "پنل_وب"])
    return {"ok": True, "changed": list(updates)}


class TicketNoteIn(BaseModel):
    text: str


@router.post("/tickets/{tid}/notes")
async def wa_ticket_note(
    tid: int, body: TicketNoteIn,
    user=Depends(_perm("tickets.manage")),
):
    ticket = await db.ticket_get(tid)
    if not ticket:
        raise HTTPException(404, "تیکت پیدا نشد")
    text = (body.text or "").strip()
    if not (1 <= len(text) <= 1500):
        raise HTTPException(422, "یادداشت باید بین ۱ تا ۱۵۰۰ کاراکتر باشد")
    actor = user.get("_db") or await db.get_user(user["id"]) or {}
    note = {"id": secrets.token_hex(8), "text": text, "actor_id": user["id"],
            "actor_name": actor.get("name", str(user["id"])), "at": _now()}
    await db.tickets.update_one({"ticket_id": tid}, {"$push": {"internal_notes": note}})
    await _audit(user["id"], "افزودن یادداشت داخلی تیکت", severity="INFO",
                 target_id=tid, target_type="ticket", target_label=ticket.get("subject", ""),
                 after={"note_id": note["id"]}, tags=["تیکت", "یادداشت_داخلی", "پنل_وب"])
    return {"ok": True, "note": note}


@router.get("/tickets/analytics/summary")
async def wa_tickets_analytics(user=Depends(_perm("tickets.manage"))):
    docs = await db.tickets.find({}, {
        "status": 1, "priority": 1, "assignee_id": 1, "assignee_name": 1,
        "created_at": 1, "closed_at": 1, "replies": 1,
    }).sort("created_at", -1).limit(5000).to_list(5000)
    status_counts, priority_counts, workload = {}, {}, {}
    response_minutes, resolution_minutes = [], []
    for t in docs:
        status = t.get("status", "open"); status_counts[status] = status_counts.get(status, 0) + 1
        priority = t.get("priority", "normal"); priority_counts[priority] = priority_counts.get(priority, 0) + 1
        if t.get("assignee_id"):
            key = str(t.get("assignee_id")); workload.setdefault(key, {"name": t.get("assignee_name", key), "count": 0})["count"] += 1
        try:
            created = datetime.fromisoformat(t.get("created_at", ""))
            admin_reply = next((r for r in (t.get("replies") or []) if not (r.get("text") or "").startswith("[دانشجو]")), None)
            if admin_reply and admin_reply.get("at"):
                response_minutes.append(max(0, (datetime.fromisoformat(admin_reply["at"]) - created).total_seconds() / 60))
            if t.get("closed_at"):
                resolution_minutes.append(max(0, (datetime.fromisoformat(t["closed_at"]) - created).total_seconds() / 60))
        except (TypeError, ValueError):
            pass
    avg = lambda rows: round(sum(rows) / len(rows), 1) if rows else None
    return {"total": len(docs), "sample_limited": len(docs) == 5000,
            "status": status_counts, "priority": priority_counts,
            "avg_first_response_minutes": avg(response_minutes),
            "avg_resolution_minutes": avg(resolution_minutes),
            "workload": sorted(workload.values(), key=lambda x: x["count"], reverse=True)[:10]}


@router.post("/tickets/{tid}/reply")
async def wa_ticket_reply(
    tid: int,
    body: owner_api.AdminReply,
    user=Depends(_perm("tickets.reply")),
):
    return await owner_api.admin_reply(tid=tid, body=body, admin=user)


@router.post("/tickets/{tid}/close")
async def wa_ticket_close(tid: int, user=Depends(_perm("tickets.manage"))):
    return await owner_api.close_ticket(tid=tid, admin=user)


@router.post("/tickets/{tid}/reopen")
async def wa_ticket_reopen(tid: int, user=Depends(_perm("tickets.manage"))):
    return await owner_api.reopen_ticket(tid=tid, admin=user)


# ── Broadcast / Poll / notification settings ──────────────────────

@router.get("/intakes-picker")
async def wa_intakes_picker(user=Depends(_perm("broadcast.send"))):
    items = await db.get_all_intakes()
    return {"intakes": [
        {"code": i.get("code", ""), "label": i.get("label", i.get("code", "")),
         "active": i.get("active", True)}
        for i in items
    ]}


@router.post("/broadcast/preview")
async def wa_broadcast_preview(
    body: owner_api.BroadcastPreview,
    user=Depends(_perm("broadcast.send")),
):
    return await owner_api.broadcast_preview(body=body, admin=user)


@router.post("/broadcast")
async def wa_broadcast_send(
    body: owner_api.BroadcastSend,
    user=Depends(_perm("broadcast.send")),
):
    return await owner_api.broadcast(body=body, admin=user)


@router.get("/broadcast/options")
async def wa_broadcast_options(user=Depends(_perm("broadcast.send"))):
    """گزینه‌های segment واقعی؛ فقط metadata نقش و وضعیت‌های persisted."""
    roles = await db.list_roles()
    return {"roles": [{"key": r.get("_id"), "label": r.get("label") or r.get("_id")}
                      for r in roles if r.get("_id") and r.get("active", True)],
            "subscription_statuses": [
                {"key": "active", "label": "اشتراک فعال"},
                {"key": "inactive", "label": "بدون اشتراک فعال"},
                {"key": "expiring_7", "label": "پایان اشتراک تا ۷ روز"},
            ]}


@router.get("/broadcast/history")
async def wa_broadcast_history(user=Depends(_perm("broadcast.send"))):
    return await owner_api.broadcast_history(admin=user, limit=20)


@router.get("/broadcast/scheduled")
async def wa_broadcast_scheduled(user=Depends(_perm("broadcast.send"))):
    return await owner_api.broadcast_scheduled(admin=user, limit=10)


@router.post("/broadcast/cancel")
async def wa_broadcast_cancel(
    body: owner_api.BroadcastCancel,
    user=Depends(_perm("broadcast.send")),
):
    return await owner_api.broadcast_cancel(body=body, admin=user)


@router.get("/poll/status")
async def wa_poll_status(user=Depends(_perm("notifications.manage"))):
    return await owner_api.poll_status(admin=user)


@router.post("/poll/channel")
async def wa_poll_channel(
    body: owner_api.PollChannelSet,
    user=Depends(_perm("notifications.manage")),
):
    old = await db.get_setting("poll_channel_id", None)
    result = await owner_api.poll_channel_set(body=body, admin=user)
    await _audit(user["id"], "تغییر کانال نظرسنجی", severity="WARNING",
                 before={"کانال": old}, after={"کانال": body.channel_id.strip()},
                 tags=["نظرسنجی", "پنل_وب"])
    return result


@router.post("/poll")
async def wa_poll_create(
    body: owner_api.PollCreate,
    user=Depends(_perm("notifications.manage")),
):
    return await owner_api.poll_create(body=body, admin=user)


@router.get("/notifications/settings")
async def wa_notif_settings(user=Depends(_perm("notifications.manage"))):
    return await owner_api.notif_settings(admin=user)


@router.post("/notifications/settings")
async def wa_notif_settings_update(
    body: owner_api.NotifSettingsUpdate,
    user=Depends(_perm("notifications.manage")),
):
    return await owner_api.notif_settings_update(body=body, admin=user)


# ── Subscription Control Center (delegated via subscription.manage) ──

@router.get("/subscription/overview")
async def wa_subscription_overview(user=Depends(_perm("subscription.manage"))):
    return await subscription_api.overview(admin=user)


@router.get("/subscription/payments")
async def wa_subscription_payments(
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    search: Optional[str] = Query(None),
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.payments(
        status=status, skip=skip, limit=limit, search=search, admin=user)


@router.post("/subscription/payments/{payment_id}/decision")
async def wa_subscription_decision(
    payment_id: str,
    body: subscription_api.DecisionBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.decide_payment(
        payment_id=payment_id, body=body, admin=user)


@router.get("/subscription/payments/{payment_id}/receipt")
async def wa_subscription_receipt(
    payment_id: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.payment_receipt(payment_id=payment_id, admin=user)


@router.get("/subscription/discounts")
async def wa_subscription_discounts(user=Depends(_perm("subscription.manage"))):
    return await subscription_api.discounts(admin=user)


@router.patch("/subscription/settings")
async def wa_subscription_settings(
    body: subscription_api.SubscriptionSettingsBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.update_subscription_settings(body=body, admin=user)


@router.post("/subscription/plans")
async def wa_subscription_plan_add(
    body: subscription_api.PlanBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.add_plan(body=body, admin=user)


@router.put("/subscription/plans/{plan_id}")
async def wa_subscription_plan_update(
    plan_id: str,
    body: subscription_api.PlanBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.update_plan(plan_id=plan_id, body=body, admin=user)


@router.post("/subscription/plans/{plan_id}/toggle")
async def wa_subscription_plan_toggle(
    plan_id: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.toggle_plan(plan_id=plan_id, admin=user)


@router.delete("/subscription/plans/{plan_id}")
async def wa_subscription_plan_delete(
    plan_id: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.delete_plan(plan_id=plan_id, admin=user)


@router.post("/subscription/payments/{payment_id}/send-receipt")
async def wa_subscription_send_receipt(
    payment_id: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.send_receipt(payment_id=payment_id, admin=user)


@router.get("/subscription/subscribers")
async def wa_subscription_subscribers(
    status: str = Query("active"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.subscribers(
        status=status, skip=skip, limit=limit, search=search, admin=user)


@router.get("/subscription/subscribers/{user_id}")
async def wa_subscription_subscriber_detail(
    user_id: int,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.subscriber_detail(user_id=user_id, admin=user)


@router.get("/subscription/users/search")
async def wa_subscription_user_search(
    q: str = Query("", max_length=80),
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.search_users_for_grant(q=q, admin=user)


@router.post("/subscription/subscribers/grant")
async def wa_subscription_grant(
    body: subscription_api.GrantBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.grant_subscription(body=body, admin=user)


@router.post("/subscription/subscribers/grant-bulk")
async def wa_subscription_grant_bulk(
    body: subscription_api.BulkGrantBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.grant_subscription_bulk(body=body, admin=user)


@router.post("/subscription/subscribers/{user_id}/revoke")
async def wa_subscription_revoke(
    user_id: int,
    body: subscription_api.RevokeBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.revoke_subscription(
        user_id=user_id, body=body, admin=user)


@router.post("/subscription/discounts")
async def wa_subscription_discount_add(
    body: subscription_api.DiscountBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.add_discount(body=body, admin=user)


@router.post("/subscription/discounts/{code}/toggle")
async def wa_subscription_discount_toggle(
    code: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.toggle_discount(code=code, admin=user)


@router.delete("/subscription/discounts/{code}")
async def wa_subscription_discount_delete(
    code: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.delete_discount(code=code, admin=user)


@router.post("/subscription/discounts/{code}/preview")
async def wa_subscription_discount_preview(
    code: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.preview_discount_campaign(code=code, admin=user)


@router.post("/subscription/discounts/{code}/broadcast")
async def wa_subscription_discount_broadcast(
    code: str,
    body: subscription_api.DiscountBroadcastBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.start_discount_broadcast(code=code, body=body, admin=user)


@router.get("/subscription/discounts/{code}/broadcast/{bid}")
async def wa_subscription_discount_broadcast_status(
    code: str, bid: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.discount_broadcast_status(code=code, bid=bid, admin=user)


@router.post("/subscription/discounts/{code}/broadcast/{bid}/cancel")
async def wa_subscription_discount_broadcast_cancel(
    code: str, bid: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.cancel_discount_broadcast(code=code, bid=bid, admin=user)


@router.get("/subscription/discounts/{code}/broadcasts")
async def wa_subscription_discount_broadcasts(
    code: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.discount_broadcasts_list(code=code, admin=user)


@router.get("/subscription/discounts/{code}/stats")
async def wa_subscription_discount_stats(
    code: str,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.discount_stats(code=code, admin=user)


@router.put("/subscription/card")
async def wa_subscription_card(
    body: subscription_api.CardBody,
    user=Depends(_perm("subscription.manage")),
):
    return await subscription_api.update_card(body=body, admin=user)


# ── AI Admin ───────────────────────────────────────────────────────

@router.get("/ai/config")
async def wa_ai_config(user=Depends(_perm("ai.manage"))):
    return await ai_admin_api.config(admin=user)


@router.put("/ai/config")
async def wa_ai_config_update(
    body: ai_admin_api.ConfigUpdate,
    user=Depends(_perm("ai.manage")),
):
    before = await ai_admin_api.config(admin=user)
    result = await ai_admin_api.update_config(body=body, admin=user)
    after = await ai_admin_api.config(admin=user)
    await _audit(user["id"], "به‌روزرسانی تنظیمات هوشیار", severity="HIGH",
                 before={k: before.get(k) for k in ("enabled", "provider", "model", "daily_limit", "thinking")},
                 after={k: after.get(k) for k in ("enabled", "provider", "model", "daily_limit", "thinking")},
                 tags=["هوشیار", "پیکربندی", "پنل_وب"])
    return result


@router.get("/ai/stats")
async def wa_ai_stats(user=Depends(_perm("ai.manage"))):
    return await ai_admin_api.stats(admin=user)


@router.get("/ai/reports")
async def wa_ai_reports(
    limit: int = Query(30, ge=1, le=100),
    user=Depends(_perm("ai.manage")),
):
    return await ai_admin_api.reports(limit=limit, admin=user)


@router.get("/ai/banned")
async def wa_ai_banned(user=Depends(_perm("ai.manage"))):
    return await ai_admin_api.banned(admin=user)


@router.get("/ai/users")
async def wa_ai_users(
    q: str = Query(..., min_length=2, max_length=100),
    user=Depends(_perm("ai.manage")),
):
    return await ai_admin_api.users(q=q, admin=user)


@router.post("/ai/users/ban")
async def wa_ai_ban(
    body: ai_admin_api.UserAction,
    user=Depends(_perm("ai.manage")),
):
    target = await db.get_user(body.user_id)
    result = await ai_admin_api.toggle_ban(body=body, admin=user)
    await _audit(user["id"], "تغییر دسترسی کاربر به هوشیار", severity="HIGH",
                 target_id=body.user_id, target_type="user",
                 target_label=(target or {}).get("name", str(body.user_id)),
                 before={"مسدود": bool((target or {}).get("ai_banned"))},
                 after={"مسدود": bool(result.get("banned"))},
                 tags=["هوشیار", "دسترسی", "پنل_وب"])
    return result


@router.post("/ai/users/reset-quota")
async def wa_ai_reset_quota(
    body: ai_admin_api.UserAction,
    user=Depends(_perm("ai.manage")),
):
    target = await db.get_user(body.user_id)
    result = await ai_admin_api.reset_quota(body=body, admin=user)
    await _audit(user["id"], "صفرکردن سهمیه روزانه هوشیار", severity="WARNING",
                 target_id=body.user_id, target_type="user",
                 target_label=(target or {}).get("name", str(body.user_id)),
                 tags=["هوشیار", "سهمیه", "پنل_وب"])
    return result


# ── Audit ──────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def wa_audit_logs(
    category: Optional[str] = Query(None),
    min_severity: Optional[str] = Query(None),
    q: Optional[str] = Query(None), actor: Optional[str] = Query(None),
    actor_role: Optional[str] = Query(None), module: Optional[str] = Query(None),
    action: Optional[str] = Query(None), target_type: Optional[str] = Query(None),
    target: Optional[str] = Query(None), date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None), correlation_id: Optional[str] = Query(None),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
    user=Depends(_perm("audit.view")),
):
    return await owner_api.audit_logs_admin(
        admin=user, category=category, min_severity=min_severity, q=q,
        actor=actor, actor_role=actor_role, module=module, action=action,
        target_type=target_type, target=target, date_from=date_from,
        date_to=date_to, correlation_id=correlation_id, sort_dir=sort_dir,
        skip=skip, limit=limit)


@router.get("/exports/audit.csv")
async def export_audit_csv(
    category: Optional[str] = Query(None), min_severity: Optional[str] = Query(None),
    q: Optional[str] = Query(None), actor: Optional[str] = Query(None),
    actor_role: Optional[str] = Query(None), module: Optional[str] = Query(None),
    action: Optional[str] = Query(None), target_type: Optional[str] = Query(None),
    target: Optional[str] = Query(None), date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None), correlation_id: Optional[str] = Query(None),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user=Depends(_perm("audit.view")),
):
    """CSV سرورساید و filter-aware برای 100k+ audit؛ بدون blobسازی dataset در React."""
    query = owner_api.build_audit_query(
        category=category, min_severity=min_severity, q=q, actor=actor,
        actor_role=actor_role, module=module, action=action,
        target_type=target_type, target=target, date_from=date_from,
        date_to=date_to, correlation_id=correlation_id)
    await _audit(user["id"], "خروجی CSV حسابرسی", severity="HIGH",
                 target_type="export", target_label="audit.csv",
                 after={"filters": {k: v for k, v in {
                     "category": category, "min_severity": min_severity, "q": q,
                     "actor": actor, "module": module, "target": target,
                     "date_from": date_from, "date_to": date_to,
                     "correlation_id": correlation_id}.items() if v}},
                 tags=["خروجی", "حسابرسی", "پنل_وب"])
    columns = ["timestamp", "severity", "category", "module", "action",
               "actor_id", "actor_name", "actor_role", "target_type", "target_id",
               "target_label", "correlation_id", "details"]

    def safe(value):
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text

    async def stream():
        buf = io.StringIO(); writer = csv.writer(buf)
        writer.writerow(columns)
        yield "\ufeff" + buf.getvalue(); buf.seek(0); buf.truncate(0)
        offset = 0
        while True:
            docs = await db.audit_logs.find(query).sort("timestamp", 1 if sort_dir == "asc" else -1).skip(offset).limit(500).to_list(500)
            if not docs: break
            for row in docs:
                actor_doc, target_doc = row.get("actor") or {}, row.get("target") or {}
                writer.writerow([safe(v) for v in [
                    row.get("timestamp"), row.get("severity"), row.get("category"), row.get("module"),
                    row.get("action"), actor_doc.get("id"), actor_doc.get("name"), actor_doc.get("role"),
                    target_doc.get("type") or row.get("target_type"),
                    target_doc.get("id") or row.get("target_id"),
                    target_doc.get("label") or row.get("target_label"),
                    row.get("correlation_id"), row.get("details")]])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
            if len(docs) < 500: break
            offset += len(docs)

    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=humsyar-audit.csv"})


# ── System / Backup / Prestige ─────────────────────────────────────

@router.get("/system/status")
async def wa_system_status(
    user=Depends(_perm_any(
        "system.manage", "backup.manage", "prestige.manage",
        "settings.manage", "notifications.manage")),
):
    out = await owner_api.bot_status(admin=user)
    perms = await db.get_user_perms(user["id"])
    allow = lambda *keys: user["id"] == ADMIN_ID or any(k in perms for k in keys)
    if allow("notifications.manage", "system.manage"):
        try:
            recent = await db.get_recent_notif_runs(limit=10)
            out["notifications"] = {
                "pending_queue": await db.bot_notifs.count_documents({"sent": False}),
                "recent_failed_runs": sum(1 for r in recent if int(r.get("failed") or 0) > 0),
                "last_run": (recent[0].get("started_at") if recent else None),
            }
        except Exception:
            out["notifications"] = None
    if allow("backup.manage", "system.manage"):
        out["backup"] = {
            "enabled": bool(await db.get_setting("auto_backup_enabled", False)),
            "last_run": await db.get_setting("auto_backup_last_run", None),
            "hour": int(await db.get_setting("auto_backup_hour", 3) or 3),
        }
    return out


@router.get("/system/observability")
async def wa_system_observability(hours: int = Query(24, ge=1, le=720),
                                  user=Depends(_perm("system.manage"))):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    match = {"at": {"$gte": since}}
    total, errors = await asyncio.gather(
        db.wa_api_metrics.count_documents(match),
        db.wa_api_metrics.count_documents({**match, "status": {"$gte": 400}}),
    )
    rows = await db.wa_api_metrics.aggregate([
        {"$match": match},
        {"$group": {"_id": "$route", "requests": {"$sum": 1},
                    "errors": {"$sum": {"$cond": [{"$gte": ["$status", 400]}, 1, 0]}},
                    "avg_ms": {"$avg": "$duration_ms"}, "max_ms": {"$max": "$duration_ms"}}},
        {"$sort": {"requests": -1}}, {"$limit": 50},
    ]).to_list(50)
    recent = await db.wa_api_metrics.find({"at": {"$gte": since}, "status": {"$gte": 400}}, {
        "route": 1, "method": 1, "status": 1, "duration_ms": 1, "request_id": 1, "at": 1,
    }).sort("at", -1).limit(30).to_list(30)
    total, errors = int(total or 0), int(errors or 0)
    return {"hours": hours, "total": total, "errors": errors,
            "error_rate": round(errors * 100 / total, 2) if total else None,
            "routes": [{"route": row.get("_id"), "requests": row.get("requests", 0),
                        "errors": row.get("errors", 0), "avg_ms": round(float(row.get("avg_ms") or 0), 2),
                        "max_ms": round(float(row.get("max_ms") or 0), 2)} for row in rows],
            "recent_errors": [{**{key: item.get(key) for key in
                                ("route", "method", "status", "duration_ms", "request_id")},
                               "at": item.get("at").isoformat() if hasattr(item.get("at"), "isoformat") else str(item.get("at") or "")}
                              for item in recent],
            "retention_days": 30, "persisted": True}


@router.get("/system/jobs")
async def wa_system_jobs(
    user=Depends(_perm_any("system.manage", "notifications.manage", "backup.manage")),
):
    """Job center فقط از queue/run/settings واقعی؛ هیچ scheduler ساختگی ندارد."""
    perms = await db.get_user_perms(user["id"])
    allow = lambda *keys: user["id"] == ADMIN_ID or any(k in perms for k in keys)
    jobs = []
    if allow("notifications.manage", "system.manage"):
        runs = await db.get_recent_notif_runs(limit=20)
        grouped = {}
        for run in runs:
            name = run.get("job_name") or "notification"
            grouped.setdefault(name, run)
        for name, run in grouped.items():
            jobs.append({
                "key": f"notif:{name}", "label": name, "kind": "notification",
                "status": run.get("status", "unknown"),
                "sent": int(run.get("sent") or 0), "failed": int(run.get("failed") or 0),
                "total": int(run.get("total") or 0),
                "last_run": (run.get("started_at") or "")[:16].replace("T", " "),
            })
        queue = await db.bot_notifs.count_documents({"sent": False})
        scheduled = await db.bot_notifs.count_documents({
            "sent": False, "send_at": {"$exists": True, "$ne": None},
        })
        jobs.append({"key": "outbox", "label": "صف خروجی ربات", "kind": "queue",
                     "status": "pending" if queue else "idle", "pending": queue,
                     "scheduled": scheduled})
    if allow("backup.manage", "system.manage"):
        enabled = bool(await db.get_setting("auto_backup_enabled", False))
        jobs.append({"key": "backup", "label": "پشتیبان خودکار", "kind": "backup",
                     "status": "enabled" if enabled else "disabled",
                     "hour": int(await db.get_setting("auto_backup_hour", 3) or 3),
                     "last_run": await db.get_setting("auto_backup_last_run", None)})
    return {"jobs": jobs, "checked_at": _now()}


@router.get("/system/backup-settings")
async def wa_backup_settings(user=Depends(_perm("backup.manage"))):
    return {
        "auto_backup_enabled": bool(await db.get_setting("auto_backup_enabled", False)),
        "auto_backup_hour": int(await db.get_setting("auto_backup_hour", 3) or 0),
        "auto_backup_last_run": await db.get_setting("auto_backup_last_run", None),
    }


class WaBackupSettingsPatch(BaseModel):
    auto_backup_enabled: Optional[bool] = None
    auto_backup_hour: Optional[int] = None


@router.patch("/system/backup-settings")
async def wa_backup_settings_patch(
    body: WaBackupSettingsPatch,
    user=Depends(_perm("backup.manage")),
):
    owner_body = owner_api.BotSettingsPatch(
        auto_backup_enabled=body.auto_backup_enabled,
        auto_backup_hour=body.auto_backup_hour,
    )
    return await owner_api.bot_settings_patch(body=owner_body, admin=user)


async def _read_restore_upload(file: UploadFile):
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(422, "فقط فایل JSON پشتیبان پذیرفته می‌شود")
    raw = await file.read(50 * 1024 * 1024 + 1)
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "حجم فایل پشتیبان بیشتر از ۵۰MB است")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(422, "فایل JSON معتبر نیست")
    if not isinstance(data, dict) or not data.get("backup_version"):
        raise HTTPException(422, "ساختار فایل پشتیبان شناخته‌شده نیست")
    section = data.get("section", "full")
    sections = data.get("sections") or {section: data}
    if not isinstance(sections, dict) or not sections:
        raise HTTPException(422, "فایل هیچ بخش قابل بازیابی ندارد")
    known = {"users", "basic_science", "content", "references", "refs", "qbank",
             "schedules", "faq", "tickets", "access_control", "access",
             "subscription_system", "subscription", "grades", "settings", "logs", "stats"}
    unknown = [key for key in sections if key not in known]
    if unknown:
        raise HTTPException(422, f"بخش ناشناخته در پشتیبان: {', '.join(unknown[:5])}")
    digest = hashlib.sha256(raw).hexdigest()
    return data, sections, digest, len(raw)


def _backup_section_count(value):
    if not isinstance(value, dict):
        return 0
    if isinstance(value.get("count"), int):
        return value["count"]
    return sum(_backup_section_count(v) for v in value.values() if isinstance(v, dict))


@router.post("/system/restore/validate")
async def wa_restore_validate(
    file: UploadFile = File(...), user=Depends(_guard_any_admin),
):
    if user["id"] != ADMIN_ID:
        raise HTTPException(403, "owner_only")
    data, sections, digest, size = await _read_restore_upload(file)
    return {"valid": True, "digest": digest, "size": size,
            "backup_version": data.get("backup_version"),
            "created_at": (data.get("created_at") or "")[:19],
            "sections": [{"key": key, "records": _backup_section_count(value)}
                         for key, value in sections.items()]}


@router.post("/system/restore/confirm")
async def wa_restore_confirm(
    file: UploadFile = File(...), digest: str = Form(...),
    confirmation: str = Form(...), user=Depends(_guard_any_admin),
):
    if user["id"] != ADMIN_ID:
        raise HTTPException(403, "owner_only")
    if confirmation.strip() != "RESTORE HUMSYAR":
        raise HTTPException(422, "عبارت تأیید بازیابی صحیح نیست")
    _data, sections, actual_digest, _size = await _read_restore_upload(file)
    if not secrets.compare_digest(actual_digest, digest.strip().lower()):
        raise HTTPException(409, "فایل با نسخه‌ی اعتبارسنجی‌شده یکسان نیست")
    restored = {}
    for key, value in sections.items():
        restored[key] = await backup_service._restore_section(key, value)
    await _audit(user["id"], "بازیابی فایل پشتیبان از Web Admin", severity="CRITICAL",
                 target_id=actual_digest[:16], target_type="backup",
                 target_label=", ".join(sections.keys()),
                 after={"sections": len(restored), "records": sum(restored.values())},
                 tags=["بازیابی_بکاپ", "پنل_وب"])
    return {"ok": True, "restored": restored, "total": sum(restored.values())}


@router.post("/system/backup")
async def wa_backup_request(
    body: owner_api.BackupRequestBody,
    user=Depends(_perm("backup.manage")),
):
    return await owner_api.request_backup(body=body, admin=user)


@router.post("/system/export/excel")
async def wa_export_excel(user=Depends(_perm("backup.manage"))):
    await db.bot_notifs.insert_one({
        "type": "excel_export_request", "chat_id": user["id"],
        "text": "__EXCEL_EXPORT__", "sent": False, "created_at": _now(),
    })
    await _audit(user["id"], "درخواست خروجی اکسل کامل", severity="HIGH",
                 tags=["اکسل", "خروجی", "پنل_وب"])
    return {"ok": True, "message": "📊 فایل اکسل از طریق ربات برای شما ارسال می‌شود."}


@router.post("/system/prestige/backfill")
async def wa_prestige_backfill(user=Depends(_perm("prestige.manage"))):
    return await owner_api.prestige_backfill(admin=user)


@router.get("/system/prestige-config")
async def wa_prestige_config(user=Depends(_perm("prestige.manage"))):
    return await owner_api.prestige_config_get(admin=user)


@router.put("/system/prestige-config")
async def wa_prestige_config_update(
    body: owner_api.PrestigeConfigPut,
    user=Depends(_perm("prestige.manage")),
):
    return await owner_api.prestige_config_put(body=body, admin=user)


@router.post("/system/notifications/force-send")
async def wa_force_resources(user=Depends(_perm("notifications.manage"))):
    return await owner_api.notifications_force_send(admin=user)


@router.post("/system/log-groups/test")
async def wa_log_groups_test(
    user=Depends(_perm_any("settings.manage", "system.manage")),
):
    return await owner_api.log_groups_test(admin=user)


# ── Content reports: تاریخچه و workflow برای reports.review ───────

@router.get("/content/reports")
async def wa_content_reports(
    status: Optional[str] = Query(None), skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    user=Depends(_perm("reports.review")),
):
    return await content_api.reports_list_ep(
        status=status, skip=skip, limit=limit, admin=user)


@router.get("/content/reports/stats")
async def wa_content_report_stats(user=Depends(_perm("reports.review"))):
    return await content_api.reports_stats_ep(admin=user)


@router.post("/content/reports/{rid}/status")
async def wa_content_report_status(
    rid: int, body: content_api.ReportStatusUpdate,
    user=Depends(_perm("reports.review")),
):
    return await content_api.report_status_ep(rid=rid, body=body, admin=user)


# ── Schedule: کلاس/امتحان/جبرانی برای schedules.manage ────────────

@router.get("/schedule")
async def wa_schedule_list(
    stype: Optional[str] = Query(None),
    user=Depends(_perm("schedules.manage")),
):
    return await content_api.schedule_list(admin=user, stype=stype)


@router.post("/schedule")
async def wa_schedule_create(
    body: content_api.ScheduleCreate,
    user=Depends(_perm("schedules.manage")),
):
    return await content_api.add_schedule(body=body, admin=user)


@router.patch("/schedule/{sid}")
async def wa_schedule_update(
    sid: str,
    body: content_api.ScheduleUpdate,
    user=Depends(_perm("schedules.manage")),
):
    return await content_api.edit_schedule(sid=sid, body=body, admin=user)


@router.delete("/schedule/{sid}")
async def wa_schedule_delete(
    sid: str,
    user=Depends(_perm("schedules.manage")),
):
    return await content_api.del_schedule(sid=sid, admin=user)


@router.post("/schedule/{sid}/flex-change")
async def wa_schedule_flex_change(
    sid: str,
    body: content_api.FlexChange,
    user=Depends(_perm("schedules.manage")),
):
    return await content_api.flex_change(sid=sid, body=body, admin=user)


# ── Grades: global/scoped permissions ──────────────────────────────

async def _grade_intake_scope(user: dict) -> Optional[str]:
    if await db.has_permission(user["id"], "grades.manage"):
        return None
    if await db.has_permission(user["id"], "grades.scoped"):
        scope = await db.get_scoped_intake(user["id"])
        if scope:
            return scope
        info = await db.get_user_roles(user["id"])
        if info.get("scope_intake"):
            return info["scope_intake"]
    raise HTTPException(403, "grade_scope_missing")


@router.get("/grades/recent")
async def wa_grades_recent(
    skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
    q: Optional[str] = Query(None, max_length=100),
    lesson: Optional[str] = Query(None, max_length=100),
    group: Optional[str] = Query(None, max_length=20), intake: Optional[str] = Query(None, max_length=80),
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    user=Depends(_perm_any("grades.manage", "grades.scoped")),
):
    requested_intake = intake if isinstance(intake, str) else None
    date_from = date_from if isinstance(date_from, str) else None
    date_to = date_to if isinstance(date_to, str) else None
    scoped_intake = await _grade_intake_scope(user)
    if scoped_intake is not None and requested_intake not in (None, "", scoped_intake):
        raise HTTPException(403, "intake_out_of_scope")
    effective_intake = scoped_intake if scoped_intake is not None else requested_intake
    return await academic_api.grades_recent(
        skip=skip, limit=limit, intake=effective_intake, group=group,
        q=q, lesson=lesson, date_from=date_from, date_to=date_to, admin=user)


@router.get("/grades/intakes")
async def wa_grades_intakes(user=Depends(_perm_any("grades.manage", "grades.scoped"))):
    scoped = await _grade_intake_scope(user)
    items = await db.get_all_intakes()
    return {"scope_intake": scoped, "intakes": [{"code": item.get("code", ""),
             "label": item.get("label", item.get("code", ""))} for item in items
             if item.get("active", True) and (scoped is None or item.get("code") == scoped)]}


@router.get("/grades/find-student")
async def wa_grades_find_student(
    q: str = Query(..., min_length=2, max_length=100),
    user=Depends(_perm_any("grades.manage", "grades.scoped")),
):
    intake = await _grade_intake_scope(user)
    users = await db.search_users(q.strip())
    return {"students": [
        {"id": s.get("user_id"), "name": s.get("name", ""),
         "student_id": s.get("student_id", ""), "group": s.get("group", ""),
         "intake": s.get("intake", "")}
        for s in users
        if s.get("approved") and (intake is None or s.get("intake") == intake)
    ]}


@router.post("/grades/bulk")
async def wa_grades_bulk(
    body: academic_api.GradeBulkCreate,
    user=Depends(_perm_any("grades.manage", "grades.scoped")),
):
    intake = await _grade_intake_scope(user)
    if intake is not None:
        ids = [e.user_id for e in body.entries]
        matched = await db.users.find(
            {"user_id": {"$in": ids}, "approved": True, "intake": intake},
            {"user_id": 1}).to_list(len(ids))
        if {u.get("user_id") for u in matched} != set(ids):
            raise HTTPException(403, "grade_intake_out_of_scope")
    return await academic_api.grades_bulk_create(body=body, admin=user)


async def _grade_for_actor(grade_id: str, user: dict) -> dict:
    grade = await db.grade_get(grade_id)
    if not grade:
        raise HTTPException(404, "نمره پیدا نشد")
    intake = await _grade_intake_scope(user)
    if intake is not None:
        student = await db.get_user(grade.get("student_id"))
        if not student or student.get("intake") != intake:
            raise HTTPException(403, "grade_intake_out_of_scope")
    return grade


@router.patch("/grades/{grade_id}")
async def wa_grade_update(
    grade_id: str, body: academic_api.GradeUpdate,
    user=Depends(_perm_any("grades.manage", "grades.scoped")),
):
    await _grade_for_actor(grade_id, user)
    return await academic_api.grade_update(
        grade_id=grade_id, body=body, admin=user)


@router.delete("/grades/{grade_id}")
async def wa_grade_delete(
    grade_id: str,
    user=Depends(_perm_any("grades.manage", "grades.scoped")),
):
    await _grade_for_actor(grade_id, user)
    return await academic_api.grade_delete(grade_id=grade_id, admin=user)
