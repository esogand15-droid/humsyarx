"""📞 م9.2 / م9.3 — پل تماس صوتی زنده‌ی هوشیار داخل ویس‌چت گروه‌های تلگرام (Group Voice Chat)

معماری:
  • تلگرام به ربات‌های عادی (Bot API) اجازه‌ی ورود به ویس‌چت گروهی (phone.JoinGroupCall) را نمی‌دهد.
  • این ماژول با استفاده از یک اکانت دستیار تلگرام (Userbot / MTProto با Kurigram/Pyrogram + PyTgCalls 3.0)
    وارد ویس‌چت گروه می‌شود و جریان صوتی دوطرفه را مستقیماً به Google Gemini Live API
    (BidiGenerateContent) متصل می‌کند:
      - صدای اعضای حاضر در ویس‌چت گروه (16kHz, 16-bit, mono PCM) ← RecordStream ← ارسال به Gemini Live
      - صدای پاسخ زنده‌ی هوشیار (24kHz, 16-bit, mono PCM) ← دریافت از Gemini Live ← send_frame به ویس‌چت گروه
      - پشتیبانی کامل از پریدن وسط حرف (Barge-in / interrupted) و ابزارهای هوشیار.
  • شامل ویزارد ورود تعاملی (ارسال کد تایید تلگرام، پشتیبانی ۲ مرحله‌ای 2FA و ثبت خودکار session_string رمزنگاری‌شده)
    در پنل ادمین وب تا نیازی به ساخت دستی session_string در بیرون از سیستم نباشد.
"""
from __future__ import annotations

import array
import asyncio
import base64
import inspect
import json
import logging
import os
import re
import time
from typing import Any

import httpx

from database import db

try:
    from utils_crypto import decrypt_value as _decrypt_val, encrypt_value as _encrypt_val
except Exception:
    _decrypt_val = lambda x: x if isinstance(x, str) else (x.get("c", "") if isinstance(x, dict) else str(x or ""))
    _encrypt_val = lambda x: x


def decrypt_secret(val) -> str:
    if not val:
        return ""
    try:
        res = _decrypt_val(val)
        return str(res or "")
    except Exception:
        return str(val) if isinstance(val, str) else ""


def encrypt_secret(val: str):
    if not val:
        return ""
    try:
        return _encrypt_val(val)
    except Exception:
        return val


logger = logging.getLogger(__name__)

# کلیدهای تنظیمات در دیتابیس (bot_settings)
SET_VC_API_ID = "tg_vc_api_id"
SET_VC_API_HASH = "tg_vc_api_hash"
SET_VC_SESSION = "tg_vc_session_string"
SET_VC_AUTO_JOIN = "tg_vc_auto_join"
SET_VC_ASSISTANT_ME = "tg_vc_assistant_me"
SET_VC_ACTIVE_CALLS = "tg_vc_active_calls"

# جدول تبدیل ارقام فارسی و عربی به انگلیسی
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _normalize_digits(val: str | int | None) -> str:
    if val is None:
        return ""
    s = str(val).translate(_DIGIT_MAP)
    # حذف کاراکترهای جهت‌دهی مخفی یونیکد (LTR/RTL marks)
    return re.sub(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069]", "", s).strip()


def _normalize_phone(phone: str) -> str:
    """نرمال‌سازی شماره موبایل تلگرام (پشتیبانی از ارقام فارسی، 0912...، 0098... و +98...)."""
    s = _normalize_digits(phone)
    s = re.sub(r"[\s\-()]+", "", s)
    if s.startswith("00"):
        s = "+" + s[2:]
    elif s.startswith("09") and len(s) == 11 and s[1:].isdigit():
        s = "+98" + s[1:]
    elif s.startswith("9") and len(s) == 10 and s.isdigit():
        s = "+98" + s
    elif s.startswith("989") and len(s) == 12 and s.isdigit():
        s = "+" + s
    elif s and s.isdigit() and not s.startswith("+"):
        s = "+" + s
    return s


def _ensure_pyrogram_compat() -> None:
    """🩹 م9.3 — سازگاری کامل Pyrogram 2.0.106 و Kurigram 2.2+ با py-tgcalls 3.0.0.

    اگر در ایمیج قبلی هنوز pyrogram==2.0.106 کش شده باشد، کلاس‌های خطا و TL جدیدی که
    `pytgcalls.mtproto.pyrogram_client` در سطح ماژول import می‌کند را شیم می‌کند تا
    هرگز خطای `cannot import name 'GroupcallForbidden' from 'pyrogram.errors'` رخ ندهد.
    """
    try:
        import pyrogram.errors as pyro_errors
        import pyrogram.raw.functions.phone as pyro_phone
        import pyrogram.raw.types as pyro_types
        from pyrogram.raw.core import TLObject
    except Exception:
        return

    base_forbidden = getattr(pyro_errors, "Forbidden", getattr(pyro_errors, "RPCError", Exception))
    base_bad_req = getattr(pyro_errors, "BadRequest", getattr(pyro_errors, "RPCError", Exception))

    if not hasattr(pyro_errors, "GroupcallForbidden"):
        setattr(
            pyro_errors,
            "GroupcallForbidden",
            type("GroupcallForbidden", (base_forbidden,), {"ID": "GROUPCALL_FORBIDDEN"}),
        )
    if not hasattr(pyro_errors, "GroupcallInvalid"):
        setattr(
            pyro_errors,
            "GroupcallInvalid",
            type("GroupcallInvalid", (base_bad_req,), {"ID": "GROUPCALL_INVALID"}),
        )

    for fn_name in (
        "CreateConferenceCall",
        "GetGroupCallChainBlocks",
        "InviteConferenceCallParticipant",
        "SendConferenceCallBroadcast",
    ):
        if not hasattr(pyro_phone, fn_name):
            setattr(
                pyro_phone,
                fn_name,
                type(fn_name, (TLObject,), {"__init__": lambda self, **kw: self.__dict__.update(kw)}),
            )

    for tp_name in (
        "InputGroupCallInviteMessage",
        "InputGroupCallSlug",
        "MessageActionConferenceCall",
        "PhoneCallDiscardReasonMigrateConferenceCall",
        "UpdateGroupCallChainBlocks",
    ):
        if not hasattr(pyro_types, tp_name):
            setattr(
                pyro_types,
                tp_name,
                type(tp_name, (TLObject,), {"__init__": lambda self, **kw: self.__dict__.update(kw)}),
            )

    # در pyrogram 2.0.106 متد JoinGroupCall.__init__ آرگومان‌های block و public_key را نداشت
    join_cls = getattr(pyro_phone, "JoinGroupCall", None)
    if join_cls is not None and not getattr(join_cls, "_hy_patched", False):
        try:
            sig = inspect.signature(join_cls.__init__)
            if "public_key" not in sig.parameters:
                orig_init = join_cls.__init__

                def _compat_join_init(self, *args, **kwargs):
                    kwargs.pop("block", None)
                    kwargs.pop("public_key", None)
                    return orig_init(self, *args, **kwargs)

                join_cls.__init__ = _compat_join_init
            join_cls._hy_patched = True
        except Exception:
            pass


