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
    _looks_like_image_model, model_free_rank, model_is_free, _voice_reply_plan,
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

    def test_probe_image_uses_real_generate_content(self):
        import base64
        png = base64.b64encode(b'\x89PNGxxxx').decode()
        _ClientCtx.responses = [
            (200, {'candidates': [{'content': {'parts': [
                {'inlineData': {'data': png, 'mimeType': 'image/png'}}]}}]}),
            (404, {'error': {'message': 'not found'}}),
        ]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            out = _rtloop.run(probe_models('gemini',
                                           ['gemini-3.1-flash-lite-image', 'imagen-4.0-generate-001'],
                                           kind='image'))
        self.assertTrue(out['results']['gemini-3.1-flash-lite-image']['ok'])
        self.assertGreaterEqual(out['results']['gemini-3.1-flash-lite-image']['ms'], 1)
        self.assertEqual(out['results']['gemini-3.1-flash-lite-image']['mode'], 'real_image_gen')
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


class _StreamResp:
    """پاسخ SSE فیک برای _stream_gemini."""
    status_code = 200

    async def aiter_lines(self):
        import json as _json
        yield 'data: ' + _json.dumps({
            'candidates': [{'content': {'parts': [{'text': 'سلام، جواب ویس'}]},
                             'finishReason': 'STOP'}],
            'usageMetadata': {'totalTokenCount': 12}})

    async def aread(self):
        return b''


class _StreamClient:
    """httpx.AsyncClient فیک — payload آخرین درخواست را روی کلاس ضبط می‌کند."""
    payloads = []

    def __init__(self, *a, **kw):
        pass

    def stream(self, method, url, headers=None, json=None, **kw):
        _StreamClient.payloads.append({'url': url, 'payload': json})
        return self

    async def __aenter__(self):
        return _StreamResp()

    async def __aexit__(self, *a):
        return False

    async def aclose(self):
        pass


class VoiceToolsFixTests(unittest.TestCase):
    """🔴 م8.1 — باگِ ویس: code_execution با audio/wav خطای ۴۰۰ می‌داد.

    ریشه: ابزارهای توکار (code_execution/url_context) بی‌قید به همه‌ی
    درخواست‌ها چسبیده بودند؛ Gemini ورودیِ صوتی را با این ابزارها رد
    می‌کند. باید با ورودی صوت/ویدیو حذف شوند ولی function declarations
    بمانند."""

    def setUp(self):
        _rtloop.adopt()
        _StreamClient.payloads = []
        self.fake = _FakeSettingsDB()
        self.fake.settings['ai_enabled'] = '1'
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _run(self, **kw):
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _StreamClient):
            async def _collect():
                out = []
                async for ev in ai_solver._stream_gemini(
                        K1, 'gemini-3.6-flash', 'شما هوشیار هستید', **kw):
                    out.append(ev)
                return out
            return _rtloop.run(_collect())

    def test_voice_audio_drops_builtin_tools(self):
        events = self._run(text='سوال ویس', image_bytes=b'RIFFwav',
                           image_mime='audio/wav', uid=111)
        self.assertTrue(any(e['type'] == 'done' for e in events))
        self.assertEqual(len(_StreamClient.payloads), 1)
        tools = _StreamClient.payloads[0]['payload']['tools']
        names = [list(t.keys())[0] for t in tools]
        # ابزار توکار حذف شد؛ تابع‌های سفارشی ماندند
        self.assertNotIn('code_execution', names)
        self.assertNotIn('url_context', names)
        self.assertIn('function_declarations', names)
        # فلگِ server-side فقط با ابزار توکار معنا دارد — نباید باشد
        tc = _StreamClient.payloads[0]['payload'].get('tool_config') or {}
        self.assertNotIn('include_server_side_tool_invocations', tc)
        # صوت واقعاً با mime درست رفته
        part0 = _StreamClient.payloads[0]['payload']['contents'][-1]['parts'][0]
        self.assertEqual(part0['inline_data']['mime_type'], 'audio/wav')

    def test_video_note_also_drops(self):
        self._run(text='ویدیونوت', image_bytes=b'\x00\x00\x00\x18ftyp',
                  image_mime='video/mp4', uid=111)
        names = [list(t.keys())[0]
                 for t in _StreamClient.payloads[0]['payload']['tools']]
        self.assertNotIn('code_execution', names)

    def test_image_keeps_builtin_tools(self):
        self._run(text='این عکس چیه؟', image_bytes=b'\x89PNGxyz',
                  image_mime='image/png', uid=111)
        names = [list(t.keys())[0]
                 for t in _StreamClient.payloads[0]['payload']['tools']]
        self.assertIn('code_execution', names)
        self.assertIn('url_context', names)
        self.assertIn('function_declarations', names)
        tc = _StreamClient.payloads[0]['payload'].get('tool_config') or {}
        self.assertTrue(tc.get('include_server_side_tool_invocations'))

    def test_text_keeps_builtin_tools(self):
        self._run(text='سلام', uid=111)
        names = [list(t.keys())[0]
                 for t in _StreamClient.payloads[0]['payload']['tools']]
        self.assertIn('code_execution', names)

    def test_mime_400_error_is_not_apikey_error(self):
        # تور ایمنی: ۴۰۰ِ «mime type» پیام روشن می‌دهد، نه «کلید نامعتبره»
        try:
            ai_solver._raise_gemini_status_error(
                400, '[INVALID_ARGUMENT] The mime type: audio/wav is not '
                     'supported for code execution.')
            self.fail('must raise')
        except ai_solver.AIError as e:
            self.assertNotIsInstance(e, ai_solver.AIConfigError)
            self.assertIn('پشتیبانی نمی‌شود', str(e))


