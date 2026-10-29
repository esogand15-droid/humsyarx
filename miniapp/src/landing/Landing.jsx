import React from 'react';

/* ─────────────────────────────────────────────────────────────
   🏠 لندینگ هامزیار — صفحهٔ ریشهٔ دامنه (/)

   جهت طراحی از Skill «UI/UX Pro Max» گرفته شده (مرجع: docs/UIPRO-DESIGN-DIRECTION.md):
     • الگو  : Trust & Authority + Conversion
               (Hero → اعتماد → معرفی راه‌حل → مسیر روشن CTA)
     • سبک   : Accessible & Ethical + Minimalism & Swiss Style
               (شبکهٔ منظم، فضای سفید، بدون تزئین اضافه، حرکت ۲۰۰ms)
     • رنگ   : آبی/فیروزه‌ای برند خودِ هامزیار (توکن‌های --hym-*)
               ـ لهجه فقط برای CTA، نه برای همه‌چیز
     • فونت  : Vazirmatn خودمیزبان (بدون CDN)

   قاعده‌های رعایت‌شده که از همان Skill آمد:
     - هیچ ایموجی به‌جای آیکون نیست (همه SVG خطی)
     - focus-visible واضح روی هر کنترل، ترتیب tab منطقی
     - prefers-reduced-motion محترم است
     - هدف لمسی ≥ 44px، فاصلهٔ ≥ 8px بین کنترل‌ها
     - h1 یکتا، سرفصل‌های سلسله‌مراتبی، skip-link
     - 100dvh به‌جای 100vh
     - داده‌های «اثبات» فقط چیزهایی است که واقعاً درست است (بدون آمار ساختگی)
   ───────────────────────────────────────────────────────────── */

/* آیکون‌های خطی — بدون وابستگی تازه، بدون ایموجی */
const ICONS = {
  calendar: 'M8 2v3M16 2v3M3.5 9h17M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
  exam: 'M9 3h6a2 2 0 0 1 2 2v14l-5-3-5 3V5a2 2 0 0 1 2-2ZM9 8h6M9 12h4',
  spark: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18',
  book: 'M4 5a2 2 0 0 1 2-2h5v18H6a2 2 0 0 1-2-2V5ZM20 5a2 2 0 0 0-2-2h-5v18h5a2 2 0 0 0 2-2V5Z',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  support: 'M12 3a9 9 0 0 0-9 9v5a2 2 0 0 0 2 2h2v-7H5a7 7 0 0 1 14 0h-2v7h2a2 2 0 0 0 2-2v-5a9 9 0 0 0-9-9Z',
  shield: 'M12 3l7 3v6c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6l7-3Z',
  key: 'M15 8a4 4 0 1 1-3.5 5.9L5 20.5H3v-3l6.6-6.6A4 4 0 0 1 15 8Z',
  phone: 'M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm4 16h2',
  monitor: 'M3 5h18v11H3zM9 20h6M12 16v4',
  tablet: 'M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm6 15h2',
  arrow: 'M14 5l-7 7 7 7',
  check: 'M4 12.5 9.5 18 20 6',
  telegram: 'M21 4 3 11l5 2 2 6 3-4 5 3 3-14Z',
};

function Icon({ name, size = 22, className = '', strokeWidth = 1.7 }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={ICONS[name] || ICONS.spark} />
    </svg>
  );
}

const FEATURES = [
  {
    icon: 'calendar',
    title: 'برنامهٔ هفتگی، هم‌زمان چارت و جدول',
    text:
      'کلاس‌های هفته در یک نمای رنگی و یک جدول دقیق، با نام کامل درس، استاد و ساعت — ' +
      'به‌همراه شمارش کلاس‌ها و آزمون‌ها و جلسه‌های جبرانی.',
  },
  {
    icon: 'exam',
    title: 'بانک سؤال و مرکز آزمون',
    text:
      'تمرین بر اساس مبحث، آزمون زمان‌دار، مرور پاسخ‌های اشتباه و تاریخچهٔ سؤال‌هایی که پرسیده‌ای.',
  },
  {
    icon: 'spark',
    title: 'دستیار هوشمند هامزیار',
    text:
      'توضیح، خلاصه و ساخت سؤال از همان درس‌ها؛ پاسخ‌ها داخل همان اپ و با همان حساب، بدون ابزار جداگانه.',
  },
  {
    icon: 'book',
    title: 'جزوه و منابع درسی',
    text:
      'فایل‌های درسی و کتاب‌ها، دسته‌بندی‌شده بر اساس درس و گروه — با دسترسی کنترل‌شده.',
  },
  {
    icon: 'chart',
    title: 'پیشرفت و رتبه',
    text:
      'درصد آمادگی، دقت پاسخ‌ها و روند هفتگی؛ تا بدانی کجا قوی هستی و کجا باید برگردی عقب.',
  },
  {
    icon: 'support',
    title: 'پشتیبانی و اعلان',
    text:
      'تیکت مستقیم به مدیریت، اعلان تیکت و تغییر برنامه — همه در یک صندوق پیام، بدون گم شدن در چت.',
  },
];