# اجرای شیم سازگاری در همان لحظه‌ی import ماژول
_ensure_pyrogram_compat()


def _friendly_tg_error(e: Exception) -> str:
    """تبدیل خطاهای فنی Pyrogram / PyTgCalls به پیام فارسی دقیق و راهنما."""
    raw = str(e or "")
    up = raw.upper()
    cls_name = type(e).__name__

    if "API_ID_INVALID" in up or cls_name == "ApiIdInvalid":
        return "API_ID یا API_HASH نامعتبر است؛ مقادیر را دقیقاً از my.telegram.org (بخش API development tools) کپی کنید."
    if "API_ID_PUBLISHED_FLOOD" in up:
        return "این API_ID در تلگرام محدود شده است؛ لطفاً از API_ID اختصاصی خودتان از my.telegram.org استفاده کنید."
    if "PHONE_NUMBER_INVALID" in up or cls_name == "PhoneNumberInvalid":
        return "فرمت شماره موبایل نامعتبر است؛ شماره را با پیش‌شماره کشور وارد کنید (مثلاً +989123456789)."
    if "PHONE_NUMBER_BANNED" in up or cls_name == "PhoneNumberBanned":
        return "این شماره موبایل از سمت تلگرام مسدود شده است؛ از یک اکانت دیگر برای دستیار استفاده کنید."
    if "PHONE_CODE_INVALID" in up or cls_name == "PhoneCodeInvalid":
        return "کد تایید ۵ رقمی واردشده اشتباه است؛ لطفاً کد را بررسی کرده و دوباره تایید را بزنید."
    if "PHONE_CODE_EXPIRED" in up or cls_name == "PhoneCodeExpired":
        return (
            "کد تایید منقضی شده است (توجه: اگر کد را داخل چت تلگرام برای کسی فوروارد کنید تلگرام فوراً آن را باطل می‌کند). "
            "لطفاً دوباره دکمه «ارسال کد تایید» را بزنید."
        )
    if "PASSWORD_HASH_INVALID" in up or cls_name == "PasswordHashInvalid":
        return "رمز تایید دو مرحله‌ای (Two-Step Verification / 2FA) اشتباه است؛ دوباره بررسی و وارد کنید."
    if "FLOOD_WAIT" in up or cls_name == "FloodWait":
        return f"تلگرام محدودیت زمانی موقت (FloodWait) اعمال کرده است ({raw}). چند دقیقه صبر کنید."
    if "CHAT_ADMIN_REQUIRED" in up or cls_name == "ChatAdminRequired":
        return (
            "ویس‌چت در گروه باز نیست یا اکانت دستیار دسترسی ادمین «مدیریت ویس‌چت» را ندارد. "
            "ابتدا ویس‌چت (Video Chat) را در گروه باز کنید و سپس دکمه دعوت هوشیار را بزنید."
        )
    if "GROUPCALL_FORBIDDEN" in up or "GROUPCALL_INVALID" in up or cls_name in ("NoActiveGroupCall", "GroupCallNotFound"):
        return "ویس‌چت فعالی در این گروه پیدا نشد؛ ابتدا ویس‌چت (Video Chat) گروه را باز کنید."
    if "PEER_ID_INVALID" in up or "CHANNEL_INVALID" in up or "CHANNEL_PRIVATE" in up or cls_name == "PeerIdInvalid":
        return (
            "اکانت دستیار هنوز به این گروه دسترسی ندارد. مطمئن شوید اکانت دستیار در گروه عضو است "
            "(یا ربات اصلی در گروه ادمین است تا بتواند دستیار را خودکار دعوت کند)."
        )
    if "AUTH_KEY_UNREGISTERED" in up or "SESSION_REVOKED" in up or "USER_DEACTIVATED" in up:
        return "نشست (Session) اکانت دستیار در تلگرام باطل شده است؛ از پنل مدیریت وب دوباره اکانت دستیار را متصل کنید."
    return raw or f"خطای تلگرام ({cls_name})"


# وضعیت کلاینت MTProto / PyTgCalls در سطح پروسه
_client_lock = asyncio.Lock()
_pyro_client: Any = None
_pytgcalls: Any = None
_assistant_me: dict | None = None

# وضعیت ویزارد لاگین OTP در پنل ادمین وب
_login_state: dict = {
    "client": None,
    "api_id": 0,
    "api_hash": "",
    "phone": "",
    "phone_code_hash": "",
    "awaiting_2fa": False,
    "created_at": 0.0,
}

# نشست‌های فعال ویس‌چت گروهی: chat_id (int) -> _GroupLiveSession
_active_sessions: dict[int, "_GroupLiveSession"] = {}


async def _sync_active_calls_to_db() -> None:
    """ذخیره لیست تماس‌های فعال در دیتابیس تا هم پروسه bot و هم پروسه web-admin آن را ببینند."""
    try:
        now = time.monotonic()
        items = [
            {
                "chat_id": cid,
                "title": s.title,
                "model": s.model,
                "voice": s.voice,
                "started_ts": int(time.time() - max(0.0, now - s.started_at)),
            }
            for cid, s in list(_active_sessions.items())
        ]
        await db.set_setting(SET_VC_ACTIVE_CALLS, json.dumps(items, ensure_ascii=False))
    except Exception:
        pass


async def get_vc_credentials() -> dict:
    """دریافت API_ID، API_HASH و SESSION_STRING از دیتابیس (یا متغیرهای محیطی Railway)."""
    raw_id = await db.get_setting(SET_VC_API_ID, "") or os.getenv("TELEGRAM_API_ID") or ""
    raw_hash_enc = await db.get_setting(SET_VC_API_HASH, "")
    raw_sess_enc = await db.get_setting(SET_VC_SESSION, "")
    auto_join = (await db.get_setting(SET_VC_AUTO_JOIN, "1")) == "1"

    api_hash = decrypt_secret(raw_hash_enc) if raw_hash_enc else (os.getenv("TELEGRAM_API_HASH") or "")
    session_string = (
        decrypt_secret(raw_sess_enc)
        if raw_sess_enc
        else (os.getenv("TELEGRAM_ASSISTANT_SESSION") or "")
    )
    try:
        api_id = int(_normalize_digits(raw_id))
    except (TypeError, ValueError):
        api_id = 0

    clean_hash = _normalize_digits(api_hash).strip().strip("\"'")
    clean_sess = (session_string or "").strip().strip("\"'")

    return {
        "api_id": api_id,
        "api_hash": clean_hash,
        "session_string": clean_sess,
        "auto_join": auto_join,
    }


