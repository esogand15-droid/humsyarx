"""💍 Ring Street — تحلیل (§۳۶): funnel، کیفیت تطبیق، moderation

فقط aggregateهای محدود با index و `allowDiskUse=False` — هیچ‌وقت روی کل
کاربران ربات اسکن نمی‌کنیم (§۵۳). آمار روزانه از `ring_stats_daily`
(شمارنده‌های atomic) می‌آید که تقریباً رایگان است؛ aggregateهای سنگین
فقط از پنل/درخواست خاص اجرا می‌شوند.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from time_utils import now_utc

logger = logging.getLogger(__name__)


def _since(days: int):
    return (now_utc() - timedelta(days=max(1, min(int(days or 7), 180)))).replace(
        microsecond=0).isoformat(timespec="seconds")


# نام شمارنده‌ها در `ring_stats_daily.c.*` — حتماً با bumpهای ماژول‌ها یکی باشد
COUNTERS = {
    "profiles": "profiles", "consents": "consents", "joins": "queue_join",
    "matches": "match", "ends": "session_end", "messages": "messages",
    "reports": "report", "blocks": "blocks", "rated": "rating",
    "wait_s": "wait_s", "session_s": "session_seconds", "bans": "bans",
}


async def funnel(days: int = 7) -> dict:
    """profile → consent → queue join → match → ≥1 message → end."""
    from database import db
    rows = await db.ring_daily(days)
    acc = {k: 0 for k in COUNTERS}
    for r in rows:
        c = r.get("c") or {}
        for out_key, db_key in COUNTERS.items():
            acc[out_key] += int(c.get(db_key) or 0)
    n = max(1, acc["joins"])
    return {
        "days": days,
        **acc,
        "match_rate": round(acc["matches"] / n, 3),
        "avg_wait_s": round(acc["wait_s"] / n, 1),
        "avg_session_s": round(acc["session_s"] / max(1, acc["ends"]), 1),
        "msgs_per_match": round(acc["messages"] / max(1, acc["matches"]), 1),
        "report_per_match": round(acc["reports"] / max(1, acc["matches"]), 3),
    }


async def mode_split(days: int = 7) -> dict:
    """تقسیم fun/serious از روی sessionها (نه شمارنده‌ها) — aggregate محدود."""
    from database import db
    cut = _since(days)
    out = {}
    pipeline = [
        {"$match": {"created_at": {"$gte": cut}}},
        {"$group": {"_id": "$mode",
                    "n": {"$sum": 1},
                    "msgs": {"$sum": "$messages_count"},
                    "dur_ms": {"$sum": {
                        "$cond": [
                            {"$and": [{"$ne": ["$ended_at", None]},
                                     {"$gt": ["$messages_count", 0]}]},
                            {"$subtract": [
                                {"$dateFromString": {"dateString": "$ended_at"}},
                                {"$dateFromString": {"dateString": "$created_at"}}]},
                            0]}}}},
        {"$limit": 10},
    ]
    try:
        async for d in db.ring_cols.sessions.aggregate(pipeline, allowDiskUse=False):
            n = max(1, int(d.get("n") or 0))
            out[d["_id"] or "unknown"] = {
                "sessions": int(d.get("n") or 0),
                "messages": int(d.get("msgs") or 0),
                "avg_duration_s": round((d.get("dur_ms") or 0) / 1000 / n, 1),
            }
    except Exception as e:
        logger.debug("ring mode_split failed: %s", e)
    return out


async def moderation_stats(days: int = 30) -> dict:
    """چند گزارش تا بن، چند تای رد شده (برای تنظیم آستانه‌ها)."""
    from database import db
    cut = _since(days)
    out = {"by_reason": {}, "by_status": {}, "dup_share": 0.0, "total": 0}
    pipeline = [{"$match": {"created_at": {"$gte": cut}}},
                {"$group": {"_id": "$reason", "n": {"$sum": 1},
                            "dup": {"$sum": {"$cond": [{"$gt": [{"$size": {"$ifNull": ["$duplicate_of", []]}}, 0]}, 1, 0]}},
                            "sev": {"$sum": "$severity"}}}]
    total = dup = 0
    try:
        async for d in db.ring_cols.reports.aggregate(pipeline, allowDiskUse=False):
            out["by_reason"][d["_id"] or "other"] = {"n": d["n"], "severity_sum": d.get("sev", 0)}
            total += d["n"]
            dup += int(d.get("dup") or 0)
        async for d in db.ring_cols.reports.aggregate(
                [{"$match": {"created_at": {"$gte": cut}}},
                 {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
            out["by_status"][d["_id"] or "pending"] = d["n"]
        bans = await db.ring_cols.bans.count_documents({"created_at": {"$gte": cut}})
        out["bans"] = bans
        out["total"] = total
        out["dup_share"] = round(dup / total, 3) if total else 0.0
        out["reports_per_ban"] = round(total / bans, 1) if bans else None
    except Exception as e:
        logger.debug("ring moderation_stats failed: %s", e)
    return out


async def top_topics(days: int = 30, limit: int = 8) -> list[dict]:
    from database import db
    cut = _since(days)
    try:
        rows = []
        async for d in db.ring_cols.profiles.aggregate(
                [{"$match": {"consent_terms_at": {"$gte": cut}}},
                 {"$unwind": "$topics"},
                 {"$group": {"_id": "$topics", "n": {"$sum": 1}}},
                 {"$sort": {"n": -1}}, {"$limit": max(1, min(limit, 30))}],
                allowDiskUse=False):
            rows.append({"topic": d["_id"], "users": d["n"]})
        return rows
    except Exception as e:
        logger.debug("ring top_topics failed: %s", e)
        return []


async def summary(days: int = 7) -> dict:
    """پاسخ `/api/ring/analytics` و کارت «📊» پنل."""
    from database import db
    ov = {}
    try:
        ov = await db.ring_overview()
    except Exception as e:
        logger.debug("ring overview failed: %s", e)
    return {"funnel": await funnel(days), "modes": await mode_split(days),
            "moderation": await moderation_stats(days), "topics": await top_topics(days),
            "live": ov}
