# -*- coding: utf-8 -*-
"""
🗄️ HUMSYAR DB layer — 🌊 موج Q2/W12: ماژولارسازی database.py
این ماژول بخشی از mixinهای کلاس DB است؛ facade در database.py بدون تغییر
رفتار، همه‌ی importهای قبلی را سالم نگه می‌دارد.
"""
import os
import logging
import asyncio
import difflib
from datetime import timedelta
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
import motor.motor_asyncio
from time_utils import (
    UTC, end_of_day_tehran, now_utc, parse_gregorian_date,
    parse_machine_datetime, remaining_days, start_of_month_tehran, utc_now_iso,
)

# نام logger عمداً «database» نگه داشته شد تا کانال لاگ تغییر نکند
logger = logging.getLogger('database')



class DBFinance:


    # ══════════════════════════════════════════════════════════════
    #  💳 سیستم اشتراک — FIX جدید
    #  پلن‌ها (چندتایی) + وضعیت هر کاربر + صف رسیدها + کدهای تخفیف
    # ══════════════════════════════════════════════════════════════

    # ── پلن‌ها ──
    async def sub_plan_add(self, name: str, days: int, price: int) -> str:
        count = await self.sub_plans.count_documents({})
        r = await self.sub_plans.insert_one({
            'name': name, 'days': days, 'price': price,
            'active': True, 'order': count,
            'created_at': utc_now_iso(),
        })
        return str(r.inserted_id)


    async def sub_plan_list(self, only_active: bool = False) -> list:
        q = {'active': True} if only_active else {}
        return await self.sub_plans.find(q).sort('order', 1).to_list(50)


    async def sub_plan_get(self, plan_id: str):
        try:
            return await self.sub_plans.find_one({'_id': ObjectId(plan_id)})
        except Exception:
            return None


    async def sub_plan_update(self, plan_id: str, data: dict) -> bool:
        try:
            await self.sub_plans.update_one({'_id': ObjectId(plan_id)}, {'$set': data})
            return True
        except Exception:
            return False


    async def sub_plan_toggle(self, plan_id: str) -> bool:
        p = await self.sub_plan_get(plan_id)
        if not p:
            return False
        await self.sub_plans.update_one(
            {'_id': ObjectId(plan_id)}, {'$set': {'active': not p.get('active', True)}}
        )
        return True


    async def sub_plan_delete(self, plan_id: str):
        try:
            await self.sub_plans.delete_one({'_id': ObjectId(plan_id)})
        except Exception:
            pass


    # ── کدهای تخفیف ──
    async def discount_add(self, code: str, percent: int, max_uses: int = 0,
                            expires_at: str = None, created_by: int = 0,
                            target_plan_ids: list = None, per_user_limit: int = 0) -> bool:
        code = code.strip().upper()
        if await self.discount_codes.find_one({'code': code}):
            return False
        if expires_at:
            try:
                if len(str(expires_at).strip()) == 10:
                    expires_at = end_of_day_tehran(parse_gregorian_date(expires_at)).astimezone(UTC).isoformat()
                else:
                    expires_at = parse_machine_datetime(expires_at).astimezone(UTC).isoformat()
            except ValueError:
                raise ValueError('invalid_discount_expiry')
        await self.discount_codes.insert_one({
            'code': code, 'percent': max(1, min(100, percent)),
            'max_uses': max_uses, 'used_count': 0,
            'expires_at': expires_at, 'active': True,
            # 🎟 موج D1 — [] یا None یعنی همه‌ی پلن‌های فعال؛
            # غیرخالی یعنی فقط همان plan_idها
            'target_plan_ids': [str(p) for p in (target_plan_ids or [])],
            # 0 = نامحدود؛ N = هر کاربر حداکثر N بار (پنیر discount_uses اتمیک)
            'per_user_limit': max(0, int(per_user_limit or 0)),
            'created_by': created_by, 'created_at': utc_now_iso(),
        })
        return True


    async def discount_list(self) -> list:
        return await self.discount_codes.find({}).sort('created_at', -1).to_list(100)


    async def discount_get(self, code: str) -> dict:
        return await self.discount_codes.find_one({'code': code.strip().upper()})


    async def discount_toggle(self, code: str) -> bool:
        d = await self.discount_codes.find_one({'code': code.strip().upper()})
        if not d:
            return False
        await self.discount_codes.update_one(
            {'_id': d['_id']}, {'$set': {'active': not d.get('active', True)}}
        )
        return True


    async def discount_delete(self, code: str) -> bool:
        result = await self.discount_codes.delete_one({'code': code.strip().upper()})
        return result.deleted_count > 0


    async def discount_validate(self, code: str, plan_id: str = None,
                                 user_id: int = None) -> dict:
        """
        اعتبارسنجی کد تخفیف — کد را مصرف نمی‌کند، فقط بررسی می‌کند.
        خروجی: {'ok': True, 'percent': N} یا {'ok': False, 'reason': '...'}
        موج D1: پارامترهای اختیاری plan_id/user_id — وقتی داده شوند،
        محدودیت پلن هدف و سقف استفاده‌ی هر کاربر هم چک می‌شود. فرم امضای
        قبلی (فقط code) کاملاً سازگار می‌ماند.
        """
        d = await self.discount_codes.find_one({'code': code.strip().upper()})
        if not d or not d.get('active'):
            return {'ok': False, 'reason': 'کد تخفیف معتبر نیست.'}
        if d.get('expires_at'):
            try:
                expiry_raw = str(d['expires_at']).strip()
                expiry = (end_of_day_tehran(parse_gregorian_date(expiry_raw)).astimezone(UTC)
                          if len(expiry_raw) == 10 else parse_machine_datetime(expiry_raw))
                if expiry < now_utc():
                    return {'ok': False, 'reason': 'این کد تخفیف منقضی شده.'}
            except ValueError:
                return {'ok': False, 'reason': 'زمان انقضای کد معتبر نیست.'}
        if d.get('max_uses', 0) > 0 and d.get('used_count', 0) >= d['max_uses']:
            return {'ok': False, 'reason': 'سقف استفاده از این کد تمام شده.'}
        # 🎟 موج D1 — محدودیت پلن هدف
        targets = d.get('target_plan_ids') or []
        if plan_id and targets and str(plan_id) not in targets:
            return {'ok': False, 'reason': 'این کد برای این پلن قابل استفاده نیست.'}
        # 🎟 موج D1 — سقف استفاده‌ی هر کاربر
        if user_id is not None and d.get('per_user_limit', 0) > 0:
            used_by_user = await self.discount_uses.count_documents(
                {'code': d['code'], 'user_id': int(user_id)})
            if used_by_user >= d['per_user_limit']:
                return {'ok': False, 'reason': 'شما قبلاً از این کد استفاده کرده‌اید.'}
        return {'ok': True, 'percent': d['percent'], 'discount': d}


    async def discount_consume(self, code: str, user_id: int = None):
        """
        مصرف کد — موج D1: کاملاً اتمیک و بدون نشتی.

          (۱) اگر per_user_limit فعال است، رزرو کاربر در discount_uses با
              unique index اتمیک ثبت می‌شود؛ تکراری ⇒ None (used_count
              دست‌نخورده می‌ماند — نشتی صفر).
          (۲) find_one_and_update با guard شرطی ($expr روی max_uses،
              expires_at و active) — در استفاده‌ی هم‌زمانِ چند کاربر
              used_count هرگز از max_uses عبور نمی‌کند (race fix).
          (۳) اگر گام ۲ شکست بخورد، رزرو گام ۱ جبران (حذف) می‌شود.

        max_uses=0 یعنی نامحدود.
        خروجی: سند به‌روزشده، یا None اگر نامعتبر/منقضی/پر شده باشد.
        """
        code_u = code.strip().upper()
        legacy = await self.discount_codes.find_one({'code': code_u}, {'expires_at': 1})
        legacy_expiry = str((legacy or {}).get('expires_at') or '').strip()
        if len(legacy_expiry) == 10:
            try:
                canonical_expiry = end_of_day_tehran(parse_gregorian_date(legacy_expiry)).astimezone(UTC).isoformat()
                await self.discount_codes.update_one({'code': code_u, 'expires_at': legacy_expiry},
                                                     {'$set': {'expires_at': canonical_expiry}})
            except ValueError:
                return None
        # (۱) رزرو per-user — قبل از افزایش شمارنده، تا شکست مصرف نشتی نسازد
        reserved = False
        if user_id is not None:
            d0 = await self.discount_codes.find_one({'code': code_u})
            if d0 and d0.get('per_user_limit', 0) > 0:
                try:
                    await self.discount_uses.insert_one({
                        'code': code_u, 'user_id': int(user_id),
                        'used_at': utc_now_iso(),
                    })
                    reserved = True
                except Exception:
                    return None  # کاربر قبلاً این کد را مصرف کرده
        # (۲) مصرف اتمیک با guard
        now_iso = utc_now_iso()
        d = await self.discount_codes.find_one_and_update(
            {
                'code': code_u, 'active': True,
                '$and': [
                    {'$or': [{'expires_at': None}, {'expires_at': {'$gt': now_iso}},
                             {'expires_at': {'$exists': False}}]},
                    {'$or': [{'max_uses': 0},
                             {'$expr': {'$lt': ['$used_count', '$max_uses']}}]},
                ],
            },
            {'$inc': {'used_count': 1}},
            return_document=True,
        )
        if not d:
            # (۳) جبران رزرو — مصرف انجام نشد
            if reserved:
                try:
                    await self.discount_uses.delete_one(
                        {'code': code_u, 'user_id': int(user_id)})
                except Exception as _rel:
                    # 🛡 AUDIT-R6 — جبران رزروی که بی‌صدا بمیرد یعنی کاربر یک
                    # مصرف سوخته روی کد دارد (ریسک مالی، نه جزئیات).
                    logger.error(f"discount compensation failed code={code_u} "
                                 f"uid={user_id}: {_rel}")
            return None
        # ⛔ موج D2 — لحظه‌ی اتمام ظرفیت: فقط همین یک مصرف‌کننده گذار از
        # max-1 به max را می‌بیند (فیلتر اتمیک تضمین می‌کند) ⇒ دقیقاً یک
        # سیگنال. خروجی ربات (mini_app_outbox_job) متن کمپین‌های ارسالی
        # را به «اتمام موجودی» ادیت می‌کند. نامحدود (۰) ⇒ هرگز.
        try:
            mu = int(d.get('max_uses', 0) or 0)
            if mu > 0 and int(d.get('used_count', 0) or 0) >= mu:
                await self.bot_notifs.insert_one({
                    'type': 'signal', 'chat_id': 0,
                    'text': f'__DISCOUNT_EXHAUSTED__:{code_u}',
                    'sent': False, 'created_at': utc_now_iso(),
                })
        except Exception:
            pass  # سیگنال نباید مسیر خرید را بشکند
        return d


    async def discount_release(self, code: str, user_id: int = None):
        """
        جبران مصرف — در رد رسید پرداخت صدا زده می‌شود: رزرو per-user حذف
        و used_count یک واحد کم می‌شود (کف ۰) تا کاربر بتواند با رسید
        درست دوباره از همان کد استفاده کند.
        برای کدهای per_user_limit تنها وقتی شمارنده کم می‌شود که رزروی
        واقعیِ همین کاربر حذف شده باشد (ضد کاهش اشتباه).
        """
        try:
            code_u = code.strip().upper()
            freed = False
            if user_id is not None:
                r = await self.discount_uses.delete_one(
                    {'code': code_u, 'user_id': int(user_id)})
                freed = (r.deleted_count or 0) > 0
            d0 = await self.discount_codes.find_one({'code': code_u})
            if not d0:
                return
            if d0.get('per_user_limit', 0) > 0 and user_id is not None and not freed:
                return
            await self.discount_codes.update_one(
                {'code': code_u, 'used_count': {'$gt': 0}},
                {'$inc': {'used_count': -1}})
        except Exception as e:
            # 🛡 AUDIT-R6 — release ناموفق کد را «مصرف‌شده» نگه می‌دارد درحالی‌که
            # پرداخت رد شده ⇒ حتماً لاگ شود.
            logger.error(f"discount_release failed code={code} uid={user_id}: {e}")


    # ── کاربران و سگمنت‌های کمپین (موج D1) ──
    async def discount_segment_users(self, segment: str = 'all') -> list:
        """کاربران هدف کمپین. segment: all | subscribers | no_sub"""
        if segment == 'subscribers':
            subs = await self.subscriptions.find(
                {'status': 'active', 'end_date': {'$gte': utc_now_iso()}}
            ).to_list(length=None)
            ids = list({int(s['_id']) for s in subs})
            if not ids:
                return []
            return await self.users.find(
                {'approved': True, 'blocked_bot': {'$ne': True}, 'user_id': {'$in': ids}}
            ).to_list(length=None)
        if segment == 'no_sub':
            subs = await self.subscriptions.find(
                {'status': 'active', 'end_date': {'$gte': utc_now_iso()}}
            ).to_list(length=None)
            ids = list({int(s['_id']) for s in subs})
            return await self.users.find(
                {'approved': True, 'blocked_bot': {'$ne': True}, 'user_id': {'$nin': ids}}
            ).to_list(length=None)
        return await self.users.find(
            {'approved': True, 'blocked_bot': {'$ne': True}}
        ).to_list(length=None)


    async def discount_payment_stats(self, code: str) -> dict:
        """آمار استفاده‌ی واقعی یک کد — از اسناد sub_payments (snapshot مالی)."""
        code_u = code.strip().upper()
        rows = await self.sub_payments.aggregate([
            {'$match': {'discount_code': code_u, 'status': 'approved'}},
            {'$group': {'_id': None, 'usage_approved': {'$sum': 1},
                        'revenue': {'$sum': {'$ifNull': ['$final_price', 0]}},
                        'discount_given': {'$sum': {'$max': [0, {'$subtract': [
                            {'$ifNull': ['$price', 0]}, {'$ifNull': ['$final_price', 0]}]}]}}}},
        ]).to_list(1)
        row = rows[0] if rows else {}
        return {'usage_approved': int(row.get('usage_approved') or 0),
                'revenue': int(row.get('revenue') or 0),
                'discount_given': int(row.get('discount_given') or 0)}


    async def discount_bcast_create(self, code: str, target: str, created_by: int,
                                     source: str = 'bot') -> str:
        import uuid
        bid = uuid.uuid4().hex[:12]
        await self.discount_bcasts.insert_one({
            'broadcast_id': bid, 'code': code, 'target': target,
            'status': 'sending', 'total': 0, 'sent': 0, 'failed': 0, 'blocked': 0,
            'source': source, 'created_by': created_by,
            'created_at': utc_now_iso(),
        })
        return bid


    async def discount_bcast_get(self, bid: str):
        return await self.discount_bcasts.find_one({'broadcast_id': bid})


    async def discount_bcast_update(self, bid: str, fields: dict):
        await self.discount_bcasts.update_one(
            {'broadcast_id': bid}, {'$set': fields})


    async def discount_bcast_active_for(self, code: str):
        """اگر برای این کد broadcast در حال ارسال است → سند (ضد دابل‌کلیک)"""
        return await self.discount_bcasts.find_one(
            {'code': code, 'status': 'sending'})


    async def discount_bcast_list(self, code: str, limit: int = 5) -> list:
        return await self.discount_bcasts.find(
            {'code': code}).sort('created_at', -1).to_list(limit)


    # ⛔ موج D2 — ادیت «اتمام موجودی»: مرجع پیام‌های کمپین
    async def discount_bcast_add_msgs(self, bid: str, refs: list):
        """ثبت مرجع پیام‌های موفق کمپین — [{'c': chat_id, 'm': message_id}]
        با $push ضمیمه می‌شود تا ادیت همگانیِ «اتمام موجودی» ممکن شود."""
        if not refs:
            return
        await self.discount_bcasts.update_one(
            {'broadcast_id': bid},
            # 🛡 AUDIT-V3 — کرانه: کمپین‌های بزرگ‌تر از SENT_MSGS_CAP فقط
            # برای «ادیت همگانی اتمام موجودی» پیام‌های ابتدایی را جا می‌اندازند
            # و یک فلگ قابل‌مشاهده می‌خورند؛ داده‌ی مالی حذف نمی‌شود.
            {'$push': {'sent_msgs': {'$each': refs, '$slice': -self.SENT_MSGS_CAP}},
             '$set': {'sent_msgs_at': utc_now_iso()}})


    SENT_MSGS_CAP = 5000             # 🛡 AUDIT-V3 — سقف مرجع‌های هر کمپین

    async def discount_bcast_with_msgs(self, code: str, limit: int = 50) -> list:
        """کمپین‌های این کد که حداقل یک مرجع پیام دارند (قابل ادیت)"""
        return await self.discount_bcasts.find(
            # 🛡 AUDIT-V4 — کرانه‌ی صریح (کمپین‌های تازه‌تر مهم‌ترند)
            {'code': code, 'soldout_marked': {'$ne': True},
             'sent_msgs.0': {'$exists': True}}
        ).sort('created_at', -1).to_list(max(1, min(int(limit or 50), 200)))


    # ── وضعیت اشتراک هر کاربر (یک سند در هر کاربر، با _id = user_id) ──
    async def sub_get(self, user_id: int) -> dict:
        return await self.subscriptions.find_one({'_id': user_id})


    async def sub_is_active(self, user_id: int) -> bool:
        s = await self.sub_get(user_id)
        if not s or s.get('status') != 'active':
            return False
        try:
            return parse_machine_datetime(s.get('end_date')) >= now_utc()
        except ValueError:
            return False


    async def sub_days_left(self, user_id: int) -> int:
        s = await self.sub_get(user_id)
        if not s or s.get('status') != 'active' or not s.get('end_date'):
            return 0
        try:
            return remaining_days(s['end_date'])
        except Exception:
            return 0


    async def sub_activate(self, user_id: int, days: int, plan_name: str,
                            source: str = 'payment', granted_by: int = 0,
                            extend: bool = False):
        """
        فعال‌سازی/تمدید اشتراک. اگر extend=True و اشتراک فعلی هنوز فعاله،
        روزها از تاریخ پایان فعلی جمع می‌شوند نه از الان (تا تمدید،
        روزهای باقی‌مانده را از بین نبرد).
        """
        now = now_utc()
        s = await self.sub_get(user_id)
        try:
            existing_end = parse_machine_datetime((s or {}).get('end_date'))
        except ValueError:
            existing_end = None
        if extend and s and s.get('status') == 'active' and existing_end and existing_end > now:
            base = existing_end
        else:
            base = now
        end_date = (base + timedelta(days=days)).isoformat()
        # total_days برای رسم نوار پیشرفت باقیمانده استفاده می‌شود
        total_days = max(1, (parse_machine_datetime(end_date) - base).days) if not extend else days
        await self.subscriptions.update_one(
            {'_id': user_id},
            {'$set': {
                'status': 'active', 'plan_name': plan_name,
                'start_date': now.isoformat(), 'end_date': end_date,
                'source': source, 'granted_by': granted_by,
                'last_plan_days': days,
                # FIX جدید: دو فلگ جدا برای یادآوری ۳روزه و ۱روزه
                'reminder_3d_sent': False, 'reminder_1d_sent': False,
                'updated_at': now.isoformat(),
            }},
            upsert=True
        )
        return end_date


    async def sub_revoke(self, user_id: int, reason: str, revoked_by: int) -> bool:
        result = await self.subscriptions.update_one(
            {'_id': user_id},
            {'$set': {
                'status': 'revoked', 'revoke_reason': reason,
                'revoked_by': revoked_by, 'revoked_at': utc_now_iso(),
            }}
        )
        return result.matched_count > 0


    async def sub_expire_due(self) -> list:
        """کاربرانی که تاریخ پایانشان گذشته ولی هنوز status=active مانده"""
        now_iso = utc_now_iso()
        due = await self.subscriptions.find(
            {'status': 'active', 'end_date': {'$lt': now_iso}}
        ).to_list(500)
        if due:
            await self.subscriptions.update_many(
                {'_id': {'$in': [d['_id'] for d in due]}},
                {'$set': {'status': 'expired'}}
            )
        return due


    async def sub_expiring_soon(self, days_before: int, flag_field: str) -> list:
        """
        اشتراک‌های فعالی که کمتر از N روز تا پایانشان مانده و هنوز
        یادآوری مخصوص همان فلگ (سه‌روزه یا یک‌روزه) را نگرفته‌اند.
        FIX جدید: دو یادآوری جدا (۳ روز و ۱ روز قبل) — دقیقاً مثل
        الگوی یادآوری‌های پلکانی امتحان که در ربات وجود دارد.
        """
        now = now_utc()
        cutoff = (now + timedelta(days=days_before)).isoformat()
        return await self.subscriptions.find({
            'status': 'active',
            'end_date': {'$gte': now.isoformat(), '$lte': cutoff},
            flag_field: {'$ne': True},
        }).to_list(500)


    async def sub_mark_reminder_sent(self, user_id: int, flag_field: str):
        await self.subscriptions.update_one(
            {'_id': user_id}, {'$set': {flag_field: True}}
        )


    async def sub_stats(self) -> dict:
        active  = await self.subscriptions.count_documents({'status': 'active'})
        expired = await self.subscriptions.count_documents({'status': 'expired'})
        revoked = await self.subscriptions.count_documents({'status': 'revoked'})
        pending = await self.sub_payments.count_documents({'status': 'pending'})
        approved_total = await self.sub_payments.count_documents({'status': 'approved'})
        rejected_total = await self.sub_payments.count_documents({'status': 'rejected'})
        month_start = start_of_month_tehran().astimezone(now_utc().tzinfo).isoformat()
        revenue_total = revenue_month = 0
        plan_counter: dict = {}
        async for p in self.sub_payments.find({'status': 'approved'}):
            amt = p.get('final_price', p.get('price', 0))
            revenue_total += amt
            if p.get('reviewed_at', '') >= month_start:
                revenue_month += amt
            plan_counter[p.get('plan_name', '-')] = plan_counter.get(p.get('plan_name', '-'), 0) + 1
        top_plan = max(plan_counter, key=plan_counter.get) if plan_counter else '-'
        conv_rate = round(approved_total / (approved_total + rejected_total) * 100) if (approved_total + rejected_total) else 0
        return {
            'active': active, 'expired': expired, 'revoked': revoked,
            'pending': pending, 'revenue': revenue_total,
            'revenue_month': revenue_month,
            'approved_total': approved_total, 'rejected_total': rejected_total,
            'top_plan': top_plan, 'conv_rate': conv_rate,
        }


    # ─── 🛡 AUDIT-A1b: ادعای یکتا (idempotency) برای عملیات‌های تکرارناپذیر ───
    # هر اثری که «دو بار اجرا شدنش» فاجعه است (اعطای روز اشتراک، لغو،
    # آزادسازی کد) باید اول کلیدش را ادعا کند. سند TTL دارد تا میز رشد
    # نکند (§58) و در خطای DB fail-open است (§49 — نبودِ قفل نباید
    # سرویس سالم را بخواباند؛ خودِ نوشتن در همان لحظه شکست می‌خورد).
    async def op_claim(self, kind: str, key: str, ttl_seconds: int = 120) -> bool:
        """ادعای کلید `kind:key` — True یعنی «مال من است»، False یعنی تکراری."""
        try:
            await self.admin_op_locks.insert_one({
                '_id': f"{kind}:{key}",
                'kind': kind,
                'created_at': utc_now_iso(),
                'expires_at': now_utc() + timedelta(seconds=ttl_seconds),
            })
            return True
        except DuplicateKeyError:
            return False
        except Exception as e:
            logger.warning(f"op_claim({kind}) degraded (fail-open): {e}")
            return True

    async def op_release(self, kind: str, key: str) -> None:
        """آزادسازی ادعا وقتی عملیات شکست خورد (تا ادمین بتواند تلاش کند)."""
        try:
            await self.admin_op_locks.delete_one({'_id': f"{kind}:{key}"})
        except Exception as e:
            logger.warning(f"op_release({kind}) failed: {e}")


    # ── صف رسیدهای پرداخت ──
    async def sub_payment_create(self, user_id: int, plan_id: str, plan_name: str,
                                  price: int, final_price: int, screenshot_file_id: str,
                                  discount_code: str = None,
                                  discount_percent: int = None) -> str:
        r = await self.sub_payments.insert_one({
            'user_id': user_id, 'plan_id': plan_id, 'plan_name': plan_name,
            'price': price, 'final_price': final_price,
            'discount_code': discount_code,
            # 🎟 موج D1 — snapshot کامل مالی: حتی اگر بعداً کد ویرایش/حذف شود،
            # درصدِ زمان تراکنش ثابت می‌ماند (immutability)
            'discount_percent': discount_percent,
            'screenshot_file_id': screenshot_file_id,
            'status': 'pending', 'submitted_at': utc_now_iso(),
            'admin_msg_id': None,
        })
        return str(r.inserted_id)


    async def sub_payment_get(self, pid: str):
        try:
            return await self.sub_payments.find_one({'_id': ObjectId(pid)})
        except Exception:
            return None


    async def sub_payment_has_pending(self, user_id: int) -> bool:
        """FIX جدید: جلوگیری از اسپم رسید — تا رسید قبلی بررسی نشده، جدید قبول نمی‌شود"""
        return await self.sub_payments.count_documents(
            {'user_id': user_id, 'status': 'pending'}
        ) > 0


    async def sub_payment_reject_count(self, user_id: int) -> int:
        """FIX جدید: تعداد رد قبلی همین کاربر — سیگنال احتمال تخلف/سوءاستفاده برای ادمین"""
        return await self.sub_payments.count_documents(
            {'user_id': user_id, 'status': 'rejected'}
        )


    async def sub_payment_set_admin_msg(self, pid: str, msg_id: int):
        try:
            await self.sub_payments.update_one(
                {'_id': ObjectId(pid)}, {'$set': {'admin_msg_id': msg_id}}
            )
        except Exception:
            pass


    async def sub_payment_decide(self, pid: str, approved: bool, admin_id: int, note: str = ''):
        """تصمیم روی رسید — 🛡 AUDIT-A1: گذار **اتمیک** از `pending`.

        شرط `status: 'pending'` داخل خودِ update نوشته می‌شود، پس فقط یک
        فراخوانی می‌تواند سند را از pending خارج کند و `True` بگیرد؛ بقیه
        `False` می‌گیرند و موظف‌اند هیچ اثر جانبی (فعال‌سازی اشتراک،
        آزادسازی کد تخفیف، نوتیف) تولید نکنند.

        چرا لازم بود: مسیرهای وب/ربات «اول می‌خواندند بعد می‌نوشتند»
        (check-then-act) و دو تأیید هم‌زمان = دو بار `sub_activate(extend=True)`
        = دو دوره اشتراک به‌ازای یک رسید.
        """
        try:
            res = await self.sub_payments.update_one(
                {'_id': ObjectId(pid), 'status': 'pending'},
                {'$set': {
                    'status': 'approved' if approved else 'rejected',
                    'reviewed_by': admin_id, 'reviewed_at': utc_now_iso(),
                    'review_note': note,
                }}
            )
            return res.modified_count == 1
        except Exception as e:
            logger.warning(f"sub_payment_decide failed for {pid}: {e}")
            return False


    async def sub_payment_list_pending(self) -> list:
        return await self.sub_payments.find({'status': 'pending'}).sort('submitted_at', 1).to_list(100)


    async def sub_payment_history(self, user_id: int) -> list:
        """FIX جدید: تاریخچه‌ی کامل پرداخت‌های یک کاربر (هر وضعیتی) — برای «تاریخچه‌ی من»"""
        return await self.sub_payments.find({'user_id': user_id}).sort('submitted_at', -1).to_list(30)


    async def sub_payment_list_all(self, status: str = None, skip: int = 0, limit: int = 8, extra: dict = None) -> list:
        """FIX جدید: مرور کامل همه‌ی رسیدها (هر وضعیتی) با صفحه‌بندی — برای پنل ادمین
        extra: فیلتر اختیاری اضافه (مثل $or جست‌وجو) — کاملاً backward-compatible."""
        q = {'status': status} if status else {}
        if extra:
            q.update(extra)
        return await self.sub_payments.find(q).sort('submitted_at', -1).skip(skip).limit(limit).to_list(limit)


    async def sub_payment_count_all(self, status: str = None, extra: dict = None) -> int:
        q = {'status': status} if status else {}
        if extra:
            q.update(extra)
        return await self.sub_payments.count_documents(q)


    async def sub_list_by_status(self, status: str = 'active', skip: int = 0, limit: int = 10, extra: dict = None) -> list:
        """FIX جدید: لیست مشترکین بر اساس وضعیت — برای صفحه‌ی «لیست مشترکین» پنل ادمین
        extra: فیلتر اختیاری اضافه (مثل $or جست‌وجو) — کاملاً backward-compatible."""
        q = {'status': status}
        if extra:
            q.update(extra)
        return await self.subscriptions.find(q) \
            .sort('end_date', 1).skip(skip).limit(limit).to_list(limit)


    async def sub_count_by_status(self, status: str = 'active', extra: dict = None) -> int:
        q = {'status': status}
        if extra:
            q.update(extra)
        return await self.subscriptions.count_documents(q)
