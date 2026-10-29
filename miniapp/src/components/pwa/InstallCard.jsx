/* ─────────────────────────────────────────────────────────────
   📲 نصب اپلیکیشن (PWA) — یک کارت، سه سکو

   • Android/Chrome و Windows/Edge: رویداد `beforeinstallprompt` را
     نگه می‌داریم و دکمهٔ «نصب» همان پرامپت بومی را باز می‌کند.
   • iOS/Safari: پرامپت بومی وجود ندارد؛ راهنمای «افزودن به صفحهٔ
     خانه» نشان داده می‌شود (تنها راه واقعی روی iOS).
   • اگر همین حالا نصب‌شده اجرا شود، کارت اصلاً رندر نمی‌شود.
   ───────────────────────────────────────────────────────────── */

import { useEffect, useState } from 'react';

import { isStandalone, platform } from '../../lib/appMode';
import Icon, { Glyph } from '../ui/Icon';

const DISMISS_KEY = 'humsyar_pwa_install_dismissed_v1';

/** رویداد نصب را در سطح ماژول نگه می‌داریم (قبل از mount اپ رخ می‌دهد). */
let deferredPrompt = null;
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    window.dispatchEvent(new CustomEvent('pwa:installable'));
  });
  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    window.dispatchEvent(new CustomEvent('pwa:installed'));
  });
}

export function canInstall() {
  return Boolean(deferredPrompt);
}

export default function InstallCard({ compact = false }) {
  const [available, setAvailable] = useState(canInstall());
  const [installed, setInstalled] = useState(isStandalone());
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === '1';
    } catch (_) {
      return false;
    }
  });

  const plat = platform();

  useEffect(() => {
    const onAvailable = () => setAvailable(true);
    const onInstalled = () => {
      setInstalled(true);
      setAvailable(false);
    };
    window.addEventListener('pwa:installable', onAvailable);
    window.addEventListener('pwa:installed', onInstalled);
    return () => {
      window.removeEventListener('pwa:installable', onAvailable);
      window.removeEventListener('pwa:installed', onInstalled);
    };
  }, []);

  if (installed || dismissed) return null;

  // روی iOS و مرورگرهایی که پرامپت ندارند، فقط راهنما منطقی است
  const showNative = available;
  const showIosHint = !available && plat === 'ios';
  if (!showNative && !showIosHint) return null;

  async function install() {
    if (!deferredPrompt) return;
    try {
      deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      if (choice?.outcome === 'accepted') setInstalled(true);
    } catch (_) {
      /* کاربر انصراف داد */
    } finally {
      deferredPrompt = null;
      setAvailable(false);
    }
  }

  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, '1');
    } catch (_) {
      /* ignore */
    }
  }

  return (
    <section className={`pwa-install${compact ? ' pwa-install--compact' : ''}`}>
      <div className="pwa-install__icon">
        <Glyph value="📲" size={20} />
      </div>

      <div className="pwa-install__body">
        <b>نصب هامزیار روی دستگاه</b>
        {showNative ? (
          <span>
            {plat === 'windows'
              ? 'به‌صورت یک برنامهٔ ویندوزی نصب می‌شود؛ آیکون روی دسکتاپ.'
              : 'مثل یک اپ معمولی نصب می‌شود؛ آیکون روی صفحهٔ اصلی.'}
          </span>
        ) : (
          <span>
            در Safari دکمهٔ اشتراک‌گذاری (مربع با فلش) را بزن و
            «افزودن به صفحهٔ خانه» را انتخاب کن.
          </span>
        )}

        <div className="pwa-install__actions">
          {showNative && (
            <button type="button" className="btn btn-xs is-primary" onClick={install}>
              <Icon name="download" size={13} />
              نصب
            </button>
          )}
          <button type="button" className="btn btn-xs" onClick={dismiss}>
            بعداً
          </button>
        </div>
      </div>
    </section>
  );
}
