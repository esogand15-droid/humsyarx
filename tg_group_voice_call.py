"""📞 م9.2 — پل تماس صوتی زنده‌ی هوشیار داخل ویس‌چت گروه‌های تلگرام (Group Voice Chat)

معماری:
  • تلگرام به ربات‌های عادی (Bot API) اجازه‌ی ورود به ویس‌چت گروهی (phone.JoinGroupCall) را نمی‌دهد.
  • این ماژول با استفاده از یک اکانت دستیار تلگرام (Userbot / MTProto با Pyrogram + PyTgCalls 3.0)
    وارد ویس‌چت گروه می‌شود و جریان صوتی دوطرفه را مستقیماً به Google Gemini Live API
    (BidiGenerateContent) متصل می‌کند:
      - صدای اعضای حاضر در ویس‌چت گروه (16kHz, 16-bit, mono PCM) ← RecordStream ← ارسال به Gemini Live
      - صدای پاسخ زنده‌ی هوشیار (24kHz, 16-bit, mono PCM) ← دریافت از Gemini Live ← send_frame به ویس‌چت گروه
      - پشتیبانی کامل از پریدن وسط حرف (Barge-in / interrupted) و ابزارهای هوشیار.
  • شامل ویزارد ورود تعاملی (ارسال کد تایید تلگرام و ثبت خودکار session_string رمزنگاری‌شده)
    در پنل ادمین وب تا نیازی به ساخت دستی session_string در بیرون از سیستم نباشد.
"""
from __future__ import annotations

import array
import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

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
    "created_at": 0.0,
}

# نشست‌های فعال ویس‌چت گروهی: chat_id (int) -> _GroupLiveSession
_active_sessions: dict[int, "_GroupLiveSession"] = {}


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
        api_id = int(str(raw_id).strip())
    except (TypeError, ValueError):
        api_id = 0

    return {
        "api_id": api_id,
        "api_hash": (api_hash or "").strip(),
        "session_string": (session_string or "").strip(),
        "auto_join": auto_join,
    }


async def save_vc_credentials(
    api_id: int | str | None = None,
    api_hash: str | None = None,
    session_string: str | None = None,
    auto_join: bool | None = None,
) -> dict:
    """ذخیره امن مشخصات اکانت دستیار ویس‌چت گروهی در دیتابیس (با رمزنگاری Fernet)."""
    if api_id is not None and str(api_id).strip():
        await db.set_setting(SET_VC_API_ID, str(int(str(api_id).strip())))
    if api_hash is not None and api_hash.strip():
        await db.set_setting(SET_VC_API_HASH, encrypt_secret(api_hash.strip()))
    if session_string is not None:
        s_clean = session_string.strip()
        await db.set_setting(SET_VC_SESSION, encrypt_secret(s_clean) if s_clean else "")
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


async def start_assistant_login(api_id: int, api_hash: str, phone: str) -> dict:
    """گام ۱ ویزارد پنل وب: ارسال کد تایید تلگرام (OTP) به شماره موبایل اکانت دستیار."""
    from pyrogram import Client

    if not api_id or not api_hash or not phone:
        raise ValueError("لطفاً API_ID، API_HASH و شماره موبایل (با پیش‌شماره مثل +98...) را کامل وارد کنید.")

    old_cli = _login_state.get("client")
    if old_cli is not None:
        try:
            await old_cli.disconnect()
        except Exception:
            pass

    cli = Client(
        name="humsyar_vc_login",
        api_id=int(api_id),
        api_hash=api_hash.strip(),
        in_memory=True,
        no_updates=True,
    )
    await cli.connect()
    try:
        sent = await cli.send_code(phone.strip())
    except Exception as e:
        try:
            await cli.disconnect()
        except Exception:
            pass
        raise RuntimeError(f"ارسال کد از سمت تلگرام ناموفق بود: {e}") from e

    _login_state.update({
        "client": cli,
        "api_id": int(api_id),
        "api_hash": api_hash.strip(),
        "phone": phone.strip(),
        "phone_code_hash": sent.phone_code_hash,
        "created_at": time.monotonic(),
    })
    await db.set_setting(SET_VC_API_ID, str(int(api_id)))
    await db.set_setting(SET_VC_API_HASH, encrypt_secret(api_hash.strip()))
    return {
        "ok": True,
        "phone": phone.strip(),
        "message": "کد تایید ۵ رقمی به تلگرام این شماره ارسال شد.",
    }


