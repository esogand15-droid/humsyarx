# -*- coding: utf-8 -*-
"""🧪 خط‌مبِ سطح API — گاردِ رگرسیونِ مسیرها (زنده‌سازی گاردِ مرده).

پیشینه
──────
`api/main.py` از مدت‌ها پیش `_ROUTE_BASELINE` را دارد و در
`/api/health/deep` گزارش می‌کند، ولی کامنت خودش می‌گوید «هیچ تستی
routes_match_baseline را نمی‌خواند» و به `tests/test_route_inventory.py`
ارجاع می‌داد که **در مخزن وجود نداشت**. نتیجه: عدد خط‌مب ۵۰۱ مانده بود
در حالی که واقعیت ۷۱۹ بود ⇒ هشدار دائمیِ کاذب در health و صفر محافظت.

این تست همان قرارداد را زنده می‌کند:
  • تعداد عملیات OpenAPI زیر /api نباید بی‌خبر عوض شود.
  • هیچ (method, path) تکراری نباید ثبت شود.

اگر تغییری **عمدی** در سطح API دادی، عدد را در `api/main.py`
(`_ROUTE_BASELINE`) و همین‌جا با هم به‌روز کن.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017/humsyar_test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("TELEGRAM_TOKEN", "123:TEST")

#: خط‌مب — با هر تغییر عمدی در سطح API آگاهانه به‌روز شود
EXPECTED_OPENAPI_OPERATIONS = 719
EXPECTED_ROUTE_OBJECTS = 726


def _load_app():
    try:
        import api.main as m
    except Exception as exc:                       # noqa: BLE001
        return None, exc
    return m, None


class RouteInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main, cls.err = _load_app()
        if cls.main is None:
            raise unittest.SkipTest(f"api.main قابل بارگذاری نبود: {cls.err}")

    def test_openapi_operation_count_matches_baseline(self):
        stats = self.main._count_api_operations()
        self.assertEqual(
            stats["openapi_operations"], EXPECTED_OPENAPI_OPERATIONS,
            "سطح API عوض شده است. اگر عمدی است: _ROUTE_BASELINE در "
            "api/main.py و EXPECTED_OPENAPI_OPERATIONS در این تست را "
            "هم‌زمان به‌روز کن. "
            f"واقعی={stats['openapi_operations']} "
            f"انتظار={EXPECTED_OPENAPI_OPERATIONS}",
        )

    def test_route_objects_match_baseline(self):
        stats = self.main._count_api_operations()
        self.assertEqual(
            stats["api_route_objects"], EXPECTED_ROUTE_OBJECTS,
            "تعداد route object زیر /api عوض شده است. "
            f"واقعی={stats['api_route_objects']} انتظار={EXPECTED_ROUTE_OBJECTS}",
        )

    def test_health_baseline_flag_is_not_stale(self):
        """گارد داخلی health نباید همیشه False باشد."""
        stats = self.main._count_api_operations()
        self.assertTrue(
            stats["routes_match_baseline"],
            "routes_match_baseline=False یعنی _ROUTE_BASELINE در api/main.py "
            f"کهنه است (خط‌مب={stats['baseline_expected']}، "
            f"واقعی={stats['openapi_operations']}).",
        )

    def test_no_duplicate_method_path(self):
        ops = [(m, p) for m, p in self.main._walk_included_routes(self.main.app.routes)
               if p.startswith("/api")]
        seen, dupes = set(), []
        for item in ops:
            if item in seen:
                dupes.append(item)
            seen.add(item)
        self.assertEqual(dupes, [], f"مسیر تکراری ثبت شده است: {dupes[:10]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