const STEPS = [
  {
    n: '۱',
    title: 'در تلگرام شروع کن',
    text: 'ربات هامزیار را باز کن، ثبت‌نام کن و منتظر تأیید مدیریت بمان.',
  },
  {
    n: '۲',
    title: 'کد ورود بگیر',
    text: 'روی «ورود به نسخهٔ وب» بزن، شناسه‌ات را وارد کن و کد ۶ رقمی را از تلگرام بگیر. رمزی در کار نیست.',
  },
  {
    n: '۳',
    title: 'روی هر دستگاه ادامه بده',
    text: 'گوشی، تبلت یا ویندوز — با همان حساب. می‌توانی نسخهٔ نصب‌شدنی را روی صفحهٔ اصلی بگذاری.',
  },
];

const PLATFORMS = [
  { icon: 'phone', title: 'آیفون', text: 'سافاری ← اشتراک‌گذاری ← «افزودن به صفحهٔ خانه».' },
  { icon: 'tablet', title: 'اندروید', text: 'کروم ← منو ← «نصب برنامه»؛ آیکون بین برنامه‌ها می‌آید.' },
  { icon: 'monitor', title: 'ویندوز', text: 'کروم یا اج ← آیکون نصب در نوار آدرس ← پنجرهٔ مستقل.' },
];

const FAQ = [
  {
    q: 'برای ورود به نسخهٔ وب باید رمز بسازم؟',
    a: 'نه. ورود با کد یک‌بارمصرف انجام می‌شود که ربات هامزیار در تلگرام برایت می‌فرستد؛ کد ۵ دقیقه اعتبار دارد و بعد از ورود، نشست تا ۳۰ روز روی همان دستگاه می‌ماند.',
  },
  {
    q: 'نسخهٔ وب و مینی‌اپ تلگرام فرق دارند؟',
    a: 'هر دو از یک کد و یک API استفاده می‌کنند. تفاوت فقط در مسیر ورود است: داخل تلگرام با همان حساب تلگرام وارد می‌شوی، بیرون از تلگرام با کد.',
  },
  {
    q: 'اگر حساب من هنوز تأیید نشده باشد چه؟',
    a: 'کد ورود فقط برای حساب تأییدشده فرستاده می‌شود. اگر در انتظار تأیید هستی، پیام ربات را ببین؛ به‌محض تأیید مدیریت، ورودت فعال می‌شود.',
  },
  {
    q: 'اپ اندروید و iOS؟',
    a: 'نسخهٔ وب دقیقاً به‌صورت اپ روی صفحهٔ اصلی نصب می‌شود. نسخهٔ بومی اندروید و iOS در دست ساخت است و بعد از انتشار همین‌جا اعلام می‌شود.',
  },
];

