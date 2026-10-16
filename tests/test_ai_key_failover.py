# -*- coding: utf-8 -*-
"""⭐ م7 — فال‌بک چند-کلیدی هوشیار (Key Failover) — تست‌های واحد.

سنجه‌ها:
  ۱) نرمال‌سازی Vault: رشته‌ی قدیمی/لیست/ترکیبی → {provider: [keys]}
  ۲) افزودن/حذف/فهرست کلید + سازگاری get_ai_config (api_key_list و …)
  ۳) طبقه‌بندی خطاها: چه خطایی چرخش می‌آورد و چه خطایی نه
  ۴) ordered_keys: رد شدن از کلیدِ cooldown و ترتیبِ نزدیک‌ترین انقضا
  ۵) run_with_key_failover: موفقیت با کلید دوم + خطای غیرچرخش‌پذیر فوری
  ۶) ask_ai_stream: 429 روی کلید اول → پاسخ کامل با کلید دوم
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('MONGODB_URI', 'mongodb://localhost:27017/test_fallback')

import _rtloop
import ai_solver
from ai_solver import (
    AIQuotaError, AIConfigError, AIError, AiImageError,
    _load_vault, ordered_keys, classify_key_error,
    mark_key_failed, mark_key_ok, key_cooldown_remaining,
    run_with_key_failover, masked_key, key_status_summary,
    set_api_key_for_provider, add_api_key_for_provider,
    remove_api_key_for_provider, list_api_keys_for_provider,
    get_ai_config,
)

K1 = 'AIza_test_key_1111'
K2 = 'AIza_test_key_2222'
K3 = 'sk-or_test_key_33'


class _FakeSettingsDB:
    """db فقط با ذخیره‌سازی تنظیمات — برای توابعِ Vault."""

    def __init__(self):
        self.settings = {}

    async def get_settings_by_prefix(self, prefix):
        return {k: v for k, v in self.settings.items() if k.startswith(prefix)}

    async def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    async def set_setting(self, key, value):
        self.settings[key] = value


class VaultNormalizeTests(unittest.TestCase):
    """۱) نرمال‌سازی — رشته‌ی قدیمی، لیست، ترکیبی، تکراری."""

    def test_legacy_string_becomes_list(self):
        v = _load_vault({'ai_api_keys': '{"gemini": "%s"}' % K1})
        self.assertEqual(v.get('gemini'), [K1])

    def test_list_passes_through_deduped(self):
        import json
        raw = {'ai_api_keys': json.dumps({'gemini': [K1, K2, K1]})}
        v = _load_vault(raw)
        self.assertEqual(v.get('gemini'), [K1, K2])

    def test_mixed_string_and_list(self):
        import json
        raw = {'ai_api_keys': json.dumps({'gemini': [K1, K2], 'groq': K3})}
        v = _load_vault(raw)
        self.assertEqual(v.get('gemini'), [K1, K2])
        self.assertEqual(v.get('groq'), [K3])

    def test_legacy_single_key_field(self):
        v = _load_vault({'ai_provider': 'gemini', 'ai_api_key': K1})
        self.assertEqual(v.get('gemini'), [K1])

    def test_dirty_key_cleaned(self):
        v = _load_vault({'ai_api_keys': '{"gemini": " %s\\u200f "}' % K1})
        self.assertEqual(v.get('gemini'), [K1])


class KeyStateTests(unittest.TestCase):
    """۳+۴) طبقه‌بندی خطا + cooldown + ترتیب."""

    def setUp(self):
        ai_solver._KEY_STATE.clear()

    def tearDown(self):
        ai_solver._KEY_STATE.clear()

    def test_classification(self):
        self.assertEqual(classify_key_error(AIQuotaError('x')), 'quota')
        self.assertEqual(classify_key_error(AIConfigError('x')), 'auth')
        self.assertEqual(classify_key_error(AIError('x')), 'server')
        import httpx
        self.assertEqual(classify_key_error(httpx.ConnectError('x')), 'server')
        self.assertEqual(classify_key_error(httpx.ReadTimeout('x')), 'server')
        # خطای منطقی تصویر — چرخش بی‌معناست
        self.assertIsNone(classify_key_error(
            AiImageError('GEMINI_SAFETY_BLOCK', 'x')))
        # خطای کاملاً خارجی — چرخش نکن
        self.assertIsNone(classify_key_error(ValueError('x')))

    def test_cooldown_skip_and_order(self):
        keys = [K1, K2, K3]
        # هیچ خطا نیست → ترتیب ذخیره
        self.assertEqual(ordered_keys('gemini', keys), keys)
        # K1 سهمیه خورد → رد می‌شود
        mark_key_failed('gemini', K1, AIQuotaError('429'))
        self.assertGreater(key_cooldown_remaining('gemini', K1), 0)
        self.assertEqual(ordered_keys('gemini', keys), [K2, K3])
        # همه cooldown → نزدیک‌ترین انقضا اول (K1 زودتر expire می‌شود)
        mark_key_failed('gemini', K2, AIConfigError('401'))  # auth = طولانی
        mark_key_failed('gemini', K3, AIConfigError('403'))
        # cooldown کوتاه‌ترِ K1 (quota) باید اول بیاید
        st = ai_solver._KEY_STATE
        st['gemini::' + K1]['cooldown_until'] -= 50
        self.assertEqual(ordered_keys('gemini', keys)[0], K1)
        # سلامت → پاک شدن وضعیت
        mark_key_ok('gemini', K1)
        self.assertEqual(key_cooldown_remaining('gemini', K1), 0)

    def test_quota_cooldown_shorter_than_auth(self):
        mark_key_failed('gemini', K1, AIQuotaError('x'))
        q = key_cooldown_remaining('gemini', K1)
        mark_key_failed('gemini', K2, AIConfigError('x'))
        a = key_cooldown_remaining('gemini', K2)
        self.assertLess(q, a)

    def test_masked_key_never_leaks(self):
        m = masked_key(K1)
        self.assertNotIn(K1, m)
        self.assertTrue(m.startswith(K1[:4]))
        self.assertIn('•', m)
        s = key_status_summary('gemini', [K1, K2])
        self.assertEqual([r['index'] for r in s], [1, 2])
        for r in s:
            self.assertNotIn(K1, r['masked'])
            self.assertNotIn(K2, r['masked'])


class FailoverRunnerTests(unittest.TestCase):
    """۵) run_with_key_failover."""

    def setUp(self):
        ai_solver._KEY_STATE.clear()
        _rtloop.adopt()

    def tearDown(self):
        ai_solver._KEY_STATE.clear()

    def test_second_key_succeeds(self):
        calls = []

        async def factory(key):
            calls.append(key)
            if key == K1:
                raise AIQuotaError('429')
            return 'ok:' + key

        res = _rtloop.run(run_with_key_failover('gemini', [K1, K2], factory))
        self.assertEqual(res, 'ok:' + K2)
        self.assertEqual(calls, [K1, K2])
        self.assertGreater(key_cooldown_remaining('gemini', K1), 0)
        self.assertEqual(key_cooldown_remaining('gemini', K2), 0)

    def test_non_rotatable_error_raises_immediately(self):
        calls = []

        async def factory(key):
            calls.append(key)
            raise ValueError('logical')

        with self.assertRaises(ValueError):
            _rtloop.run(run_with_key_failover('gemini', [K1, K2], factory))
        self.assertEqual(calls, [K1])   # کلید دوم اصلاً امتحان نشد

    def test_last_key_error_propagates(self):
        async def factory(key):
            raise AIQuotaError('429')

        with self.assertRaises(AIQuotaError):
            _rtloop.run(run_with_key_failover('gemini', [K1, K2], factory))
        # هر دو کلید cooldown شدند
        for k in (K1, K2):
            self.assertGreater(key_cooldown_remaining('gemini', k), 0)

    def test_cooldown_key_skipped_without_call(self):
        mark_key_failed('gemini', K1, AIQuotaError('429'))
        calls = []

        async def factory(key):
            calls.append(key)
            return 'ok'

        res = _rtloop.run(run_with_key_failover('gemini', [K1, K2], factory))
        self.assertEqual(res, 'ok')
        self.assertEqual(calls, [K2])   # K1 بدون درخواست شبکه رد شد


class VaultCrudTests(unittest.TestCase):
    """۲) افزودن/حذف/فهرست + سازگاری config."""

    def setUp(self):
        ai_solver._KEY_STATE.clear()
        _rtloop.adopt()
        self.fake = _FakeSettingsDB()
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        ai_solver._KEY_STATE.clear()

    def test_set_replaces_add_appends(self):
        _rtloop.run(set_api_key_for_provider('gemini', K1))
        cfg = _rtloop.run(get_ai_config())
        self.assertEqual(cfg['api_key_list'], [K1])
        self.assertEqual(cfg['api_key'], K1)
        self.assertEqual(cfg['vault_counts'], {'gemini': 1})

        n = _rtloop.run(add_api_key_for_provider('gemini', K2))
        self.assertEqual(n, 2)
        cfg = _rtloop.run(get_ai_config())
        # primary همان اولی می‌ماند (compat)
        self.assertEqual(cfg['api_key'], K1)
        self.assertEqual(cfg['api_key_list'], [K1, K2])
        self.assertEqual(cfg['vault_counts'], {'gemini': 2})
        # فرم compat قدیمی (رشته) هم حفظ شده
        self.assertEqual(cfg['vault'].get('gemini'), K1)
        self.assertEqual(cfg['api_keys'].get('gemini'), K1)

    def test_add_duplicate_rejected(self):
        _rtloop.run(set_api_key_for_provider('gemini', K1))
        with self.assertRaises(ValueError):
            _rtloop.run(add_api_key_for_provider('gemini', K1))

    def test_add_invalid_key_rejected(self):
        with self.assertRaises(ValueError):
            _rtloop.run(add_api_key_for_provider('gemini', 'کلید فارسی نامعتبر'))

    def test_remove_by_index(self):
        _rtloop.run(set_api_key_for_provider('gemini', K1))
        _rtloop.run(add_api_key_for_provider('gemini', K2))
        removed = _rtloop.run(remove_api_key_for_provider('gemini', 1))
        self.assertNotIn(K1, removed)
        cfg = _rtloop.run(get_ai_config())
        self.assertEqual(cfg['api_key_list'], [K2])
        # حذف آخرین کلید → provider خالی
        _rtloop.run(remove_api_key_for_provider('gemini', 1))
        cfg = _rtloop.run(get_ai_config())
        self.assertEqual(cfg['api_key_list'], [])
        with self.assertRaises(ValueError):
            _rtloop.run(remove_api_key_for_provider('gemini', 1))

    def test_list_masked_only(self):
        _rtloop.run(set_api_key_for_provider('gemini', K1))
        _rtloop.run(add_api_key_for_provider('gemini', K2))
        info = _rtloop.run(list_api_keys_for_provider('gemini'))
        self.assertEqual(info['count'], 2)
        joined = ''.join(r['masked'] for r in info['keys'])
        self.assertNotIn(K1, joined)
        self.assertNotIn(K2, joined)

    def test_image_key_list_fallback(self):
        _rtloop.run(set_api_key_for_provider('gemini', K1))
        _rtloop.run(add_api_key_for_provider('gemini', K2))
        cfg = _rtloop.run(get_ai_config())
        # image_provider پیش‌فرض = provider فعلی
        self.assertEqual(cfg.get('image_api_key_list'), [K1, K2])


class AskAiStreamFallbackTests(unittest.TestCase):
    """۶) مسیر اصلی چت: 429 روی کلید اول → پاسخ با کلید دوم."""

    def setUp(self):
        ai_solver._KEY_STATE.clear()
        _rtloop.adopt()

    def tearDown(self):
        ai_solver._KEY_STATE.clear()

    @staticmethod
    def _fake_cfg(keys):
        return {
            'enabled': True, 'provider': 'gemini', 'api_key': keys[0],
            'api_key_list': list(keys), 'api_key_error': None,
            'model': 'gemini-2.5-flash', 'system_prompt': 'تو هوشیار هستی.',
            'thinking': 'auto', 'vault': {'gemini': keys[0]},
            'api_keys': {'gemini': keys[0]},
            'vault_multi': {'gemini': list(keys)},
            'vault_counts': {'gemini': len(keys)},
            'image_api_key_list': list(keys),
        }

    def test_quota_on_first_key_falls_to_second(self):
        seen = []

        async def fake_stream(api_key, model, system_prompt, text=None,
                              image_bytes=None, image_mime='image/jpeg',
                              history=None, thinking='auto', uid=None,
                              doc=None, **_):
            seen.append(api_key)
            if api_key == K1:
                raise AIQuotaError('سقف رایگان API برای امروز پر شده')
            yield {'type': 'delta', 'text': 'سلام'}
            yield {'type': 'done', 'answer': 'سلام دنیا', 'tokens': 7}

        async def fake_cfg():
            return self._fake_cfg([K1, K2])

        events = []
        with mock.patch.object(ai_solver, 'get_ai_config', fake_cfg), \
             mock.patch.dict(ai_solver.STREAM_PROVIDERS, {'gemini': fake_stream}):
            async def _collect():
                async for ev in ai_solver.ask_ai_stream(text='سلام', uid=None):
                    events.append(ev)
            _rtloop.run(_collect())

        self.assertEqual(seen, [K1, K2])
        self.assertEqual(events[-1]['type'], 'done')
        self.assertEqual(events[-1]['answer'], 'سلام دنیا')
        # وضعیت: K1 در cooldown، K2 سالم
        self.assertGreater(key_cooldown_remaining('gemini', K1), 0)
        self.assertEqual(key_cooldown_remaining('gemini', K2), 0)

    def test_non_rotatable_error_no_fallback(self):
        seen = []

        async def fake_stream(api_key, **kw):
            seen.append(api_key)
            raise AiImageError('GEMINI_SAFETY_BLOCK', 'blocked')
            yield  # nunca — فقط برای async-generator بودن

        async def fake_cfg():
            return self._fake_cfg([K1, K2])

        with mock.patch.object(ai_solver, 'get_ai_config', fake_cfg), \
             mock.patch.dict(ai_solver.STREAM_PROVIDERS, {'gemini': fake_stream}):
            with self.assertRaises(AiImageError):
                async def _collect():
                    async for _ in ai_solver.ask_ai_stream(text='سلام', uid=None):
                        pass
                _rtloop.run(_collect())
        self.assertEqual(seen, [K1])   # چرخش نکرد

    def test_all_keys_fail_raises_last(self):
        async def fake_stream(api_key, **kw):
            raise AIQuotaError('429')
            yield  # nunca — فقط برای async-generator بودن

        async def fake_cfg():
            return self._fake_cfg([K1, K2])

        with mock.patch.object(ai_solver, 'get_ai_config', fake_cfg), \
             mock.patch.dict(ai_solver.STREAM_PROVIDERS, {'gemini': fake_stream}):
            with self.assertRaises(AIQuotaError):
                async def _collect():
                    async for _ in ai_solver.ask_ai_stream(text='سلام', uid=None):
                        pass
                _rtloop.run(_collect())
        # هر دو کلید cooldown
        for k in (K1, K2):
            self.assertGreater(key_cooldown_remaining('gemini', k), 0)

    def test_partial_stream_no_key_switch(self):
        """اگر جوابی به کاربر جاری شده، تعویض کلید ممکن نیست."""
        seen = []

        async def fake_stream(api_key, **kw):
            seen.append(api_key)
            yield {'type': 'delta', 'text': 'نص'}
            raise AIQuotaError('429 وسط استریم')

        async def fake_cfg():
            return self._fake_cfg([K1, K2])

        with mock.patch.object(ai_solver, 'get_ai_config', fake_cfg), \
             mock.patch.dict(ai_solver.STREAM_PROVIDERS, {'gemini': fake_stream}):
            with self.assertRaises(AIQuotaError):
                async def _collect():
                    async for _ in ai_solver.ask_ai_stream(text='سلام', uid=None):
                        pass
                _rtloop.run(_collect())
        self.assertEqual(seen, [K1])   # K2 امتحان نشد — استریم نیمه‌جاری


if __name__ == '__main__':
    unittest.main()
