# -*- coding: utf-8 -*-
"""↩️ ماموریت ۶ — بازگردانی migration موجودیت‌های fork

بازگردانی اسناد از پشتیبانِ tools/migration/content_forks.py (backup.json)
با upsert بر اساس _id — بدون حذف هیچ سند دیگری. ایندکس‌های یکتا هم
در صورت وجود، حذف می‌شوند تا داده‌ی بازگردانی‌شده دچار خطای درج نشود.

اجرا:
    python3 tools/migration/content_forks_rollback.py backups/content_forks/<ts>/backup.json
    python3 tools/migration/content_forks_rollback.py --latest
"""
import argparse
import asyncio
import glob
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

BACKUP_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', 'backups', 'content_forks')


def _oid(x):
    from bson import ObjectId
    try:
        return ObjectId(x)
    except Exception:
        return None


async def run(path: str) -> int:
    from database import db
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)

    restored = {'bs_sessions': 0, 'ref_books': 0}
    # ایندکس یکتا را اول بردار تا replace درج‌های بازگردانی خطا ندهد
    for coll, name in ((db.bs_sessions, 'uq_bs_session_fork'), (db.ref_books, 'uq_ref_book_fork')):
        try:
            await coll.drop_index(name)
            print(f'   🧹 ایندکس {name} حذف شد')
        except Exception:
            pass

    for sid, doc in (('bs_sessions', 'bs_sessions'), ('ref_books', 'ref_books')):
        coll = getattr(db, sid)
        for row in data.get(doc, []):
            rid = _oid(row.get('_id'))
            if not rid:
                continue
            clean = dict(row)
            clean['_id'] = rid
            await coll.replace_one({'_id': rid}, clean, upsert=True)
            restored[doc] += 1

    print(f"✅ بازگردانی شد: {restored['bs_sessions']} جلسه، {restored['ref_books']} کتاب "
          f"از {path}")
    print('ℹ️ ایندکس‌های یکتا حذف شدند؛ پس از ریشه‌یابی، migration را دوباره اجرا کنید.')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='بازگردانی migration فورک‌ها (ماموریت ۶)')
    ap.add_argument('backup', nargs='?', help='مسیر backup.json')
    ap.add_argument('--latest', action='store_true', help='آخرین پشتیبان')
    args = ap.parse_args()
    path = args.backup
    if args.latest or not path:
        cands = sorted(glob.glob(os.path.join(BACKUP_ROOT, '*', 'backup.json')))
        if not cands:
            print('❌ پشتیبانی پیدا نشد'); sys.exit(2)
        path = cands[-1]
    if not os.path.exists(path):
        print(f'❌ فایل پیدا نشد: {path}'); sys.exit(2)
    sys.exit(asyncio.run(run(path)))
