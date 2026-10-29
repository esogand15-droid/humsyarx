/* ─────────────────────────────────────────────────────────────
   🔐 ورود نسخهٔ وب/PWA — دو مرحله، بدون رمز

   چرا این صفحه؟
   نسخهٔ نصب‌شدنی روی iOS/Android/Windows بیرون تلگرام اجرا می‌شود و
   `initData` ندارد. بدون این صفحه، اپ نصب می‌شد ولی «کار نمی‌کرد».

   جریان:
     ۱) شناسه (آیدی عددی تلگرام / @یوزرنیم / شماره دانشجویی)
     ۲) کد ۶ رقمی که ربات هامزیار در تلگرام می‌فرستد
     ۳) کوکی نشست (HttpOnly) صادر می‌شود و اپ بالا می‌آید

   هیچ‌جای این صفحه نمی‌گوید «این حساب هست یا نه» — پاسخ سرور هم
   عمداً یکسان است (ضد شمارش حساب).
   ───────────────────────────────────────────────────────────── */

import { useEffect, useMemo, useRef, useState } from 'react';

import api from '../../lib/api';
import { BOT_URL, isStandalone, platform } from '../../lib/appMode';
import { faNum } from '../../lib/format';
import Icon, { Glyph } from '../ui/Icon';

const RESEND_SECONDS = 60;

/** ارقام فارسی → لاتین (کاربر موبایل معمولاً فارسی تایپ می‌کند) */
function toLatinDigits(value) {
  return String(value || '')
    .replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
    .trim();
}

export default function WebLogin({ onDone }) {
  const [step, setStep] = useState('identifier'); // identifier | code
  const [identifier, setIdentifier] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [left, setLeft] = useState(0);

  const codeRef = useRef(null);
  const idRef = useRef(null);

  const plat = useMemo(() => platform(), []);
  const standalone = useMemo(() => isStandalone(), []);

  useEffect(() => {
    if (step === 'code') codeRef.current?.focus();
    else idRef.current?.focus();
  }, [step]);

  useEffect(() => {
    if (left <= 0) return undefined;
    const t = setTimeout(() => setLeft((v) => v - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);

  async function requestCode(event) {
    event?.preventDefault?.();
    const ident = toLatinDigits(identifier);
    if (!ident) {
      setError('شناسه را وارد کنید.');
      return;
    }

    setBusy(true);
    setError('');
    setNotice('');

    try {
      const { data } = await api.post('/api/web-auth/request', { identifier: ident });
      setIdentifier(ident);
      setStep('code');
      setCode('');
      setLeft(RESEND_SECONDS);
      setNotice(data?.message || 'اگر حساب شما تأییدشده باشد، کد در تلگرام ارسال شد.');
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'ارسال کد ممکن نشد؛ دوباره تلاش کنید.');
      if (err?.response?.status === 429) setStep('code');
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(event) {
    event?.preventDefault?.();
    const value = toLatinDigits(code);
    if (value.length < 4) {
      setError('کد ارسال‌شده را کامل وارد کنید.');
      return;
    }

    setBusy(true);
    setError('');

    try {
      await api.post('/api/web-auth/verify', { identifier, code: value });
      onDone?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'کد نامعتبر یا منقضی است.');
      setCode('');
      codeRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pwa-auth" dir="rtl">
      <div className="pwa-auth__card">
        <div className="pwa-auth__brand">
          <span className="pwa-auth__logo">
            <Icon name="home" size={22} />
          </span>
          <div>
            <b>هامزیار</b>
            <i>ورود به نسخهٔ وب</i>
          </div>
        </div>

        {step === 'identifier' ? (
          <form onSubmit={requestCode} noValidate>
            <p className="pwa-auth__lead">
              برای ورود، شناسهٔ تلگرام یا شمارهٔ دانشجویی‌ات را وارد کن؛
              کد ورود از طریق <b>ربات هامزیار در تلگرام</b> برایت می‌آید.
            </p>

            <label className="pwa-auth__label" htmlFor="pwa-ident">
              شناسه
            </label>
            <input
              id="pwa-ident"
              ref={idRef}
              className="pwa-auth__input"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="آیدی عددی، @یوزرنیم یا شماره دانشجویی"
              inputMode="text"
              autoComplete="username"
              spellCheck={false}
              dir="ltr"
              disabled={busy}
            />

            {error && (
              <div className="pwa-auth__error" role="alert">
                <Icon name="info" size={14} />
                {error}
              </div>
            )}

            <button type="submit" className="btn btn-p btn-full pwa-auth__cta" disabled={busy}>
              {busy ? 'در حال ارسال…' : 'دریافت کد ورود'}
              {!busy && <Icon name="arrowLeft" size={15} />}
            </button>
          </form>
        ) : (
          <form onSubmit={submitCode} noValidate>
            <p className="pwa-auth__lead">
              کد ۶ رقمی به حساب <b dir="ltr">{identifier}</b> در تلگرام فرستاده شد.
            </p>

            {notice && (
              <div className="pwa-auth__notice">
                <Icon name="info" size={14} />
                {notice}
              </div>
            )}

            <label className="pwa-auth__label" htmlFor="pwa-code">
              کد ورود
            </label>
            <input
              id="pwa-code"
              ref={codeRef}
              className="pwa-auth__input pwa-auth__input--code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="••••••"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={8}
              dir="ltr"
              disabled={busy}
            />

            {error && (
              <div className="pwa-auth__error" role="alert">
                <Icon name="info" size={14} />
                {error}
              </div>
            )}

            <button type="submit" className="btn btn-p btn-full pwa-auth__cta" disabled={busy}>
              {busy ? 'در حال بررسی…' : 'ورود'}
              {!busy && <Icon name="check" size={15} />}
            </button>

            <div className="pwa-auth__row">
              <button
                type="button"
                className="btn btn-xs"
                onClick={requestCode}
                disabled={busy || left > 0}
              >
                <Icon name="refresh" size={13} />
                {left > 0 ? `ارسال دوباره (${faNum(left)})` : 'ارسال دوباره'}
              </button>

              <button
                type="button"
                className="btn btn-xs"
                onClick={() => {
                  setStep('identifier');
                  setError('');
                  setNotice('');
                }}
                disabled={busy}
              >
                ویرایش شناسه
              </button>
            </div>
          </form>
        )}

        <div className="pwa-auth__foot">
          <span>
            <Glyph value="💬" size={13} /> کد در تلگرام می‌آید
          </span>
          {BOT_URL && BOT_URL !== 'https://t.me/' && (
            <a className="pwa-auth__link" href={BOT_URL} target="_blank" rel="noreferrer">
              باز کردن ربات
            </a>
          )}
        </div>

        {standalone && (
          <div className="pwa-auth__hint">
            <Icon name="check" size={13} />
            این صفحه در حالت نصب‌شده اجرا می‌شود — پس از ورود، تا {faNum(30)} روز
            باز نمی‌مانی خارج شوی.
          </div>
        )}

        {!standalone && plat === 'ios' && (
          <div className="pwa-auth__hint">
            <Icon name="info" size={13} />
            برای نصب روی iPhone: دکمهٔ اشتراک‌گذاری Safari ← «افزودن به صفحهٔ خانه».
          </div>
        )}
      </div>
    </div>
  );
}
