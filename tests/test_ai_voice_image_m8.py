# -*- coding: utf-8 -*-
"""⭐ م8 — تست‌های واحد: پاسخ صوتی (TTS)، مدل‌های تصویرِ زنده،
سلامت‌سنجی مدل‌ها (تستِ واقعیِ توکن) و مرتب‌سازیِ رایگانِ زنده.

بدون شبکه/Mongo — همه‌ی مسیرهای HTTP با فیک httpx ماک می‌شوند."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('MONGODB_URI', 'mongodb://127.0.0.1:27017')

import _rtloop
import ai_solver
from ai_solver import (
    _looks_like_image_model, model_free_rank, model_is_free,
    merge_models_with_health, list_image_models, probe_models,
    get_models_health, generate_speech_gemini, get_ai_config,
    set_api_key_for_provider, add_api_key_for_provider,
    IMAGE_ASPECT_RATIOS, IMAGE_SIZES, PREBUILT_TTS_VOICES,
    VOICE_REPLY_MODES, TTS_MODEL_DEFAULT,
)

K1 = 'AIza_test_key_8888'
K2 = 'AIza_test_key_9999'


class _FakeSettingsDB:
    def __init__(self):
        self.settings = {}

    async def get_settings_by_prefix(self, prefix):
        return {k: v for k, v in self.settings.items() if k.startswith(prefix)}

    async def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    async def set_setting(self, key, value):
        self.settings[key] = value


class _Resp:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _ClientCtx:
    """httpx.AsyncClient ماک — صف پاسخ‌ها."""
    responses = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, **kw):
        item = _ClientCtx.responses.pop(0) if _ClientCtx.responses else (200, {})
        return _Resp(*item) if isinstance(item, tuple) else _Resp(item)

    async def post(self, url, headers=None, json=None, **kw):
        _ClientCtx.last_post = (url, headers, json)
        item = _ClientCtx.responses.pop(0) if _ClientCtx.responses else (200, {})
        return _Resp(*item) if isinstance(item, tuple) else _Resp(item)


class ImageModelDetectionTests(unittest.TestCase):
    """تشخیص مدل تصویر از نام + رتبه‌ی رایگان."""

    def test_looks_like_image_model(self):
        for mid in ('gemini-nano-banana-2.1', 'gemini-3.1-flash-lite-image',
                    'gemini-3-pro-image', 'imagen-4.0-generate-001'):
            self.assertTrue(_looks_like_image_model(mid), mid)
        for mid in ('gemini-3.6-flash', 'gemini-3.8-flash-tts',
                    'text-embedding-2', 'gemma-4-31b-it'):
            self.assertFalse(_looks_like_image_model(mid), mid)

    def test_free_rank(self):
        # openrouter :free قطعاً رایگان
        self.assertEqual(model_free_rank('openrouter', 'x/FLUX.1-schnell:free'), 4)
        self.assertEqual(model_free_rank('openrouter', 'openai/gpt-5'), 0)
        # gemini: lite > flash/banana > pro
        self.assertGreater(model_free_rank('gemini', 'gemini-3.1-flash-lite-image'),
                           model_free_rank('gemini', 'gemini-nano-banana-2.1'))
        self.assertGreater(model_free_rank('gemini', 'gemini-nano-banana-2.1'),
                           model_free_rank('gemini', 'gemini-3-pro-image'))
        self.assertTrue(model_is_free('gemini', 'gemini-3.1-flash-lite-image'))
        self.assertFalse(model_is_free('gemini', 'gemini-3-pro-image'))

    def test_catalog_ratios_and_sizes(self):
        # نسبت‌های پانورامای نانوبانانا 2.1 موجود است
        for r in ('1:4', '4:1', '1:8', '8:1', '21:9'):
            self.assertIn(r, IMAGE_ASPECT_RATIOS)
        self.assertEqual(IMAGE_SIZES, ('1K', '2K', '4K'))
        # ۳۰ صدای پیش‌ساخته + حالت‌های پاسخ صوتی
        self.assertEqual(len(PREBUILT_TTS_VOICES), 30)
        self.assertIn('Sulafat', PREBUILT_TTS_VOICES)
        self.assertEqual(VOICE_REPLY_MODES, ('off', 'voice', 'all'))
        self.assertEqual(TTS_MODEL_DEFAULT, 'gemini-3.8-flash-lite-tts')


class HealthSortTests(unittest.TestCase):
    """مرتب‌سازی: زنده > تست‌نشده > مرده، بعد رایگان‌تر، بعد سریع‌تر."""

    def test_sort_alive_free_fast_first(self):
        models = [
            {'id': 'gemini-3-pro-slow', 'label': 'A'},        # زنده ولی pro و کُند
            {'id': 'gemini-3.6-flash-lite-fast', 'label': 'B'},  # زنده + lite + سریع
            {'id': 'gemini-3.6-flash-dead', 'label': 'C'},    # مرده
            {'id': 'gemini-3.6-untested', 'label': 'D'},      # تست‌نشده
        ]
        health = {'kind': 'chat', 'models': {
            'gemini-3-pro-slow': {'ok': True, 'ms': 3000},
            'gemini-3.6-flash-lite-fast': {'ok': True, 'ms': 400},
            'gemini-3.6-flash-dead': {'ok': False, 'ms': 100},
        }}
        out = merge_models_with_health('gemini', models, health)
        ids = [m['id'] for m in out]
        # زنده‌ی سریعِ lite اول؛ مرده آخر؛ تست‌نشده وسط
        self.assertEqual(ids[0], 'gemini-3.6-flash-lite-fast')
        self.assertEqual(ids[-1], 'gemini-3.6-flash-dead')
        self.assertIn('gemini-3.6-untested', ids[1:3])
        # نشان رایگان چسبیده (lite/flash رایگان‌اند؛ pro نه)
        by_id = {m['id']: m for m in out}
        self.assertTrue(by_id['gemini-3.6-flash-lite-fast']['free'])
        self.assertFalse(by_id['gemini-3-pro-slow']['free'])

    def test_no_health_keeps_order(self):
        models = [{'id': 'a'}, {'id': 'b'}]
        out = merge_models_with_health('gemini', models, {})
        self.assertEqual([m['id'] for m in out], ['a', 'b'])
        self.assertIsNone(out[0]['health_ok'])


class ListImageModelsTests(unittest.TestCase):
    """فهرست زنده از ListModels + fallback کاتالوگ."""

    def setUp(self):
        _rtloop.adopt()
        self.fake = _FakeSettingsDB()
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_live_from_listmodels(self):
        _ClientCtx.responses = [(200, {'models': [
            {'name': 'models/gemini-nano-banana-2.1'},
            {'name': 'models/gemini-3.1-flash-lite-image'},
            {'name': 'models/gemini-3.6-flash'},          # چت — رد
            {'name': 'models/gemini-embedding-2'},        # رد
        ]})]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            out = _rtloop.run(list_image_models('gemini', api_key=K1, refresh=True))
        ids = [m['id'] for m in out['models']]
        self.assertEqual(ids, ['gemini-nano-banana-2.1', 'gemini-3.1-flash-lite-image'])
        self.assertFalse(out['fallback'])
        self.assertTrue(out['models'][1]['free'])    # lite = رایگان

    def test_fallback_catalog_on_error(self):
        _ClientCtx.responses = [(403, {'error': {'message': 'no access'}})]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            out = _rtloop.run(list_image_models('gemini', api_key=K1, refresh=True))
        self.assertTrue(out['fallback'])
        self.assertTrue(len(out['models']) >= 2)
        # مدل‌های مرده‌ی imagen-4 در کاتالوگ روزآمد نیستند
        self.assertFalse(any('imagen-4' in m['id'] for m in out['models']))
        # نانوبانانا 2.1 هست
        self.assertTrue(any(m['id'] == 'gemini-nano-banana-2.1' for m in out['models']))


class ProbeTests(unittest.TestCase):
    """سلامت‌سنجی: پاسخِ ۲۰۰ = زنده؛ خطا = مرده؛ ذخیره در settings."""

    def setUp(self):
        _rtloop.adopt()
        ai_solver._KEY_STATE.clear()
        self.fake = _FakeSettingsDB()
        self.fake.settings['ai_api_keys'] = '{"gemini": ["%s", "%s"]}' % (K1, K2)
        self.fake.settings['ai_enabled'] = '1'
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        ai_solver._KEY_STATE.clear()

    def test_probe_marks_and_stores(self):
        _ClientCtx.responses = [
            (200, {'candidates': [{'content': {'parts': [{'text': '۱'}]}}]}),
            (429, {'error': {'message': 'quota'}}),
        ]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            out = _rtloop.run(probe_models('gemini', ['gemini-3.6-flash', 'gemini-3.8-flash'],
                                           kind='chat'))
        self.assertEqual(out['ok_count'], 1)
        self.assertTrue(out['results']['gemini-3.6-flash']['ok'])
        self.assertFalse(out['results']['gemini-3.8-flash']['ok'])
        self.assertIn('HTTP 429', out['results']['gemini-3.8-flash']['error'])
        # ذخیره در settings
        stored = self.fake.settings.get('ai_models_health_gemini')
        self.assertIsNotNone(stored)
        self.assertEqual(stored['kind'], 'chat')
        # خواندن سلامت
        got = _rtloop.run(get_models_health('gemini'))
        self.assertEqual(got['kind'], 'chat')

    def test_probe_image_uses_cheap_get(self):
        _ClientCtx.responses = [(200, {'name': 'models/x'}), (404, {})]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            out = _rtloop.run(probe_models('gemini',
                                           ['gemini-nano-banana-2.1', 'imagen-4.0-generate-001'],
                                           kind='image'))
        self.assertTrue(out['results']['gemini-nano-banana-2.1']['ok'])
        self.assertFalse(out['results']['imagen-4.0-generate-001']['ok'])


class TtsTests(unittest.TestCase):
    """درخواست TTS: شکل payload طبق مستندات + فال‌بک کلید + خروجی WAV."""

    def setUp(self):
        _rtloop.adopt()
        ai_solver._KEY_STATE.clear()
        self.fake = _FakeSettingsDB()
        self.fake.settings['ai_api_keys'] = '{"gemini": ["%s", "%s"]}' % (K1, K2)
        self.fake.settings['ai_enabled'] = '1'
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        ai_solver._KEY_STATE.clear()

    def test_tts_request_shape_and_fallback(self):
        import base64
        wav = b'RIFFxxxxWAVEfmt '
        _ClientCtx.responses = [
            (429, {'error': {'message': 'quota'}}),          # کلید ۱: سهمیه
            (200, {'candidates': [{'content': {'parts': [
                {'inlineData': {'data': base64.b64encode(wav).decode(),
                                'mimeType': 'audio/wav'}}]}}]}),
        ]
        seen = []
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            data, mime = _rtloop.run(generate_speech_gemini(
                'سلام دنیا', voice='Sulafat'))
        # کلید دوم موفق شد
        self.assertEqual(data, wav)
        self.assertEqual(mime, 'audio/wav')
        self.assertGreater(ai_solver.key_cooldown_remaining('gemini', K1), 0)
        # شکل درخواست طبق مستندات 3.8 TTS
        url, headers, payload = _ClientCtx.last_post
        self.assertIn('gemini-3.8-flash-lite-tts', url)
        self.assertIn(':generateContent', url)
        gc = payload['generationConfig']
        self.assertEqual(gc['responseModalities'], ['AUDIO'])
        self.assertEqual(gc['speechConfig']['voiceConfig']['voice'], 'Sulafat')
        part = payload['contents'][0]['parts'][0]
        self.assertEqual(part['text'], 'سلام دنیا')
        self.assertIn('style', part.get('speech_metadata', {}))

    def test_config_voice_fields(self):
        self.fake.settings['ai_voice_reply'] = 'all'
        self.fake.settings['ai_tts_voice'] = 'Kore'
        self.fake.settings['ai_voice_reply_max_chars'] = '300'
        self.fake.settings['ai_image_size'] = '2K'
        cfg = _rtloop.run(get_ai_config())
        self.assertEqual(cfg['voice_reply'], 'all')
        self.assertEqual(cfg['tts_voice'], 'Kore')
        self.assertEqual(cfg['tts_model'], 'gemini-3.8-flash-lite-tts')
        self.assertEqual(cfg['voice_reply_max_chars'], 300)
        self.assertEqual(cfg['image_size'], '2K')

    def test_config_rejects_bad_values(self):
        self.fake.settings['ai_voice_reply'] = 'bogus'
        self.fake.settings['ai_tts_voice'] = 'NotAVoice'
        self.fake.settings['ai_image_size'] = '9K'
        cfg = _rtloop.run(get_ai_config())
        self.assertEqual(cfg['voice_reply'], 'voice')       # پیش‌فرض امن
        self.assertEqual(cfg['tts_voice'], 'Sulafat')
        self.assertEqual(cfg['image_size'], '1K')


class ImagePayloadTests(unittest.TestCase):
    """payload تصویر: aspectRatio + imageSize (نانوبانانا 2.1)."""

    def setUp(self):
        _rtloop.adopt()

    def test_payload_has_image_size(self):
        import base64
        png = base64.b64encode(b'\x89PNGxxxx').decode()
        _ClientCtx.responses = [(200, {'candidates': [{'content': {'parts': [
            {'inlineData': {'data': png, 'mimeType': 'image/png'}}]}}]})]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            res = _rtloop.run(ai_solver._generate_image_gemini(
                K1, 'gemini-nano-banana-2.1', 'یک نقطه', '16:9', 5, 0, '2K'))
        _url, _h, payload = _ClientCtx.last_post
        ic = payload['generationConfig']['imageConfig']
        self.assertEqual(ic['aspectRatio'], '16:9')
        self.assertEqual(ic['imageSize'], '2K')


if __name__ == '__main__':
    unittest.main()
