"""💍 Ring Street — گفت‌وگوی ناشناس (V1)

ماژولی **افزودنی و ایزوله**: هیچ importی از این بسته در مسیرهای اصلی ربات
نیست مگر `bot.py` (ثبت هندلر/job)، `utils.py` (دکمه‌ی منوی اصلی) و
`api/main.py` (روت admin). همه‌ی رفتارها پشت یک flag در دیتابیس‌اند
(`ring_enabled`)؛ اگر flag خاموش باشد، این بسته عملاً نامرئی است.

ساختار:
  settings    §۲۹/§۳۸  flag + knobs (منبع: bot_settings)
  models      §۲/§۱۱    سن/جنسیت/حالت + ماشین حالت + تشخیص نشت اطلاعات
  matcher     §۸/§۱۰    فیلتر سخت + امتیاز نرم (fairness در DB انجام می‌شود)
  service     §۷..§۲۱   صف، match اتمیک، پایان جلسه، reveal، اکشن‌های ادمین
  relay       §۱۳..§۱۵  رله از طریق بات با copyMessage/فرستادن مجدد
  moderation  §۱۹..§۲۵  بلاک/گزارش/بن + آستانه‌ها
  state       §۴۲/§۴۳   کش رجیستری چت + بازیابی از DB
  handlers    §۴۲        هندلرهای تلگرام
  jobs        §۲۲/§۴۵   timeoutها + reconcile + آمار روزانه
  analytics   §۳۶        funnel/moderation برای پنل
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["register_handlers", "post_init", "pre_dispose"]


def register_handlers(app) -> None:
    """ثبت هندلرهای تلگرام (callback در bot.py انجام می‌شود چون الگوی
    ربات یک لیست `cbs` است و اولویت = ترتیب ثبت)."""
    from ring.handlers import register
    register(app)


async def post_init(bot=None) -> dict:
    """at boot: flag را می‌خواند و sessionهای فعال را از DB برمی‌گرداند.
    هیچ‌وقت raise نمی‌کند — رینگ نباید بوت ربات را بشکند."""
    out = {"flag": False, "loaded": 0, "dropped": 0}
    try:
        from ring import jobs, settings as S, state
        out["flag"] = await S.get_flag()
        await S.get_cfg()
        st = await S.disable_mode()
        if not out["flag"]:
            if st == "hard":
                from database import db
                await jobs._hard_disable(db)
            return out
        from ring.handlers import flow_mark
        rec = await state.load_from_db(mark=flow_mark)
        out["loaded"] = int(rec.get("loaded") or 0)
        out["dropped"] = int(rec.get("dropped") or 0)
        rep = await db_repair()
        out.update(rep)
        return out
    except Exception as e:
        logger.warning("💍 post_init رینگ کامل نشد: %s", e)
        return out


async def db_repair() -> dict:
    """reconcile یک‌باره در بوت (session/queue یتیم)."""
    try:
        from database import db
        r = await db.ring_reconcile()
        return {"reconciled": r}
    except Exception as e:
        logger.debug("ring reconcile skipped: %s", e)
        return {}


async def pre_dispose() -> None:
    """رجیستری RAM را پاک می‌کند تا در تست/ری‌استارت چیزی جا نماند."""
    try:
        from ring import state
        state.clear()
    except Exception:
        pass
