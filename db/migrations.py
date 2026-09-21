# -*- coding: utf-8 -*-
"""
🗄️ W3 — Migration runner (versioned, idempotent)

Each migration is a small async function; runner tracks `db_version` in settings (`_id: 'global'`).
Current version: 5
- v1: initial (legacy)
- v2: W1 security (init_nonces TTL) — already handled via ensure_indexes
- v3: W3 exam_sessions expires_at backfill + wallet/broadcast guards
- v4: W7 feature_policies seed (all FREE) + subscription_enforced migration
- v5: canonical UTC instants for subscription, payment, and stats clocks.
  Resumable batches. Civil dates and ambiguous user clocks are not rewritten.

Run via `await run_migrations(db)` in lifespan / ensure_indexes.
Idempotent: re-running does nothing.
"""
import logging
import re
import time
from time_utils import canonical_utc, utc_now_iso, parse_machine_datetime, now_utc

logger = logging.getLogger("database")
CURRENT_DB_VERSION = 5

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

async def _migrate_v4_feature_policies(db):
    """🌊 W7 — بذر پالیسی همه‌ی فیچرها (FREE/enabled) + مهاجرت سوییچ قدیمی.

    اگر subscription_enforced روشن بود، question_bank و resources و
    references به subscription می‌روند تا رفتار عیناً حفظ شود. idempotent.
    """
    try:
        from core.features import FEATURE_CATALOG, default_policy
    except ImportError as e:
        logger.warning(f"migration v4: catalog import failed: {e}")
        return 0
    try:
        enforced = await db.get_setting("subscription_enforced", False)
    except Exception:
        enforced = False
    n = 0
    for key in FEATURE_CATALOG:
        try:
            cur = await db.feature_policies.find_one({"_id": key})
            if cur:
                continue
            pol = default_policy(key)
            if enforced and key in ("question_bank", "resources",
                                    "references"):
                pol["access"] = "subscription"
                pol["note"] = "مهاجرت خودکار از subscription_enforced (v4)"
            pol["updated_at"] = utc_now_iso()
            await db.feature_policies.insert_one(pol)
            n += 1
        except Exception as e:
            logger.warning(f"migration v4 seed {key} failed: {e}")
    if n:
        logger.info(f"migration v4: seeded {n} feature policies "
                    f"(enforced_was={bool(enforced)})")
    return n


async def _migrate_v5_canonical_instants(db) -> bool:
    """Rewrite a short batch of mixed ISO instants. True only when the scan is finished.

    The 120s bootstrap lease must not be held for a full collection rewrite.
    Progress is stored beside db_version so the next boot continues.
    Naive machine timestamps are UTC. Civil YYYY-MM-DD is skipped.
    users.registered_at and users.last_active stay untouched.
    """
    from pymongo import UpdateOne

    targets = (
        ("subscriptions", "subscriptions", ("start_date", "end_date", "updated_at", "revoked_at")),
        ("sub_payments", "sub_payments", ("submitted_at", "reviewed_at", "refunded_at", "created_at")),
        ("stats", "stats_col", ("timestamp",)),
    )
    date_only = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    canon_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")
    batch_size = 500
    budget_s = 8

    def pack_id(value):
        from bson import ObjectId
        if isinstance(value, ObjectId):
            return {"k": "oid", "v": str(value)}
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return {"k": "int", "v": int(value)}
        if isinstance(value, str):
            return {"k": "str", "v": value}
        return {"k": "str", "v": str(value)}

    def unpack_id(packed):
        if not isinstance(packed, dict):
            return None
        kind = packed.get("k")
        if kind == "oid":
            from bson import ObjectId
            try:
                return ObjectId(packed.get("v"))
            except Exception:
                return None
        if kind == "int":
            try:
                return int(packed.get("v"))
            except (TypeError, ValueError):
                return None
        if kind == "str":
            return packed.get("v")
        return None

    def canon(value):
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw or date_only.fullmatch(raw) or canon_re.fullmatch(raw) or len(raw) > 80:
            return None
        try:
            rewritten = canonical_utc(raw)
        except Exception:
            return None
        return None if rewritten == raw else rewritten

    state = await db.settings.find_one({"_id": "time_canon_v5"}) or {}
    done = set(state.get("done") or [])
    cursors = dict(state.get("cursors") or {})
    started = time.monotonic()
    changed = 0

    async def save():
        await db.settings.update_one(
            {"_id": "time_canon_v5"},
            {"$set": {
                "done": sorted(done),
                "cursors": cursors,
                "updated_at": utc_now_iso(),
            }},
            upsert=True,
        )

    for name, attr, fields in targets:
        if name in done:
            continue
        col = getattr(db, attr, None)
        if col is None:
            done.add(name)
            cursors.pop(name, None)
            await save()
            continue
        while time.monotonic() - started < budget_s:
            query = {}
            last = unpack_id(cursors.get(name))
            if last is not None:
                query["_id"] = {"$gt": last}
            docs = await col.find(
                query, {field: 1 for field in fields},
            ).sort("_id", 1).limit(batch_size).to_list(batch_size)
            if not docs:
                done.add(name)
                cursors.pop(name, None)
                await save()
                break
            ops = []
            for doc in docs:
                patch = {}
                for field in fields:
                    rewritten = canon(doc.get(field))
                    if rewritten:
                        patch[field] = rewritten
                if patch:
                    ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": patch}))
            if ops:
                await col.bulk_write(ops, ordered=False)
                changed += len(ops)
            packed = pack_id(docs[-1]["_id"])
            if not packed:
                logger.warning("migration v5: unusable _id on %s; stopping that collection", name)
                done.add(name)
                cursors.pop(name, None)
                await save()
                break
            cursors[name] = packed
            if len(docs) < batch_size:
                done.add(name)
                cursors.pop(name, None)
            await save()
            if name in done:
                break
        if name not in done:
            logger.info("migration v5: paused after %s rewrites; resume next boot", changed)
            return False
    logger.info("migration v5: canonical instants finished (%s rewrites this pass)", changed)
    return True


async def run_migrations(db):
    try:
        raw = await db.settings.find_one({"_id": "global"})
        cur = int((raw or {}).get("db_version", 1) or 1)
        if cur >= CURRENT_DB_VERSION:
            return {"migrated": False, "version": cur}
        logger.info(f"migrations: {cur} -> {CURRENT_DB_VERSION}")
        if cur < 3:
            await _migrate_v3_exam_sessions(db)
        if cur < 4:
            await _migrate_v4_feature_policies(db)
        if cur < 5:
            # نسخه را تا تمام شدن اسکن بالا نبر، وگرنه بقیه‌ی ردیف‌ها جا می‌مانند.
            if not await _migrate_v5_canonical_instants(db):
                return {"migrated": False, "version": cur, "pending": "v5_canonical_instants"}
        await db.settings.update_one({"_id": "global"}, {"$set": {"db_version": CURRENT_DB_VERSION, "db_version_updated_at": utc_now_iso()}}, upsert=True)
        return {"migrated": True, "from": cur, "to": CURRENT_DB_VERSION}
    except Exception as e:
        logger.warning(f"run_migrations failed: {e}")
        return {"migrated": False, "error": str(e)}