async def save_vc_credentials(
    api_id: int | str | None = None,
    api_hash: str | None = None,
    session_string: str | None = None,
    auto_join: bool | None = None,
) -> dict:
    """ذخیره امن مشخصات اکانت دستیار ویس‌چت گروهی در دیتابیس (با رمزنگاری Fernet)."""
    if api_id is not None and _normalize_digits(api_id):
        try:
            aid = int(_normalize_digits(api_id))
        except ValueError:
            raise ValueError("مقدار API_ID باید یک عدد صحیح معتبر باشد (از my.telegram.org).")
        if aid <= 0:
            raise ValueError("مقدار API_ID باید بزرگ‌تر از صفر باشد.")
        await db.set_setting(SET_VC_API_ID, str(aid))

    if api_hash is not None and api_hash.strip():
        h_clean = _normalize_digits(api_hash).strip().strip("\"'")
        if len(h_clean) < 16:
            raise ValueError("مقدار API_HASH نامعتبر است؛ رشته ۳۲ کاراکتری را از my.telegram.org کپی کنید.")
        await db.set_setting(SET_VC_API_HASH, encrypt_secret(h_clean))

    if session_string is not None:
        s_clean = session_string.strip().strip("\"'")
        await db.set_setting(SET_VC_SESSION, encrypt_secret(s_clean) if s_clean else "")
        if not s_clean:
            await db.set_setting(SET_VC_ASSISTANT_ME, "")
        await stop_assistant_client()

    if auto_join is not None:
        await db.set_setting(SET_VC_AUTO_JOIN, "1" if auto_join else "0")
    return await get_assistant_status()


async def stop_assistant_client() -> None:
    """بستن همه‌ی تماس‌های فعال و خاموش کردن کلاینت دستیار."""
    global _pyro_client, _pytgcalls, _assistant_me
    for cid in list(_active_sessions.keys()):
        try:
            await leave_group_voice_chat(cid)
        except Exception:
            pass
    if _pyro_client is not None:
        try:
            await _pyro_client.stop()
        except Exception:
            pass
    _pyro_client = None
    _pytgcalls = None
    _assistant_me = None


async def start_assistant_login(
    api_id: int | str | None = None,
    api_hash: str | None = None,
    phone: str = "",
) -> dict:
    """گام ۱ ویزارد پنل وب: ارسال کد تایید تلگرام (OTP) به شماره موبایل اکانت دستیار."""
    _ensure_pyrogram_compat()
    from pyrogram import Client

    creds = await get_vc_credentials()
    raw_id = _normalize_digits(api_id) if api_id else str(creds["api_id"] or "")
    try:
        clean_api_id = int(raw_id) if raw_id else 0
    except ValueError:
        clean_api_id = 0

    clean_api_hash = (_normalize_digits(api_hash).strip().strip("\"'") if api_hash else "") or creds["api_hash"]
    clean_phone = _normalize_phone(phone)

    if not clean_api_id or clean_api_id <= 0:
        raise ValueError("لطفاً API_ID معتبر (عدد دریافتی از my.telegram.org) را وارد کنید.")
    if not clean_api_hash or len(clean_api_hash) < 16:
        raise ValueError("لطفاً API_HASH معتبر (رشته ۳۲ کاراکتری از my.telegram.org) را وارد کنید.")
    if not clean_phone or len(clean_phone) < 8:
        raise ValueError("لطفاً شماره موبایل اکانت دستیار را وارد کنید (مثلاً +989123456789 یا 09123456789).")

    old_cli = _login_state.get("client")
    if old_cli is not None:
        try:
            await old_cli.disconnect()
        except Exception:
            pass
        _login_state["client"] = None

    cli = Client(
        name="humsyar_vc_login",
        api_id=clean_api_id,
        api_hash=clean_api_hash,
        in_memory=True,
        no_updates=True,
        workdir="/tmp",
    )
    try:
        await cli.connect()
        sent = await cli.send_code(clean_phone)
    except Exception as e:
        try:
            await cli.disconnect()
        except Exception:
            pass
        raise RuntimeError(f"ارسال کد از سمت تلگرام ناموفق بود: {_friendly_tg_error(e)}") from e

    _login_state.update({
        "client": cli,
        "api_id": clean_api_id,
        "api_hash": clean_api_hash,
        "phone": clean_phone,
        "phone_code_hash": sent.phone_code_hash,
        "awaiting_2fa": False,
        "created_at": time.monotonic(),
    })
    await db.set_setting(SET_VC_API_ID, str(clean_api_id))
    await db.set_setting(SET_VC_API_HASH, encrypt_secret(clean_api_hash))
    return {
        "ok": True,
        "phone": clean_phone,
        "message": f"کد تایید ۵ رقمی به تلگرام شماره {clean_phone} ارسال شد ✅",
    }


async def verify_assistant_login(code: str = "", password: str = "") -> dict:
    """گام ۲ ویزارد پنل وب: تایید کد ۵ رقمی (و رمز تایید دو مرحله‌ای در صورت وجود) و ذخیره session_string."""
    _ensure_pyrogram_compat()
    from pyrogram.errors import SessionPasswordNeeded

    cli = _login_state.get("client")
    if cli is None or not _login_state.get("phone_code_hash"):
        raise RuntimeError("نشست ورود منقضی شده است؛ لطفاً دوباره دکمه «ارسال کد تایید» را بزنید.")

    if not getattr(cli, "is_connected", False):
        try:
            await cli.connect()
        except Exception:
            pass

    clean_code = re.sub(r"[\s\-]+", "", _normalize_digits(code))
    awaiting_2fa = bool(_login_state.get("awaiting_2fa"))

    if not awaiting_2fa and not clean_code:
        raise ValueError("کد تایید ۵ رقمی تلگرام را وارد کنید.")

    should_close = False
    try:
        if awaiting_2fa:
            if not password:
                return {
                    "ok": False,
                    "needs_2fa": True,
                    "message": "این اکانت تایید دو مرحله‌ای (2FA) دارد؛ لطفاً رمز دوم را وارد کنید.",
                }
            await cli.check_password(password)
        else:
            try:
                await cli.sign_in(
                    phone_number=_login_state["phone"],
                    phone_code_hash=_login_state["phone_code_hash"],
                    phone_code=clean_code,
                )
            except SessionPasswordNeeded:
                _login_state["awaiting_2fa"] = True
                if not password:
                    # ⚠️ مهم: کلاینت نباید بسته شود تا در کلیک بعدی رمز 2FA روی همین نشست چک شود!
                    return {
                        "ok": False,
                        "needs_2fa": True,
                        "message": "کد تایید درست بود ✅؛ این اکانت رمز دو مرحله‌ای (2FA) دارد — رمز دوم را وارد کرده و دوباره تایید را بزنید.",
                    }
                await cli.check_password(password)

        session_str = await cli.export_session_string()
        me = await cli.get_me()
        info = {
            "id": me.id,
            "first_name": getattr(me, "first_name", "") or "دستیار هوشیار",
            "username": getattr(me, "username", "") or "",
            "phone": getattr(me, "phone_number", "") or _login_state["phone"],
        }
        should_close = True
    except Exception as e:
        up = str(e or "").upper()
        # اگر فقط کد یا رمز 2FA اشتباه تایپ شده، کلاینت را باز نگه می‌داریم تا کاربر اصلاح کند
        if "PHONE_CODE_EXPIRED" in up or type(e).__name__ == "PhoneCodeExpired":
            should_close = True
        raise RuntimeError(_friendly_tg_error(e)) from e
    finally:
        if should_close:
            try:
                await cli.disconnect()
            except Exception:
                pass
            _login_state["client"] = None
            _login_state["awaiting_2fa"] = False

    await db.set_setting(SET_VC_ASSISTANT_ME, json.dumps(info, ensure_ascii=False))
    await save_vc_credentials(
        api_id=_login_state["api_id"],
        api_hash=_login_state["api_hash"],
        session_string=session_str,
    )
    return {
        "ok": True,
        "needs_2fa": False,
        "assistant": info,
        "message": f"اکانت دستیار «{info['first_name']}» با موفقیت متصل و ذخیره شد ✅",
    }


