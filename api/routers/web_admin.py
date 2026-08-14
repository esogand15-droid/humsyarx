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
import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta, date

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from typing import Optional

from api.auth import (
    ADMIN_ID, _hash_token, get_current_user, get_content_admin_user,
    get_content_global_user, new_session_token, resolve_content_intake,
    resolve_web_session, WA_SESSION_COOKIE, WA_SESSION_TTL_H,
)
from database import db

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
    return datetime.utcnow().isoformat()


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
    """کارت‌های داشبورد — فقط خواندنی، از سرویس‌های موجود db."""
    pending_users = await db.pending_users()
    pending_pays = await db.sub_payment_list_pending()
    pending_qs = await db.pending_questions()
    total_users = await db.users.count_documents({})
    open_tickets = await db.tickets.count_documents({"status": "open"})
    sub_stats = await db.sub_stats()
    return {
        "total_users": total_users,
        "pending_users": len(pending_users),
        "pending_payments": len(pending_pays),
        "pending_questions": len(pending_qs),
        "open_tickets": open_tickets,
        "active_subs": (sub_stats or {}).get("active", 0),
        "expiring_soon": (sub_stats or {}).get("expiring", 0),
    }


@router.get("/users")
async def users_table(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    q: str | None = Query(None),
    intake: str | None = Query(None),
    group: str | None = Query(None),
    status: str | None = Query(None),   # pending | suspended | active
    user=Depends(_guard_any_admin),
):
    """جدول سرورساید کاربران — pagination واقعی (تا ۱۰۰ در صفحه)."""
    filt = db.build_user_search_query(q) if q else {}
    if intake:
        filt["intake"] = intake
    if group:
        filt["group"] = group
    if status == "pending":
        filt["approved"] = False
    elif status == "suspended":
        filt["suspended"] = True
    elif status == "active":
        filt["approved"] = True
        filt["suspended"] = {"$ne": True}
    total = await db.users.count_documents(filt)
    _projection = {
        "user_id": 1, "name": 1, "nickname": 1, "username": 1, "student_id": 1,
        "group": 1, "intake": 1, "role": 1, "approved": 1, "suspended": 1,
        "registered_at": 1, "total_answers": 1, "prestige_rank": 1, "prestige_div": 1,
    }
    docs = await (db.users.find(filt, _projection)
                  .sort("registered_at", -1)
                  .skip((page - 1) * per_page).limit(per_page).to_list(per_page))
    return {
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "users": [{
            "id": u.get("user_id"), "name": u.get("name", ""),
            "nickname": u.get("nickname"), "username": u.get("username", ""),
            "display_name": db.display_name_of(u),
            "student_id": u.get("student_id", ""), "group": u.get("group", ""),
            "intake": u.get("intake", ""), "role": u.get("role", "student"),
            "approved": u.get("approved", False), "suspended": u.get("suspended", False),
            "registered_at": u.get("registered_at", "")[:10],
            "total_answers": u.get("total_answers", 0),
            "rank": u.get("prestige_rank", ""), "div": u.get("prestige_div", ""),
        } for u in docs],
    }


