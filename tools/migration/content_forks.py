# -*- coding: utf-8 -*-
"""🧳 ماموریت ۶ — Migration موجودیت‌های Fork/Override (A/B/C/D)

رده‌بندی و رفع کلون‌های موجودِ bs_sessions / bs_content / ref_books / ref_files
برای گذار به مدل Copy-on-Write (⭐):

  A) fork بدون «تغییر واقعی» نسبت به base (عنوان/شماره/استاد یکی +
     همان مجموعه فایل)            → archived: true (بدون حذف داده)
  B) fork با تغییر واقعی          → حفظ (override معتبر؛ دست‌نخورده)
  C) fork تکراری برای (base,intake) → نگه‌داشتنِ غنی‌ترین/جدیدترین؛
                                     بقیه archived: true
  D) fork یتیم (base حذف شده)      → قطع پیوند: حذف fork_of → «بومی ورودی»

سپس ساخت ایندکس‌های یکتای جزئی (fork_of, intake) — اگر C هنوز وجود
داشت خطا می‌خورد و گزارش می‌شود (ایدمپوتنت: دوباره‌اجرا = بدون تغییر).

اجرا:
    python3 tools/migration/content_forks.py                 # dry-run (پیش‌فرض)
    python3 tools/migration/content_forks.py --apply         # اعمال
    MONGODB_URI="mongodb://…" python3 tools/migration/content_forks.py --apply

پشتیبان: پیش از هر تغییر، اسناد درگیر در backups/content_forks/<ts>/
ذخیره می‌شوند (JSON؛ بازگردانی با content_forks_rollback.py).
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

BACKUP_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', 'backups', 'content_forks')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── رده‌بندی (خالص — تست‌پذیر بدون DB) ──────────────────────────

def session_signature(base: dict, contents: list) -> dict:
    """امضای مقایسه: فیلدهای شناسه‌ی جلسه + مجموعه‌ی فایل‌ها (مستقل از ترتیب)."""
    files = set()
    for c in contents:
        files.add((
            str(c.get('file_id') or ''),
            str(c.get('type') or ''),
            str(c.get('description') or ''),
            int(c.get('order') or 0),
        ))
    return {
        'number': int(base.get('number') or 0),
        'topic': str(base.get('topic') or ''),
        'teacher': str(base.get('teacher') or ''),
        'files': files,
    }


def is_unchanged_copy(base_sig: dict, fork_sig: dict) -> bool:
    """A: fork عملاً همان base است (هیچ تغییر واقعی)."""
    return base_sig == fork_sig


def classify_forks(base_sessions: dict, fork_docs: list, contents_of: dict) -> list:
    """خروجی: [{fork, cls}] که cls ∈ {'A','B','D'}؛ C در گام بعدی."""
    out = []
    for f in fork_docs:
        base = base_sessions.get(str(f.get('fork_of')))
        if base is None:
            out.append({'fork': f, 'cls': 'D'})
            continue
        base_sig = session_signature(base, contents_of.get(str(base['_id']), []))
        fork_sig = session_signature(f, contents_of.get(str(f['_id']), []))
        out.append({'fork': f, 'cls': 'A' if is_unchanged_copy(base_sig, fork_sig) else 'B'})
    return out


def pick_duplicate_keepers(items: list) -> dict:
    """C: از هر گروه (base, intake) فقط یک fork فعال می‌ماند.
    معیار: (تعداد فایل، created_at) — غنی‌ترین و جدیدترین."""
    groups = {}
    for it in items:
        if it['cls'] == 'D':
            continue
        f = it['fork']
        key = (str(f.get('fork_of')), str(f.get('intake') or ''))
        groups.setdefault(key, []).append(it)
    verdict = {}   # fork_id → 'keep' | 'archive'
    for key, group in groups.items():
        if len(group) == 1:
            verdict[str(group[0]['fork']['_id'])] = 'keep'
            continue
        def rank(it):
            f = it['fork']
            return (it.get('nfiles', 0), str(f.get('created_at') or ''))
        ranked = sorted(group, key=rank, reverse=True)
        for i, it in enumerate(ranked):
            verdict[str(it['fork']['_id'])] = 'keep' if i == 0 else 'archive'
    return verdict


# ── اجرا ───────────────────────────────────────────────────────

async def run(apply: bool) -> int:
    from database import db

    bs_sessions, bs_content = db.bs_sessions, db.bs_content
    ref_books, ref_files = db.ref_books, db.ref_files

    print('⏳ خواندن forkهای فعال…')
    fork_sessions = await bs_sessions.find(
        {'fork_of': {'$type': 'string'}, 'archived': {'$ne': True}}).to_list(10000)
    fork_books = await ref_books.find(
        {'fork_of': {'$type': 'string'}, 'archived': {'$ne': True}}).to_list(10000)
    print(f'   جلسه-fork: {len(fork_sessions)} · کتاب-fork: {len(fork_books)}')

    # baseهای مرجع
    base_ids = {str(f.get('fork_of')) for f in fork_sessions}
    bases = {str(s['_id']): s for s in
             (await bs_sessions.find({'_id': {'$in': [
                 _oid(x) for x in base_ids] if base_ids else []}}).to_list(10000))
             if _oid(str(s['_id'])) or True}
    # (find با $in روی ObjectId؛ نگاشت رشته‌ای)
    base_map = {}
    for f in fork_sessions:
        bid = str(f.get('fork_of'))
        if bid not in base_map:
            base_map[bid] = await db.bs_get_session(bid)
    base_sessions = {k: v for k, v in base_map.items() if v}

    # محتوای forkها و baseها برای امضا
    contents_of = {}
    for f in fork_sessions:
        sid = str(f['_id'])
        contents_of[sid] = await db.bs_get_content(sid)
    for bid in base_sessions:
        if bid not in contents_of:
            contents_of[bid] = await db.bs_get_content(bid)

    nfiles = {str(f['_id']): len(contents_of.get(str(f['_id']), [])) for f in fork_sessions}

    items = classify_forks(base_sessions, fork_sessions, contents_of)
    for it in items:
        it['nfiles'] = nfiles.get(str(it['fork']['_id']), 0)
    verdict = pick_duplicate_keepers(items)

    # ── گزارش ──
    report = {'generated_at': _now(), 'apply': apply,
              'sessions': {'A': [], 'B': [], 'C_archive': [], 'D_detach': [], 'keep': 0},
              'books': {'orphan_detach': [], 'duplicates': []}}

    for it in items:
        fid = str(it['fork']['_id'])
        f = it['fork']
        row = {'id': fid, 'fork_of': str(f.get('fork_of')), 'intake': str(f.get('intake') or ''),
               'topic': f.get('topic', ''), 'files': it['nfiles']}
        if it['cls'] == 'D':
            report['sessions']['D_detach'].append(row)
        elif it['cls'] == 'A':
            row['verdict'] = verdict.get(fid, 'keep')
            (report['sessions']['C_archive'] if row['verdict'] == 'archive'
             else report['sessions']['A']).append(row)
        else:
            row['verdict'] = verdict.get(fid, 'keep')
            if row['verdict'] == 'archive':
                report['sessions']['C_archive'].append(row)
            else:
                report['sessions']['keep'] += 1

    # کتاب‌ها: فقط D (یتیم) و C (تکراری) — B بدون تغییر
    book_bases = {}
    for f in fork_books:
        bid = str(f.get('fork_of'))
        if bid not in book_bases:
            book_bases[bid] = await db.ref_get_book(bid)
    book_groups = {}
    for f in fork_books:
        if not book_bases.get(str(f.get('fork_of'))):
            report['books']['orphan_detach'].append(
                {'id': str(f['_id']), 'name': f.get('name', ''),
                 'intake': str(f.get('intake') or '')})
        key = (str(f.get('fork_of')), str(f.get('intake') or ''))
        book_groups.setdefault(key, []).append(f)
    for key, group in book_groups.items():
        if len(group) > 1:
            group_sorted = sorted(group, key=lambda b: str(b.get('created_at') or ''), reverse=True)
            for loser in group_sorted[1:]:
                report['books']['duplicates'].append(
                    {'id': str(loser['_id']), 'name': loser.get('name', ''),
                     'intake': str(loser.get('intake') or ''), 'fork_of': key[0]})

    print('\n📊 گزارش رده‌بندی:')
    print(f"   جلسات → A(آرشیو بدون-تغییر): {len(report['sessions']['A'])}"
          f" · B(حفظ override): {report['sessions']['keep']}"
          f" · C(تکراری→آرشیو): {len(report['sessions']['C_archive'])}"
          f" · D(یتیم→بومی): {len(report['sessions']['D_detach'])}")
    print(f"   کتاب‌ها → یتیم: {len(report['books']['orphan_detach'])}"
          f" · تکراری: {len(report['books']['duplicates'])}")

    if not apply:
        out = os.path.join(BACKUP_ROOT, 'dry_run_report.json')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
        print(f'\n🔍 DRY-RUN — هیچ تغییری اعمال نشد. گزارش: {out}')
        print('   برای اعمال: python3 tools/migration/content_forks.py --apply')
        return 0

    # ── پشتیبان ──
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    bdir = os.path.abspath(os.path.join(BACKUP_ROOT, ts))
    os.makedirs(bdir, exist_ok=True)
    affected_ids = [str(f['_id']) for f in fork_sessions] + \
                   [str(f.get('fork_of')) for f in fork_sessions] + \
                   [str(f['_id']) for f in fork_books]
    backup = {'bs_sessions': [], 'ref_books': []}
    for sid in dict.fromkeys(x for x in affected_ids if x):
        doc = await bs_sessions.find_one({'_id': _oid(sid)})
        if doc:
            backup['bs_sessions'].append(_doc_json(doc))
    for f in fork_books:
        backup['ref_books'].append(_doc_json(f))
    with open(os.path.join(bdir, 'backup.json'), 'w', encoding='utf-8') as fh:
        json.dump({'created_at': _now(), **backup}, fh, ensure_ascii=False, default=str)
    print(f'💾 پشتیبان: {bdir}/backup.json ({len(backup["bs_sessions"])} جلسه، '
          f'{len(backup["ref_books"])} کتاب)')

    # ── اعمال (ایدمپوتنت) ──
    n_archived = n_detached = 0
    for it in items:
        fid = str(it['fork']['_id'])
        if it['cls'] == 'A' and verdict.get(fid) != 'archive':
            await bs_sessions.update_one({'_id': _oid(fid), 'archived': {'$ne': True}},
                                         {'$set': {'archived': True, 'archived_at': _now(),
                                                   'archived_reason': 'm6_case_A_no_change'}})
            n_archived += 1
        elif verdict.get(fid) == 'archive':   # C
            await bs_sessions.update_one({'_id': _oid(fid), 'archived': {'$ne': True}},
                                         {'$set': {'archived': True, 'archived_at': _now(),
                                                   'archived_reason': 'm6_case_C_duplicate'}})
            n_archived += 1
        elif it['cls'] == 'D':
            await bs_sessions.update_one({'_id': _oid(fid)},
                                         {'$unset': {'fork_of': ''},
                                          '$set': {'migrated_native_at': _now()}})
            n_detached += 1

    b_detached = 0
    for row in report['books']['orphan_detach']:
        await ref_books.update_one({'_id': _oid(row['id'])},
                                   {'$unset': {'fork_of': ''},
                                    '$set': {'migrated_native_at': _now()}})
        b_detached += 1
    b_archived = 0
    for row in report['books']['duplicates']:
        await ref_books.update_one({'_id': _oid(row['id'])},
                                   {'$set': {'archived': True, 'archived_at': _now(),
                                             'archived_reason': 'm6_case_C_duplicate'}})
        b_archived += 1

    # ── ایندکس‌های یکتای جزئی ──
    idx_errors = []
    for coll, name in ((bs_sessions, 'uq_bs_session_fork'), (ref_books, 'uq_ref_book_fork')):
        try:
            await coll.create_index(
                [('fork_of', 1), ('intake', 1)], unique=True,
                partialFilterExpression={'fork_of': {'$type': 'string'}},
                name=name, background=True)
            print(f'   ✅ ایندکس یکتا ساخته شد: {name}')
        except Exception as e:
            idx_errors.append(f'{name}: {e}')
            print(f'   ⚠️ ساخت ایندکس {name} ناموفق: {e}')

    print(f'\n✅ اعمال شد: آرشیو {n_archived} جلسه · بومی‌سازی {n_detached} یتیم · '
          f'کتاب: {b_archived} آرشیو / {b_detached} بومی')
    if idx_errors:
        print('⚠️ ایندکس‌ها (دوباره بعد از رفع تکراری‌ها اجرا کنید):')
        for e in idx_errors:
            print(f'   - {e}')
        return 1
    return 0


def _oid(x):
    from bson import ObjectId
    try:
        return ObjectId(x)
    except Exception:
        return None


def _doc_json(doc):
    d = dict(doc)
    d['_id'] = str(d['_id'])
    return d


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Migration موجودیت‌های fork (ماموریت ۶)')
    ap.add_argument('--apply', action='store_true', help='اعمال تغییرات (بدون آن: dry-run)')
    args = ap.parse_args()
    code = asyncio.run(run(apply=args.apply))
    sys.exit(code)
