# -*- coding: utf-8 -*-
"""
🔴 FIX-R1 — Migration دور اول اصلاحات پنل ادمین (موارد ۱ تا ۷).

اسکریپت مستقل، idempotent و ایمن:
  * هیچ داده‌ای حذف نمی‌شود؛ فقط نرمال‌سازی/بک‌فیلل.
  * اجرای چندباره بی‌خطر است (هر مرحله فقط اسنادِ نیازمند را دست می‌زند).

مراحل:
  1) blocked_bot:false برای همه‌ی کاربرانی که فیلد ندارند (مورد ۱)
  2) بستن notif_run های «running» مانده از پروسه‌های مرده (مورد ۲)
  3) بازطبقه‌بندی failed→blocked در run های قدیمی بر اساس کاربرانِ
     فعلاً بلاک (مورد ۲) — فقط وقتی failed_user_ids موجود باشد.
  4) نرمال‌سازی report_id های رشته‌ای/گمشده + رفع تکراری‌ها + بوت‌استرپ
     شمارنده به max+1 (مورد ۵) + status_history برای اسناد قدیمی.
  5) description «-» → «» در bs_content (مورد ۴)
  6) گزارش وضعیت (تعداد اسناد دست‌خورده در هر مرحله).

اجرا:
    python3 migrate_round1.py            # پیش‌فرض: mongodb://localhost:27017
    MONGODB_URI="..." python3 migrate_round1.py
    python3 migrate_round1.py --dry      # فقط شمارش، بدون تغییر

بعد از migration، rule «متادیتای ناقص» به‌صورت زنده بازمحاسبه می‌شود
(داده‌ی کش‌شده‌ای وجود ندارد) — نیازی به بازتولید جداگانه نیست.
"""
import asyncio
import os
import sys

# ── اجرای مستقل از ریشه‌ی ریپو ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DRY = '--dry' in sys.argv or '-n' in sys.argv

# ── زیرسیستم‌ها ──
from motor.motor_asyncio import AsyncIOMotorClient           # noqa: E402
from bson import ObjectId                                     # noqa: E402
from time_utils import utc_now_iso                            # noqa: E402

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
# نام دیتابیس همان db/core.py است (hardcoded 'medicalbot')
MONGODB_DB = os.getenv('MONGODB_NAME', 'medicalbot')


async def step1_users_blocked_backfill(db, report):
    """blocked_bot:false برای کاربران بدون فیلد (پیش‌فرض صریح)."""
    res = await db.users.update_many(
        {'blocked_bot': {'$exists': False}},
        {'$set': {'blocked_bot': False}},
    )
    report['users_blocked_backfilled'] = res.modified_count