def _mix_pcm16_frames(frames_bytes: list[bytes]) -> bytes:
    """میکس کردن چند فریم صوتی PCM16 هم‌زمان (از چند گوینده در ویس‌چت گروه) با جلوگیری از Clipping."""
    valid = [f for f in frames_bytes if f and len(f) >= 2]
    if not valid:
        return b""
    if len(valid) == 1:
        v0 = valid[0]
        return v0 if (len(v0) % 2 == 0) else v0[:-1]
    min_len = min(len(f) for f in valid)
    min_len -= (min_len % 2)
    if min_len <= 0:
        return b""
    acc = array.array("h")
    acc.frombytes(valid[0][:min_len])
    for extra in valid[1:]:
        arr = array.array("h")
        arr.frombytes(extra[:min_len])
        for i in range(len(acc)):
            s = int(acc[i]) + int(arr[i])
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            acc[i] = s
    return acc.tobytes()


# ── ثوابت موتور صوتی WebRTC / ntgcalls (م9.4) ──
# در ntgcalls::media::AudioSink نرخ فریم ثابت 100Hz (هر فریم دقیقاً 10ms) است و
# AudioStreamer::send_data همیشه فقط به اندازه frame_size = (sample_rate * 2 / 100) * channels
# به WebRTC AudioTrackSinkInterface::OnData تحویل می‌دهد.
# نرخ بومی Opus در WebRTC تلگرام 48000Hz است (هر 10ms دقیقاً 480 نمونه = 960 بایت mono).
VC_OUT_SAMPLE_RATE = 48000
VC_OUT_CHANNELS = 1
VC_FRAME_DURATION_SEC = 0.010  # 10ms (100 fps — الزام سخت ntgcalls::media::AudioSink::frame_rate)
VC_FRAME_SAMPLES = VC_OUT_SAMPLE_RATE // 100  # 480 samples per 10ms
VC_FRAME_BYTES = VC_FRAME_SAMPLES * 2 * VC_OUT_CHANNELS  # 960 bytes per 10ms
VC_PREBUFFER_FRAMES = 14  # 140ms پیش‌بافرینگ (Jitter Buffer) قبل از شروع هر نوبت صحبت
VC_PREBUFFER_BYTES = VC_FRAME_BYTES * VC_PREBUFFER_FRAMES  # 13,440 bytes
VC_PREBUFFER_MAX_WAIT_SEC = 0.16  # حداکثر انتظار برای پر شدن Jitter Buffer
_SILENCE_FRAME_48K_10MS = b"\x00" * VC_FRAME_BYTES


def _upsample_pcm16_24k_to_48k(pcm24k: bytes, prev_sample: int = 0) -> tuple[bytes, int]:
    """تبدیل نرخ نمونه‌برداری باکیفیت و بدون پرش مرز چانک از 24000Hz به 48000Hz (PCM16 mono).

    از درونیابی خطی نقطه‌میانی (فیلتر مثلثی بدون اعوجاج فاز) با حفظ آخرین نمونه‌ی چانک قبلی
    استفاده می‌کند تا بین چانک‌های متوالی هیچ پرش پله‌ای (Click / Crackle) ایجاد نشود.
    """
    if not pcm24k or len(pcm24k) < 2:
        return b"", prev_sample
    if len(pcm24k) % 2 != 0:
        pcm24k = pcm24k[:-1]
    src = array.array("h")
    src.frombytes(pcm24k)
    n = len(src)
    if n == 0:
        return b"", prev_sample
    dst = array.array("h", [0]) * (n * 2)
    p = int(prev_sample)
    for i in range(n):
        c = int(src[i])
        dst[2 * i] = (p + c) >> 1
        dst[2 * i + 1] = c
        p = c
    return dst.tobytes(), p


def _apply_fade_in_pcm16(frame_bytes: bytes, start_sample: int = 0, ramp_samples: int = 96) -> bytes:
    """نرم‌سازی لبه‌ی شروع صحبت (2ms = 96 نمونه در 48kHz) برای حذف کامل صدای تق/خش‌خش ابتدای جمله."""
    if not frame_bytes or len(frame_bytes) < 4:
        return frame_bytes
    arr = array.array("h")
    arr.frombytes(frame_bytes)
    n = min(len(arr), max(1, ramp_samples))
    s0 = int(start_sample)
    for i in range(n):
        w = (i + 1) / float(n)
        val = int(round(s0 * (1.0 - w) + int(arr[i]) * w))
        if val > 32767:
            val = 32767
        elif val < -32768:
            val = -32768
        arr[i] = val
    return arr.tobytes()


def _make_fadeout_frame_pcm16(last_sample: int, num_samples: int = VC_FRAME_SAMPLES) -> bytes:
    """ساخت یک فریم 10ms با شیب ملایم به صفر (Fade-Out) هنگام اتمام صحبت یا Barge-in برای حذف صدای تق."""
    s0 = int(last_sample)
    if abs(s0) <= 4:
        return _SILENCE_FRAME_48K_10MS
    arr = array.array("h", [0]) * num_samples
    ramp = min(num_samples, 192)  # 4ms نرم‌سازی به صفر
    for i in range(ramp):
        w = 1.0 - ((i + 1) / float(ramp))
        arr[i] = int(round(s0 * w * w))
    return arr.tobytes()


