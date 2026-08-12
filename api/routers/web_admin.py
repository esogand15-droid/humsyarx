# -*- coding: utf-8 -*-
"""
🖥️ موج WA — Web Admin Control Center API

احراز هویت مستقل دسکتاپ: OTP تلگرامی → سشن HttpOnly (۱۲ ساعته).
هیچ منطق کسب‌وکاری تکرار نمی‌شود: همان user/RBAC/audit/db موجود.
- مالک (ADMIN_ID) یا دارای هر مجوز RBAC یا ادمین محتوا ⇒ اجازه‌ی ورود وب.
- دسترسی به هر endpoint همچنان permission-based است (require_perm/owner).
"""
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from api.auth import (
    ADMIN_ID, _hash_token, get_current_user, new_session_token,
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


def _now() -> str:
    return datetime.utcnow().isoformat()


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


async def _audit(actor_uid: int, action: str, *, severity: str = "INFO",
                 target_id: str = "", target_type: str = "",
                 target_label: str = "", tags=None):
    try:
        u = await db.get_user(actor_uid)
        await db.log_action(
            actor_uid, (u or {}).get("name", str(actor_uid)),
            await db.get_actor_role_label(actor_uid),
            action, "WebAdmin", category="admin", severity=severity,
            target_id=str(target_id), target_type=target_type,
            target_label=target_label, tags=tags or [],
        )
    except Exception:
        pass


class RequestCode(BaseModel):
    identifier: str


class VerifyCode(BaseModel):
    identifier: str
    code: str


class BulkBody(BaseModel):
    action: str            # approve | suspend | unsuspend
    ids: list[int]


@router.post("/auth/request-code")
async def request_code(body: RequestCode, request: Request):
    """ارسال کد ورود ۶ رقمی از طریق ربات تلگرام (بدون نشت وجود حساب)."""
    ident = (body.identifier or "").strip()[:64]
    # ── rate limit ──
    now = time.time()
    hits = [t for t in _otp_rl.get(ident, []) if now - t < OTP_RL_WINDOW]
    if len(hits) >= OTP_RL_COUNT:
        raise HTTPException(status_code=429,
                            detail="تعداد درخواست زیاد است؛ چند دقیقه دیگر تلاش کنید.")
    hits.append(now)
    _otp_rl[ident] = hits

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
    """اکشن گروهی کاربران — approve/unsuspend/suspend (سقف ۱۰۰)."""
    ids = [int(i) for i in (body.ids or []) if isinstance(i, (int, str)) and str(i).isdigit()][:100]
    if not ids:
        raise HTTPException(400, "لیست کاربران خالی است.")
    if ADMIN_ID in ids:
        ids.remove(ADMIN_ID)
    actor = user["id"]
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
        else:
            raise HTTPException(400, "اکشن نامعتبر است.")
        done += 1
    fa = {"approve": "تأیید گروهی", "suspend": "تعلیق گروهی", "unsuspend": "رفع تعلیق گروهی"}
    await _audit(actor, f"{fa.get(body.action, body.action)} کاربران ({done} نفر)",
                 severity="HIGH" if body.action == "suspend" else "INFO",
                 target_label=f"{done} کاربر", tags=["bulk_users", "پنل_وب"])
    return {"ok": True, "done": done}
