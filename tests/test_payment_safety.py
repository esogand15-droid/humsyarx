# -*- coding: utf-8 -*-
"""💳 تست امنیتیِ درگاه پرداخت — «پرداخت جعلیِ موفق» نباید ممکن باشد.

چرا این تست حیاتی است
──────────────────────
در حالت **mock** هیچ پولی جابه‌جا نمی‌شود ولی `zarinpal_verify` نتیجهٔ
`ok=True` برمی‌گرداند. اگر این حالت در محیط تولید باز شود، هر کاربری
می‌تواند بدون پرداخت، اشتراک یا شارژ کیف پول بگیرد.

باگ اصلی (fail-open): تشخیص محیط با زنجیرهٔ
`RAILWAY_ENVIRONMENT_NAME → APP_ENV → ENVIRONMENT` و شرط
`env not in ("production","prod")` بود. اگر **هیچ‌کدام** ست نشده بود،
`env = ""` و شرط True می‌شد ⇒ mock باز. روی VPS با docker-compose
(که هیچ‌کدام را ست نمی‌کند) این سناریو واقعی است.

این تست هر دو جهت را قفل می‌کند:
  • محیط ناشناخته ⇒ mock **بسته** (fail-closed)
  • محیط توسعه‌ای اعلام‌شده یا `ZARINPAL_ALLOW_MOCK=1` ⇒ mock باز
  • مرچنت واقعی + authority جعلی TEST- ⇒ رد می‌شود
"""
from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch

_ENV_KEYS = ("ZARINPAL_ALLOW_MOCK", "APP_ENV", "ENVIRONMENT",
             "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT")


def _reload_zarinpal():
    """ماژول را با محیط تمیز دوباره بارگذاری می‌کند."""
    import payments.zarinpal as zp
    return importlib.reload(zp)


class _EnvIsolated(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in _ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class MockPaymentGuardTests(_EnvIsolated):
    def test_unknown_environment_denies_mock(self):
        """قلبِ اصلاح: بدون هیچ متغیر محیطی، mock ممنوع است."""
        zp = _reload_zarinpal()
        self.assertFalse(
            zp._mock_allowed(),
            "محیط ناشناخته باید mock را ببندد (fail-closed)؛ وگرنه روی VPS "
            "بدون APP_ENV، هر پرداخت «موفق» گزارش می‌شود.")

    def test_production_denies_mock(self):
        for key in ("APP_ENV", "ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME"):
            with self.subTest(key=key):
                zp = _reload_zarinpal()
                with patch.dict(os.environ, {key: "production"}):
                    self.assertFalse(zp._mock_allowed())

    def test_explicit_flag_allows_mock(self):
        zp = _reload_zarinpal()
        for value in ("1", "true", "yes", "on"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"ZARINPAL_ALLOW_MOCK": value}):
                    self.assertTrue(zp._mock_allowed())

    def test_explicit_flag_denies_mock_even_in_dev(self):
        zp = _reload_zarinpal()
        with patch.dict(os.environ, {"APP_ENV": "development",
                                     "ZARINPAL_ALLOW_MOCK": "0"}):
            self.assertFalse(zp._mock_allowed())

    def test_declared_dev_environment_allows_mock(self):
        zp = _reload_zarinpal()
        for env in ("development", "dev", "local", "test", "staging"):
            with self.subTest(env=env):
                with patch.dict(os.environ, {"APP_ENV": env}):
                    self.assertTrue(zp._mock_allowed())

    def test_production_beats_dev_flag_in_other_var(self):
        """اگر یکی از متغیرها production باشد، mock بسته است."""
        zp = _reload_zarinpal()
        with patch.dict(os.environ, {"APP_ENV": "production",
                                     "RAILWAY_ENVIRONMENT_NAME": "dev"}):
            self.assertFalse(zp._mock_allowed())


class VerifyGuardTests(_EnvIsolated):
    """`zarinpal_verify` نباید در تولید، پرداخت جعلی را تأیید کند."""

    def setUp(self):
        super().setUp()
        self.zp = _reload_zarinpal()

    def _cfg_patch(self, merchant_id: str):
        async def _fake_cfg():
            return {"merchant_id": merchant_id, "sandbox": bool(not merchant_id),
                    "callback_base": "https://example.test/verify", "enabled": True}
        return patch.object(self.zp, "_get_cfg", _fake_cfg)

    def test_mock_authority_rejected_with_live_merchant(self):
        async def run():
            with self._cfg_patch("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"):
                return await self.zp.zarinpal_verify("TEST-DEADBEEF", 100000)

        res = unittest.IsolatedAsyncioTestCase().run  # noqa: F841 (نمادسازی)
        import asyncio
        out = asyncio.run(run())
        self.assertFalse(out["ok"])
        self.assertEqual(out["code"], -99)

    def test_mock_verify_blocked_when_environment_unknown(self):
        async def run():
            # مرچنت خالی ⇒ mock؛ محیط ناشناخته ⇒ باید رد شود
            with self._cfg_patch(""):
                return await self.zp.zarinpal_verify("TEST-ABC", 100000)

        import asyncio
        out = asyncio.run(run())
        self.assertFalse(
            out["ok"],
            "در محیط ناشناخته، verifyِ mock نباید موفق شود (fail-closed).")
        self.assertEqual(out["code"], -98)

    def test_mock_verify_allowed_in_declared_dev(self):
        async def run():
            with self._cfg_patch(""):
                return await self.zp.zarinpal_verify("TEST-ABC", 100000)

        import asyncio
        with patch.dict(os.environ, {"APP_ENV": "development"}):
            out = asyncio.run(run())
        self.assertTrue(out["ok"])
        self.assertTrue(out["mock"])


class PublicStatusTests(_EnvIsolated):
    def test_online_pay_disabled_when_mock_not_allowed(self):
        """در تولیدِ بدون مرچنت، وضعیت عمومی باید پرداخت آنلاین را خاموش اعلام کند."""
        zp = _reload_zarinpal()

        async def _fake_cfg():
            return {"merchant_id": "", "sandbox": True,
                    "callback_base": "https://example.test/verify", "enabled": True}

        import asyncio
        with patch.object(zp, "_get_cfg", _fake_cfg):
            status = asyncio.run(zp.gateway_public_status())
        self.assertFalse(status["online_pay_enabled"])
        self.assertTrue(status["mock"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