class VoiceReplyPlanTests(unittest.TestCase):
    """⭐ م8.2 — ماتریس تصمیمِ پاسخ صوتی (پیش‌فرض: ویس ⇒ فقط ویس)."""

    def _cfg(self, **kw):
        base = {'voice_reply': 'voice', 'voice_with_text': 'off',
                'voice_reply_max_chars': 500}
        base.update(kw)
        return base

    def test_default_voice_input_is_voice_only(self):
        # خواسته‌ی صریح کاربر: ویس فرستادی ⇒ فقط ویس، بدون تکرار متن
        self.assertEqual(_voice_reply_plan(self._cfg(), True, 200), 'voice_only')

    def test_voice_with_text_on_sends_both(self):
        self.assertEqual(
            _voice_reply_plan(self._cfg(voice_with_text='on'), True, 200),
            'text_and_voice')

    def test_long_answer_falls_back_to_text(self):
        self.assertEqual(
            _voice_reply_plan(self._cfg(), True, 800), 'text_only')

    def test_text_input_no_voice_in_voice_mode(self):
        self.assertEqual(_voice_reply_plan(self._cfg(), False, 200), 'off')

    def test_all_mode_text_input_gets_extra_voice(self):
        self.assertEqual(
            _voice_reply_plan(self._cfg(voice_reply='all'), False, 200),
            'text_and_voice')

    def test_all_mode_voice_input_voice_only_by_default(self):
        # دوباره‌کاری در همه‌ی حالت‌ها ممنوع — حتی حالتِ all با ورودی ویس
        self.assertEqual(
            _voice_reply_plan(self._cfg(voice_reply='all'), True, 200),
            'voice_only')

    def test_off_mode_never_voice(self):
        self.assertEqual(
            _voice_reply_plan(self._cfg(voice_reply='off'), True, 200), 'off')

    def test_config_parses_voice_with_text(self):
        _rtloop.adopt()
        fake = _FakeSettingsDB()
        fake.settings['ai_enabled'] = '1'
        fake.settings['ai_voice_with_text'] = 'on'
        with mock.patch.object(ai_solver, 'db', fake):
            cfg = _rtloop.run(get_ai_config())
        self.assertEqual(cfg['voice_with_text'], 'on')
        # مقدار نامعتبر → پیش‌فرضِ امن (خاموش = فقط ویس)
        fake.settings['ai_voice_with_text'] = 'bogus'
        with mock.patch.object(ai_solver, 'db', fake):
            cfg2 = _rtloop.run(get_ai_config())
        self.assertEqual(cfg2['voice_with_text'], 'off')


class _Ctx401:
    """CM استریم با کد وضعیت قابل‌تنظیم."""
    def __init__(self, resp):
        self._r = resp

    async def __aenter__(self):
        return self._r

    async def __aexit__(self, *a):
        return False


class _Resp401:
    def __init__(self, status, body=b''):
        self.status_code = status
        self._body = body

    async def aiter_lines(self):
        import json as _json
        yield 'data: ' + _json.dumps({
            'candidates': [{'content': {'parts': [{'text': 'جواب با کلید دوم'}]},
                             'finishReason': 'STOP'}],
            'usageMetadata': {'totalTokenCount': 9}})

    async def aread(self):
        return self._body