export default function Landing() {
  const [botUrl, setBotUrl] = React.useState('');

  /* آدرس ربات فقط از تنظیمات واقعیِ سرور خوانده می‌شود
     (`/api/web/auth/config` → support_url). هیچ نام کاربری حدس زده نمی‌شود. */
  React.useEffect(() => {
    let alive = true;
    fetch('/api/web/auth/config', { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (alive && data && typeof data.support_url === 'string') setBotUrl(data.support_url);
      })
      .catch(() => {
        /* بی‌صدا: نبودن این آدرس نباید لندینگ را بشکند */
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <a className="lp-skip" href="#main">
        رفتن به محتوای اصلی
      </a>

      <header className="lp-header">
        <div className="lp-wrap lp-header__inner">
          <a className="lp-brand" href="/" aria-label="هامزیار — خانه">
            <img
              className="lp-brand__logo"
              src="/icons/icon-192.png"
              width="40"
              height="40"
              alt=""
              loading="eager"
              decoding="async"
            />
            <span className="lp-brand__text">
              <b>هامزیار</b>
              <small>دستیار دانشجوی پزشکی</small>
            </span>
          </a>

          <nav className="lp-nav" aria-label="بخش‌های صفحه">
            <a href="#features">امکانات</a>
            <a href="#how">چطور کار می‌کند</a>
            <a href="#platforms">نصب</a>
            <a href="#faq">سؤال‌های متداول</a>
          </nav>

          <div className="lp-header__cta">
            <a className="lp-btn lp-btn--primary" href="/pwa/">
              ورود به نسخهٔ وب
              <Icon name="arrow" size={18} />
            </a>
          </div>
        </div>
      </header>

      <main id="main">
        {/* ── ۱) Hero: مأموریت + مسیر روشن ───────────────────── */}
        <section className="lp-hero" aria-labelledby="hero-title">
          <div className="lp-wrap lp-hero__grid">
            <div className="lp-hero__copy">
              <span className="lp-pill">
                <Icon name="shield" size={16} />
                همان حساب تلگرام — بدون رمز
              </span>

              <h1 id="hero-title">
                همه‌چیزِ دانشجوی پزشکی،
                <br />
                <span className="lp-hero__accent">در یک اپ آرام و منظم</span>
              </h1>

              <p className="lp-hero__lead">
                برنامهٔ هفتگی، بانک سؤال و آزمون، جزوه و منابع، دستیار هوشمند و پشتیبانی —
                با یک حساب، هم داخل تلگرام و هم در نسخهٔ نصب‌شدنی روی گوشی و ویندوز.
              </p>

              <div className="lp-hero__actions">
                <a className="lp-btn lp-btn--primary lp-btn--lg" href="/pwa/">
                  ورود به نسخهٔ وب
                  <Icon name="arrow" size={18} />
                </a>
                {botUrl ? (
                  <a
                    className="lp-btn lp-btn--ghost lp-btn--lg"
                    href={botUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Icon name="telegram" size={18} />
                    باز کردن در تلگرام
                  </a>
                ) : (
                  <a className="lp-btn lp-btn--ghost lp-btn--lg" href="/app/">
                    نسخهٔ داخل تلگرام
                    <Icon name="arrow" size={18} />
                  </a>
                )}
              </div>

              <ul className="lp-hero__facts">
                <li>
                  <Icon name="check" size={16} /> کد ورود در تلگرام، بدون رمز
                </li>
                <li>
                  <Icon name="check" size={16} /> بدون نصب از استور
                </li>
                <li>
                  <Icon name="check" size={16} /> دادهٔ درسی، در همان حساب
                </li>
              </ul>
            </div>

            {/* تصویر محصول: همان آیکون رسمی + یک پیش‌نمایش سبک، بدون اسکرین‌شات جعلی */}
            <div className="lp-hero__art" aria-hidden="true">
              <div className="lp-hero__glow" />
              <img
                className="lp-hero__emblem"
                src="/icons/icon-512.png"
                width="512"
                height="512"
                alt=""
                decoding="async"
              />
            </div>
          </div>
        </section>

        {/* ── ۲) اعتماد: چیزهایی که واقعاً درست‌اند ───────────── */}
        <section className="lp-proof" aria-label="چرا هامزیار">
          <div className="lp-wrap lp-proof__grid">
            <div className="lp-proof__item">
              <Icon name="key" size={24} />
              <b>ورود بدون رمز</b>
              <span>کد یک‌بارمصرف از ربات؛ کد فقط هش‌شده ذخیره می‌شود.</span>
            </div>
            <div className="lp-proof__item">
              <Icon name="shield" size={24} />
              <b>یک هویت، سه سطح</b>
              <span>دانشجو، پشتیبان و مدیریت — روی یک حساب و یک دیتابیس.</span>
            </div>
            <div className="lp-proof__item">
              <Icon name="phone" size={24} />
              <b>بدون استور</b>
              <span>نسخهٔ نصب‌شدنی مستقیم از مرورگر نصب می‌شود.</span>
            </div>
          </div>
        </section>

        {/* ── ۳) معرفی راه‌حل ────────────────────────────────── */}
        <section className="lp-section" id="features" aria-labelledby="features-title">
          <div className="lp-wrap">
            <header className="lp-section__head">
              <h2 id="features-title">چه چیزی داخل هامزیار هست؟</h2>
              <p>
                هر بخش یک کار مشخص را تمام می‌کند؛ نه فهرستی از دکمه‌های بی‌مصرف.
              </p>
            </header>

            <div className="lp-cards">
              {FEATURES.map((f) => (
                <article className="lp-card" key={f.title}>
                  <span className="lp-card__icon">
                    <Icon name={f.icon} size={22} />
                  </span>
                  <h3>{f.title}</h3>
                  <p>{f.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── ۴) مسیر استفاده ────────────────────────────────── */}
        <section className="lp-section lp-section--alt" id="how" aria-labelledby="how-title">
          <div className="lp-wrap">
            <header className="lp-section__head">
              <h2 id="how-title">سه قدم تا شروع</h2>
              <p>هیچ رمزی نمی‌سازی، هیچ فایلی نصب نمی‌کنی.</p>
            </header>

            <ol className="lp-steps">
              {STEPS.map((s) => (
                <li className="lp-step" key={s.n}>
                  <span className="lp-step__num" aria-hidden="true">
                    {s.n}
                  </span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ── ۵) نصب روی سکوها + نشانهٔ «در دست ساخت» ─────────── */}
        <section className="lp-section" id="platforms" aria-labelledby="platforms-title">
          <div className="lp-wrap">
            <header className="lp-section__head">
              <h2 id="platforms-title">نصب روی دستگاهت</h2>
              <p>
                نسخهٔ وب یک اپ واقعی است: پنجرهٔ مستقل، آیکون روی صفحهٔ اصلی و نمایش آفلاینِ
                صفحهٔ آفلاین.
              </p>
            </header>

            <div className="lp-platforms">
              {PLATFORMS.map((p) => (
                <article className="lp-platform" key={p.title}>
                  <Icon name={p.icon} size={26} />
                  <h3>{p.title}</h3>
                  <p>{p.text}</p>
                </article>
              ))}
            </div>

            <p className="lp-soon">
              <span className="lp-soon__badge">در دست ساخت</span>
              نسخهٔ بومی اندروید و iOS در حال ساخت است؛ تا آن زمان همین نسخهٔ وب دقیقاً
              مثل اپ کار می‌کند.
            </p>
          </div>
        </section>

        {/* ── ۶) پرسش‌های متداول ─────────────────────────────── */}
        <section className="lp-section lp-section--alt" id="faq" aria-labelledby="faq-title">
          <div className="lp-wrap lp-faq">
            <header className="lp-section__head">
              <h2 id="faq-title">سؤال‌های متداول</h2>
            </header>

            {FAQ.map((item, i) => (
              <details className="lp-faq__item" key={item.q} open={i === 0}>
                <summary>{item.q}</summary>
                <p>{item.a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* ── ۷) CTA پایانی ──────────────────────────────────── */}
        <section className="lp-final" aria-labelledby="final-title">
          <div className="lp-wrap lp-final__inner">
            <h2 id="final-title">آماده‌ای شروع کنی؟</h2>
            <p>با همان حساب تلگرام وارد شو؛ اگر حساب نداری، اول در ربات ثبت‌نام کن.</p>
            <div className="lp-hero__actions lp-hero__actions--center">
              <a className="lp-btn lp-btn--primary lp-btn--lg" href="/pwa/">
                ورود به نسخهٔ وب
                <Icon name="arrow" size={18} />
              </a>
              {botUrl && (
                <a
                  className="lp-btn lp-btn--ghost lp-btn--lg"
                  href={botUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Icon name="telegram" size={18} />
                  ربات هامزیار
                </a>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap lp-footer__inner">
          <div className="lp-footer__brand">
            <img src="/icons/icon-192.png" width="28" height="28" alt="" decoding="async" />
            <span>هامزیار — دستیار دانشجوی پزشکی</span>
          </div>

          <nav className="lp-footer__links" aria-label="پیوندهای پانوشت">
            <a href="/pwa/">نسخهٔ وب</a>
            <a href="/app/">نسخهٔ تلگرام</a>
            <a href="/admin/">پنل مدیریت</a>
            <a href="/api/health">وضعیت سرویس</a>
          </nav>

          <p className="lp-footer__note">
            نسخهٔ بومی اندروید و iOS در دست ساخت است · این صفحه بدون هیچ اسکریپت ردیابی
            خارجی اجرا می‌شود.
          </p>
        </div>
      </footer>
    </>
  );
}