async def _ensure_assistant_started() -> tuple[Any, Any, dict]:
    """راه‌اندازی Singleton کلاینت Pyrogram/Kurigram و PyTgCalls برای اکانت دستیار."""
    global _pyro_client, _pytgcalls, _assistant_me
    async with _client_lock:
        if _pyro_client is not None and _pytgcalls is not None and _assistant_me is not None:
            return _pyro_client, _pytgcalls, _assistant_me

        creds = await get_vc_credentials()
        if not creds["api_id"] or not creds["api_hash"] or not creds["session_string"]:
            raise RuntimeError(
                "اکانت دستیار ویس‌چت گروهی هنوز تنظیم نشده است. "
                "از «پنل مدیریت وب ← هوشیار ← تماس صوتی زنده ← دستیار ویس‌چت گروه» اکانت دستیار را متصل کنید."
            )

        _ensure_pyrogram_compat()
        from pyrogram import Client
        from pytgcalls import PyTgCalls, filters
        from pytgcalls.types import Device, Direction, StreamFrames

        cli = Client(
            name="humsyar_vc_assistant",
            api_id=int(creds["api_id"]),
            api_hash=creds["api_hash"],
            session_string=creds["session_string"],
            in_memory=True,
            workdir="/tmp",
        )
        call_py = PyTgCalls(cli)

        @call_py.on_update(filters.stream_frame(Direction.INCOMING, Device.MICROPHONE | Device.SPEAKER))
        async def _on_incoming_voice(_client: Any, update: StreamFrames):
            sess = _active_sessions.get(int(update.chat_id))
            if sess is None or not update.frames:
                return
            mixed = _mix_pcm16_frames([f.frame for f in update.frames if getattr(f, "frame", None)])
            if mixed:
                sess.on_incoming_pcm16_16k(mixed)

        try:
            await call_py.start()
            me = await cli.get_me()
        except Exception as e:
            try:
                await cli.stop()
            except Exception:
                pass
            raise RuntimeError(f"راه‌اندازی اکانت دستیار ناموفق بود: {_friendly_tg_error(e)}") from e

        # گرم‌کردن کش Peerهای MemoryStorage با دریافت لیست گفتگوهای اکانت دستیار
        # (بدون این گام، در حالت in_memory=True مقدار access_hash سوپرگروه‌ها در کش نیست و PeerIdInvalid می‌دهد)
        try:
            async for _ in cli.get_dialogs(limit=200):
                pass
        except Exception as dlg_err:
            logger.debug("TG_VC_DIALOGS_WARMUP_WARN err=%s", dlg_err)

        _pyro_client = cli
        _pytgcalls = call_py
        _assistant_me = {
            "id": me.id,
            "first_name": getattr(me, "first_name", "") or "دستیار هوشیار",
            "username": getattr(me, "username", "") or "",
        }
        try:
            await db.set_setting(SET_VC_ASSISTANT_ME, json.dumps(_assistant_me, ensure_ascii=False))
        except Exception:
            pass
        logger.info("TG_VC_ASSISTANT_STARTED id=%s username=@%s", me.id, _assistant_me["username"])
        return _pyro_client, _pytgcalls, _assistant_me


async def _fetch_invite_link_via_bot_token(chat_id: int | str) -> str | None:
    """دریافت لینک دعوت گروه از طریق BOT_TOKEN (برای زمانی که از پنل وب بدون شیء bot فراخوانی شده)."""
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        return None
    base = f"https://api.telegram.org/bot{token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/exportChatInviteLink", json={"chat_id": chat_id})
            data = r.json()
            if data.get("ok") and data.get("result"):
                return str(data["result"])
            r2 = await client.post(f"{base}/getChat", json={"chat_id": chat_id})
            d2 = r2.json()
            if d2.get("ok") and isinstance(d2.get("result"), dict):
                res = d2["result"]
                if res.get("invite_link"):
                    return str(res["invite_link"])
                if res.get("username"):
                    return f"@{res['username']}"
    except Exception as e:
        logger.debug("TG_VC_BOT_API_INVITE_ERR chat=%s err=%s", chat_id, e)
    return None


async def _ensure_assistant_in_group(
    pyro_cli: Any,
    chat_target: int | str,
    bot: Any = None,
    assistant_me: dict | None = None,
) -> tuple[int, str]:
    """اطمینان از عضویت اکانت دستیار در گروه و کش شدن InputPeer (access_hash) در MemoryStorage."""
    raw_target = _normalize_digits(chat_target)

    # پشتیبانی از لینک‌های t.me/c/1234567890/...
    m_c = re.search(r"t\.me/c/(\d+)", raw_target)
    if m_c:
        raw_target = f"-100{m_c.group(1)}"

    # اگر لینک دعوت مستقیم یا @username داده شده، ابتدا با همان join/get_chat کنیم
    if raw_target.startswith(("http://", "https://", "t.me/", "@")):
        try:
            chat_obj = await pyro_cli.join_chat(raw_target)
            return int(chat_obj.id), getattr(chat_obj, "title", "") or str(chat_obj.id)
        except Exception:
            chat_obj = await pyro_cli.get_chat(raw_target)
            return int(chat_obj.id), getattr(chat_obj, "title", "") or str(chat_obj.id)

    try:
        cid = int(raw_target)
    except ValueError:
        raise ValueError(
            "شناسه گروه (Chat ID) نامعتبر است؛ آیدی عددی گروه (مثلاً -1001234567890) یا @username گروه را وارد کنید."
        )

    # اگر کاربر آیدی سوپرگروه را مثبت بدون -100 وارد کرده (مثلاً 1001234567890)
    if cid > 1000000000000:
        cid = -cid

    # ۱) تلاش اول: بررسی مستقیم در کش فعلی
    try:
        chat_obj = await pyro_cli.get_chat(cid)
        return int(chat_obj.id), getattr(chat_obj, "title", "") or str(cid)
    except Exception:
        pass

    # ۲) تلاش دوم: تازه‌سازی دیالوگ‌ها (اگر دستیار قبلاً در گروه عضو شده ولی در کش نبوده)
    try:
        async for _ in pyro_cli.get_dialogs(limit=200):
            pass
        chat_obj = await pyro_cli.get_chat(cid)
        return int(chat_obj.id), getattr(chat_obj, "title", "") or str(cid)
    except Exception:
        pass

    # ۳) تلاش سوم: عضویت خودکار دستیار در گروه از طریق لینک دعوت ربات اصلی
    invite_link: str | None = None
    if bot is not None:
        if assistant_me and assistant_me.get("id"):
            try:
                await bot.unban_chat_member(cid, int(assistant_me["id"]), only_if_banned=True)
            except Exception:
                pass
        try:
            invite_link = await bot.export_chat_invite_link(cid)
        except Exception:
            try:
                tg_chat = await bot.get_chat(cid)
                invite_link = getattr(tg_chat, "invite_link", None) or (
                    f"@{tg_chat.username}" if getattr(tg_chat, "username", None) else None
                )
            except Exception:
                pass

    if not invite_link:
        invite_link = await _fetch_invite_link_via_bot_token(cid)

    if invite_link:
        try:
            await pyro_cli.join_chat(invite_link)
        except Exception as join_err:
            if "USER_ALREADY_PARTICIPANT" not in str(join_err).upper():
                logger.warning("TG_VC_JOIN_CHAT_WARN chat=%s err=%s", cid, join_err)
        try:
            async for _ in pyro_cli.get_dialogs(limit=100):
                pass
        except Exception:
            pass

    try:
        chat_obj = await pyro_cli.get_chat(cid)
        return int(chat_obj.id), getattr(chat_obj, "title", "") or str(cid)
    except Exception as final_err:
        uname = f"@{assistant_me['username']}" if (assistant_me and assistant_me.get("username")) else (
            assistant_me.get("first_name", "اکانت دستیار") if assistant_me else "اکانت دستیار"
        )
        raise RuntimeError(
            f"اکانت دستیار ({uname}) هنوز عضو این گروه ({cid}) نیست و ربات هم دسترسی ساخت لینک دعوت را نداشت. "
            f"لطفاً ابتدا {uname} را در گروه عضو کنید (یا ربات را در گروه ادمین کنید) و دوباره تلاش کنید."
        ) from final_err