class _Client401:
    """streamGenerateContent: کلید اول 401 سرویس‌اکانت، کلید دوم 200."""
    def __init__(self, *a, **kw):
        pass

    def stream(self, method, url, headers=None, json=None, **kw):
        key = (headers or {}).get('x-goog-api-key')
        if key == K1:
            return _Ctx401(_Resp401(
                401, b'{"error":{"message":"The bound service account is '
                     b'deleted or disabled. The service account bound to the '
                     b'API key must be active"}}'))
        return _Ctx401(_Resp401(200))

    async def aclose(self):
        pass


class _ClientAll401:
    """همه‌ی کلیدها 401 می‌گیرند."""
    def __init__(self, *a, **kw):
        pass

    def stream(self, method, url, headers=None, json=None, **kw):
        return _Ctx401(_Resp401(
            401, b'{"error":{"message":"The bound service account is deleted '
                 b'or disabled"}}'))

    async def aclose(self):
        pass


class KeyFailover401Tests(unittest.TestCase):
    """⭐ م8.3 — فال‌بک روی 401 (سرویس‌اکانتِ حذف‌شده) باید کلید بعدی را
    امتحان کند؛ اگر همه شکست خوردند، پیام باید بگوید همه امتحان شدند."""

    def setUp(self):
        _rtloop.adopt()
        ai_solver._KEY_STATE.clear()
        self.fake = _FakeSettingsDB()
        self.fake.settings['ai_enabled'] = '1'
        self.fake.settings['ai_provider'] = 'gemini'
        self.fake.settings['ai_model'] = 'gemini-3.6-flash'
        self.fake.settings['ai_api_keys'] = '{"gemini": ["%s", "%s"]}' % (K1, K2)
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        ai_solver._KEY_STATE.clear()

    def _collect(self):
        async def _go():
            out = []
            async for ev in ai_solver.ask_ai_stream(text='سلام', uid=None):
                out.append(ev)
            return out
        return _rtloop.run(_go())

    def test_401_rotates_to_next_key(self):
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _Client401):
            events = self._collect()
        done = [e for e in events if e['type'] == 'done']
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]['answer'], 'جواب با کلید دوم')
        # کلیدِ خراب cooldown شد؛ کلیدِ سالم علامتِ ok خورد
        self.assertGreater(ai_solver.key_cooldown_remaining('gemini', K1), 0)
        self.assertEqual(ai_solver.key_cooldown_remaining('gemini', K2), 0)

    def test_all_keys_401_says_all_tried(self):
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientAll401):
            with self.assertRaises(ai_solver.AIConfigError) as cm:
                self._collect()
        msg = str(cm.exception)
        self.assertIn('همه‌ی ۲ کلید', msg)
        self.assertIn('سرویس‌اکانت', msg)
        # هر دو کلید cooldown شدند
        self.assertGreater(ai_solver.key_cooldown_remaining('gemini', K1), 0)
        self.assertGreater(ai_solver.key_cooldown_remaining('gemini', K2), 0)


class _PingClient:
    """httpx فیک برای _chat_ping_gemini — POST را ضبط می‌کند."""
    responses = []          # [(status, body)]
    last = None

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **kw):
        _PingClient.last = {'url': url, 'headers': headers, 'payload': json}
        st, body = _PingClient.responses.pop(0) if _PingClient.responses else (200, b'')
        class _R:
            status_code = st
            text = body.decode('utf-8', 'replace')
        return _R()


class RealKeyTestTests(unittest.TestCase):
    """⭐ م8.3 — تستِ کلیدِ پنل باید تولیدِ واقعی بزند، نه ListModels."""

    def setUp(self):
        _rtloop.adopt()
        ai_solver._KEY_STATE.clear()
        self.fake = _FakeSettingsDB()
        self.fake.settings['ai_enabled'] = '1'
        self.fake.settings['ai_model'] = 'gemini-3.6-flash'
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        ai_solver._KEY_STATE.clear()

    def test_ping_is_real_generate_content(self):
        _PingClient.responses = [(200, b'{}')]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _PingClient):
            ok, err = _rtloop.run(ai_solver.test_api_key('gemini', K1))
        self.assertTrue(ok)
        self.assertEqual(err, '')
        # همان مسیر چت: generateContent + maxOutputTokens=1 + هدر کلید
        self.assertIn(':generateContent', _PingClient.last['url'])
        self.assertIn('gemini-3.6-flash', _PingClient.last['url'])
        self.assertEqual(
            _PingClient.last['payload']['generationConfig']['maxOutputTokens'], 1)
        self.assertEqual(_PingClient.last['headers'].get('x-goog-api-key'), K1)

    def test_dead_service_account_key_reported_clearly(self):
        _PingClient.responses = [(
            401, b'{"error":{"message":"The bound service account is deleted '
                 b'or disabled. The service account bound to the API key must '
                 b'be active"}}')]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _PingClient):
            ok, err = _rtloop.run(ai_solver.test_api_key('gemini', K1))
        self.assertFalse(ok)
        self.assertIn('سرویس‌اکانت', err)
        self.assertIn('aistudio.google.com', err)
        # کلیدِ مرده cooldown می‌شود تا فال‌بکِ چت از آن رد شود
        self.assertGreater(ai_solver.key_cooldown_remaining('gemini', K1), 0)