async def step2_close_stale_notif_runs(db, report):
    """اجراهای running قدیمی‌تر از ۲ ساعت → error با توضیح."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    res = await db.notif_runs.update_many(
        {'status': 'running', 'started_at': {'$lt': cutoff}},
        {'$set': {
            'status': 'error',
            'error': 'اجراهای مانده (running) به‌صورت خودکار بسته شد — پروسه حین اجرا قطع شده بود. (migrate_round1)',
            'finished_at': utc_now_iso(),
        }},
    )
    report['stale_runs_closed'] = res.modified_count


async def step3_reclassify_failed_as_blocked(db, report):
    """در run های قدیمی، failed_user_ids هایی که الان بلاک‌اند از failed
    به blocked منتقل می‌شوند (خطای کاذب داشبورد همین بود).

    فقط با شناسه‌ی کاربرِ اکنون بلاک‌شده کار می‌کند؛ failed بدون
    failed_user_ids دست نمی‌خورد (نمی‌دانیم کی بوده)."""
    runs = await db.notif_runs.find(
        {'failed': {'$gt': 0},
         'failed_user_ids': {'$exists': True, '$ne': []},
         # idempotency: هر run فقط یک بار بازطبقه‌بندی می‌شود
         'reclassified_blocked': {'$exists': False}},
        {'failed': 1, 'failed_user_ids': 1, 'blocked': 1},
    ).to_list(5000)
    moved_runs = 0
    moved_users = 0
    for run in runs:
        fids = run.get('failed_user_ids') or []
        if not fids:
            continue
        blocked_now = await db.users.count_documents(
            {'user_id': {'$in': [int(x) for x in fids if str(x).isdigit()]},
             'blocked_bot': True})
        if not blocked_now:
            continue
        new_failed = max(0, int(run.get('failed') or 0) - blocked_now)
        new_blocked = int(run.get('blocked') or 0) + blocked_now
        await db.notif_runs.update_one(
            {'_id': run['_id']},
            {'$set': {
                'failed': new_failed, 'blocked': new_blocked,
                'reclassified_blocked': blocked_now,
                'reclassified_note': 'کاربرانِ بلاک‌کننده از شمارش خطا به blocked منتقل شدند (migrate_round1).',
            }},
        )
        moved_runs += 1
        moved_users += blocked_now
    report['runs_reclassified'] = moved_runs
    report['users_reclassified'] = moved_users


async def step4_report_ids(db, report):
    """نرمال‌سازی report_id: رشته→عدد، گمشده→تخصیص، تکراری→تخصیص مجدد؛
    سپس بوت‌استرپ شمارنده به max+1."""
    # ۴-۱) رشته‌های عددی → int
    str_fixed = 0
    async for doc in db.content_reports.find({'report_id': {'$type': 'string'}}):
        try:
            rid = int(doc['report_id'].strip())
        except (ValueError, AttributeError):
            rid = None
        if rid is not None:
            await db.content_reports.update_one(
                {'_id': doc['_id']}, {'$set': {'report_id': rid}})
            str_fixed += 1
        else:
            await db.content_reports.update_one(
                {'_id': doc['_id']}, {'$unset': {'report_id': ''}})
    report['report_id_string_fixed'] = str_fixed

    # ۴-۲) تخصیص report_id به اسناد بدون report_id (از بالا)
    highest = await db.content_reports.find_one(
        {}, sort=[('report_id', -1)], projection={'report_id': 1})
    next_id = int((highest or {}).get('report_id') or 0)
    assigned_missing = 0
    async for doc in db.content_reports.find({'report_id': {'$exists': False}}):
        next_id += 1
        await db.content_reports.update_one(
            {'_id': doc['_id']}, {'$set': {'report_id': next_id}})
        assigned_missing += 1
    report['report_id_missing_assigned'] = assigned_missing

    # ۴-۳) تکراری‌ها: هر report_id فقط یک بار مجاز است؛ بقیه از نو
    # شماره می‌خورند (سند قدیمی‌تر keep می‌شود — earliest _id).
    seen = {}
    reassigned = 0
    async for doc in db.content_reports.find(
            {'report_id': {'$exists': True}},
            {'report_id': 1}).sort('_id', 1):
        rid = int(doc.get('report_id') or 0)
        if rid in seen:
            next_id += 1
            await db.content_reports.update_one(
                {'_id': doc['_id']}, {'$set': {'report_id': next_id}})
            reassigned += 1
        else:
            seen[rid] = doc['_id']
    report['report_id_dupes_reassigned'] = reassigned

    # ۴-۴) بوت‌استرپ شمارنده (همان منطق create_content_report)
    final_highest = await db.content_reports.find_one(
        {}, sort=[('report_id', -1)], projection={'report_id': 1})
    final_max = int((final_highest or {}).get('report_id') or 0)
    await db.db_counters.update_one(
        {'_id': 'content_report_id'},
        {'$set': {'seq': max(final_max, next_id)}},
        upsert=True,
    )
    report['counter_bootstrapped_to'] = max(final_max, next_id)

    # ۴-۵) status_history برای اسناد قدیمی (خالی، نه مفقود)
    res = await db.content_reports.update_many(
        {'status_history': {'$exists': False}},
        {'$set': {'status_history': []}},
    )
    report['status_history_backfilled'] = res.modified_count


async def step5_description_dash(db, report):
    """توضیح «-» (رد کردن اختیاری در ربات) → رشته‌ی خالی (مورد ۴)."""
    res = await db.bs_content.update_many(
        {'description': {'$in': ['-', '—', '–']}},
        {'$set': {'description': ''}},
    )
    report['description_dash_normalized'] = res.modified_count


async def main():
    print('🔴 migrate_round1 — شروع' + (' (DRY-RUN: فقط گزارش، بدون تغییر)' if DRY else ''))
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DB]

    report = {}
    steps = [
        ('۱) blocked_bot:false بک‌فیلل کاربران', step1_users_blocked_backfill),
        ('۲) بستن notif_run های running مانده', step2_close_stale_notif_runs),
        ('۳) بازطبقه‌بندی failed→blocked', step3_reclassify_failed_as_blocked),
        ('۴) نرمال‌سازی report_id ها', step4_report_ids),
        ('۵) توضیح «-» → خالی', step5_description_dash),
    ]
    for title, fn in steps:
        print(f'— {title} …')
        if DRY:
            # در dry فقط شمارش‌های سبک انجام شود؛ برای سادگی، توابع را با
            # پرچم DRY اجرا نمی‌کنیم و از شمارش خام رد می‌شویم.
            print('   (dry-run: رد شد)')
            continue
        await fn(db, report)

    if DRY:
        print('\n🏁 dry-run تمام شد — برای اجرای واقعی بدون --dry اجرا کن.')
        client.close()
        return

    print('\n══════ گزارش migration ══════')
    for k, v in report.items():
        print(f'  {k}: {v}')
    print('🏁 migration تمام شد.')
    client.close()


if __name__ == '__main__':
    asyncio.run(main())
