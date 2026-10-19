import { useEffect, useMemo, useRef, useState } from 'react';

import { Brand, Button, Input } from '../components';
import { api, errorText } from '../lib/api';
import type { StartPayload } from '../lib/api';
import { useSession } from '../lib/session';

/* ورود دو مرحله‌ای (موج P1) — بدون تلگرام‌وب‌اپ:
   ۱) شناسه (یوزرنیم تلگرام یا شمارهٔ دانشجویی)
   ۲) کد یک‌بارمصرف که ربات هامزیار در تلگرام می‌فرستد
   هیچ رمز عبوری وجود ندارد، پس چیزی برای فراموش‌کردن یا لو رفتن نیست. */

type Step = 'identifier' | 'code';

export function LoginScreen() {
  const { refresh, offline, config } = useSession();

  const [step, setStep] = useState<Step>('identifier');
  const [identifier, setIdentifier] = useState('');
  const [code, setCode] = useState('');
  const [challenge, setChallenge] = useState<StartPayload | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(0);

  const codeRef = useRef<HTMLInputElement>(null);
  const otpLength = config?.otp_length ?? 6;

  // شمارش معکوس ارسال دوباره — از مقدار سرور، نه عدد ثابت در UI
  useEffect(() => {
    if (left <= 0) return;
    const id = window.setTimeout(() => setLeft((v) => v - 1), 1000);
    return () => window.clearTimeout(id);
  }, [left]);

  useEffect(() => {
    if (step === 'code') codeRef.current?.focus();
  }, [step]);

  const canSend = useMemo(() => identifier.trim().length >= 3, [identifier]);
  const canVerify = useMemo(() => code.replace(/\D/g, '').length >= 4, [code]);

  async function send() {
    setError('');
    setBusy(true);
    try {
      const res = await api.start(identifier.trim());
      setChallenge(res);
      setCode('');
      setLeft(res.resend_in);
      setStep('code');
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function verify(value: string) {
    if (!challenge) return;
    setError('');
    setBusy(true);
    try {
      await api.verify(challenge.challenge, value.replace(/\D/g, ''));
      // گارد اپ بعد از refresh تصمیم می‌گیرد: خانه، «در انتظار تأیید» یا «تعلیق»
      await refresh();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  if (step === 'code') {
    return (
      <div className="auth">
        <div className="auth__head">
          <Brand size="lg" />
          <h1 className="h1 mt-16">کد را وارد کن</h1>
          <p className="body mt-8">
            {challenge?.hint ?? 'کد به تلگرام تو فرستاده شد.'}
          </p>
        </div>

        <form
          className="auth__form"
          onSubmit={(e) => {
            e.preventDefault();
            if (canVerify && !busy) void verify(code);
          }}
        >
          <Input
            ref={codeRef as never}
            label={`کد ${otpLength} رقمی`}
            code
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, '').slice(0, otpLength))}
            inputMode="numeric"
            autoComplete="one-time-code"
            dir="ltr"
            placeholder="— — — — — —"
            error={error || undefined}
            aria-describedby="otp-help"
          />

          <p className="tiny" id="otp-help">
            کد یک‌بارمصرف است و تا {Math.round((challenge?.expires_in ?? 300) / 60)} دقیقه معتبر
            می‌ماند.
          </p>

          <Button type="submit" block loading={busy} disabled={!canVerify}>
            ورود به هامزیار
          </Button>

          <div className="auth__row">
            <button
              type="button"
              className="linkbtn"
              onClick={() => void send()}
              disabled={left > 0 || busy}
            >
              {left > 0 ? `ارسال دوباره تا ${left} ثانیه` : 'ارسال دوبارهٔ کد'}
            </button>
            <button
              type="button"
              className="linkbtn"
              onClick={() => {
                setStep('identifier');
                setError('');
                setCode('');
              }}
            >
              تغییر شناسه
            </button>
          </div>
        </form>

        <p className="tiny auth__foot">
          کد را فقط در چت رسمی ربات هامزیار می‌بینی. هیچ‌کس — از جمله پشتیبانی — نباید کد را از
          تو بپرسد.
        </p>
      </div>
    );
  }

  return (
    <div className="auth">
      <div className="auth__head">
        <Brand size="lg" />
        <h1 className="h1 mt-16">ورود به هامزیار</h1>
        <p className="body mt-8">
          شناسهٔ حسابَت را وارد کن؛ کد ورود به تلگرام خودت فرستاده می‌شود. رمز عبوری لازم نیست.
        </p>
      </div>

      <form
        className="auth__form"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend && !busy) void send();
        }}
      >
        <Input
          label="یوزرنیم تلگرام یا شمارهٔ دانشجویی"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          dir="ltr"
          placeholder="ali_ahmadi یا 40213456"
          error={error || undefined}
          disabled={busy}
        />

        {offline && (
          <p className="notice notice--warn" role="status">
            اتصال به سرور برقرار نشد. اگر همین حالا تلاش کنی، دوباره پیام خطا می‌گیری؛ بعد از
            وصل‌شدن اینترنت دوباره امتحان کن.
          </p>
        )}

        <Button type="submit" block loading={busy} disabled={!canSend}>
          دریافت کد ورود
        </Button>
      </form>

      <p className="tiny auth__foot">
        حساب هامزیار همان حسابی است که در ربات تلگرام ساخته‌ای. اگر هنوز عضو نیستی، اول از ربات
        ثبت‌نام کن.
      </p>
    </div>
  );
}