class _GroupLiveSession:
    """نشست زنده‌ی اتصال یک ویس‌چت گروه تلگرام به Google Gemini Live API (م9.4 — بهینه‌سازی 48kHz 10ms)."""

    def __init__(self, chat_id: int, title: str, model: str, voice: str, google_ws: Any, call_py: Any):
        self.chat_id = int(chat_id)
        self.title = title or str(chat_id)
        self.model = model
        self.voice = voice
        self.google_ws = google_ws
        self.call_py = call_py
        self.started_at = time.monotonic()
        self.last_audio_in_at = 0.0
        self.last_audio_out_at = 0.0
        self.first_buffered_at = 0.0
        self.in_buf = bytearray()
        self.out_buf = bytearray()  # 48000Hz 16-bit mono PCM (960 bytes = 10ms)
        self._upsample_prev_sample = 0
        self._last_out_sample = 0
        self._playout_active = False
        self._needs_fade_in = True
        self._turn_complete = False
        self.closed = False
        self.tasks: list[asyncio.Task] = []

    def on_incoming_pcm16_16k(self, pcm_bytes: bytes) -> None:
        if self.closed or not pcm_bytes:
            return
        # جلوگیری از انباشته شدن تاخیر بیش از ۲ ثانیه در صورت کندی موقت شبکه
        if len(self.in_buf) > 64000:
            del self.in_buf[:-32000]
        self.in_buf.extend(pcm_bytes)
        self.last_audio_in_at = time.monotonic()

    def enqueue_gemini_pcm24k(self, pcm24k: bytes) -> None:
        """تبدیل بی‌درنگ چانک صوتی 24kHz جمینی به 48kHz بومی WebRTC و افزودن به Jitter Buffer."""
        if self.closed or not pcm24k:
            return
        pcm48k, self._upsample_prev_sample = _upsample_pcm16_24k_to_48k(
            pcm24k, self._upsample_prev_sample
        )
        if not pcm48k:
            return
        now = time.monotonic()
        if not self.out_buf:
            self.first_buffered_at = now
        self.out_buf.extend(pcm48k)
        self.last_audio_out_at = now
        self._turn_complete = False

    def clear_playback_buffer(self) -> None:
        """پاک‌سازی فوری صف پخش هنگام پریدن وسط حرف (Barge-in / interrupted)."""
        self.out_buf.clear()
        self._upsample_prev_sample = 0
        self._playout_active = False
        self._needs_fade_in = True
        self._turn_complete = False
        self.first_buffered_at = 0.0

    def pop_next_10ms_frame(self, now: float | None = None) -> bytes:
        """استخراج دقیق یک فریم 10ms (۹۶۰ بایت در 48kHz mono) با Jitter Buffer و حذف کامل خش‌خش/کلیک."""
        if now is None:
            now = time.monotonic()

        buf_len = len(self.out_buf)

        # ۱) حالت پیش‌بافرینگ (Jitter Buffer) در ابتدای هر نوبت صحبت هوشیار
        if not self._playout_active:
            if buf_len == 0:
                if abs(self._last_out_sample) > 4:
                    fade = _make_fadeout_frame_pcm16(self._last_out_sample)
                    self._last_out_sample = 0
                    return fade
                return _SILENCE_FRAME_48K_10MS

            waited = max(0.0, now - (self.first_buffered_at or now))
            ready = (
                buf_len >= VC_PREBUFFER_BYTES
                or self._turn_complete
                or waited >= VC_PREBUFFER_MAX_WAIT_SEC
            )
            if not ready:
                return _SILENCE_FRAME_48K_10MS

            self._playout_active = True
            self._needs_fade_in = True

        # ۲) حالت پخش پیوسته فریم‌های ۱۰ میلی‌ثانیه‌ای
        if buf_len >= VC_FRAME_BYTES:
            chunk = bytes(self.out_buf[:VC_FRAME_BYTES])
            del self.out_buf[:VC_FRAME_BYTES]
            if self._needs_fade_in:
                chunk = _apply_fade_in_pcm16(chunk, self._last_out_sample, ramp_samples=96)
                self._needs_fade_in = False
            self._last_out_sample = int.from_bytes(chunk[-2:], "little", signed=True)
            return chunk

        # ۳) انتهای جمله (چانک ناقص کمتر از 10ms که نوبت تمام شده یا بیش از 90ms داده جدید نیامده)
        if 0 < buf_len < VC_FRAME_BYTES and (
            self._turn_complete or (now - self.last_audio_out_at) > 0.09
        ):
            rem = bytes(self.out_buf)
            self.out_buf.clear()
            if len(rem) % 2 != 0:
                rem = rem[:-1]
            last_s = int.from_bytes(rem[-2:], "little", signed=True) if len(rem) >= 2 else self._last_out_sample
            missing_samples = (VC_FRAME_BYTES - len(rem)) // 2
            tail = _make_fadeout_frame_pcm16(last_s, num_samples=missing_samples) if missing_samples > 0 else b""
            chunk = rem + tail
            if self._needs_fade_in:
                chunk = _apply_fade_in_pcm16(chunk, self._last_out_sample, ramp_samples=48)
                self._needs_fade_in = False
            self._last_out_sample = 0
            self._playout_active = False
            self._needs_fade_in = True
            return chunk

        # ۴) خلا موقت شبکه در میانه صحبت (Underrun): بازگشت به پیش‌بافرینگ با شیب ملایم بدون صدای تق
        self._playout_active = False
        self._needs_fade_in = True
        self.first_buffered_at = now
        if abs(self._last_out_sample) > 4:
            fade = _make_fadeout_frame_pcm16(self._last_out_sample)
            self._last_out_sample = 0
            return fade
        return _SILENCE_FRAME_48K_10MS

    def start_loops(self) -> None:
        self.tasks = [
            asyncio.create_task(self._flush_incoming_to_gemini_loop()),
            asyncio.create_task(self._gemini_to_outgoing_loop()),
            asyncio.create_task(self._outgoing_pacer_loop()),
        ]

    async def _flush_incoming_to_gemini_loop(self) -> None:
        """ارسال کم‌تاخیر چانک‌های ~40-80ms (در 16kHz 16-bit mono) از ویس‌چت گروه به Gemini Live."""
        while not self.closed:
            await asyncio.sleep(0.04)
            buf_len = len(self.in_buf)
            if buf_len < 2:
                continue
            now = time.monotonic()
            # ارسال فوری وقتی حداقل 40ms (۱۲۸۰ بایت) جمع شده یا انتهای صحبت کاربر است (>100ms مکث)
            if buf_len < 1280 and (now - self.last_audio_in_at) < 0.10:
                continue
            take = min(buf_len, 6400)
            take -= (take % 2)
            if take <= 0:
                continue
            chunk = bytes(self.in_buf[:take])
            del self.in_buf[:take]
            b64 = base64.b64encode(chunk).decode("ascii")
            try:
                await self.google_ws.send(json.dumps({
                    "realtimeInput": {
                        "audio": {
                            "data": b64,
                            "mimeType": "audio/pcm;rate=16000",
                        }
                    }
                }))
            except Exception as e:
                logger.warning("TG_VC_SEND_GEMINI_ERR chat=%s err=%s", self.chat_id, e)
                break

    async def _gemini_to_outgoing_loop(self) -> None:
        """دریافت پاسخ صوتی 24kHz PCM16 و رویدادهای ابزار/Barge-in از Gemini Live."""
        from ai_solver import execute_live_tool_calls, parse_live_server_message

        try:
            async for raw in self.google_ws:
                if self.closed:
                    break
                evs = parse_live_server_message(raw)
                for ev in evs:
                    etype = ev.get("type")
                    if etype == "audio" and ev.get("data"):
                        try:
                            pcm24k = base64.b64decode(ev["data"])
                            self.enqueue_gemini_pcm24k(pcm24k)
                        except Exception:
                            pass
                    elif etype == "interrupted":
                        # وقتی یکی از اعضای گروه وسط صحبت هوشیار حرف بزند، صف پخش بلافاصله خالی می‌شود
                        self.clear_playback_buffer()
                    elif etype == "turn_state":
                        if ev.get("turn_complete") or ev.get("interaction_status") == "IDLE":
                            self._turn_complete = True
                    elif etype == "tool_call":
                        tool_resp = await execute_live_tool_calls(ev.get("calls") or [], 0)
                        await self.google_ws.send(json.dumps(tool_resp))
        except Exception as e:
            if not self.closed:
                logger.warning("TG_VC_GEMINI_RECV_CLOSED chat=%s err=%s", self.chat_id, e)

    async def _outgoing_pacer_loop(self) -> None:
        """تزریق دقیق فریم‌های ۱۰ میلی‌ثانیه‌ای (۹۶۰ بایت در 48kHz 16-bit mono = 100fps) به WebRTC تلگرام.

        نکته‌ی حیاتی معماری ntgcalls:
        در باینری ntgcalls، متد AudioSink::frame_rate() مقدار ثابت 100 (فریم‌های 10ms) دارد و
        AudioStreamer::send_data در هر فراخوانی دقیقاً 10ms (در 48kHz معادل 480 نمونه = 960 بایت)
        به WebRTC AudioTrackSinkInterface::OnData تحویل می‌دهد. ارسال مستمر هر 10ms با ساعت
        یکنواخت (Monotonic) هرگونه خش‌خش، پرش و Underrun کدک Opus را به‌طور کامل حذف می‌کند.
        """
        from pytgcalls.types import Device

        # مسیر سریع مستقیم به C++ binding برای حذف سربار دکوراتورهای PyTgCalls در ۱۰۰ فریم بر ثانیه
        binding = getattr(self.call_py, "_binding", None)
        fast_send = None
        if binding is not None and hasattr(binding, "send_external_frame"):
            try:
                from ntgcalls import FrameData
                raw_dev = Device.to_raw(Device.MICROPHONE)
                raw_fd = FrameData(0, False, 0, 0)
                fast_send = (binding.send_external_frame, raw_dev, raw_fd)
            except Exception:
                fast_send = None

        next_tick = time.monotonic()
        err_streak = 0
        while not self.closed:
            now = time.monotonic()
            if now < next_tick:
                await asyncio.sleep(next_tick - now)
                now = time.monotonic()

            # حفظ ساعت دقیق 10ms بدون تجمیع خطای زمانی (جلوگیری از شتاب ناگهانی پس از توقف‌های کوتاه)
            next_tick += VC_FRAME_DURATION_SEC
            if now - next_tick > 0.050:
                next_tick = now + VC_FRAME_DURATION_SEC

            chunk = self.pop_next_10ms_frame(now)
            try:
                if fast_send is not None:
                    fn, r_dev, r_fd = fast_send
                    await fn(self.chat_id, r_dev, chunk, r_fd)
                else:
                    await self.call_py.send_frame(self.chat_id, Device.MICROPHONE, chunk)
                err_streak = 0
            except Exception as e:
                err_streak += 1
                if err_streak >= 40:
                    logger.warning("TG_VC_SEND_FRAME_ERR chat=%s err=%s", self.chat_id, e)
                    break

    async def close(self) -> None:
        self.closed = True
        for t in self.tasks:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self.tasks.clear()
        try:
            await self.google_ws.close()
        except Exception:
            pass


