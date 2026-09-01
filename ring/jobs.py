"""💍 Ring Street — jobهای دوره‌ای (§۲۲، §۴۳، §۴۵، §۶۴)

دو job، هر دو idempotent و هر دو «بی‌خطر اگر رینگ خاموش باشد»:

  • housekeeping (هر ۳۰ ثانیه): timeout صف، هشدار/بستن sessionهای بی‌فعال،
    رفع claimهای یتیم، هم‌سان‌سازی رجیستری RAM با DB، تازه‌سازی flag.
  • daily (روزانه): چرخش آمار روز، purge شواهد، لاگ خلاصه.

ایمنی ری‌استارت: هیچ state‌ای فقط در RAM نیست؛ همه از Mongo خوانده
می‌شود (§۴۳) و اگر DB موقتاً نایاب باشد، job فقط warning می‌دهد.
"""
from __future__ import annotations

import logging

from ring import models as M
from ring import notify
from ring import service
from ring import settings as S
from ring import state
from ring import texts
from time_utils import now_utc

logger = logging.getLogger(__name__)

_WARNED: set[str] = set()        # sidهایی که هشدار «نزدیک به پایان» گرفته‌اند (best-effort)


SWEEP_LIMIT = 12


async def _sweep(db, cfg: dict) -> int:
    """تلاش مجدد برای match کردن منتظرهای صف — idempotent (§۶۲)."""
    from ring import handlers as H
    rows = await db.ring_cols.queue.find(
        {"status": "waiting"}, {"user_id": 1, "mode": 1}
    ).sort("queued_at", 1).to_list(SWEEP_LIMIT)
    if len(rows) < 2:
        return 0
    made = 0
    for d in rows:
        uid = int(d["user_id"])
        cur = await db.ring_queue_get(uid)
        if not cur or cur.get("status") != "waiting":
            continue                    # همین لحظه توسط کسی دیگری برداشته شد
        r = await service.try_match(uid, announce=True)
        if r.get("kind") == "matched":
            made += 1
    if made:
        logger.info("RING_QUEUE_SWEPT pairs=%s", made)
    return made


async def ring_housekeeping_job(context) -> None:
    """timeoutها + reconcile. هزینه‌ی هر دور: ۴ query محدود (§۵۳)."""
    from database import db
    try:
        cfg = await S.get_cfg()
        flag = await S.get_flag()
        if not flag:
            if state.count():
                # فیچر همین حالا خاموش شده ⇒ sessions را ببند (hard) یا بگذار تمام شود (soft)
                if await S.disable_mode() == "hard":
                    await _hard_disable(db)
            return
        closed = warned = repaired = swept = 0
        # ۱) صف‌های کهنه (queue_timeout) — §۲۲
        for uid in await db.ring_queue_stale(int(cfg["queue_timeout_s"])):
            q = await db.ring_queue_get(uid)
            if not q:
                continue
            if q.get("status") == "in_chat":
                continue
            await db.ring_queue_leave(uid)
            closed += 1
            await notify.send_text(uid, texts.queue_empty(q.get("mode") or "fun", cfg))
        # ۲) claimهای یتیم (crash وسط match) — §۶۳
        repaired = await db.ring_queue_repair_claims(max(60, int(cfg["queue_timeout_s"]) // 4))
        # ۲.۵) جاروی صف (§۴۰): اگر زیر همزمانی، دو نفرِ آخر همدیگر را
        # لحظه‌اً claimed ببینند و واگذار کنند، کسی نیست که trigger بعدی را
        # بزند ⇒ این job جفت‌های جامانده را وصل می‌کند. حداکثر SWEEP_LIMIT
        # کاربر در هر دور، و فقط وقتی ≥۲ نفر منتظر باشند (هزینه محدود §۵۳).
        swept = await _sweep(db, cfg)
        # ۳) sessionهای بی‌فعال
        idle_s = int(cfg["session_idle_s"])
        grace = int(cfg["session_grace_s"])
        for sess in await db.ring_session_idle(max(30, idle_s - grace), limit=200):
            sid = sess["session_id"]
            mins = max(1, (idle_s - min(idle_s, idle_s - grace)) // 60 or grace // 60 or 1)
            age = _age_s(sess.get("last_activity_at"))
            if age >= idle_s:
                await service.end_session(None, sid, "idle_timeout")
                await _notify_pair(sess, "⌛ به‌دلیل بی‌فعالیت، گفت‌وگو بسته شد.")
                _WARNED.discard(sid)
                closed += 1
            elif sid not in _WARNED and grace > 0:
                _WARNED.add(sid)
                for u in (sess.get("slots") or []):
                    await notify.send_text(int(u), texts.ending_soon(max(1, int((idle_s - age) / 60))))
                warned += 1
        # ۴) هم‌سان‌سازی RAM با DB
        rows = await db.ring_cols.sessions.find({"status": "active"},
                                                {"session_id": 1}).to_list(1000)
        valid = {r["session_id"] for r in rows}
        stale = state.drop_staleuids(valid)
        if stale:
            logger.info("ring: %d entry بیات از RAM حذف شد", stale)
        if closed or warned or repaired or swept:
            logger.info("💍 رینگ housekeeping: بسته=%s هشدار=%s ترمیم‌claim=%s جارو=%s",
                        closed, warned, repaired, swept)
    except Exception as e:
        logger.warning("ring housekeeping ناتمام: %s", e)


async def _hard_disable(db) -> None:
    from ring import state
    for row in state.snapshot():
        await service.end_session(None, row["session_id"], "disabled_hard")
    await db.ring_cols.queue.update_many({"status": {"$in": ["waiting", "claimed", "claiming"]}},
                                        {"$set": {"status": "left", "left_at": now_utc().isoformat()}})
    logger.info("💍 رینگ خاموش شد (hard): sessions و صف بسته شدند")


async def _notify_pair(sess: dict, text: str) -> None:
    for u in (sess.get("slots") or []):
        await notify.send_text(int(u), text)


def _age_s(iso) -> int:
    try:
        t = now_utc().fromisoformat(str(iso))
        if t.tzinfo is None:
            t = t.replace(tzinfo=now_utc().tzinfo)
        return max(0, int((now_utc() - t).total_seconds()))
    except Exception:
        return 10 ** 9      # ناشناخته ⇒ قدیمی فرض کن (fail-closed به سمت بستن)


async def ring_daily_job(context) -> None:
    """چرخش آمار + پاک‌سازی شواهد (§۳۵) — TTL Mongo هم کار را می‌کند؛
    این تابع فقط برای روزهای بدون تردد و لاگ خلاصه است."""
    from database import db
    try:
        purged = await db.ring_evidence_purge()
        ov = await db.ring_overview()
        logger.info("💍 رینگ daily: in_chat=%s waiting=%s گزارش_باز=%s شواهد_purge=%s",
                    ov.get("in_chat"), ov.get("waiting"),
                    ov.get("reports_pending"), purged)
        if purged:
            await db.ring_audit("system", "PURGE_EVIDENCE", "", f"n={purged}", {})
    except Exception as e:
        logger.warning("ring daily job failed: %s", e)