@router.post("/users/bulk")
async def users_bulk(body: BulkBody, user=Depends(_guard_any_admin)):
    """اکشن گروهی کاربران (سقف ۱۰۰).
    🛡 WA2.9 — هر اکشن به مجوز متناظر RBAC محدود شد (تصمیم فقط با Permission):
    approve/set_intake → users.manage ، suspend/unsuspend → users.suspend"""
    _ACTION_PERM = {
        "approve":   "users.manage",
        "set_intake": "users.manage",
        "suspend":   "users.suspend",
        "unsuspend": "users.suspend",
    }
    need = _ACTION_PERM.get(body.action)
    if not need:
        raise HTTPException(400, "اکشن نامعتبر است.")
    actor = user["id"]
    if not await db.has_permission(actor, need):
        raise HTTPException(403, "forbidden")
    ids = [int(i) for i in (body.ids or []) if isinstance(i, (int, str)) and str(i).isdigit()][:100]
    if not ids:
        raise HTTPException(400, "لیست کاربران خالی است.")
    if ADMIN_ID in ids:
        ids.remove(ADMIN_ID)
    done = 0
    for uid in ids:
        u = await db.get_user(uid)
        if not u:
            continue
        if body.action == "approve":
            await db.update_user(uid, {"approved": True})
            await db.inbox_add(uid, 'account', "✅ حسابت تأیید شد!",
                               "اکنون به تمام بخش‌های هامزیار دسترسی داری — خوش اومدی! 🎓", link='/')
        elif body.action == "suspend":
            await db.update_user(uid, {"suspended": True, "approved": False})
        elif body.action == "unsuspend":
            await db.update_user(uid, {"suspended": False, "approved": True})
        elif body.action == "set_intake":
            await db.update_user(uid, {"intake": (body.value or "").strip()})
        done += 1
    fa = {"approve": "تأیید گروهی", "suspend": "تعلیق گروهی",
          "unsuspend": "رفع تعلیق گروهی", "set_intake": "تغییر ورودی گروهی"}
    await _audit(actor, f"{fa.get(body.action, body.action)} کاربران ({done} نفر)",
                 severity="HIGH" if body.action == "suspend" else "INFO",
                 target_label=f"{done} کاربر", tags=["bulk_users", "پنل_وب"])
    return {"ok": True, "done": done}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.7 — «نیازمند اقدام» + فید فعالیت واقعی
# ══════════════════════════════════════════════════════════════════

@router.get("/attention")
async def attention(user=Depends(_guard_any_admin)):
    """⚠️ صف‌های نیازمند اقدام — هر آیتم مستقیم به صف کلیک می‌شود (Client-side)."""
    pend_users = await db.users.count_documents({"approved": False, "suspended": {"$ne": True}})
    pend_pays = len(await db.sub_payment_list_pending())
    pend_qs = await db.questions.count_documents({"approved": False})
    open_ticks = await db.tickets.count_documents({"status": "open"})
    pend_reports = 0
    try:
        pend_reports = await db.content_reports.count_documents({"status": "new"}) \
            + await db.content_reports.count_documents({"status": "pending"})
    except Exception:
        pass
    last_backup = await db.get_setting("auto_backup_last_run", None)
    items = [
        {"key": "payments", "icon": "🧾", "label": "رسید پرداخت در انتظار بررسی",
         "count": pend_pays, "go": "/subscriptions", "urgent": pend_pays > 0},
        {"key": "tickets", "icon": "🎫", "label": "تیکت بدون پاسخ",
         "count": open_ticks, "go": "/tickets", "urgent": open_ticks > 0},
        {"key": "questions", "icon": "🧪", "label": "سؤال در انتظار بازبینی",
         "count": pend_qs, "go": "/questions", "urgent": pend_qs > 0},
        {"key": "users", "icon": "🧑‍🎓", "label": "کاربر در انتظار تأیید",
         "count": pend_users, "go": "/users?status=pending", "urgent": pend_users > 0},
        {"key": "reports", "icon": "🚩", "label": "گزارش محتوا/سؤال در انتظار",
         "count": pend_reports, "go": "/content", "urgent": pend_reports > 0},
    ]
    return {"items": items,
            "backup": {"last_run": last_backup,
                       "enabled": bool(await db.get_setting("auto_backup_enabled", False))}}


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


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.5 — جست‌وجوی سراسری سریع (Command Palette)
# ══════════════════════════════════════════════════════════════════