async def join_group_voice_chat(
    chat_id: int | str,
    bot: Any = None,
    model: str | None = None,
    voice: str | None = None,
    title: str = "",
) -> dict:
    """ورود اکانت دستیار هوشیار به ویس‌چت گروه تلگرام و شروع مکالمه صوتی زنده با اعضای گروه."""
    _ensure_pyrogram_compat()
    from ai_solver import (
        DEFAULT_LIVE_MODEL,
        PREBUILT_TTS_VOICES,
        build_live_setup_message,
        connect_gemini_live_with_failover,
        get_ai_config,
    )
    from pytgcalls.types import ExternalMedia, GroupCallConfig, MediaStream, RecordStream
    from pytgcalls.types.raw import AudioParameters

    pyro_cli, call_py, assistant_me = await _ensure_assistant_started()

    resolved_cid, resolved_title = await _ensure_assistant_in_group(
        pyro_cli=pyro_cli,
        chat_target=chat_id,
        bot=bot,
        assistant_me=assistant_me,
    )
    final_title = title or resolved_title or str(resolved_cid)

    if resolved_cid in _active_sessions:
        await leave_group_voice_chat(resolved_cid)

    cfg = await get_ai_config()
    effective_model = (model or cfg.get("live_model") or DEFAULT_LIVE_MODEL).strip()
    effective_voice = (voice or cfg.get("live_voice") or cfg.get("tts_voice") or "Sulafat").strip()
    if effective_voice not in PREBUILT_TTS_VOICES:
        effective_voice = "Sulafat"

    group_prompt = (
        (cfg.get("system_prompt") or "")
        + "\n\n[محیط فعلی: شما اکنون داخل «ویس‌چت گروهی تلگرام» (Group Voice Chat) هستید و "
        "دانشجویان گروه به‌صورت زنده با شما صحبت می‌کنند. پاسخ‌های خود را صمیمی، کوتاه، "
        "روان و مناسب جمع دانشجویی بیان کن.]"
    )
    setup_msg = build_live_setup_message(
        model=effective_model,
        system_prompt=group_prompt,
        voice=effective_voice,
        thinking_level=cfg.get("live_thinking_level") or "low",
        target_language=cfg.get("live_target_language") or "fa",
        include_tools=("translate" not in effective_model.lower()),
    )

    keys = (cfg.get("vault_multi") or {}).get("gemini") or cfg.get("live_api_key_list") or []
    google_ws, _init_evs, _active_key = await connect_gemini_live_with_failover(
        effective_model, setup_msg, keys
    )
    connected_model = getattr(google_ws, "live_model", None) or effective_model

    try:
        # ۱) باز کردن مسیر خروجی صدا با نرخ بومی Opus WebRTC (48kHz mono PCM16 — هر فریم 10ms = 960 بایت)
        await call_py.play(
            resolved_cid,
            MediaStream(
                ExternalMedia.AUDIO,
                AudioParameters(bitrate=VC_OUT_SAMPLE_RATE, channels=VC_OUT_CHANNELS),
                video_flags=MediaStream.Flags.IGNORE,
            ),
            config=GroupCallConfig(auto_start=True),
        )
        # ۲) باز کردن مسیر دریافت صدای اعضای گروه (16kHz mono PCM16)
        await call_py.record(
            resolved_cid,
            RecordStream(
                audio=True,
                audio_parameters=AudioParameters(bitrate=16000, channels=1),
            ),
            config=GroupCallConfig(auto_start=True),
        )
    except Exception as call_err:
        try:
            await google_ws.close()
        except Exception:
            pass
        raise RuntimeError(
            f"ورود دستیار به ویس‌چت گروه ناموفق بود: {_friendly_tg_error(call_err)}"
        ) from call_err

    sess = _GroupLiveSession(
        chat_id=resolved_cid,
        title=final_title,
        model=connected_model,
        voice=effective_voice,
        google_ws=google_ws,
        call_py=call_py,
    )
    _active_sessions[resolved_cid] = sess
    sess.start_loops()
    await _sync_active_calls_to_db()

    # ارسال پیام خوش‌آمدگویی اولیه به Gemini تا در ویس‌چت گروه سلام کند
    if "translate" not in connected_model.lower():
        try:
            await google_ws.send(json.dumps({
                "clientContent": {
                    "turns": [{
                        "role": "user",
                        "parts": [{
                            "text": "الان وارد ویس‌چت گروه شدی؛ یک سلام کوتاه و گرم به بچه‌های گروه بگو و اعلام آمادگی کن."
                        }],
                    }],
                    "turnComplete": True,
                }
            }))
        except Exception:
            pass

    return {
        "ok": True,
        "chat_id": resolved_cid,
        "title": sess.title,
        "model": connected_model,
        "voice": effective_voice,
        "assistant": assistant_me,
    }


