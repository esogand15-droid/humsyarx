# -*- coding: utf-8 -*-
"""🩺 اسکریپت سلامت داده (فاز ۵ ماموریت تکمیل) — فقط-خواندنی.

بررسی ناسازگاری‌های داده با docs/DATA_CONTRACT.md:
  ۱) enumهای خارج از قرارداد (پرداخت/سؤال/تیکت/سؤال هوشمند)
  ۲) تناقض فیلدهای کاربر (suspended+approved)
  ۳) سندهای ناقص (پاسخ AI بدون نتیجه، پرداخت تأییدی بدون مرجع)

اجرا (production یا local با MONGO_URI):
    python3 tools/health/data_health.py
    MONGODB_URI="mongodb://…" python3 tools/health/data_health.py

قاعده ماموریت: هیچ تغییری اعمال نمی‌شود؛ فقط گزارش. خروجی با کد ۱
برای «مشکل یافت شد» (قابل استفاده در cron/monitor).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

PAY_STATUS = {'pending', 'approved', 'rejected', 'zarinpal_pending', 'cancelled', 'refunded'}
QUESTION_STATUS = {'pending', 'approved', 'rejected', 'needs_changes'}
TICKET_STATUS = {'open', 'in_progress', 'waiting_user', 'resolved', 'answered', 'closed'}
AI_STATUS = {'ready', 'answered'}


async def main() -> int:
    try:
        from database import db  # DAL موجود — همان اتصال پروژه
    except Exception as exc:
        print(f'❌ اتصال به دیتابیس ممکن نشد: {exc}')
        print('   MONGODB_URI را تنظیم کنید (مثلاً از vps.env).')
        return 2
    problems: list[tuple[str, str, int]] = []

    async def check_enum(coll, field, allowed, label):
        pipeline = [
            {'$group': {'_id': f'${field}', 'n': {'$sum': 1}}},
            {'$sort': {'n': -1}},
        ]
        try:
            rows = await getattr(db, coll).aggregate(pipeline).to_list(100)
        except Exception as exc:
            problems.append((label, f'خطا در خواندن {coll}: {exc}', -1))
            return
        for row in rows:
            val = row['_id']
            if val is None or val in allowed:
                continue
            problems.append((label, f'مقدار «{val}» خارج از قرارداد', row['n']))

    await check_enum('sub_payments', 'status', PAY_STATUS, 'پرداخت')
    await check_enum('questions', 'status', QUESTION_STATUS, 'سؤال')
    await check_enum('tickets', 'status', TICKET_STATUS, 'تیکت')
    await check_enum('ai_practice_questions', 'status', AI_STATUS, 'سؤال هوشمند')

    # تناقض کاربر: suspended=True ولی approved=True (wa_user_action هر دو را هم‌زمان تنظیم می‌کند)
    n = await db.users.count_documents({'suspended': True, 'approved': True})
    if n:
        problems.append(('کاربر', 'suspended=True همراه approved=True (تناقض)', n))

    # سؤال هوشمند: پاسخ‌داده اما بدون نتیجه
    n = await db.ai_practice_questions.count_documents(
        {'status': 'answered', 'is_correct': None})
    if n:
        problems.append(('سؤال هوشمند', 'answered بدون is_correct', n))

    # پرداخت تأییدیِ درگاه بدون ref (اطلاعاتی — تأیید دستی ممکن است)
    n = await db.sub_payments.count_documents(
        {'status': 'approved', 'zarinpal_ref_id': {'$in': [None, '']}})
    info_note = n

    # تیکت بدون وضعیت (سند قدیمی/خراب)
    n = await db.tickets.count_documents({'status': {'$in': [None, '']}})
    if n:
        problems.append(('تیکت', 'بدون status (سند قدیمی)', n))

    print('🩺 گزارش سلامت داده — ', end='')
    if not problems:
        print('سالم ✓')
        if info_note:
            print(f'ℹ️  {info_note} پرداخت تأییدشده بدون مرجع زرین‌پال '
                  f'(احتمالاً تأیید دستی/کارت‌به‌کارت — فقط اطلاع)')
        return 0
    print(f'{len(problems)} مورد:')
    for label, desc, count in problems:
        c = f' [{count} سند]' if count >= 0 else ''
        print(f'  🔸 [{label}] {desc}{c}')
    if info_note:
        print(f'ℹ️  {info_note} پرداخت تأییدشده بدون مرجع زرین‌پال (اطلاعاتی)')
    print('\n⚠️ طبق قاعده ماموریت، این اسکریپت چیزی اصلاح نمی‌کند — '
          'برای تعمیر، migration ایمن جداگانه لازم است.')
    return 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