@router.get("/search")
async def global_quick_search(q: str = Query(..., min_length=2, max_length=80),
                              user=Depends(_guard_any_admin)):
    """🔎 یک جست‌وجوی واحد روی موجودیت‌های کلیدی سامانه (گروه‌بندی‌شده)."""
    query = " ".join(q.split())[:80]
    rx = {"$regex": re.escape(query), "$options": "i"}
    res = {"users": [], "tickets": [], "questions": [], "content": [], "audit": []}

    try:
        filt = db.build_user_search_query(query)
        us = await db.users.find(filt).sort("registered_at", -1).limit(6).to_list(6)
        res["users"] = [{
            "id": u.get("user_id"), "name": u.get("name", ""),
            "student_id": u.get("student_id", ""), "intake": u.get("intake", ""),
            "username": u.get("username", ""),
        } for u in us]
    except Exception:
        pass

    try:
        ts = await db.tickets.find({"subject": rx}).sort("created_at", -1).limit(5).to_list(5)
        res["tickets"] = [{
            "id": t.get("ticket_id"), "subject": t.get("subject", ""),
            "status": t.get("status", ""), "user_name": t.get("user_name", ""),
        } for t in ts]
    except Exception:
        pass

    try:
        qs = await db.questions.find({"question": rx}).sort("created_at", -1).limit(5).to_list(5)
        res["questions"] = [{
            "id": str(x.get("_id", "")), "text": (x.get("question", "") or "")[:90],
            "lesson": x.get("lesson", ""), "topic": x.get("topic", ""),
            "approved": bool(x.get("approved")),
        } for x in qs]
    except Exception:
        pass

    try:
        rs = await db.search_resources(query, intake=None)
        res["content"] = [{
            "title": r.get("title") or r.get("description") or "",
            "type": r.get("type", ""), "path": r.get("path", ""),
        } for r in (rs or [])[:5]]
    except Exception:
        pass

    try:
        al = await db.audit_logs.find({"$or": [{"action": rx}, {"actor.name": rx}]}) \
                              .sort("timestamp", -1).limit(5).to_list(5)
        res["audit"] = [{
            "id": str(a.get("_id", "")), "action": a.get("action", ""),
            "actor": (a.get("actor") or {}).get("name", ""),
            "at": (a.get("timestamp") or "")[:16].replace("T", " "),
        } for a in al]
    except Exception:
        pass
    return {"q": query, **res}


# ══════════════════════════════════════════════════════════════════
# 🌊 WA2.4 — فیلترهای ذخیره‌شده + اکشن گروهی تیکت/سؤال
# ══════════════════════════════════════════════════════════════════

class SavedFilterIn(BaseModel):
    name: str
    scope: str            # users | questions | content | audit | payments
    filters: dict = {}


@router.get("/saved-filters")
async def saved_filters_list(scope: str | None = Query(None),
                             user=Depends(_guard_any_admin)):
    """⏱ فیلترهای ذخیره‌شده‌ی خود کاربر (person-scoped)."""
    q = {"owner": user["id"]}
    if scope:
        q["scope"] = scope
    docs = await db.wa_saved_filters.find(q).sort("created_at", -1).to_list(50)
    return {"filters": [{
        "id": str(d.get("_id", "")), "name": d.get("name", ""),
        "scope": d.get("scope", ""), "filters": d.get("filters") or {},
        "created_at": d.get("created_at", "")[:16],
    } for d in docs]}


@router.post("/saved-filters")
async def saved_filters_add(body: SavedFilterIn, user=Depends(_guard_any_admin)):
    name = (body.name or "").strip()[:60]
    if not name:
        raise HTTPException(422, "نام فیلتر الزامی است")
    if body.scope not in ("users", "questions", "content", "audit", "payments"):
        raise HTTPException(422, "scope نامعتبر است")
    uid = user["id"]
    if await db.wa_saved_filters.count_documents({"owner": uid}) >= 30:
        raise HTTPException(422, "حداکثر ۳۰ فیلتر ذخیره می‌توانید داشته باشید")
    doc = {"owner": uid, "name": name, "scope": body.scope,
           "filters": body.filters or {}, "created_at": _now()}
    r = await db.wa_saved_filters.insert_one(doc)
    return {"ok": True, "id": str(getattr(r, "inserted_id", "") or "")}


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


class TicketsBulk(BaseModel):
    action: str           # close | reopen
    ids: list[int]


