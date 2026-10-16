# -*- coding: utf-8 -*-
"""🧪 تست قرارداد داده (فاز ۵ ماموریت تکمیل) — هم‌خوانی enum بین لایه‌ها.

قرارداد مرجع: docs/DATA_CONTRACT.md §۴
تست static است (بدون DB) — مقایسه‌ی enumهای نوشته‌شده در بک‌اند
با جدول برچسب فارسی پنل/مینی‌اپ. اگر مقدار جدیدی اضافه شود بدون
برچسب، این تست شکست می‌خورد تا قرارداد بشکند.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def read(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8', errors='replace').read()


def payment_statuses_in_backend():
    """وضعیت‌های پرداخت که DAL پرداخت (finance.py) می‌نویسد — فقط
    literalهای نزدیک به sub_payments (نوشتن/فیلتر سند پرداخت)."""
    statuses = set()
    src = read('db/finance.py')
    # نوشتن وضعیت روی سند پرداخت
    for m in re.finditer(r"['\"]status['\"]\s*:\s*['\"](\w+)['\"]", src):
        statuses.add(m.group(1))
    # فیلتر/مقایسه روی sub_payments
    for m in re.finditer(r"sub_payments\.(?:count_documents|find|find_one|update_one)"
                         r"\(\s*\{[^}]*['\"]status['\"]\s*:\s*['\"](\w+)['\"]", src):
        statuses.add(m.group(1))
    # عملگرهای شرطی روی وضعیت پرداخت
    for m in re.finditer(r"\.get\(['\"]status['\"]\)\s*==\s*['\"](\w+)['\"]", src):
        statuses.add(m.group(1))
    return statuses


def pay_status_fa_keys():
    src = read('webadmin/src/pages/Subscriptions.jsx')
    m = re.search(r'const PAY_STATUS_FA = \{([^}]*)\}', src)
    assert m, 'PAY_STATUS_FA در Subscriptions.jsx پیدا نشد'
    return set(re.findall(r'(\w+)\s*:', m.group(1)))


class TestPaymentStatusContract(unittest.TestCase):
    """DATA_CONTRACT §۴.۱ — نویسنده: db/finance.py؛ برچسب: پنل."""

    CONTRACT = {'pending', 'approved', 'rejected', 'zarinpal_pending',
                'cancelled', 'refunded'}

    # وضعیت‌های «سند دیگر» که در همان فایل DAL نوشته می‌شوند و عمداً
    # خارج از قرارداد §۴.۱ (پرداخت) هستند:
    #  - subscriptions.status: active/expired/revoked (قرارداد اشتراک)
    #  - notif_runs.status: sending/… (قرارداد ارسال)
    OTHER_DOCS = {'active', 'expired', 'revoked', 'sending', 'completed',
                  'failed', 'cancelled_draft'}

    def test_backend_statuses_are_in_contract(self):
        written = payment_statuses_in_backend()
        unknown = written - self.CONTRACT - self.OTHER_DOCS
        self.assertFalse(
            unknown,
            f'وضعیت پرداخت خارج از قرارداد نوشته می‌شود: {unknown} — '
            f'اول DATA_CONTRACT §۴.۱ و PAY_STATUS_FA را به‌روز کن')

    def test_panel_labels_cover_contract(self):
        labels = pay_status_fa_keys()
        self.assertEqual(
            labels, self.CONTRACT,
            f'کلیدهای PAY_STATUS_FA ({labels}) با قرارداد ({self.CONTRACT}) '
            f'فرق دارد — مقدار بدون برچسب با enum انگلیسی خام نمایش داده می‌شود')

    def test_no_dead_status_labels(self):
        # EN-01: failed هرگز نوشته نمی‌شود — نباید برچسب مرده برگردد
        self.assertNotIn('failed', pay_status_fa_keys())


class TestQuestionStatusContract(unittest.TestCase):
    """DATA_CONTRACT §۴.۲."""

    CONTRACT = {'pending', 'approved', 'rejected', 'needs_changes'}

    def test_panel_labels_cover_contract(self):
        src = read('webadmin/src/pages/Questions.jsx')
        m = re.search(r'pending:\s*\[[^\]]*\],\s*approved:\s*\[[^\]]*\],\s*'
                      r'rejected:\s*\[[^\]]*\],\s*needs_changes:\s*\[[^\]]*\]', src)
        for status in self.CONTRACT:
            self.assertIn(
                f'{status}:', src,
                f'برچسب وضعیت سؤال «{status}» در Questions.jsx نیست')


class TestTicketStatusContract(unittest.TestCase):
    """DATA_CONTRACT §۴.۳."""

    CONTRACT = {'open', 'in_progress', 'waiting_user', 'resolved',
                'answered', 'closed'}

    def test_panel_labels_cover_contract(self):
        src = read('webadmin/src/pages/Tickets.jsx')
        for status in self.CONTRACT:
            self.assertIn(
                f'{status}:', src,
                f'برچسب وضعیت تیکت «{status}» در Tickets.jsx نیست')

    def test_backend_ticket_statuses_in_contract(self):
        """شش وضعیت قرارداد باید در DAL تیکت واقعاً نوشته/فیلتر شوند."""
        src = read('db/core.py')
        for status in self.CONTRACT:
            self.assertIn(f"'{status}'", src,
                          f'وضعیت تیکت «{status}» در DAL (db/core.py) نیست')


class TestAIPracticeContract(unittest.TestCase):
    """DATA_CONTRACT §۴.۴ — EP-01: قرارداد سؤال هوشمند miniapp↔server."""

    def test_miniapp_wired_to_ai_practice(self):
        """کلاینت باید هر سه مسیر generate/answer/propose را صدا بزند."""
        src = read('miniapp/src/pages/Learn/Questions.jsx')
        self.assertIn('/api/questions/practice/ai/generate', src,
                      'EP-01: miniapp مسیر generate را صدا نمی‌زند')
        self.assertIn('/practice/ai/${questionId}/answer', src,
                      'EP-01: miniapp مسیر answer را صدا نمی‌زند')
        self.assertIn('/practice/ai/${result.ai_question_id}/propose', src,
                      'EP-01: miniapp مسیر propose را صدا نمی‌زند')

    def test_ai_practice_statuses_in_contract(self):
        src = read('question_bank/ai_practice.py')
        for status in ('ready', 'answered'):
            self.assertIn(f'"status": "{status}"', src,
                          f'وضعیت سؤال هوشمند «{status}» در سرویس نیست')
        self.assertIn('quality_status', src)


class TestSettingsVaultContract(unittest.TestCase):
    """DATA_CONTRACT §۶ — ST-02: کلید AI از vault خوانده می‌شود."""

    def test_vault_reader_exists(self):
        src = read('ai_solver.py')
        self.assertIn("def _load_vault", src)
        self.assertIn("raw.get('ai_api_keys'", src,
                      'خواندن ai_api_keys باید از _load_vault بگذرد')


if __name__ == '__main__':
    unittest.main()
