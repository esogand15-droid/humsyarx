"""💍 Ring Street — ارسال پیام از سمت ربات (بدون وابستگی به context)

هندلرها `context.bot` دارند، اما jobها و روتر API ندارند. PTB 21
`Application.get_current()` را دقیقاً برای همین گذاشته است: اگر فراخوانی
از داخل تسکِ خودِ Application باشد، به bot می‌رسیم. هر جا نرسیدیم،
ارسال «بی‌صدا رد” می‌شود و لاگ می‌شود — چون هیچ پیام اطلاع‌رسانی نباید
فلو اصلی (match/end/report) را بشکند.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _bot():
    try:
        from telegram.ext import Application
        app = Application.get_current()
        return getattr(app, "bot", None) if app else None
    except Exception:
        return None


async def send_text(uid: int, text: str, **kw) -> bool:
    bot = kw.pop("bot", None) or _bot()
    if bot is None or not text:
        if text:
            logger.debug("ring notify skipped (no bot) uid=%s", uid)
        return False
    from telegram.error import RetryAfter
    for attempt in range(3):
        try:
            await bot.send_message(int(uid), text, **kw)
            return True
        except RetryAfter as e:
            await asyncio.sleep(min(getattr(e, "retry_after", 3), 20) + 0.4)
        except Exception as e:
            # §۹ (V5) — «طرف مقابل اطلاعیه نگرفت» نباید در لاگ گم شود: قبلاً
            # debug بود و در سطح INFO پروداکشن هیچ‌جا دیده نمی‌شد، برای همین
            # نشانهٔ «بستن چت از یک طرف بدون اطلاعیهٔ طرف مقابل» قابل ردیابی
            # نبود. حالا یک warning با برچسبِ grep‌پذیر می‌ماند.
            logger.warning("RING_NOTIFY_FAIL uid=%s err=%s", uid, str(e)[:160])
            return False
    return False


async def send_to_peer_of(uid: int, session: dict, text: str, bot=None) -> bool:
    """ارسال به طرف مقابل یک جلسه (اگر جلسه دیگر فعال نبود، کاری نمی‌کنیم)."""
    if not session:
        return False
    slots = session.get("slots") or []
    peer = next((int(s) for s in slots if int(s) != int(uid)), None)
    if peer is None:
        return False
    return await send_text(peer, text, bot=bot)