async def verify_assistant_login(code: str, password: str = "") -> dict:
    """گام ۲ ویزارد پنل وب: تایید کد ۵ رقمی (و رمز تایید دو مرحله‌ای در صورت وجود) و ذخیره session_string."""
    from pyrogram.errors import SessionPasswordNeeded

    cli = _login_state.get("client")
    if cli is None or not _login_state.get("phone_code_hash"):
        raise RuntimeError("نشست ورود منقضی شده است؛ لطفاً دوباره دکمه «ارسال کد تایید» را بزنید.")

    clean_code = (code or "").strip().replace("-", "").replace(" ", "")
    if not clean_code:
        raise ValueError("کد تایید تلگرام را وارد کنید.")

    try:
        try:
            await cli.sign_in(
                phone_number=_login_state["phone"],
                phone_code_hash=_login_state["phone_code_hash"],
                phone_code=clean_code,
            )
        except SessionPasswordNeeded:
            if not password:
                return {
                    "ok": False,
                    "needs_2fa": True,
                    "message": "این اکانت تایید دو مرحله‌ای (Two-Step Verification) دارد؛ رمز دوم را هم وارد کنید.",
                }
            await cli.check_password(password)

        session_str = await cli.export_session_string()
        me = await cli.get_me()
        info = {
            "id": me.id,
            "first_name": getattr(me, "first_name", "") or "",
            "username": getattr(me, "username", "") or "",
            "phone": getattr(me, "phone_number", "") or _login_state["phone"],
        }
    finally:
        try:
            await cli.disconnect()
        except Exception:
            pass
        _login_state["client"] = None

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
        return valid[0]
    min_len = min(len(f) for f in valid)
    min_len -= (min_len % 2)
    if min_len <= 0:
        return b""
    acc = array.array("h", valid[0][:min_len])
    for extra in valid[1:]:
        arr = array.array("h", extra[:min_len])
        for i in range(len(acc)):
            s = int(acc[i]) + int(arr[i])
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            acc[i] = s
    return acc.tobytes()


async def _ensure_assistant_started() -> tuple[Any, Any, dict]:
    """راه‌اندازی Singleton کلاینت Pyrogram و PyTgCalls برای اکانت دستیار."""
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

        from pyrogram import Client
        from pytgcalls import PyTgCalls, filters
        from pytgcalls.types import Device, Direction, StreamFrames

        cli = Client(
            name="humsyar_vc_assistant",
            api_id=int(creds["api_id"]),
            api_hash=creds["api_hash"],
            session_string=creds["session_string"],
            in_memory=True,
        )
        call_py = PyTgCalls(cli)

        @call_py.on_update(filters.stream_frame(Direction.INCOMING, Device.MICROPHONE))
        async def _on_incoming_voice(_client: Any, update: StreamFrames):
            sess = _active_sessions.get(int(update.chat_id))
            if sess is None or not update.frames:
                return
            mixed = _mix_pcm16_frames([f.frame for f in update.frames if getattr(f, "frame", None)])
            if mixed:
                sess.on_incoming_pcm16_16k(mixed)

        await call_py.start()
        me = await cli.get_me()
        _pyro_client = cli
        _pytgcalls = call_py
        _assistant_me = {
            "id": me.id,
            "first_name": getattr(me, "first_name", "") or "دستیار هوشیار",
            "username": getattr(me, "username", "") or "",
        }
        logger.info("TG_VC_ASSISTANT_STARTED id=%s username=@%s", me.id, _assistant_me["username"])
        return _pyro_client, _pytgcalls, _assistant_me


