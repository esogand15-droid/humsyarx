# -*- coding: utf-8 -*-
"""🩹 RAG سبک هوشیار — تست‌های رگرسیون کرشِ «بعد از ارسال PDF».

باگ اصلی: PDF آپلود می‌شد ولی کد صبر نمی‌کرد تا فایل روی سرور گوگل
ACTIVE شود (یا FAILED می‌شد و بی‌خبر می‌ماندیم)؛ از آن به بعد سندِ
الصاق‌شده به هر سوالِ کاربر خطای 400 می‌داد — برای همیشه.

سه گارد:
  ۱) _gemini_wait_file_active — نظرسنجی تا ACTIVE/FAILED/timeout
  ۲) خودترمیمی ask_ai_stream — خطای سند ⇒ جدا کردن + یک retry بدون سند
  ۳) skip_doc — سوالِ اولِ بعد از آپلودِ هنوز‌در‌حال‌پردازش
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import _rtloop

_HAS_MONGO_URI = bool(os.environ.get("MONGODB_URI"))

if _HAS_MONGO_URI:
    import ai_solver
    from ai_solver import AIConfigError


def _mongo_available() -> bool:
    if not _HAS_MONGO_URI:
        return False
    import socket
    from urllib.parse import urlparse
    u = urlparse(os.environ["MONGODB_URI"])
    try:
        socket.create_connection((u.hostname or "127.0.0.1", u.port or 27017), 1).close()
        return True
    except OSError:
        return False


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClientCtx:
    """httpx.AsyncClient ماک با صف پاسخ‌های GET."""

    responses = []   # [(status, payload), ...]

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        item = _FakeClientCtx.responses.pop(0) if _FakeClientCtx.responses \
            else (200, {})
        status, payload = item if isinstance(item, tuple) else (item, {})
        return _FakeResp(status, payload)


@unittest.skipUnless(_mongo_available(), "Mongo در دسترس نیست")
class WaitFileActiveTests(unittest.TestCase):

    def setUp(self):
        _rtloop.adopt()

    def test_polls_until_active(self):
        _FakeClientCtx.responses = [
            (200, {'name': 'files/a', 'state': 'PROCESSING'}),
            (200, {'name': 'files/a', 'state': 'PROCESSING'}),
            (200, {'name': 'files/a', 'state': 'ACTIVE',
                   'uri': 'https://x/files/a'}),
        ]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _FakeClientCtx), \
             mock.patch.object(ai_solver.asyncio, 'sleep',
                               _rtloop._fast_sleep if hasattr(_rtloop, '_fast_sleep')
                               else _noop_sleep):
            out = _rtloop.run(ai_solver._gemini_wait_file_active(
                'k', {'name': 'files/a', 'state': 'PROCESSING'},
                timeout=10))
        self.assertEqual(out['state'], 'ACTIVE')

    def test_failed_state(self):
        _FakeClientCtx.responses = [(200, {'name': 'files/b',
                                           'state': 'FAILED'})]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _FakeClientCtx), \
             mock.patch.object(ai_solver.asyncio, 'sleep', _noop_sleep):
            out = _rtloop.run(ai_solver._gemini_wait_file_active(
                'k', {'name': 'files/b', 'state': 'PROCESSING'}, timeout=5))
        self.assertEqual(out['state'], 'FAILED')

    def test_timeout_leaves_processing(self):
        # هیچ پاسخی نمی‌دهیم → sleep ماک بلافاصله برمی‌گردد → timeout
        _FakeClientCtx.responses = []
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _FakeClientCtx), \
             mock.patch.object(ai_solver.asyncio, 'sleep', _noop_sleep):
            out = _rtloop.run(ai_solver._gemini_wait_file_active(
                'k', {'name': 'files/c', 'state': 'PROCESSING'},
                timeout=0.0))
        self.assertEqual(out['state'], 'PROCESSING')

    def test_404_means_failed(self):
        _FakeClientCtx.responses = [(404, {})]
        with mock.patch.object(ai_solver.httpx, 'AsyncClient', _FakeClientCtx), \
             mock.patch.object(ai_solver.asyncio, 'sleep', _noop_sleep):
            out = _rtloop.run(ai_solver._gemini_wait_file_active(
                'k', {'name': 'files/d', 'state': 'PROCESSING'}, timeout=5))
        self.assertEqual(out['state'], 'FAILED')


async def _noop_sleep(_s):
    return None


@unittest.skipUnless(_mongo_available(), "Mongo در دسترس نیست")
class SelfHealStreamTests(unittest.TestCase):
    """خطای 4xx بخاطر سند ⇒ جدا کردن سند + retry بدون سند."""

    def setUp(self):
        _rtloop.adopt()
        import database
        self.db = database.db
        self.uid = 881001
        _rtloop.run(self._cleanup())

    def tearDown(self):
        _rtloop.run(self._cleanup())

    async def _cleanup(self):
        await self.db.users.update_one(
            {'user_id': self.uid},
            {'$unset': {'ai_doc_uri': '', 'ai_doc_mime': '',
                        'ai_doc_name': '', 'ai_doc_at': ''}})

    def _fake_stream_provider(self, calls):
        async def _fn(**kwargs):
            calls.append(dict(kwargs))
            if kwargs.get('doc'):
                # همان 400 معروفِ «فایل در state درست نیست»
                raise AIConfigError(
                    "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — "
                    "ادمین باید از پنل هوشیار تنظیماتش رو چک کنه. (کد خطا: 400)",
                    detail='[FAILED_PRECONDITION] File files/abc is not in '
                           'ACTIVE state')
            yield {'type': 'delta', 'text': 'سلام! '}
            yield {'type': 'done', 'answer': 'سلام! جواب بدون سند.', 'tokens': 5}
        return _fn

    def test_doc_error_detaches_and_retries(self):
        calls, cleared = [], []

        async def fake_get_doc(uid):
            return {'uri': 'https://generativelanguage.googleapis.com/v1beta/files/abc',
                    'mime': 'application/pdf', 'name': 'جزوه', 'at': None}

        async def fake_clear_doc(uid):
            cleared.append(uid)

        async def fake_notes(uid):
            return []

        async def fake_cfg():
            return {'enabled': True, 'api_key': 'k', 'provider': 'gemini',
                    'model': 'gemini-2.5-flash', 'system_prompt': 'تو کمک هستی.',
                    'thinking': 'auto', 'api_key_error': ''}

        fn = self._fake_stream_provider(calls)
        with mock.patch.object(ai_solver, 'get_ai_config', fake_cfg), \
             mock.patch.dict(ai_solver.STREAM_PROVIDERS, {'gemini': fn}), \
             mock.patch.object(self.db, 'ai_get_doc', fake_get_doc), \
             mock.patch.object(self.db, 'ai_clear_doc', fake_clear_doc), \
             mock.patch.object(self.db, 'ai_get_profile_notes', fake_notes):
            events = _rtloop.run(self._collect())

        self.assertEqual(len(calls), 2)               # اول با سند، بعد بدون
        self.assertIsNotNone(calls[0]['doc'])
        self.assertIsNone(calls[1]['doc'])
        self.assertEqual(cleared, [self.uid])         # سند جدا شد
        self.assertTrue(any(e['type'] == 'done' for e in events))

    def test_config_error_without_doc_propagates(self):
        """4xx بدونِ سند ⇒ retry نمی‌کنیم؛ خطا همان‌جا می‌ماند."""
        calls = []

        async def _fn(**kwargs):
            calls.append(1)
            raise AIConfigError("کلید API نامعتبره ... (کد خطا: 400)")
            yield  # pragma: no cover

        async def fake_cfg():
            return {'enabled': True, 'api_key': 'k', 'provider': 'gemini',
                    'model': 'm', 'system_prompt': 's', 'thinking': 'auto',
                    'api_key_error': ''}

        async def fake_notes(uid):
            return []

        with mock.patch.object(ai_solver, 'get_ai_config', fake_cfg), \
             mock.patch.dict(ai_solver.STREAM_PROVIDERS, {'gemini': _fn}), \
             mock.patch.object(self.db, 'ai_get_profile_notes', fake_notes):
            with self.assertRaises(AIConfigError):
                _rtloop.run(self._collect())
        self.assertEqual(len(calls), 1)               # فقط یک تلاش

    def test_skip_doc_skips_fetch(self):
        """skip_doc=True ⇒ سند اصلاً خوانده نمی‌شود (سوالِ اولِ بعد از
        آپلودِ هنوز PROCESSING)."""
        calls, fetched = [], []

        async def fake_get_doc(uid):
            fetched.append(uid)
            return {'uri': 'x', 'mime': 'application/pdf', 'name': 'j',
                    'at': None}

        async def fake_notes(uid):
            return []

        async def fake_cfg():
            return {'enabled': True, 'api_key': 'k', 'provider': 'gemini',
                    'model': 'm', 'system_prompt': 's', 'thinking': 'auto',
                    'api_key_error': ''}

        async def _fn(**kwargs):
            calls.append(kwargs)
            yield {'type': 'done', 'answer': 'ok', 'tokens': 1}

        with mock.patch.object(ai_solver, 'get_ai_config', fake_cfg), \
             mock.patch.dict(ai_solver.STREAM_PROVIDERS, {'gemini': _fn}), \
             mock.patch.object(self.db, 'ai_get_doc', fake_get_doc), \
             mock.patch.object(self.db, 'ai_get_profile_notes', fake_notes):
            events = _rtloop.run(self._collect(skip_doc=True))
        self.assertEqual(fetched, [])                 # سند خوانده نشد
        self.assertIsNone(calls[0]['doc'])
        self.assertTrue(events)

    async def _collect(self, **kw):
        out = []
        async for ev in ai_solver.ask_ai_stream(text='سلام', uid=self.uid, **kw):
            out.append(ev)
        return out


if __name__ == "__main__":
    unittest.main(verbosity=2)