class M84GoogleImageFixTests(unittest.TestCase):
    """⭐ م8.4 — فقط مدل‌های رایگان/رسمی گوگل، حذف imageSize برای flash-lite/2.5-flash،
    بازتلاش خودکار با ['TEXT', 'IMAGE']، حذف نتایج جعلی 0ms و مهاجرت مدل‌های قدیمی."""

    def setUp(self):
        _rtloop.adopt()
        ai_solver._KEY_STATE.clear()
        self.fake = _FakeSettingsDB()
        self.fake.settings['ai_enabled'] = '1'
        self.fake.settings['ai_api_keys'] = '{"gemini": ["%s"], "openrouter": ["sk-or-test-123456"]}' % K1
        self._p = mock.patch.object(ai_solver, 'db', self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        ai_solver._KEY_STATE.clear()

    def test_catalog_contains_only_google_models(self):
        self.assertEqual(ai_solver.DEFAULT_IMAGE_MODEL, 'gemini-3.1-flash-lite-image')
        ids = [mid for mid, _lbl, _free in ai_solver.IMAGE_MODEL_CATALOG]
        self.assertIn('gemini-3.1-flash-lite-image', ids)
        self.assertIn('gemini-2.5-flash-image', ids)
        self.assertIn('gemini-nano-banana-2.1', ids)
        for mid in ids:
            self.assertTrue(mid.startswith('gemini'), f'Non-Google model in catalog: {mid}')
            self.assertNotIn('/', mid)

    def test_legacy_non_google_model_migrated_to_google_and_gemini_key(self):
        self.fake.settings['ai_provider'] = 'openrouter'
        self.fake.settings['ai_image_model'] = 'black-forest-labs/FLUX.1-schnell'
        cfg = _rtloop.run(get_ai_config())
        self.assertEqual(cfg['image_model'], 'gemini-3.1-flash-lite-image')
        self.assertEqual(cfg['image_provider'], 'gemini')
        self.assertEqual(cfg['image_api_key'], K1)

    def test_flash_lite_omits_image_size_and_retries_400_with_text_image(self):
        import base64
        png = base64.b64encode(b'\x89PNGxxxx').decode()
        _ClientCtx.responses = [
            (400, {'error': {'message': 'INVALID_ARGUMENT: responseModalities must include TEXT'}},
             '{"error":{"message":"INVALID_ARGUMENT: responseModalities must include TEXT"}}'),
            (200, {'candidates': [{'content': {'parts': [
                {'inlineData': {'data': png, 'mimeType': 'image/png'}}]}}]}),
        ]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _ClientCtx):
            res = _rtloop.run(ai_solver._generate_image_gemini(
                K1, 'gemini-3.1-flash-lite-image', 'یک دایره آبی', '1:1', 5, 0, '2K'))
        self.assertEqual(res['mime'], 'image/png')
        _url, _h, last_payload = _ClientCtx.last_post
        self.assertEqual(last_payload['generationConfig']['responseModalities'], ['TEXT', 'IMAGE'])

    def test_merge_models_strips_fake_0ms_catalog_entries(self):
        models = [{'id': 'gemini-3.1-flash-lite-image', 'label': 'Lite', 'free': True}]
        stale_health = {
            'models': {
                'gemini-3.1-flash-lite-image': {
                    'ok': True, 'ms': 0, 'mode': 'catalog', 'tested_at': '2026-10-16T00:00:00Z'
                }
            }
        }
        merged = merge_models_with_health('gemini', models, stale_health)
        self.assertIsNone(merged[0]['health_ok'])
        self.assertIsNone(merged[0]['health_ms'])

        real_health = {
            'models': {
                'gemini-3.1-flash-lite-image': {
                    'ok': True, 'ms': 840, 'mode': 'real_image_gen', 'tested_at': '2026-10-16T00:00:00Z'
                }
            }
        }
        merged_real = merge_models_with_health('gemini', models, real_health)
        self.assertTrue(merged_real[0]['health_ok'])
        self.assertEqual(merged_real[0]['health_ms'], 840)

