# -*- coding: utf-8 -*-
"""
💰 HUMSYAR — WALLET SUBSYSTEM (🌊 W6)

کیف پول داخلی = یک زیرسیستم مالی واقعی، نه یک عدد روی User:

    Wallet Ledger (wallet_transactions)  ←  منبع حقیقت مالی
              ↓
    Cached Balance (wallets.balance)     ←  بهینه‌سازی عملکرد

قوانین حسابداری (همه با شواهد معماری موجود هماهنگ‌اند):
- مبالغ integer و به «تومان» — همان واحد sub_payments (بدون float).
- هر تغییر موجودی یک تراکنش مستقل و **تغییرناپذیر** است؛ اصلاح فقط با
  compensating transaction (type='reversal')، هرگز overwrite.
- Idempotency با unique index روی (reference_type, reference_id):
  دابل‌کلیک/ری‌تری = یک اثر اقتصادی.
- الگوی insert-first: اول تراکنش `pending` با کلید یکتا درج می‌شود، بعد
  موجودی اتمیک اعمال می‌شود، بعد تراکنش `ok` می‌شود. کرش بین مراحل =
  تراکنش pendingِ قابل‌شناسایی در مغایرت‌گیری، نه اثر اقتصادی دوباره.
- Debit اتمیک و شرطی: `balance >= amount` داخل خودِ update — دو خرید
  هم‌زمان روی موجودی یکسان، فقط یکی برنده می‌شود.
- Ledger هرگز حذف نمی‌شود (data retention مالی).

استاندارد پول: تومان (int) — یکسان در Bot / Mini App / Web Admin / API.
"""
import logging
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from time_utils import utc_now_iso

logger = logging.getLogger('database')

# واحد پول سراسری — از معماری موجود استخراج شده (plan.price تومان int است)
WALLET_CURRENCY = 'تومان'

# انواع تراکنش — فقط آنچه واقعاً لازم است
TX_REFUND_CREDIT = 'refund_credit'
TX_SUB_PURCHASE = 'subscription_purchase'
TX_ADMIN_CREDIT = 'admin_credit'
TX_ADMIN_DEBIT = 'admin_debit'
TX_REVERSAL = 'reversal'

_TX_LABELS = {
    TX_REFUND_CREDIT: 'بازگشت وجه',
    TX_SUB_PURCHASE: 'خرید اشتراک با کیف پول',
    TX_ADMIN_CREDIT: 'افزایش موجودی توسط ادمین',
    TX_ADMIN_DEBIT: 'کسر موجودی توسط ادمین',
    TX_REVERSAL: 'اصلاح مالی (جبران تراکنش قبلی)',
}

# عمر آستانه‌ی تراکنش pending برای پرچم‌خوردن در مغایرت‌گیری (ثانیه)
_STUCK_PENDING_SECONDS = 600


class WalletError(ValueError):
    """خطای مالی کیف پول با کد ماشین‌خوان + پیام فارسی برای کاربر."""

    def __init__(self, code: str, message: str = ''):
        self.code = code
        super().__init__(message or code)


