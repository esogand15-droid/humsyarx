"""Safe migration & backfill tool for HumsYar v2:
  1) Section 1: Legacy users `educational_group` schema + non-destructive AI name suggestion backfill
  2) Section 2 & 4: Schedule & template `term` / `educational_group` normalization + safe duplicate/stale anomaly archiving
  3) Section 5: Scoped lesson `bs_sessions` intake inheritance & duplicate fork audit

Usage (always run --dry-run first):
    python -m tools.migration.educational_groups_and_schedules --dry-run
    python -m tools.migration.educational_groups_and_schedules --apply
    python -m tools.migration.educational_groups_and_schedules --rollback --backup backups/edu_sched_YYYYMMDD_HHMMSS.json
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


COLLECTIONS = (
    "users",
    "roles",
    "user_roles",
    "admin_roles",
    "schedules",
    "schedule_templates",
    "course_offerings",
    "course_selections",
    "bs_sessions",
)


def _json_default(o):
    from bson import ObjectId
    if isinstance(o, ObjectId):
        return {"$oid": str(o)}
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def _from_json(doc: dict) -> dict:
    from bson import ObjectId
    out = dict(doc)
    raw_id = out.get("_id")
    if isinstance(raw_id, dict) and "$oid" in raw_id:
        out["_id"] = ObjectId(raw_id["$oid"])
    return out


async def take_backup(db, backup_dir: str = "backups") -> str:
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir, f"edu_sched_{ts}.json")
    payload = {"created_at": ts, "collections": {}}
    for name in COLLECTIONS:
        col = getattr(db, name)
        payload["collections"][name] = await col.find({}).to_list(50000)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
    return path


async def run_migration(db, dry_run: bool = True) -> dict:
    term_cfg = await db.get_current_term_config()
    active_term = term_cfg.get("term", "1404-2")

    # ۱) Backfill پیشنهاد گروه آموزشی کاربران قدیمی (بدون تغییر قطعی بدون تایید)
    users_report = await db.backfill_legacy_users_educational_group(dry_run=dry_run)

    # ۲) نرمال‌سازی فیلدهای educational_group و term در schedules / schedule_templates / course_offerings
    sched_docs = await db.schedules.find({}).to_list(10000)
    tpl_docs = await db.schedule_templates.find({}).to_list(5000)
    off_docs = await db.course_offerings.find({}).to_list(5000)

    sched_norm_count = 0
    for s in sched_docs or []:
        updates = {}
        if not s.get("educational_group"):
            updates["educational_group"] = "mixed"
        if not s.get("term"):
            updates["term"] = active_term
        if "archived" not in s:
            updates["archived"] = False
        if updates:
            sched_norm_count += 1
            if not dry_run:
                await db.schedules.update_one({"_id": s["_id"]}, {"$set": updates})

    tpl_norm_count = 0
    for t in tpl_docs or []:
        updates = {}
        if not t.get("educational_group"):
            updates["educational_group"] = "mixed"
        if not t.get("term"):
            updates["term"] = active_term
        if "archived" not in t:
            updates["archived"] = False
        if updates:
            tpl_norm_count += 1
            if not dry_run:
                await db.schedule_templates.update_one({"_id": t["_id"]}, {"$set": updates})

    off_norm_count = 0
    for o in off_docs or []:
        updates = {}
        if not o.get("educational_group"):
            updates["educational_group"] = "mixed"
        if "archived" not in o:
            updates["archived"] = False
        if updates:
            off_norm_count += 1
            if not dry_run:
                await db.course_offerings.update_one({"_id": o["_id"]}, {"$set": updates})

    # ۳) شناسایی و آرشیو ایمن رکوردهای تکراری/منسوخ برنامه کلاسی
    anomaly_report = await db.audit_and_cleanup_schedule_anomalies(
        dry_run=dry_run, active_term=active_term,
    )

    # ۴) بررسی جلسات علوم پایه (bs_sessions) برای ارث‌بری صحیح intake از درس والد
    lessons = await db.bs_lessons.find({}).to_list(2000)
    lesson_intake_map = {str(l["_id"]): (l.get("intake") or "") for l in (lessons or [])}
    sessions = await db.bs_sessions.find({}).to_list(10000)
    session_intake_fixed = 0
    redundant_self_forks = []
    by_id = {str(s["_id"]): s for s in (sessions or [])}

    for s in sessions or []:
        lid = str(s.get("lesson_id") or "")
        parent_intake = lesson_intake_map.get(lid, "")
        s_intake = s.get("intake") or ""
        if parent_intake and not s_intake and not s.get("fork_of"):
            session_intake_fixed += 1
            if not dry_run:
                await db.bs_sessions.update_one(
                    {"_id": s["_id"]},
                    {"$set": {"intake": parent_intake}},
                )
        fork_of = str(s.get("fork_of") or "")
        if fork_of and fork_of in by_id:
            base_doc = by_id[fork_of]
            base_eff_intake = (base_doc.get("intake") or "") or lesson_intake_map.get(str(base_doc.get("lesson_id") or ""), "")
            if base_eff_intake and base_eff_intake == (s.get("intake") or ""):
                redundant_self_forks.append({
                    "fork_id": str(s["_id"]),
                    "base_id": fork_of,
                    "title": s.get("title", ""),
                    "intake": base_eff_intake,
                })

    # ۵) یکپارچه‌سازی و خودترمیم RBAC (همگام‌سازی user_roles، admin_roles و users.role + رفع تداخل content_scoped/content_admin)
    ur_docs = await db.user_roles.find({}).to_list(5000)
    ar_docs = await db.admin_roles.find({}).to_list(5000)
    ca_users = await db.users.find({"role": "content_admin"}).to_list(5000)
    rbac_collisions = []
    for ur in ur_docs or []:
        r_list = list(ur.get("roles") or [])
        if "content_admin" in r_list and "content_scoped" in r_list:
            rbac_collisions.append({"uid": ur.get("_id"), "roles": r_list, "scope_intake": ur.get("scope_intake")})
    rbac_migrated = 0
    if not dry_run and hasattr(db, "rbac_migrate_users"):
        await db.seed_system_roles()
        rbac_migrated = await db.rbac_migrate_users()

    return {
        "dry_run": dry_run,
        "active_term": active_term,
        "users_backfill": users_report,
        "rbac_unification": {
            "user_roles_count": len(ur_docs or []),
            "admin_roles_count": len(ar_docs or []),
            "legacy_content_admin_users": len(ca_users or []),
            "collisions_detected": len(rbac_collisions),
            "collisions": rbac_collisions,
            "migrated_records": rbac_migrated,
        },
        "normalized_documents": {
            "schedules": sched_norm_count,
            "schedule_templates": tpl_norm_count,
            "course_offerings": off_norm_count,
        },
        "schedule_anomalies": anomaly_report,
        "content_sessions": {
            "inherited_intake_backfilled": session_intake_fixed,
            "redundant_self_forks_detected": len(redundant_self_forks),
            "redundant_self_forks": redundant_self_forks[:20],
        },
    }


async def rollback_from_backup(db, backup_path: str) -> dict:
    with open(backup_path, encoding="utf-8") as f:
        payload = json.load(f)
    restored = {}
    for name, docs in (payload.get("collections") or {}).items():
        if name not in COLLECTIONS:
            continue
        col = getattr(db, name)
        await col.delete_many({})
        if docs:
            await col.insert_many([_from_json(d) for d in docs])
        restored[name] = len(docs)
    return {"restored": restored, "from": backup_path}


async def _amain():
    ap = argparse.ArgumentParser(description="Safe educational_group & schedule migration tool")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Report planned changes without writing")
    g.add_argument("--apply", action="store_true", help="Take JSON backup then apply migration")
    g.add_argument("--rollback", action="store_true", help="Restore collections from --backup")
    ap.add_argument("--backup", default="", help="Backup file path for --rollback")
    args = ap.parse_args()

    from database import db
    if args.rollback:
        if not args.backup:
            raise SystemExit("--rollback requires --backup <path>")
        out = await rollback_from_backup(db, args.backup)
    elif args.apply:
        bpath = await take_backup(db)
        out = await run_migration(db, dry_run=False)
        out["backup"] = bpath
    else:
        out = await run_migration(db, dry_run=True)

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_amain())
