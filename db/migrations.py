# -*- coding: utf-8 -*-
"""
🗄️ W3 — Migration runner (versioned, idempotent)

Each migration is a small async function; runner tracks `db_version` in settings (`_id: 'global'`).
Current version: 3
- v1: initial (legacy)
- v2: W1 security (init_nonces TTL) — already handled via ensure_indexes
- v3: W3 exam_sessions expires_at backfill + wallet/broadcast guards

Run via `await run_migrations(db)` in lifespan / ensure_indexes.
Idempotent: re-running does nothing.
"""
import logging
from time_utils import utc_now_iso, parse_machine_datetime, now_utc

logger = logging.getLogger("database")
CURRENT_DB_VERSION = 3

async def _migrate_v3_exam_sessions(db):
    """Backfill expires_at for existing exam_sessions without it.
    - promotion/challenge: expires_at = now + CH_TTL_HOURS (from expires_ts)
    - normal exam: expires_at = deadline + 7 days, or started_at + 7 days if no deadline
    Uses bulk write in batches to avoid OOM.
    """
    from datetime import datetime, timedelta, timezone
    try:
        # Find sessions missing expires_at
        cursor = db.exam_sessions.find({"expires_at": {"$exists": False}})
        batch = []
        migrated = 0
        async for doc in cursor:
            try:
                expires_at = None
                if doc.get("promotion"):
                    ts = doc.get("expires_ts")
                    if ts:
                        expires_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    else:
                        # fallback 48h from started_at
                        try:
                            sa = parse_machine_datetime(doc.get("started_at") or doc.get("created_at") or utc_now_iso())
                            expires_at = sa + timedelta(hours=48)
                        except:
                            expires_at = now_utc() + timedelta(hours=48)
                else:
                    dl = doc.get("deadline")
                    if dl:
                        try:
                            d = parse_machine_datetime(dl)
                            expires_at = d + timedelta(days=7)
                        except:
                            expires_at = now_utc() + timedelta(days=7)
                    else:
                        try:
                            sa = parse_machine_datetime(doc.get("started_at") or doc.get("created_at") or utc_now_iso())
                            expires_at = sa + timedelta(days=7)
                        except:
                            expires_at = now_utc() + timedelta(days=7)
                if expires_at:
                    batch.append((doc["_id"], expires_at))
                if len(batch) >= 500:
                    for _id, iso in batch:
                        await db.exam_sessions.update_one({"_id": _id}, {"$set": {"expires_at": iso}})
                    migrated += len(batch)
                    batch.clear()
            except Exception as e:
                logger.warning(f"migration v3 exam_sessions doc {doc.get('_id')} failed: {e}")
        if batch:
            for _id, iso in batch:
                await db.exam_sessions.update_one({"_id": _id}, {"$set": {"expires_at": iso}})
            migrated += len(batch)
        if migrated:
            logger.info(f"migration v3: backfilled expires_at for {migrated} exam_sessions")
        return migrated
    except Exception as e:
        logger.warning(f"migration v3 failed: {e}")
        return 0

async def run_migrations(db):
    try:
        raw = await db.settings.find_one({"_id": "global"})
        cur = int((raw or {}).get("db_version", 1) or 1)
        if cur >= CURRENT_DB_VERSION:
            return {"migrated": False, "version": cur}
        logger.info(f"migrations: {cur} -> {CURRENT_DB_VERSION}")
        if cur < 3:
            await _migrate_v3_exam_sessions(db)
        await db.settings.update_one({"_id": "global"}, {"$set": {"db_version": CURRENT_DB_VERSION, "db_version_updated_at": utc_now_iso()}}, upsert=True)
        return {"migrated": True, "from": cur, "to": CURRENT_DB_VERSION}
    except Exception as e:
        logger.warning(f"run_migrations failed: {e}")
        return {"migrated": False, "error": str(e)}