@router.post("/tickets/bulk")
async def tickets_bulk(body: TicketsBulk, user=Depends(_perm("tickets.manage"))):
    """⚡ اکشن گروهی تیکت (سقف ۱۰۰) — با همان متدهای موجود db."""
    ids = [int(i) for i in (body.ids or []) if isinstance(i, (int, str)) and str(i).isdigit()][:100]
    if not ids:
        raise HTTPException(400, "لیست تیکت‌ها خالی است")
    done = 0
    for tid in ids:
        t = await db.ticket_get(tid)
        if not t:
            continue
        if body.action == "close" and t.get("status") != "closed":
            await db.ticket_close(tid)
            done += 1
        elif body.action == "reopen" and t.get("status") == "closed":
            await db.ticket_reopen(tid)
            done += 1
    fa = {"close": "بستن گروهی", "reopen": "بازگشایی گروهی"}
    await _audit(user["id"], f"{fa.get(body.action, body.action)} تیکت ({done} مورد)",
                 severity="INFO", target_label=f"{done} تیکت",
                 tags=["bulk_tickets", "پنل_وب"])
    return {"ok": True, "done": done}


class QuestionsBulk(BaseModel):
    action: str           # approve | reject
    ids: list[str]


@router.post("/questions/bulk")
async def questions_bulk(body: QuestionsBulk, user=Depends(_perm("questions.review"))):
    """⚡ تأیید/رد گروهی سؤال‌های پیشنهادی — معناشناسی دقیقاً مثل مسیر تکی:
    approve → db.approve_question ؛ reject → db.delete_question + اطلاع به طراح (outbox)."""
    ids = [str(i) for i in (body.ids or [])][:100]
    if not ids:
        raise HTTPException(400, "لیست سؤال‌ها خالی است")
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "اکشن نامعتبر است")
    done = 0
    notif = db.client["medicalbot"]["bot_notifications"]
    for qid in ids:
        q = await db.get_question_by_id(qid)
        if not q or q.get("approved"):
            continue
        # scope enforce همان مسیر تکی
        if not await db.can_access_intake(user["id"], q.get("intake", "") or ""):
            continue
        if body.action == "approve":
            await db.approve_question(qid)
        else:
            await db.delete_question(qid)
        done += 1
        if q.get("source") == "webapp" and q.get("creator_id"):
            try:
                ok = body.action == "approve"
                await notif.insert_one({
                    "type": "question_approved" if ok else "question_rejected",
                    "chat_id": q["creator_id"],
                    "text": (("✅ <b>سوال شما تأیید شد!</b>" if ok else "❌ <b>سوال شما رد شد</b>")
                             + f"\n📚 {q.get('lesson','')} — {q.get('topic','')}"),
                    "sent": False, "created_at": _now()})
            except Exception:
                pass
    fa = {"approve": "تأیید گروهی", "reject": "رد گروهی"}
    await _audit(user["id"], f"{fa[body.action]} سؤال‌ها ({done} مورد)",
                 severity="INFO", target_label=f"{done} سؤال",
                 tags=["bulk_questions", "پنل_وب"])
    return {"ok": True, "done": done}


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
async def settings_center(user=Depends(_perm("settings.manage"))):
    """⚙️ نمای دسته‌بندی‌شده‌ی تنظیمات + متا (آخرین تغییردهنده/زمان)."""
    meta_docs = await db.settings_meta.find({}).to_list(200)
    meta = {str(m.get("_id")): m for m in meta_docs}
    notif_defaults = await db.get_notif_defaults()

    cats = []
    for cat_key, rows in _SETTINGS_CATALOG:
        items = []
        for key, label, desc, typ, perm, sev in rows:
            val = await db.get_setting(key, None)
            m = meta.get(key) or {}
            items.append({
                "key": key, "label": label, "desc": desc, "type": typ,
                "value": val,
                "updated_by": m.get("by_name", ""), "updated_at": m.get("at", "")[:16],
            })
        cats.append({"key": cat_key, "items": items})

    # 🔔 پیش‌فرض اعلان‌ها — همان کلیدهای get_notif_defaults (بدون توقف ربات)
    notif_items = []
    notif_labels = {}
    try:
        for row in db.NOTIF_CATALOG:
            notif_labels[row[0]] = row[1]
    except Exception:
        pass
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
    sid = await db.add_schedule("exam", lesson, (body.teacher or "").strip()[:80],
                                d, t, (body.location or "").strip()[:80],
                                notes=(body.notes or "").strip()[:300], group=grp)
    await _audit(user["id"], "ایجاد آزمون جدید", severity="INFO",
                 target_id=str(sid), target_type="exam", target_label=lesson,
                 tags=["امتحان", "پنل_وب"])
    return {"ok": True, "id": str(sid)}