class DBWallet:
    """Mixin کیف پول — همان الگوی DBFinance (بدون سیستم مالی موازی)."""

    # ── پروویژن ────────────────────────────────────────────────
    async def wallet_get_or_create(self, user_id: int) -> dict:
        """کیف پول یکتا per کاربر، idempotent و امن زیر هم‌زمانی:
        unique index روی user_id + گرفتن DuplicateKeyError و خواندن مجدد."""
        user_id = int(user_id)
        w = await self.wallets.find_one({'user_id': user_id})
        if w:
            return w
        try:
            await self.wallets.insert_one({
                'user_id': user_id, 'balance': 0,
                'currency': WALLET_CURRENCY,
                'created_at': utc_now_iso(), 'updated_at': utc_now_iso()})
        except DuplicateKeyError:
            pass  # request هم‌زمان ساخت — همان یک wallet معتبر است
        w = await self.wallets.find_one({'user_id': user_id})
        if not w:
            raise WalletError('wallet_provision_failed',
                              'ساخت کیف پول ممکن نشد')
        return w

    # ── هسته‌ی ledger ──────────────────────────────────────────
    async def _wallet_tx_insert_pending(self, user_id, amount, tx_type,
                                        ref_type, ref_id, actor_id, label):
        """درج تراکنش pending با کلید یکتا (ref_type, ref_id).
        خروجی: (tx_dict, is_new). is_new=False یعنی قبلاً ثبت شده (ری‌تری)."""
        doc = {
            'user_id': int(user_id), 'type': tx_type,
            'direction': 'credit' if tx_type in (
                TX_REFUND_CREDIT, TX_ADMIN_CREDIT, TX_REVERSAL) else 'debit',
            'amount': int(amount), 'currency': WALLET_CURRENCY,
            'reference_type': ref_type, 'reference_id': str(ref_id),
            'balance_before': None, 'balance_after': None,
            'label': (label or _TX_LABELS.get(tx_type, tx_type))[:120],
            'actor_id': int(actor_id or 0),
            'status': 'pending', 'created_at': utc_now_iso(),
        }
        try:
            r = await self.wallet_transactions.insert_one(doc)
            doc['_id'] = r.inserted_id
            return doc, True
        except DuplicateKeyError:
            existing = await self.wallet_transactions.find_one(
                {'reference_type': ref_type, 'reference_id': str(ref_id)})
            if not existing:
                raise WalletError('tx_key_conflict',
                                  'کلید تراکنش مالی تکراری است')
            return existing, False

    async def _wallet_apply(self, wallet, tx, delta: int) -> dict:
        """اعمال اتمیک delta روی موجودی + ثبت before/after روی تراکنش.
        برای debit از شرط `balance >= amount` در خودِ query استفاده می‌شود؛
        اگر شرط نگرفت، تراکنش `failed` می‌شود و WalletError برمی‌گردانیم
        (موجودی دست‌نخورده می‌ماند)."""
        if delta < 0:
            updated = await self.wallets.find_one_and_update(
                {'_id': wallet['_id'], 'balance': {'$gte': -delta}},
                {'$inc': {'balance': delta},
                 '$set': {'updated_at': utc_now_iso()}})
            if updated is None:
                await self.wallet_transactions.update_one(
                    {'_id': tx['_id'], 'status': 'pending'},
                    {'$set': {'status': 'failed',
                              'fail_reason': 'insufficient_balance'}})
                w = await self.wallets.find_one({'_id': wallet['_id']})
                raise WalletError(
                    'insufficient_balance',
                    'موجودی کیف پول کافی نیست'
                    f' (موجودی: {int((w or {}).get("balance", 0)):,} تومان)')
            balance_before = int(updated['balance'])
        else:
            updated = await self.wallets.find_one_and_update(
                {'_id': wallet['_id']},
                {'$inc': {'balance': delta},
                 '$set': {'updated_at': utc_now_iso()}})
            balance_before = int((updated or {}).get('balance', 0))
        balance_after = balance_before + delta
        await self.wallet_transactions.update_one(
            {'_id': tx['_id']},
            {'$set': {'status': 'ok', 'balance_before': balance_before,
                      'balance_after': balance_after}})
        tx.update({'status': 'ok', 'balance_before': balance_before,
                   'balance_after': balance_after})
        return tx

    async def wallet_credit(self, user_id: int, amount: int, tx_type: str,
                            ref_type: str, ref_id, actor_id: int,
                            label: str = '') -> dict:
        """اعتبار کیف پول — idempotent بر اساس (ref_type, ref_id)."""
        amount = int(amount)
        if amount <= 0:
            raise WalletError('invalid_amount', 'مبلغ باید مثبت باشد')
        tx, is_new = await self._wallet_tx_insert_pending(
            user_id, amount, tx_type, ref_type, ref_id, actor_id, label)
        if not is_new:
            return tx  # ری‌تری/دابل‌کلیک → همان اثر قبلی، بدون اعتبار دوم
        wallet = await self.wallet_get_or_create(user_id)
        return await self._wallet_apply(wallet, tx, amount)

    async def wallet_debit(self, user_id: int, amount: int, tx_type: str,
                           ref_type: str, ref_id, actor_id: int,
                           label: str = '') -> dict:
        """کسر از کیف پول — اتمیک، شرطی (بدون موجودی منفی) و idempotent."""
        amount = int(amount)
        if amount <= 0:
            raise WalletError('invalid_amount', 'مبلغ باید مثبت باشد')
        tx, is_new = await self._wallet_tx_insert_pending(
            user_id, amount, tx_type, ref_type, ref_id, actor_id, label)
        if not is_new:
            return tx
        wallet = await self.wallet_get_or_create(user_id)
        return await self._wallet_apply(wallet, tx, -amount)

    # ── خواندن ─────────────────────────────────────────────────
    async def wallet_tx_list(self, user_id: int, skip: int = 0,
                             limit: int = 20) -> list:
        limit = max(1, min(int(limit), 50))
        return await self.wallet_transactions.find(
            {'user_id': int(user_id), 'status': 'ok'}
        ).sort('created_at', -1).skip(max(0, int(skip))).limit(limit).to_list(limit)

    async def wallet_tx_count(self, user_id: int) -> int:
        return await self.wallet_transactions.count_documents(
            {'user_id': int(user_id), 'status': 'ok'})

    async def wallet_summary(self, user_id: int) -> dict:
        """خلاصه‌ی کیف پول یک کاربر — همه از بک‌اند (client هیچ‌وقت
        موجودی را تعیین نمی‌کند)."""
        w = await self.wallet_get_or_create(user_id)
        agg = {'credit': 0, 'debit': 0}
        async for row in self.wallet_transactions.aggregate([
                {'$match': {'user_id': int(user_id), 'status': 'ok'}},
                {'$group': {'_id': '$direction',
                            'total': {'$sum': '$amount'}}}]):
            agg[row['_id']] = int(row['total'])
        last = await self.wallet_transactions.find_one(
            {'user_id': int(user_id), 'status': 'ok'},
            sort=[('created_at', -1)])
        return {'user_id': int(user_id),
                'balance': int(w.get('balance', 0)),
                'currency': WALLET_CURRENCY,
                'credits_total': agg['credit'], 'debits_total': agg['debit'],
                'last_tx': ({'id': str(last['_id']),
                             'label': last.get('label'),
                             'amount': last.get('amount'),
                             'direction': last.get('direction'),
                             'at': last.get('created_at')} if last else None),
                'created_at': w.get('created_at')}

    async def wallet_stats_global(self) -> dict:
        """آمار سراسری برای مرکز مالی ادمین (aggregate، نه اسکن)."""
        totals = {'wallets': 0, 'balance': 0}
        async for row in self.wallets.aggregate([
                {'$group': {'_id': None, 'n': {'$sum': 1},
                            'b': {'$sum': '$balance'}}}]):
            totals = {'wallets': int(row['n']), 'balance': int(row['b'])}
        by_type = {}
        async for row in self.wallet_transactions.aggregate([
                {'$match': {'status': 'ok'}},
                {'$group': {'_id': {'t': '$type', 'd': '$direction'},
                            'n': {'$sum': 1},
                            'total': {'$sum': '$amount'}}}]):
            key = row['_id']['t'] or 'unknown'
            cur = by_type.setdefault(key, {'count': 0, 'total': 0})
            cur['count'] += int(row['n'])
            cur['total'] += int(row['total'])
        return {**totals, 'by_type': by_type}

    async def wallet_get_for_user_id(self, user_id: int):
        return await self.wallets.find_one({'user_id': int(user_id)})

    # ── مغایرت‌گیری کیف پول ────────────────────────────────────
    async def wallet_reconcile_items(self, limit: int = 50) -> list:
        """مغایرت‌های بحرانی کیف پول — human-readable در لایه‌ی ادمین:
        ۱) balance کش‌شده ≠ جمع ledger (اختلاف حسابداری)
        ۲) بازگشت وجه انجام‌شده بدون اعتبار کیف پول
        ۳) کسر کیف پول بدون رسید تأییدشده
        ۴) تراکنش pending گیرکرده (کرش بین مراحل)"""
        items = []
        # ۱) ledger sum vs cached balance
        ledger_sums = {}
        async for row in self.wallet_transactions.aggregate([
                {'$match': {'status': 'ok'}},
                {'$group': {'_id': '$user_id',
                            's': {'$sum': {'$cond': [
                                {'$eq': ['$direction', 'credit']},
                                '$amount', {'$multiply': ['$amount', -1]}]}}}}]):
            ledger_sums[int(row['_id'])] = int(row['s'])
        async for w in self.wallets.find({}).limit(2000):
            uid = int(w['user_id'])
            bal = int(w.get('balance', 0))
            ledger = ledger_sums.get(uid, 0)
            if bal != ledger:
                items.append({'type': 'wallet_balance_mismatch',
                              'severity': 'critical', 'user_id': uid,
                              'amount': bal - ledger, 'balance': bal,
                              'ledger': ledger, 'at': w.get('updated_at')})
        # ۲) refunded payment without wallet credit
        credited_refs = {
            t['reference_id'] async for t in self.wallet_transactions.find(
                {'reference_type': 'sub_payment_refund',
                 'status': 'ok'}, {'reference_id': 1})}
        async for p in self.sub_payments.find(
                {'status': 'refunded'}).sort('refunded_at', -1).limit(200):
            if str(p['_id']) not in credited_refs:
                items.append({'type': 'refund_without_wallet_credit',
                              'severity': 'critical',
                              'user_id': int(p.get('user_id') or 0),
                              'payment_id': str(p['_id']),
                              'amount': int(p.get('final_price')
                                            or p.get('amount') or 0),
                              'at': p.get('refunded_at')})
        # ۳) wallet debit without approved payment
        async for t in self.wallet_transactions.find(
                {'reference_type': 'sub_payment_wallet',
                 'status': 'ok'}).sort('created_at', -1).limit(200):
            pid = t['reference_id']
            try:
                p = await self.sub_payments.find_one({'_id': ObjectId(pid)})
            except Exception:
                p = None
            if not p or p.get('status') not in ('approved', 'refunded'):
                items.append({'type': 'wallet_debit_without_payment',
                              'severity': 'critical',
                              'user_id': int(t.get('user_id') or 0),
                              'payment_id': pid, 'amount': int(t['amount']),
                              'at': t.get('created_at')})
        # ۴) stuck pending tx (crash recovery)
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(seconds=_STUCK_PENDING_SECONDS)).isoformat()
        async for t in self.wallet_transactions.find(
                {'status': 'pending',
                 'created_at': {'$lt': cutoff}}).limit(50):
            items.append({'type': 'wallet_tx_stuck_pending',
                          'severity': 'warning',
                          'user_id': int(t.get('user_id') or 0),
                          'tx_id': str(t['_id']), 'amount': int(t['amount']),
                          'at': t.get('created_at')})
        return items[:limit]

    # ── خرید اشتراک با کیف پول (لایه‌ی db — سرویس واحد) ────────
    async def sub_payment_create_wallet(self, user_id: int, plan_id: str,
                                        plan_name: str, price: int,
                                        idem_key: str = '') -> str:
        """رسید خرید کیف‌پولی روی همان sub_payments — مسیر موازی نیست.
        status='wallet_processing' تا debit اتمیک تأیید شود؛ در صف رسیدهای
        دستی (pending) ظاهر نمی‌شود."""
        if idem_key:
            existing = await self.sub_payments.find_one(
                {'idem_key': idem_key}, {'_id': 1})
            if existing:
                return str(existing['_id'])
        doc = {
            'user_id': int(user_id), 'plan_id': plan_id,
            'plan_name': plan_name, 'price': int(price),
            'final_price': int(price), 'discount_code': None,
            'discount_percent': None, 'screenshot_file_id': None,
            'method': 'wallet', 'status': 'wallet_processing',
            'submitted_at': utc_now_iso(), 'admin_msg_id': None,
        }
        if idem_key:
            doc['idem_key'] = idem_key
        try:
            r = await self.sub_payments.insert_one(doc)
            return str(r.inserted_id)
        except DuplicateKeyError:  # race روی idem_key یکتا
            existing = await self.sub_payments.find_one(
                {'idem_key': idem_key}, {'_id': 1})
            if existing:
                return str(existing['_id'])
            raise

    async def wallet_purchase_finalize(self, pid: str) -> bool:
        """CAS اتمیک wallet_processing→approved — فقط یک بار موفق می‌شود."""
        try:
            res = await self.sub_payments.update_one(
                {'_id': ObjectId(pid), 'status': 'wallet_processing'},
                {'$set': {'status': 'approved', 'reviewed_by': 0,
                          'reviewed_at': utc_now_iso(),
                          'review_note': 'پرداخت از کیف پول داخلی'}})
            return res.modified_count == 1
        except Exception as e:
            logger.warning(f'wallet_purchase_finalize failed {pid}: {e}')
            return False

    # ── سرویس واحد خرید با کیف پول (API و Bot مشترک) ───────────
    async def wallet_purchase(self, user_id: int, plan_id: str,
                              idem_key: str = '') -> dict:
        """🌊 W6 — تنها منطق خرید با کیف پول؛ Bot و MiniApp/Web API هر دو
        همین را صدا می‌زنند (منطق موازی ممنوع).

        order (sub_payments, method=wallet) → debit اتمیک شرطی →
        CAS اتمیک → همان سرویس فعال‌سازیِ تأیید رسید (finalize_approved_payment).

        خطاها WalletError با کد ماشین‌خوان هستند:
        plan_not_found / plan_price_invalid / insufficient_balance /
        order_conflict / plan_days_invalid (با جبران reversal)."""
        user_id = int(user_id)
        plan = await self.sub_plan_get(plan_id)
        if not plan or not plan.get('active'):
            raise WalletError('plan_not_found', 'پلن پیدا نشد')
        price = int(plan.get('price') or 0)
        if price <= 0:
            raise WalletError('plan_price_invalid', 'قیمت پلن نامعتبر است')
        idem = (idem_key or '').strip()[:64]
        pid = await self.sub_payment_create_wallet(
            user_id, str(plan['_id']), plan.get('name', 'اشتراک'), price, idem)
        # ری‌تری با idem یکسان و سفارشِ کامل‌شده → همان نتیجه، بدون اثر دوم
        existing = await self.sub_payment_get(pid)
        if existing and existing.get('status') == 'approved' \
                and existing.get('method') == 'wallet':
            sub = await self.sub_get(user_id)
            return {'payment_id': pid, 'plan_name': plan.get('name'),
                    'amount': price, 'replay': True,
                    'end_date': (sub or {}).get('end_date')}
        try:
            await self.wallet_debit(
                user_id, price, TX_SUB_PURCHASE, 'sub_payment_wallet',
                pid, user_id, f"خرید اشتراک {plan.get('name', '')} با کیف پول")
        except WalletError as e:
            if e.code == 'insufficient_balance':
                await self.sub_payments.update_one(
                    {'_id': ObjectId(pid), 'status': 'wallet_processing'},
                    {'$set': {'status': 'rejected',
                              'review_note': 'موجودی کیف پول کافی نبود'}})
            raise
        if not await self.wallet_purchase_finalize(pid):
            existing = await self.sub_payment_get(pid)
            if not existing or existing.get('status') != 'approved':
                raise WalletError('order_conflict',
                                  'سفارش در حال پردازش است یا بسته شده')
        payment = await self.sub_payment_get(pid)
        try:
            act = await self.finalize_approved_payment(payment, admin_id=user_id)
        except ValueError:
            # جبران مالی صریح: مبلغ با compensating transaction برمی‌گردد
            await self.wallet_credit(
                user_id, price, TX_REVERSAL, 'sub_payment_wallet_reversal',
                pid, 0, 'بازگشت مبلغ به دلیل خطای فعال‌سازی')
            await self.sub_payments.update_one(
                {'_id': ObjectId(pid)},
                {'$set': {'status': 'rejected',
                          'review_note': 'خطای فعال‌سازی — مبلغ به کیف پول برگشت'}})
            raise WalletError('plan_days_invalid',
                              'پلن معتبر نیست؛ مبلغ به کیف پول شما برگشت')
        return {'payment_id': pid, 'plan_name': plan.get('name'),
                'amount': price, 'end_date': act.get('end_date'),
                'days': act.get('days'), 'replay': False}
