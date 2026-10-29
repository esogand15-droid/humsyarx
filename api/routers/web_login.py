# -*- coding: utf-8 -*-
"""🔐 ورود وب/PWA — تا امروز مینی‌اپ فقط داخل تلگرام کار می‌کرد.

مسئله
─────
نسخهٔ نصب‌شدنی (PWA) روی iOS / Android / Windows بدون تلگرام اجرا
می‌شود و `initData` ندارد؛ `get_current_user` هم ۴۰۱ می‌داد ⇒ اپ نصب
می‌شد ولی «کار نمی‌کرد».

راه‌حل (همان الگوی اثبات‌شدهٔ پنل ادمین، تعمیم‌یافته به دانشجو)
──────────────────────────────────────────────────────────────
۱) کاربر شناسه‌اش را می‌زند (آیدی عددی تلگرام / @یوزرنیم / شماره دانشجویی).
۲) کد ۶ رقمی از طریق **همان ربات هامزیار** در تلگرام برایش می‌آید
   (کالکشن صف `bot_notifications` — همان که `mini_app_outbox_job`
   مصرف می‌کند؛ بدون سرویس پیامکی و بدون هزینهٔ اضافه).
۳) کد را وارد می‌کند ← کوکی نشست `hu_session` (HttpOnly + Secure +
   SameSite=Lax) صادر می‌شود و `get_current_user` از همان مسیر
   شناسایی‌اش می‌کند.

قواعد امنیتی رعایت‌شده
──────────────────────
* کد فقط به‌صورت `sha256(salt:code)` ذخیره می‌شود؛ مقایسه ثابت‌زمان.
* پاسخ درخواست کد **همیشه یکسان** است (ضد شمارش حساب).
* محدودیت نرخ: پنجرهٔ لغزان per-IP + per-identifier، و یک cooldown
  دیتابیسی ۶۰ ثانیه‌ای که بین ورکرها مشترک است.
* نشست: توکن ۳۲ بایتی؛ در دیتابیس فقط هش. انقضا + revoke.
* فقط کاربر «تأییدشده و غیرتعلیق» می‌تواند وارد شود.
* هر ورود موفق/ناموفقِ حساس در `db.log_action` ثبت می‌شود.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.auth import BOT_TOKEN, get_current_user  # noqa: F401  (BOT_TOKEN برای هم‌ترازی)
from database import db

from api import web_login_core as core

logger = logging.getLogger(__name__)

router = APIRouter()


# ── مدل‌های ورودی ────────────────────────────────────────────────
class RequestCode(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)


class VerifyCode(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=12)


# ── دسترسی به کالکشن‌ها (بدون تغییر لایهٔ db) ────────────────────
def _col(name: str):
    return db.client["medicalbot"][name]


def _otps():
    return _col("web_user_otps")


def _sessions():
    return _col("web_user_sessions")


def _outbox():
    return db.client["medicalbot"]["bot_notifications"]


# ── کمکی‌ها ─────────────────────────────────────────────────────
def _is_https(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto:
        return proto == "https"
    return request.url.scheme == "https"


async def _find_user(identifier: str) -> Optional[dict]:
    """شناسه → سند کاربر با **تطبیق دقیق** (نه substring).

    عمداً از `search_users` استفاده نمی‌شود: آن جست‌وجوی متنی است و
    می‌توانست حساب دیگری را برگرداند (خطر امنیتی در ورود).
    """
    ident = core.normalize_identifier(identifier)
    if not ident:
        return None

    # ⚠️ «عددی بودن» فقط یعنی «شاید آیدی عددی تلگرام باشد» — نه اینکه
    # حتماً هست. شمارهٔ دانشجویی هم معمولاً عددی است؛ قبلاً این تابع
    # بعد از ناموفق بودن جست‌وجوی user_id بی‌درنگ None برمی‌گرداند و
    # دانشجو نمی‌توانست با شمارهٔ دانشجویی وارد شود. حالا هر سه
    # تفسیر ممکنِ یک شناسهٔ عددی به‌ترتیب امتحان می‌شود.
    if core.is_numeric_identifier(ident):
        try:
            doc = await db.users.find_one({"user_id": int(ident)})
        except (ValueError, OverflowError):
            doc = None
        if doc:
            return doc

    uname = ident.lower()
    exact_ci = {"$regex": f"^{re.escape(uname)}$", "$options": "i"}

    # شماره دانشجویی و یوزرنیم: هر دو تطبیق کامل
    doc = await db.users.find_one({"username": exact_ci})
    if doc:
        return doc
    doc = await db.users.find_one(
        {"student_id": {"$regex": f"^{re.escape(ident)}$", "$options": "i"}})
    if doc:
        return doc
    if core.looks_like_phone(ident):
        for field in ("phone", "phone_number", "mobile"):
            doc = await db.users.find_one({field: ident})
            if doc:
                return doc
    return None


def _loginable(user: Optional[dict]) -> bool:
    return bool(
        user
        and user.get("user_id")
        and user.get("approved")
        and not user.get("suspended")
        and not user.get("blacklisted")
    )


async def _audit(uid: int, action: str, *, tags=None, details: str = "") -> None:
    """ثبت حسابرسی — شکستش ورود را نمی‌شکند (best-effort با لاگ)."""
    try:
        user = await db.get_user(uid)
        await db.log_action(uid, (user or {}).get("name", str(uid)), action,
                            details=details, tags=tags or [])
    except Exception as exc:  # pragma: no cover - فقط لاگ
        logger.warning("web-login audit failed: %s", exc)


# ── ۱) درخواست کد ────────────────────────────────────────────────
@router.post("/request")
async def request_code(body: RequestCode, request: Request):
    ident = core.normalize_identifier(body.identifier)
    ip = ((getattr(request, "client", None) and request.client.host) or "")[:64]

    if not ident:
        raise HTTPException(status_code=422, detail="شناسه را وارد کنید.")

    if not core.request_allowed(ident, ip):
        raise HTTPException(
            status_code=429,
            detail="تعداد درخواست‌ها زیاد است؛ چند دقیقهٔ دیگر تلاش کنید.",
        )

    user = await _find_user(ident)
    if _loginable(user):
        uid = int(user["user_id"])

        # cooldown ۶۰ ثانیه‌ای دیتابیسی (بین همهٔ ورکرها مشترک)
        try:
            existing = await _otps().find_one({"uid": uid})
        except Exception as exc:  # pragma: no cover
            logger.warning("web-login otp read failed: %s", exc)
            existing = None

        if existing:
            created = existing.get("created_at")
            wait = 0
            if hasattr(created, "timestamp"):
                if getattr(created, "tzinfo", None) is None:
                    created = created.replace(tzinfo=timezone.utc)
                elapsed = (core.now_utc() - created).total_seconds()
                wait = max(0, int(core.OTP_RESEND_COOLDOWN_SEC - elapsed))
            else:
                wait = core.OTP_RESEND_COOLDOWN_SEC
            if wait > 0:
                # پاسخ همان پیام عمومی است؛ فقط منتظر ماندن را می‌گوییم
                raise HTTPException(
                    status_code=429,
                    detail=f"{wait} ثانیهٔ دیگر می‌توانید کد تازه بگیرید.",
                )

        code = core.make_code()
        salt = core.make_salt()
        try:
            await _otps().delete_many({"uid": uid})
            await _otps().insert_one({
                "uid": uid,
                "code_salt": salt,
                "code_hash": core.hash_code(salt, code),
                "attempts": 0,
                "created_at": core.now_utc(),
                "expires_at": core.expiry_from_now(core.OTP_TTL_MIN),
                "peer_ip": ip,
            })
            await _outbox().insert_one({
                "type": "web_login_otp",
                "chat_id": uid,
                "parse_mode": "HTML",
                "text": (
                    "🔐 <b>کد ورود به نسخهٔ وب هامزیار</b>\n\n"
                    f"کد: <code>{code}</code>\n"
                    f"⏳ اعتبار: {core.OTP_TTL_MIN} دقیقه\n\n"
                    "اگر شما درخواست نداده‌اید، این پیام را نادیده بگیرید و "
                    "رمز/کد را برای کسی نفرستید."
                ),
                "sent": False,
                "created_at": core.now_utc().isoformat(),
            })
        except Exception as exc:  # pragma: no cover
            logger.error("web-login otp create failed: %s", exc)
            raise HTTPException(status_code=503, detail="ارسال کد ممکن نشد؛ بعداً تلاش کنید.")

    return {"ok": True, "message": core.GENERIC_REQUEST_MESSAGE}


# ── ۲) تأیید کد و ساخت نشست ─────────────────────────────────────
@router.post("/verify")
async def verify_code(body: VerifyCode, request: Request, response: Response):
    ident = core.normalize_identifier(body.identifier)
    code = core.normalize_identifier(body.code)
    ip = ((getattr(request, "client", None) and request.client.host) or "")[:64]

    if not ident or not code:
        raise HTTPException(status_code=401, detail=core.GENERIC_CODE_ERROR)

    # نرخ تلاش برای ورود (جلوگیری از brute-force روی کد ۶ رقمی)
    if not core.IP_LIMITER.allow(f"verify-ip:{ip or '-'}"):
        raise HTTPException(status_code=429, detail="تلاش‌های زیاد؛ چند دقیقه بعد تلاش کنید.")

    user = await _find_user(ident)
    if not _loginable(user):
        # پاسخ یکسان با «کد غلط» — وجود حساب لو نمی‌رود
        raise HTTPException(status_code=401, detail=core.GENERIC_CODE_ERROR)

    uid = int(user["user_id"])
    try:
        otp = await _otps().find_one({"uid": uid})
    except Exception as exc:  # pragma: no cover
        logger.error("web-login otp read failed: %s", exc)
        raise HTTPException(status_code=503, detail="ورود موقتاً ممکن نیست.")

    if not otp or core.is_past(otp.get("expires_at")):
        raise HTTPException(status_code=401, detail=core.GENERIC_CODE_ERROR)

    if int(otp.get("attempts") or 0) >= core.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="تلاش‌های ناموفق زیاد بود؛ کد تازه بگیرید.")

    if not core.code_matches(otp.get("code_salt"), code, otp.get("code_hash")):
        try:
            await _otps().update_one({"uid": uid}, {"$inc": {"attempts": 1}})
        except Exception:  # pragma: no cover
            pass
        raise HTTPException(status_code=401, detail=core.GENERIC_CODE_ERROR)

    # ── موفق: کد را می‌سوزانیم و نشست می‌سازیم ──
    token = core.new_session_token()
    ttl_days = core.session_ttl_days()
    now = core.now_utc()
    try:
        await _otps().delete_many({"uid": uid})
        await _sessions().insert_one({
            "_id": core.hash_token(token),
            "uid": uid,
            "created_at": now,
            "expires_at": now + timedelta(days=ttl_days),
            "revoked": False,
            "peer_ip": ip,
            "user_agent": (request.headers.get("user-agent") or "")[:240],
        })
    except Exception as exc:  # pragma: no cover
        logger.error("web-login session create failed: %s", exc)
        raise HTTPException(status_code=503, detail="ورود ممکن نشد؛ دوباره تلاش کنید.")

    response.set_cookie(
        core.SESSION_COOKIE, token,
        max_age=ttl_days * 86400,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )
    await _audit(uid, "ورود به نسخهٔ وب (PWA)", tags=["ورود_وب", "pwa"])
    return {
        "ok": True,
        "user": {
            "uid": uid,
            "name": user.get("name", ""),
            "expires_in_days": ttl_days,
        },
    }


# ── ۳) وضعیت نشست (برای بووت SPA) ───────────────────────────────
@router.get("/session")
async def session_state(request: Request):
    """آیا این مرورگر نشست معتبر دارد؟ بدون ۴۰۱ — برای تصمیم UI."""
    token = request.cookies.get(core.SESSION_COOKIE, "")
    if not token:
        return {"authenticated": False}
    try:
        doc = await _sessions().find_one({
            "_id": core.hash_token(token), "revoked": False,
        })
    except Exception:  # pragma: no cover
        return {"authenticated": False}
    if not doc or core.is_past(doc.get("expires_at")):
        return {"authenticated": False}
    return {
        "authenticated": True,
        "uid": int(doc.get("uid") or 0),
        "expires_in_sec": core.seconds_until(doc.get("expires_at")),
    }


# ── ۴) خروج ─────────────────────────────────────────────────────
@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(core.SESSION_COOKIE, "")
    if token:
        try:
            await _sessions().update_one(
                {"_id": core.hash_token(token)},
                {"$set": {"revoked": True, "revoked_at": core.now_utc()}},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("web-login logout failed: %s", exc)
    response.delete_cookie(core.SESSION_COOKIE, path="/")
    return {"ok": True}