@router.patch("/exams/{sid}")
async def exams_update(sid: str, body: ExamIn,
                       user=Depends(_perm("schedules.manage"))):
    lesson, d, t, grp = _valid_exam_fields(body)
    old = await db.get_schedule_by_id(sid)
    if not old or old.get("type") != "exam":
        raise HTTPException(404, "آزمون یافت نشد")
    ok = await db.update_schedule_full(sid, lesson, (body.teacher or "").strip()[:80],
                                       d, t, (body.location or "").strip()[:80],
                                       (body.notes or "").strip()[:300], grp)
    if not ok:
        raise HTTPException(500, "به‌روزرسانی ناموفق بود")
    await _audit(user["id"], "ویرایش آزمون", severity="INFO",
                 target_id=sid, target_type="exam", target_label=lesson,
                 tags=["امتحان", "پنل_وب"])
    return {"ok": True}


@router.delete("/exams/{sid}")
async def exams_delete(sid: str, user=Depends(_perm("schedules.manage"))):
    old = await db.get_schedule_by_id(sid)
    if not old or old.get("type") != "exam":
        raise HTTPException(404, "آزمون یافت نشد")
    await db.delete_schedule(sid)
    await _audit(user["id"], "حذف آزمون", severity="HIGH",
                 target_id=sid, target_type="exam",
                 target_label=old.get("lesson", ""), tags=["امتحان", "پنل_وب"])
    return {"ok": True}


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
                    "content_count": counts.get(sid, {}).get("n", 0),
                    "types": counts.get(sid, {}).get("types", {}),
                })
            trow["lessons"].append({
                "id": lid, "name": l.get("name", ""), "teacher": l.get("teacher", ""),
                "intake": l.get("intake") or "",
                "sessions": srows, "session_count": len(srows),
                "content_count": sum(r["content_count"] for r in srows),
            })
        tree.append(trow)
    return {"intake": iv, "tree": tree,
            "intakes": [{"code": c, "label": l} for c, l in intake_labels.items()]}


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
                       days: int = Query(14, ge=7, le=90)):
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
    except Exception as e:
        raise HTTPException(500, f"محاسبه‌ی هشدارها ناموفق بود: {str(e)[:120]}")


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
                                "created_at": _now()})
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
            "registered_at": target.get("registered_at", "")[:10],
            "total_answers": target.get("total_answers", 0),
            "prestige_rank": target.get("prestige_rank", ""),
            "prestige_div": target.get("prestige_div", ""),
        },
        "subscription": None, "admin_role": None, "perms": [],
        "counts": {"tickets": 0, "grades": 0},
        "recent_tickets": [], "recent_audit": [],
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
    except Exception:
        pass
    try:
        logs = await db.audit_logs.find({"actor.id": uid}).sort("timestamp", -1).limit(10).to_list(10)
        out["recent_audit"] = [{
            "action": l.get("action", ""), "module": l.get("module", ""),
            "at": (l.get("timestamp") or "")[:16].replace("T", " "),
            "severity": l.get("severity", "INFO"),
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
    try:  # 🔔 اعلان‌ها — شمارش خوانده‌نشده/کل
        un = await db.user_notifs.count_documents({"user_id": uid, "read": {"$ne": True}})
        tot = await db.user_notifs.count_documents({"user_id": uid})
        out["notifs"] = {"unread": un, "total": tot}
    except Exception:
        out.setdefault("notifs", {})
    return out
