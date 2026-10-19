# -*- coding: utf-8 -*-
"""🌐 موج P1 — احراز هویت و سرو کلاینت وب دانشجو (`apps/student`).

این فایل **تنها** فایل بک‌اندی موج P1 است و کاملاً افزایشی است:
هیچ روتر، کالکشن، مدل یا مسیر موجودی تغییر نمی‌کند.

سه کار انجام می‌دهد
────────────────────
۱) ورود بدون تلگرام: کاربر «شناسه» (یوزرنیم تلگرام یا شمارهٔ دانشجویی)
   را وارد می‌کند، کد یک‌بارمصرف **از طریق ربات هامزیار در تلگرام**
   برایش فرستاده می‌شود و با تأیید کد، سشن کوکی‌محور ساخته می‌شود.
۲) وضعیت حساب را یک‌جا برمی‌گرداند: `active` / `pending_approval` /
   `suspended` — همان سه وضعیتی که در `design/16` تعریف شده‌اند.
۳) SPA کلاینت دانشجو را روی `/student` سرو می‌کند.

چرا `/student` و نه `/app`
──────────────────────────
در مخزن فعلی `/app` متعلق به مینی‌اپ تلگرام است (`miniapp/dist`). سرو
کلاینت وب روی همان پیشوند، مینی‌اپ را shadow می‌کرد. تصمیم D-033.

قرارداد امنیتی
──────────────
* هیچ کدی داخل پاسخ API برنمی‌گردد مگر `WEB_AUTH_DEBUG=1` (فقط dev).
* شناسهٔ ناموجود هم «چالش» می‌گیرد (decoy) تا پاسخ، وجود حساب را لو ندهد.
* کد با `secrets.compare_digest` روی هش+نمک مقایسه می‌شود، نه متن خام.
* توکن سشن فقط به‌صورت هش‌شده (sha256) ذخیره می‌شود.
* کوکی: HttpOnly + SameSite=Lax + Secure + path=/ (ورودی از JS خوانده
  نمی‌شود؛ XSS نمی‌تواند نشست را بدزدد).
* هر ورود/خروج در `web_auth_events` ثبت می‌شود (بدون کد و بدون توکن).

نصب (سه خط، بخش «نصب» در INSTALL.txt)
──────────────────────────────────────
    from api.routers import web_student
    app.include_router(web_student.router, prefix="/api/web", tags=["web-student"])
    web_student.mount(app)          # بعد از mountهای /admin و /app
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.rate_limit import rate_limit
from database import db
from time_utils import TimeContractError, now_utc, parse_machine_datetime

logger = logging.getLogger("web_student")

# ─────────────────────────────────────────────────────────────
#  ⚙️ پیکربندی — همه با پیش‌فرض سالم؛ env فقط برای تنظیم، نه لازم
# ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


COOKIE_NAME = (os.getenv("WEB_STUDENT_COOKIE", "hy_student_session") or "hy_student_session").strip()
SESSION_TTL_DAYS = max(1, min(_env_int("WEB_STUDENT_SESSION_DAYS", 30), 180))
OTP_TTL_SEC = max(60, min(_env_int("WEB_STUDENT_OTP_TTL_SEC", 300), 1800))
OTP_MAX_ATTEMPTS = max(3, min(_env_int("WEB_STUDENT_OTP_MAX_ATTEMPTS", 5), 10))
OTP_RESEND_SEC = max(30, min(_env_int("WEB_STUDENT_OTP_RESEND_SEC", 60), 600))
DEBUG = str(os.getenv("WEB_AUTH_DEBUG", "0")).strip().lower() not in ("0", "false", "no", "off", "")
#: روی HTTPS (Railway) همیشه روشن. فقط برای dev روی http می‌توان ۰ کرد،
#: وگرنه مرورگر کوکی Secure را روی http دور می‌ریزد و نشست ساخته نمی‌شود.
COOKIE_SECURE = str(os.getenv("WEB_STUDENT_COOKIE_SECURE", "1")).strip().lower() not in ("0", "false", "no", "off")
MASK = "•"

router = APIRouter()

_INDEXES_READY = False
_CODE_RE = re.compile(r"^\d{4,8}$")
_DIGITS_RE = re.compile(r"^\d+$")


# ─────────────────────────────────────────────────────────────
#  🧰 کمکی‌های داخلی
# ─────────────────────────────────────────────────────────────
def _coll(name: str):
    """دسترسی به کالکشن بدون دست‌زدن به `db/core.py`.

    `db.users.database` همان دیتابیس جاری موتور است، پس نام دیتابیس
    هاردکد نمی‌شود و اگر بعداً عوض شد، این فایل سالم می‌ماند.
    """
    return db.users.database[name]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now():
    return now_utc()


def _parse_dt(value):
    """تاریخ ذخیره‌شده → datetime. مخزن، تاریخ‌ها را همیشه UTC می‌نویسد."""
    if hasattr(value, "tzinfo"):
        return value
    try:
        return parse_machine_datetime(value)
    except (TimeContractError, TypeError, ValueError):
        return None


def _expired(value) -> bool:
    parsed = _parse_dt(value)
    if parsed is None:
        return True
    now = _now()
    try:
        return parsed <= now
    except TypeError:  # naive/aware ناسازگار → محافظه‌کارانه منقضی بدان
        return True


def _normalize_identifier(raw: str) -> str:
    """یکسان‌سازی شناسه ورود: `@Ali`, ` ali `, `ali` → `ali`."""
    value = (raw or "").strip().lower()
    value = value.replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")
    value = value.lstrip("@")
    return re.sub(r"\s+", "", value)


def _mask_target(user: dict) -> str:
    """پوشاندن مقصد کد برای نمایش در UI — نه نام کامل، نه یوزرنیم کامل."""
    username = (user.get("username") or "").strip()
    if username:
        return "@" + username[:2] + MASK * max(2, min(5, len(username) - 2))
    return "تلگرام شما"


def _public_user(user: dict) -> dict:
    """فقط فیلدهایی که وجود دارند و کلاینت واقعاً لازم دارد.

    هیچ فیلد تازه‌ای ساخته نمی‌شود؛ اگر کلید در سند نبود، مقدار خالی
    برمی‌گردد (نه مقدار حدسی).
    """
    return {
        "id": int(user.get("user_id") or 0),
        "name": user.get("name") or "",
        "username": user.get("username") or "",
        "student_id": user.get("student_id") or "",
        "group": user.get("group") or "",
        "intake": user.get("intake") or "",
        "role": user.get("role") or "student",
        "registered_at": str(user.get("registered_at") or ""),
    }


def account_state(user: dict) -> str:
    """سه وضعیت مستقلِ حساب — همان واژگان `design/16`.

    ترتیب مهم است: تعلیق بر «در انتظار تأیید» اولویت دارد تا کاربر
    تعلیق‌شده پیام گمراه‌کنندهٔ «منتظر تأیید» نبیند.
    """
    if user.get("suspended"):
        return "suspended"
    if not user.get("approved"):
        return "pending_approval"
    return "active"


async def _find_user(identifier: str) -> dict | None:
    """یافتن کاربر با یوزرنیم تلگرام یا شمارهٔ دانشجویی.

    عمداً «نام» جستجو نمی‌شود (نام یکتا نیست) و جستجو همیشه exact و
    case-insensitive است؛ regex با `re.escape` ساخته می‌شود تا
    ورودی کاربر به الگوی کوئری تزریق نشود.
    """
    if not identifier:
        return None
    pattern = {"$regex": "^" + re.escape(identifier) + "$", "$options": "i"}
    if _DIGITS_RE.match(identifier):
        user = await db.users.find_one({"student_id": identifier})
        if user:
            return user
        if len(identifier) <= 12:
            try:
                return await db.users.find_one({"user_id": int(identifier)})
            except (TypeError, ValueError):
                return None
        return None
    return await db.users.find_one({"username": pattern})


async def _ensure_indexes() -> None:
    """ایندکس‌های موج P1 — یک‌بار در عمر پروسه.

    TTL روی `expires_at` باعث می‌شود چالش‌ها و سشن‌های منقضی خودشان
    پاک شوند؛ بدون این، هر ورود یک سند برای همیشه می‌گذاشت.
    """
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    try:
        await _coll("web_login_challenges").create_index("expires_at", expireAfterSeconds=0)
        await _coll("web_login_challenges").create_index([("created_at", -1)])
        await _coll("web_sessions").create_index("expires_at", expireAfterSeconds=0)
        await _coll("web_sessions").create_index([("uid", 1), ("created_at", -1)])
        await _coll("web_auth_events").create_index([("uid", 1), ("at", -1)])
        _INDEXES_READY = True
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("web_auth_indexes_failed err=%s", type(exc).__name__)


async def _audit(uid: int | None, event: str, request: Request, **extra) -> None:
    """ثبت رخداد احراز هویت. هرگز کد/توکن/IP خام کامل ذخیره نمی‌شود."""
    try:
        peer = ((getattr(request, "client", None) and request.client.host) or "")[:64]
        await _coll("web_auth_events").insert_one({
            "uid": int(uid) if uid else None,
            "event": event,
            "at": _now(),
            "peer_ip": peer,
            "user_agent": (request.headers.get("user-agent") or "")[:240],
            **extra,
        })
    except Exception as exc:  # pragma: no cover
        logger.info("web_auth_audit_failed event=%s err=%s", event, type(exc).__name__)


async def _send_code(uid: int, code: str) -> bool:
    """ارسال کد از ربات تلگرام به همان کاربر.

    کد هرگز در لاگ نمی‌نشیند. اگر توکن ربات نبود یا تلگرام خطا داد،
    `False` برمی‌گردد تا endpoint پاسخ صریح `send_failed` بدهد — نه
    یک «موفق» دروغین که کاربر منتظر کدی بماند که نیامده.
    """
    if not BOT_TOKEN:
        logger.warning("web_otp_send_failed reason=no_bot_token")
        return False
    text = (
        "🔐 کد ورود شما به هامزیار\n\n"
        f"{code}\n\n"
        f"این کد تا {OTP_TTL_SEC // 60} دقیقه معتبر است و فقط یک‌بار کار می‌کند.\n"
        "اگر شما درخواست نداده‌اید، این پیام را نادیده بگیرید."
    )
    payload = {"chat_id": int(uid), "text": text, "disable_web_page_preview": True}
    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
        if resp.status_code != 200:
            logger.warning("web_otp_send_failed status=%s", resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.warning("web_otp_send_failed err=%s", type(exc).__name__)
        return False


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


# ─────────────────────────────────────────────────────────────
#  📦 مدل‌های ورودی
# ─────────────────────────────────────────────────────────────
class StartBody(BaseModel):
    identifier: str = Field(default="", max_length=64)


class VerifyBody(BaseModel):
    challenge: str = Field(default="", max_length=64)
    code: str = Field(default="", max_length=12)


# ─────────────────────────────────────────────────────────────
#  🍪 سشن — ساخت، خواندن، باطل‌کردن
# ─────────────────────────────────────────────────────────────
async def _create_session(uid: int, request: Request) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    peer = ((getattr(request, "client", None) and request.client.host) or "")[:64]
    await _coll("web_sessions").insert_one({
        "_id": _sha(token),
        "uid": int(uid),
        "created_at": now,
        "last_seen_at": now,
        "expires_at": now + timedelta(days=SESSION_TTL_DAYS),
        "revoked": False,
        "peer_ip": peer,
        "user_agent": (request.headers.get("user-agent") or "")[:240],
    })
    return token


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


async def _resolve_session(request: Request) -> dict | None:
    token = (request.cookies.get(COOKIE_NAME) or "").strip()
    if not token:
        return None
    doc = await _coll("web_sessions").find_one({"_id": _sha(token), "revoked": False})
    if not doc or _expired(doc.get("expires_at")):
        return None
    # تمدید نرم: حداکثر یک‌بار در ساعت، نه در هر درخواست.
    last = _parse_dt(doc.get("last_seen_at"))
    try:
        stale = last is None or (_now() - last) > timedelta(hours=1)
    except TypeError:
        stale = True
    if stale:
        try:
            await _coll("web_sessions").update_one(
                {"_id": doc["_id"]},
                {"$set": {"last_seen_at": _now(), "expires_at": _now() + timedelta(days=SESSION_TTL_DAYS)}},
            )
        except Exception:
            pass
    return doc


async def current_student(request: Request) -> dict:
    """وابستگی برای مسیرهای بعدی (P2+): کاربر فعال و تأییدشده.

    خطاها با کد رشته‌ای برمی‌گردند تا کلاینت بتواند بدون parse کردن
    متن فارسی، بین «وارد شو» و «منتظر تأیید» و «تعلیق» تفکیک کند.
    """
    session = await _resolve_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="login_required")
    user = await db.get_user(int(session["uid"]), use_cache=False)
    if not user:
        raise HTTPException(status_code=403, detail="not_registered")
    state = account_state(user)
    if state == "suspended":
        raise HTTPException(status_code=403, detail="suspended")
    if state == "pending_approval":
        raise HTTPException(status_code=403, detail="pending_approval")
    return {**user, "_session": session}


# ─────────────────────────────────────────────────────────────
#  🔌 اندپوینت‌ها
# ─────────────────────────────────────────────────────────────
@router.post("/auth/start")
async def auth_start(body: StartBody, request: Request):
    """مرحلهٔ ۱ ورود: شناسه → ارسال کد به تلگرام همان کاربر.

    پاسخ برای «کاربر موجود» و «کاربر ناموجود» یک شکل است؛ فقط
    کاربر ناموجود کدی دریافت نمی‌کند. این تنها راه جلوگیری از
    ساخت یک ابزار شناسایی کاربران از روی این endpoint است.
    """
    await _ensure_indexes()
    await rate_limit(request, "web_login_start", limit=12, window=600)

    identifier = _normalize_identifier(body.identifier)
    if len(identifier) < 3:
        raise HTTPException(status_code=422, detail="identifier_invalid")

    await rate_limit(
        request, "web_login_start", limit=5, window=900,
        key=f"id:{_sha(identifier + BOT_TOKEN[:8])}:web_login_start",
    )

    user = await _find_user(identifier)
    uid = int(user.get("user_id")) if user else None
    code = _new_code()
    salt = secrets.token_hex(8)
    now = _now()
    challenge_id = secrets.token_urlsafe(18)

    # چالش‌های قبلی همین شناسه باطل می‌شوند تا فقط آخرین کد معتبر باشد.
    try:
        await _coll("web_login_challenges").update_many(
            {"identifier": identifier, "consumed": False},
            {"$set": {"consumed": True, "consumed_at": now, "reason": "superseded"}},
        )
    except Exception:
        pass

    await _coll("web_login_challenges").insert_one({
        "_id": challenge_id,
        "uid": uid,
        "identifier": identifier,
        "code_hash": _sha(f"{salt}:{code}"),
        "code_salt": salt,
        "attempts": 0,
        "consumed": False,
        "created_at": now,
        "expires_at": now + timedelta(seconds=OTP_TTL_SEC),
        "peer_ip": ((getattr(request, "client", None) and request.client.host) or "")[:64],
    })

    sent = False
    if uid:
        sent = await _send_code(uid, code)
        await _audit(uid, "otp_sent" if sent else "otp_send_failed", request)

    payload = {
        "ok": True,
        "challenge": challenge_id,
        "channel": "telegram",
        "hint": f"کد به {_mask_target(user) if user else 'تلگرام شما'} فرستاده شد" if user
                else "اگر این شناسه در هامزیار ثبت شده باشد، کد به تلگرام آن فرستاده می‌شود",
        "resend_in": OTP_RESEND_SEC,
        "expires_in": OTP_TTL_SEC,
    }
    if DEBUG:
        payload["debug_code"] = code
        payload["debug_user_found"] = bool(user)
        if uid and not sent:
            payload["debug_send_failed"] = True
    return payload


@router.post("/auth/verify")
async def auth_verify(body: VerifyBody, request: Request, response: Response):
    """مرحلهٔ ۲ ورود: چالش + کد → سشن.

    خطاها همه از یک خانواده‌اند (401 `code_invalid`) تا تفاوت پیام،
    وجود حساب یا صحیح‌بودن کد را لو ندهد. تنها استثنا `429` است که
    فقط به تعداد تلاش خودِ همین چالش بستگی دارد.
    """
    await _ensure_indexes()
    await rate_limit(request, "web_login_verify", limit=30, window=600)

    code = (body.code or "").strip()
    challenge_id = (body.challenge or "").strip()
    if not _CODE_RE.match(code.replace(" ", "").replace("-", "")):
        raise HTTPException(status_code=422, detail="code_format")
    code = code.replace(" ", "").replace("-", "")

    challenge = await _coll("web_login_challenges").find_one({"_id": challenge_id})
    if not challenge:
        raise HTTPException(status_code=401, detail="code_invalid")
    if challenge.get("consumed"):
        raise HTTPException(status_code=401, detail="code_invalid")
    if _expired(challenge.get("expires_at")):
        raise HTTPException(status_code=401, detail="code_expired")
    attempts = int(challenge.get("attempts") or 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="too_many_attempts")

    salt = str(challenge.get("code_salt") or "")
    candidate = _sha(f"{salt}:{code}")
    expected = str(challenge.get("code_hash") or "")
    ok = bool(expected) and hmac.compare_digest(candidate, expected)

    if not ok:
        await _coll("web_login_challenges").update_one(
            {"_id": challenge_id}, {"$inc": {"attempts": 1}, "$set": {"last_attempt_at": _now()}}
        )
        uid_fail = challenge.get("uid")
        if uid_fail:
            await _audit(int(uid_fail), "otp_wrong", request)
        raise HTTPException(status_code=401, detail="code_invalid")

    # کد درست، اما چالش بدون کاربر (decoy) → همان پاسخ عمومی.
    if not challenge.get("uid"):
        await _coll("web_login_challenges").update_one(
            {"_id": challenge_id}, {"$set": {"consumed": True, "consumed_at": _now()}}
        )
        raise HTTPException(status_code=401, detail="code_invalid")

    uid = int(challenge["uid"])
    user = await db.get_user(uid, use_cache=False)
    if not user:
        raise HTTPException(status_code=403, detail="not_registered")

    await _coll("web_login_challenges").update_one(
        {"_id": challenge_id}, {"$set": {"consumed": True, "consumed_at": _now()}}
    )

    token = await _create_session(uid, request)
    _set_cookie(response, token)
    state = account_state(user)
    await _audit(uid, "login_ok" if state == "active" else f"login_ok_{state}", request)
    return {"ok": True, "state": state, "user": _public_user(user)}


@router.get("/auth/session")
async def auth_session(request: Request):
    """وضعیت نشست — تنها منبع حقیقت برای گارد سمت کلاینت.

    حتی وقتی سشن هست ولی حساب تأیید نشده، `authenticated: true` و
    `state: pending_approval` برمی‌گردد تا کاربر صفحهٔ «در انتظار
    تأیید» ببیند، نه فرم ورود تکراری.
    """
    session = await _resolve_session(request)
    if not session:
        return {"authenticated": False, "state": "anonymous", "user": None}
    user = await db.get_user(int(session["uid"]), use_cache=False)
    if not user:
        return {"authenticated": False, "state": "not_registered", "user": None}
    return {"authenticated": True, "state": account_state(user), "user": _public_user(user)}


@router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    """باطل‌کردن سشن جاری. حتی اگر سشن نبود، `ok` برمی‌گردد (idempotent)."""
    token = (request.cookies.get(COOKIE_NAME) or "").strip()
    if token:
        try:
            await _coll("web_sessions").update_one(
                {"_id": _sha(token)}, {"$set": {"revoked": True, "revoked_at": _now()}}
            )
        except Exception:
            pass
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/config")
async def auth_config():
    """اطلاعات ثابتِ ورود برای UI (تا کلاینت عدد جادویی هاردکد نکند)."""
    bot_username = (os.getenv("BOT_USERNAME", "") or "").strip().lstrip("@")
    return {
        "otp_length": 6,
        "otp_ttl_sec": OTP_TTL_SEC,
        "resend_in": OTP_RESEND_SEC,
        "session_days": SESSION_TTL_DAYS,
        "channels": ["telegram"],
        # آدرس پشتیبانی فقط اگر ادمین BOT_USERNAME را ست کرده باشد؛
        # هیچ نام کاربری‌ای حدس زده نمی‌شود.
        "support_url": f"https://t.me/{bot_username}" if bot_username else None,
    }


# ─────────────────────────────────────────────────────────────
#  🖥️ سرو SPA دانشجو روی /student
# ─────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIST = os.path.join(_ROOT, "apps", "student", "dist")
PREFIX = os.getenv("WEB_STUDENT_PREFIX", "/student").rstrip("/") or "/student"
_ASSET_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


class _Spa(StaticFiles):
    """`StaticFiles` با fallback به `index.html` برای مسیرهای بدون پسوند.

    مسیر دارای پسوندِ ناموجود باید 404 بماند: پاسخ HTML به درخواست
    JS، خطای «Unexpected token '<'» می‌دهد و تشخیص را غیرممکن می‌کند.
    """

    async def get_response(self, path: str, scope):  # noqa: D102
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from starlette.responses import Response as _Resp

        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            if _ASSET_RE.search(path.split("?")[0]):
                raise
            try:
                return await super().get_response("index.html", scope)
            except StarletteHTTPException:
                return _Resp(status_code=404, content=b"")


def mount(app) -> bool:
    """کلاینت دانشجو را mount می‌کند؛ اگر بیلد نبود، 503 روشن می‌دهد.

    برخلاف `raise`، نبودِ بیلد کل سرویس را نمی‌خواباند: داشبورد ادمین
    و مینی‌اپ و ربات باید در هر حال کار کنند.
    """
    from fastapi.responses import JSONResponse

    built = os.path.isdir(DIST) and os.path.isfile(os.path.join(DIST, "index.html"))
    if built:
        app.mount(PREFIX, _Spa(directory=DIST, html=True), name="web-student-spa")
        logger.info("web_student_spa_mounted prefix=%s", PREFIX)
        return True

    @app.get(PREFIX, include_in_schema=False)
    @app.get(PREFIX + "/", include_in_schema=False)
    async def _student_not_built():
        return JSONResponse(
            status_code=503,
            content={
                "detail": "web_student_build_not_present",
                "hint": "build it: cd apps/student && npm install && npm run build",
                "expected": os.path.relpath(DIST, _ROOT),
            },
        )

    logger.warning("web_student_spa_missing dist=%s", os.path.relpath(DIST, _ROOT))
    return False