async def leave_group_voice_chat(chat_id: int | str) -> dict:
    """خروج اکانت دستیار از ویس‌چت گروه و بستن نشست Gemini Live."""
    raw_cid = _normalize_digits(chat_id)
    cid = int(raw_cid)
    sess = _active_sessions.pop(cid, None)
    if sess is not None:
        await sess.close()
    if _pytgcalls is not None:
        try:
            await _pytgcalls.leave_call(cid)
        except Exception:
            pass
    await _sync_active_calls_to_db()
    return {"ok": True, "chat_id": cid}


async def get_assistant_status() -> dict:
    """وضعیت کامل دستیار ویس‌چت گروهی برای پنل مدیریت وب و ربات."""
    creds = await get_vc_credentials()
    configured = bool(creds["api_id"] and creds["api_hash"] and creds["session_string"])
    active_list = []
    now = time.monotonic()
    for cid, s in list(_active_sessions.items()):
        active_list.append({
            "chat_id": cid,
            "title": s.title,
            "model": s.model,
            "voice": s.voice,
            "elapsed_sec": max(0, int(now - s.started_at)),
        })

    # اگر تماس‌ها در پروسه‌ی دیگر (مثلاً bot.py) فعال باشند، از دیتابیس هم بخوانیم
    if not active_list:
        try:
            raw_calls = await db.get_setting(SET_VC_ACTIVE_CALLS, "")
            if raw_calls:
                now_ts = int(time.time())
                for item in json.loads(raw_calls):
                    active_list.append({
                        "chat_id": item["chat_id"],
                        "title": item.get("title") or str(item["chat_id"]),
                        "model": item.get("model") or "",
                        "voice": item.get("voice") or "",
                        "elapsed_sec": max(0, now_ts - int(item.get("started_ts") or now_ts)),
                    })
        except Exception:
            pass

    assistant_info = _assistant_me
    if not assistant_info and configured:
        try:
            raw_me = await db.get_setting(SET_VC_ASSISTANT_ME, "")
            if raw_me:
                assistant_info = json.loads(raw_me)
        except Exception:
            pass

    return {
        "configured": configured,
        "api_id": creds["api_id"] or "",
        "has_api_hash": bool(creds["api_hash"]),
        "has_session": bool(creds["session_string"]),
        "auto_join": creds["auto_join"],
        "running": (_pyro_client is not None and _pytgcalls is not None) or bool(active_list),
        "assistant": assistant_info,
        "active_calls": active_list,
    }