class _GroupLiveSession:
    """نشست زنده‌ی اتصال یک ویس‌چت گروه تلگرام به Google Gemini Live API."""

    def __init__(self, chat_id: int, title: str, model: str, voice: str, google_ws: Any, call_py: Any):
        self.chat_id = int(chat_id)
        self.title = title or str(chat_id)
        self.model = model
        self.voice = voice
        self.google_ws = google_ws
        self.call_py = call_py
        self.started_at = time.monotonic()
        self.in_buf = bytearray()
        self.out_buf = bytearray()
        self.closed = False
        self.tasks: list[asyncio.Task] = []

    def on_incoming_pcm16_16k(self, pcm_bytes: bytes) -> None:
        if self.closed:
            return
        self.in_buf.extend(pcm_bytes)

    def start_loops(self) -> None:
        self.tasks = [
            asyncio.create_task(self._flush_incoming_to_gemini_loop()),
            asyncio.create_task(self._gemini_to_outgoing_loop()),
            asyncio.create_task(self._outgoing_pacer_loop()),
        ]

    async def _flush_incoming_to_gemini_loop(self) -> None:
        """ارسال چانک‌های ~100ms (۳۲۰۰ بایت در 16kHz 16-bit mono) از ویس‌چت گروه به Gemini Live."""
        while not self.closed:
            await asyncio.sleep(0.08)
            if len(self.in_buf) < 3200:
                continue
            chunk = bytes(self.in_buf[:6400])
            del self.in_buf[:len(chunk)]
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
                            self.out_buf.extend(pcm24k)
                        except Exception:
                            pass
                    elif etype == "interrupted":
                        # وقتی یکی از اعضای گروه وسط صحبت هوشیار حرف بزند، صف پخش بلافاصله خالی می‌شود
                        self.out_buf.clear()
                    elif etype == "tool_call":
                        tool_resp = await execute_live_tool_calls(ev.get("calls") or [], 0)
                        await self.google_ws.send(json.dumps(tool_resp))
        except Exception as e:
            if not self.closed:
                logger.warning("TG_VC_GEMINI_RECV_CLOSED chat=%s err=%s", self.chat_id, e)

    async def _outgoing_pacer_loop(self) -> None:
        """تزریق فریم‌های ۲۰ میلی‌ثانیه‌ای (۹۶۰ بایت در 24kHz 16-bit mono) به میکروفون ویس‌چت تلگرام."""
        from pytgcalls.types import Device

        frame_bytes = 960  # 24000 Hz * 2 bytes * 0.020 sec = 960 bytes
        next_tick = time.monotonic()
        while not self.closed:
            now = time.monotonic()
            if now < next_tick:
                await asyncio.sleep(next_tick - now)
            next_tick = max(time.monotonic(), next_tick + 0.020)

            if len(self.out_buf) >= frame_bytes:
                chunk = bytes(self.out_buf[:frame_bytes])
                del self.out_buf[:frame_bytes]
                try:
                    await self.call_py.send_frame(self.chat_id, Device.MICROPHONE, chunk)
                except Exception as e:
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
    chat_id: int,
    bot: Any = None,
    model: str | None = None,
    voice: str | None = None,
    title: str = "",
) -> dict:
    """ورود اکانت دستیار هوشیار به ویس‌چت گروه تلگرام و شروع مکالمه صوتی زنده با اعضای گروه."""
    from ai_solver import (
        DEFAULT_LIVE_MODEL,
        PREBUILT_TTS_VOICES,
        build_live_setup_message,
        connect_gemini_live_with_failover,
        get_ai_config,
    )
    from pytgcalls.types import AudioQuality, ExternalMedia, GroupCallConfig, MediaStream, RecordStream
    from pytgcalls.types.raw import AudioParameters

    chat_id = int(chat_id)
    if chat_id in _active_sessions:
        await leave_group_voice_chat(chat_id)

    pyro_cli, call_py, assistant_me = await _ensure_assistant_started()

    # اطمینان از عضویت اکانت دستیار در گروه تلگرام
    try:
        await pyro_cli.get_chat(chat_id)
    except Exception:
        if bot is not None:
            try:
                invite_link = await bot.export_chat_invite_link(chat_id)
                await pyro_cli.join_chat(invite_link)
            except Exception as join_err:
                logger.warning("TG_VC_JOIN_CHAT_WARN chat=%s err=%s", chat_id, join_err)

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
        # ۱) باز کردن مسیر خروجی صدا (24kHz mono PCM16) در ویس‌چت گروه
        await call_py.play(
            chat_id,
            MediaStream(
                ExternalMedia.AUDIO,
                AudioParameters(bitrate=24000, channels=1),
                video_flags=MediaStream.Flags.IGNORE,
            ),
            config=GroupCallConfig(auto_start=True),
        )
        # ۲) باز کردن مسیر دریافت صدای اعضای گروه (16kHz mono PCM16)
        await call_py.record(
            chat_id,
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
            f"ورود دستیار به ویس‌چت گروه ناموفق بود ({call_err}). "
            "مطمئن شوید ویس‌چت (Video Chat) در گروه باز است و اکانت دستیار در گروه عضو است."
        ) from call_err

    sess = _GroupLiveSession(
        chat_id=chat_id,
        title=title or str(chat_id),
        model=connected_model,
        voice=effective_voice,
        google_ws=google_ws,
        call_py=call_py,
    )
    _active_sessions[chat_id] = sess
    sess.start_loops()

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
        "chat_id": chat_id,
        "title": sess.title,
        "model": connected_model,
        "voice": effective_voice,
        "assistant": assistant_me,
    }


async def leave_group_voice_chat(chat_id: int) -> dict:
    """خروج اکانت دستیار از ویس‌چت گروه و بستن نشست Gemini Live."""
    chat_id = int(chat_id)
    sess = _active_sessions.pop(chat_id, None)
    if sess is not None:
        await sess.close()
    if _pytgcalls is not None:
        try:
            await _pytgcalls.leave_call(chat_id)
        except Exception:
            pass
    return {"ok": True, "chat_id": chat_id}


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
    return {
        "configured": configured,
        "api_id": creds["api_id"] or "",
        "has_api_hash": bool(creds["api_hash"]),
        "has_session": bool(creds["session_string"]),
        "auto_join": creds["auto_join"],
        "running": _pyro_client is not None and _pytgcalls is not None,
        "assistant": _assistant_me,
        "active_calls": active_list,
    }
