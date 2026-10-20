import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { Badge, Chip, Note, SectionHead } from '../components/ui';
import { PageTitle } from '../components/Shell';
import { useProto } from '../lib/store';

/* ═══════════════════════════════════════════════════════════════════
   سند تحویل — بازرسی، معماری اطلاعات، دو جهت بصری، مشخصات، محدودیت‌ها
   این صفحه همان «سند طراحی» است، ولی قابل کلیک و همراه خود نسخهٔ طراحی.
   ═══════════════════════════════════════════════════════════════════ */

const AUDIT_CONFIRMED: [string, string, string][] = [
  ['منابع علوم پایه (درس/جلسه/فایل)', 'GET /api/web/library/* · /api/resources/*', 'P2 — پیاده‌شده در وب'],
  ['خواندن PDF/ویدیو/صوت + یادداشت روی PDF', '/api/web/reader/* · /api/web/ink/*', 'P3/P4 — پیاده‌شده'],
  ['بانک سؤال: تمرین، آمار، تاریخچه', '/api/web/exam/*', 'P5 — پیاده‌شده'],
  ['آزمون زمان‌دار + کارنامه + بازبینی', '/api/web/exam/mock/*', 'P5.2 — پیاده‌شده'],
  ['هوشیار (گفتگو + سهمیهٔ روزانه)', '/api/routers/ai.py · feature ai_chat', 'در ربات/مینی‌اپ هست؛ وب ندارد'],
  ['برنامهٔ کلاسی و آزمون‌ها', 'GET /api/schedule · /api/schedule/exams', 'موجود؛ وب ندارد'],
  ['اشتراک، پلن‌ها، پرداخت', '/api/subscription/status · buy · zarinpal', 'موجود؛ وب ندارد'],
  ['پروفایل، رتبه، پرستیژ', '/api/profile · /api/profile/rank', 'موجود؛ وب ندارد'],
  ['اعلان‌ها و صندوق', '/api/notifications/*', 'موجود؛ وب ندارد'],
  ['جست‌وجوی سراسری', 'GET /api/global_search', 'موجود؛ وب ندارد'],
  ['گیت قابلیت (۷ فیچر enforced)', 'core/features.py · core/access.py', 'منبع حقیقت دسترسی'],
];

const AUDIT_UNKNOWN: [string, string][] = [
  ['ادامهٔ مطالعه (last position) یک منبع', 'در ریدر وب ذخیره می‌شود؛ قرارداد سراسری «آخرین منبع» هنوز تعریف نشده است.'],
  ['برنامه‌ریزی مطالعهٔ دستی (کار، هدف روزانه)', 'در محصول اندپوینت ندارد؛ در نقشهٔ راه پس از طراحی.'],
  ['لیست انتظار/یادآور آزمون از راه اعلان', 'سرویس اعلان هست، اما قاعدهٔ یادآوری آزمون تعریف نشده.'],
  ['پیوست PDF/تصویر در هوشیار وب', 'در ربات هست (ai.py)؛ پشتیبانی وب و محدودیت حجم باید تصمیم شود.'],
  ['قیمت و نام پلن‌ها', 'از پایگاه داده می‌آید؛ در این نسخه هیچ عددی جای‌گزین نشده.'],
];

const IA: [string, string, string][] = [
  ['/', 'خانه', 'ادامهٔ مطالعه، کارهای امروز، وضعیت هفته، تازه‌ها'],
  ['/library', 'منابع درسی', 'جست‌وجو، فیلتر درس/نوع، فهرست منابع'],
  ['/library/:id', 'جزئیات منبع', 'پیش‌نمایش، فراداده، تمرین مرتبط، وضعیت دسترسی'],
  ['/exam', 'بانک سؤال', 'انتخاب محدوده، آمار، دو مسیر: تمرین / آزمون'],
  ['/exam/practice', 'تمرین آزاد', 'سؤال، پاسخ، بازخورد، توضیح، نقشهٔ پیشرفت'],
  ['/exam/run', 'آزمون زمان‌دار', 'تنظیم، اجرا با تایمر، خروج با تأیید'],
  ['/exam/result', 'کارنامه', 'درصد، بازبینی سؤال‌به‌سؤال، تحلیل'],
  ['/ai', 'هوشیار', 'ریسهٔ گفتگوها، پاسخ ساخت‌یافته، منابع، کنش‌ها'],
  ['/plan', 'برنامهٔ مطالعه', 'هفته، آزمون‌های پیشِ رو، کارها'],
  ['/me', 'پیشرفت من', 'دقت، پیوستگی، پیشرفت درس‌ها، دستاوردها'],
  ['/me/subscription', 'اشتراک', 'وضعیت، مقایسهٔ پلن، تاریخ پرداخت'],
  ['/me/settings', 'تنظیمات', 'اطلاعات تحصیلی، اعلان، حریم خصوصی، امنیت'],
];

export function Handoff() {
  const { direction, setDirection } = useProto();
  const [tab, setTab] = useState<'audit' | 'ia' | 'directions' | 'specs' | 'handoff'>('audit');

  return (
    <div className="page page--narrow">
      <PageTitle
        title="سند تحویل و معماری اطلاعات"
        sub="بازرسی محصول، تصمیم‌های ناوبری، دو جهت بصری و مشخصات پیاده‌سازی"
        actions={
          <Link to="/system" className="btn btn--ghost btn--sm">
            <Icon name="layers" size={14} />
            سیستم طراحی
          </Link>
        }
      />

      <div className="tabs" role="tablist" style={{ marginBottom: 18 }}>
        {(
          [
            ['audit', '۱. بازرسی'],
            ['ia', '۲. معماری اطلاعات'],
            ['directions', '۳. دو جهت بصری'],
            ['specs', '۴. مشخصات'],
            ['handoff', '۵. تحویل'],
          ] as [typeof tab, string][]
        ).map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>
            {l}
          </button>
        ))}
      </div>

      {tab === 'audit' && (
        <>
          <SectionHead title="قابلیت‌های تأییدشده" hint="از کد و روترهای موجود مخزن" />
          <div className="panel panel--flush">
            {AUDIT_CONFIRMED.map(([f, e, s]) => (
              <div key={f} className="rrow" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(160px,0.9fr) auto' }}>
                <span className="rrow__t">{f}</span>
                <span className="xs ltr" style={{ color: 'var(--text-3)', direction: 'ltr', textAlign: 'left' }}>
                  {e}
                </span>
                <Badge tone={s.includes('پیاده') ? 'ok' : 'info'}>{s}</Badge>
              </div>
            ))}
          </div>

          <SectionHead title="ناشناخته‌ها و وابستگی‌ها" hint="پنهان نمی‌شوند؛ در نقشهٔ راه تصمیم می‌خواهند" />
          <div className="panel panel--flush">
            {AUDIT_UNKNOWN.map(([f, w]) => (
              <div key={f} className="rrow" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.4fr)' }}>
                <span className="rrow__t">{f}</span>
                <span className="xs muted">{w}</span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 16 }}>
            <Note tone="warn" icon="alert">
              <b>محدودیت سخت:</b> در این مرحله هیچ بک‌اند، احراز هویت، اجازه یا منطق پرداخت تغییر نکرد. نسخهٔ طراحی
              یک اپ مستقل است و به سرویس‌های تولیدی وصل نیست.
            </Note>
          </div>
        </>
      )}

      {tab === 'ia' && (
        <>
          <SectionHead title="درخت ناوبری" hint="۶ مقصد اصلی — بیشتر از این، حافظهٔ کاربر را می‌شکند" />
          <div className="panel panel--flush">
            {IA.map(([to, name, desc]) => (
              <Link key={to} to={to} className="rrow" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }}>
                <span>
                  <span className="rrow__t">
                    {name} <span className="xs ltr" style={{ color: 'var(--text-3)', marginInlineStart: 8 }}>{to}</span>
                  </span>
                  <span className="rrow__m">
                    <span>{desc}</span>
                  </span>
                </span>
                <span className="rrow__go">
                  <Icon name="back" size={15} />
                </span>
              </Link>
            ))}
          </div>

          <SectionHead title="چرا این ترتیب؟" />
          <div className="panel panel--pad" style={{ display: 'grid', gap: 10 }}>
            {[
              ['خانه اول', 'دانشجو باید بداند «الان چه کار کنم». خانه با «ادامهٔ مطالعه» شروع می‌شود، نه با فهرست ابزارها.'],
              ['منابع پیش از بانک سؤال', 'مسیر روزانهٔ دانشجو خواندن است؛ سؤال، ابزار سنجش است نه نقطهٔ ورود.'],
              ['هوشیار مقصد مستقل، نه دکمهٔ شناور', 'دستیار بخشی از محصول است؛ فضای گفتگو باید آرام و قابل بازگشت باشد.'],
              ['برنامه بعد از محتوا', 'برنامه معنایش را از محتوا و آزمون می‌گیرد؛ اگر اول بیاید خالی به نظر می‌رسد.'],
              ['پیشرفت آخر', 'ستون انگیزه است، نه نقطهٔ شروع جلسهٔ مطالعه.'],
              ['تنظیمات و اشتراک در «بیشتر»', 'کم‌بسامد؛ در سایدبار جایگاه ثانویه دارند و در موبایل از «پیشرفت من» باز می‌شوند.'],
            ].map(([t, d]) => (
              <div key={t} className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
                <span className="center" style={{ width: 22, height: 22, borderRadius: 7, background: 'var(--surface-3)', color: 'var(--cyan-400)', flex: 'none', marginTop: 2 }}>
                  <Icon name="check" size={13} />
                </span>
                <div>
                  <b className="sm">{t}</b>
                  <p className="xs muted" style={{ marginTop: 2, lineHeight: 1.8 }}>
                    {d}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <SectionHead title="سه سفر اصلی" />
          <div className="ds-grid">
            {[
              ['۱. «امروز چه بخوانم؟»', ['خانه → ادامهٔ مطالعه', 'خواندن جزوه، یادداشت روی صفحه', 'تمرین از همان مبحث', 'بازخورد و بازگشت به خانه']],
              ['۲. «برای آزمون آماده‌ام؟»', ['بانک سؤال → انتخاب محدوده', 'آزمون زمان‌دار', 'کارنامه و بازبینی', 'تمرین روی غلط‌ها / تحلیل هوشیار']],
              ['۳. «این مفهوم را نفهمیدم»', ['هر جای محصول → هوشیار', 'پرسش با ارجاع به منبع', 'سؤال تمرینی از پاسخ', 'افزودن به برنامه']],
            ].map(([t, steps]) => (
              <div key={String(t)} className="panel panel--pad">
                <b className="h3">{t}</b>
                <ol style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                  {(steps as string[]).map((s, i) => (
                    <li key={s} className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                      <span className="xs num muted-2" style={{ width: 16, marginTop: 3 }}>{i + 1}</span>
                      <span className="sm">{s}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'directions' && (
        <>
          <SectionHead title="دو جهت بصری — و انتخاب" hint="می‌توانی همین‌جا جابه‌جا کنی" />
          <div className="row" style={{ gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
            <button
              type="button"
              className={`chip${direction === 'intelligent' ? ' chip--on' : ''}`}
              aria-pressed={direction === 'intelligent'}
              onClick={() => setDirection('intelligent')}
            >
              B — Intelligent Minimalism (انتخاب‌شده)
            </button>
            <button
              type="button"
              className={`chip${direction === 'quiet' ? ' chip--on' : ''}`}
              aria-pressed={direction === 'quiet'}
              onClick={() => setDirection('quiet')}
            >
              A — Quiet Academic Minimalism
            </button>
          </div>

          <div className="ds-grid">
            <div className="panel panel--pad">
              <div className="row">
                <b className="h3">A — آکادمیک آرام</b>
                <span className="grow" />
                <Badge>امتحان‌شده</Badge>
              </div>
              <ul style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                {[
                  'سطوح یک‌دست، بدون هاله و گرادیان؛ تأکید فقط با وزن و فاصله.',
                  'آبی برند تنها در کنش اصلی؛ فیروزه‌ای عملاً حذف می‌شود.',
                  'حرکت تقریباً صفر؛ مرزها نازک‌تر و آرام‌تر.',
                  'خوانایی بالا برای مطالعهٔ طولانی؛ اما هوشیار از بقیهٔ محصول جدا نمی‌شود.',
                ].map((x) => (
                  <li key={x} className="row sm" style={{ gap: 8, alignItems: 'flex-start' }}>
                    <Icon name="check" size={13} style={{ color: 'var(--ok)', marginTop: 4 }} />
                    {x}
                  </li>
                ))}
              </ul>
            </div>

            <div className="panel panel--pad" style={{ borderColor: 'rgba(42,218,215,.3)' }}>
              <div className="row">
                <b className="h3">B — مینیمال هوشمند</b>
                <span className="grow" />
                <Badge tone="info">پیشنهاد</Badge>
              </div>
              <ul style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                {[
                  'همان خوانایی، با یک لایهٔ هویت: خط عصبی برند، گره‌های نوری کنترل‌شده.',
                  'فیروزه‌ای فقط برای هوشیار، پیشرفت و وضعیت فعال — نه همهٔ دکمه‌ها.',
                  'حرکت کوتاه و هدفمند (۱۸۰–۳۰۰ms)، با احترام کامل به reduced-motion.',
                  'شناسایی برند بدون تکرار لوگو؛ از لوگو رنگ، فرم و «حس مدار» گرفته شده.',
                ].map((x) => (
                  <li key={x} className="row sm" style={{ gap: 8, alignItems: 'flex-start' }}>
                    <Icon name="check" size={13} style={{ color: 'var(--cyan-400)', marginTop: 4 }} />
                    {x}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <Note tone="ai" icon="sparkle">
              <b>توصیه: B.</b> تفاوت دو جهت فقط رنگ نیست: در A سلسله‌مراتب از «وزن و فاصله» می‌آید و هوشیار
              هویت بصری جدا ندارد؛ در B همان چیدمان با یک لایهٔ شناسایی برند و مسیر بصری مشخص برای AI حفظ
              می‌شود. هزینهٔ پیاده‌سازی هر دو یکی است (همان توکن‌ها)، ولی B ارزش برند بیشتری می‌دهد و برای
              مطالعهٔ طولانی هم آرام می‌ماند.
            </Note>
          </div>

          <SectionHead title="قاعدهٔ استفاده از رنگ برند" />
          <div className="panel panel--pad">
            <div className="kv">
              <dt>آبی برند</dt>
              <dd>کنش اصلی، ناوبری فعال، لینک — حداکثر یک دکمهٔ پر در هر ناحیه.</dd>
              <dt>فیروزه‌ای</dt>
              <dd>هوشیار، پیشرفت، وضعیت فعال، تأکید داده — نه متن بدنه، نه همهٔ دکمه‌ها.</dd>
              <dt>گرادیان</dt>
              <dd>فقط در قهرمان خانه، نوار AI و حلقهٔ پیشرفت. هیچ پنل معمولی گرادیان ندارد.</dd>
              <dt>هاله و سایه</dt>
              <dd>یک سطح ارتفاع برای کارت، یک سطح برای لایه‌های روی صفحه؛ بدون سایهٔ رنگی پرحجم.</dd>
            </div>
          </div>
        </>
      )}

      {tab === 'specs' && (
        <>
          <SectionHead title="مسئولیت واکنش‌گرا" hint="هر سه عرض واقعاً بازبینی شد" />
          <div className="panel panel--flush">
            {[
              ['۱۴۴۰px', 'سایدبار کامل + نوار بالا؛ ستون محتوا حداکثر ۱۲۲۰px تا خطوط بلند نشوند.'],
              ['۷۶۸px', 'سایدبار به ریل آیکن جمع می‌شود (۷۶px)؛ ستون کنار زیر محتوا می‌رود؛ جدول‌ها افقی نمی‌شکنند.'],
              ['۳۹۰px', 'ناوبری پایین ۵ مقصد؛ سربرگ چسبان؛ محتوا یک‌ستونه؛ هدف لمسی ≥ ۴۴px؛ فرم‌ها عمودی.'],
            ].map(([w, d]) => (
              <div key={w} className="rrow" style={{ gridTemplateColumns: '84px minmax(0,1fr)' }}>
                <span className="num sm" style={{ color: 'var(--cyan-400)' }}>{w}</span>
                <span className="sm muted">{d}</span>
              </div>
            ))}
          </div>

          <SectionHead title="RTL و دسترس‌پذیری — چک‌لیست" />
          <div className="panel panel--pad" style={{ display: 'grid', gap: 8 }}>
            {[
              'همهٔ فاصله‌ها با inset-inline / margin-inline نوشته شده‌اند، نه left/right.',
              'آیکن‌های جهت‌دار (بازگشت/بعدی) در RTL آینه می‌شوند؛ آیکن‌های بی‌جهت نه.',
              'متن لاتین و اعداد با dir="ltr" و ایزوله‌سازی، داخل جملهٔ فارسی نمی‌شکنند.',
              'ارقام فارسی از یک نگاشت واحد؛ جدول‌های عددی از tnum استفاده می‌کنند.',
              'فوکوس دیدنی با outline مستقل از رنگ؛ ترتیب Tab منطقی است.',
              'معنای رنگ هرگز تنها نیست: برچسب متنی + آیکن همراه رنگ هست.',
              'هدف لمسی ≥ ۴۴px در موبایل؛ فاصلهٔ کافی بین گزینه‌های سؤال.',
              'حالت‌های خطا با role="alert" و دیالوگ‌ها با aria-modal و Escape.',
              'prefers-reduced-motion همهٔ حرکت‌ها را خاموش می‌کند.',
              'کنتراست متن اصلی/ثانویه روی سطوح بررسی و در هر دو تم کنترل شد.',
            ].map((x) => (
              <div key={x} className="row sm" style={{ gap: 8, alignItems: 'flex-start' }}>
                <Icon name="check" size={13} style={{ color: 'var(--ok)', marginTop: 4 }} />
                {x}
              </div>
            ))}
          </div>

          <SectionHead title="فهرست کامپوننت" hint="همه در صفحهٔ سیستم طراحی با حالت‌هایشان" />
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            {[
              'Button (۵ گونه، ۳ اندازه)', 'IconButton', 'Chip', 'Badge (۶ تُن)', 'Field/Input/Textarea/Select',
              'SearchBox + Kbd', 'Switch', 'Tabs', 'Segmented', 'Progress', 'Ring', 'Stat', 'WeekBars',
              'ListRow (ResourceRow)', 'Panel (pad/flush/quiet/ai)', 'Dialog', 'Drawer', 'Toasts',
              'Skeleton', 'Empty', 'Note (۴ تُن)', 'Countdown', 'Timer', 'QuestionCard', 'OptionRow',
              'QMap', 'AI Message/Composer/SourceChip', 'PlanCard', 'SlotCell', 'Nav (sidebar/tabbar/rail)',
            ].map((c) => (
              <Chip key={c} ghost>
                {c}
              </Chip>
            ))}
          </div>

          <SectionHead title="مشخصات صفحه‌ها" hint="حالت‌های الزامی برای پیاده‌سازی" />
          <div className="panel panel--flush">
            {[
              ['خانه', 'loading · خطا · بدون محتوا · اشتراک منقضی'],
              ['منابع', 'loading · خالی با فیلتر · قفل · خطای شبکه · نتیجهٔ صفحه‌بندی'],
              ['جزئیات منبع', 'پیش‌نمایش PDF/ویدیو/صوت/اسلاید · قفل · فایل ناموجود · آفلاین'],
              ['بانک سؤال', 'آمار خالی · پلن بسته · انتخاب بدون سؤال'],
              ['تمرین', 'پاسخ درست/غلط · پایان محدوده · خطا با تلاش دوباره · قفل'],
              ['آزمون', 'تنظیم · اجرا · انقضا · خروج با تأیید · ثبت پاسخ'],
              ['کارنامه', 'کلید و توضیح · فقط غلط‌ها · آزمون رهاشده'],
              ['هوشیار', 'فکر کردن · پاسخ · خطا با تلاش دوباره · سهمیه تمام · پیوست (غیرفعال)'],
              ['برنامه', 'هفته/فهرست · روز خالی · آزمون نزدیک · کار انجام‌شده'],
              ['پیشرفت', 'داده کم · حریم خصوصی خاموش'],
              ['اشتراک', 'فعال · منقضی · پلن مقایسه · تاریخ پرداخت خالی'],
              ['تنظیمات', 'ذخیرهٔ موفق · خطای اعتبارسنجی · خروج تأیید'],
            ].map(([p, s]) => (
              <div key={p} className="rrow" style={{ gridTemplateColumns: '150px minmax(0,1fr)' }}>
                <span className="rrow__t">{p}</span>
                <span className="xs muted">{s}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'handoff' && (
        <>
          <SectionHead title="رابطه با کد فعلی" hint="نسخهٔ طراحی جدا، تولید دست‌نخورده" />
          <div className="panel panel--pad">
            <div className="kv">
              <dt>جای این نسخه</dt>
              <dd>پوشهٔ مستقل <span className="ltr">humsyar-proto/</span> — هیچ فایلی از <span className="ltr">apps/student</span>، <span className="ltr">api/</span> یا دیتابیس تغییر نکرد.</dd>
              <dt>پشته</dt>
              <dd>همان پشتهٔ محصول: React 18 + Vite + TypeScript. بدون shadcn/ui و بدون کتابخانهٔ UI؛ چون پروژه از قبل توکن و کامپوننت اختصاصی دارد و افزودن سیستم دوم یعنی دو زبان بصری.</dd>
              <dt>داده</dt>
              <dd>محلی (<span className="ltr">src/data/demo.ts</span>). شکل داده‌ها عمداً شبیه قراردادهای واقعی است تا در پیاده‌سازی، هر mock با یک فراخوانی API عوض شود.</dd>
              <dt>مسیر تبدیل</dt>
              <dd>توکن‌ها و کامپوننت‌ها به <span className="ltr">src/design/</span> و <span className="ltr">src/components/</span> منتقل می‌شوند؛ صفحه‌ها یکی‌یکی با API واقعی جایگزین mock می‌شوند.</dd>
            </div>
          </div>

          <SectionHead title="محدودیت‌های شناخته‌شده" hint="وضعیت واقعی، بدون ادعای اضافه" />
          <div className="panel panel--pad" style={{ display: 'grid', gap: 8 }}>
            {[
              'سرویس هوشیار هنوز وصل نیست؛ پاسخ‌ها نمونه‌اند و همین در همان صفحه گفته می‌شود.',
              'یادداشت‌ها و دست‌نویس فقط در حافظهٔ همین نشست‌اند؛ ذخیرهٔ پایدار (IndexedDB) و همگام‌سازی ساخته نشده است.',
              'نمای PDF روی متن ساختگی است؛ نمایش‌گر واقعی (pdf.js) و پیوند پایدار به پاراگراف کار مهندسی است.',
              'رد کف دست، فشار قلم به‌صورت یکنواخت و جوهر کم‌تأخیر در وب در دسترس نیستند و به لایهٔ بومی نیاز دارند.',
              'نصب PWA روی دستگاه واقعی و HTTPS راستی‌آزمایی نشده؛ manifest و service worker آماده‌اند.',
              'پرداخت، درگاه، اعلان و تقویم بیرونی وصل نیستند.',
              'تاریخ‌ها و ارقام شمسی روی دادهٔ نمونه محاسبه شده‌اند؛ تبدیل تقویم در محصول انجام می‌شود.',
              'لیست «ادامهٔ مطالعه» بر پایهٔ قرارداد سراسری موجود نیست و در پیاده‌سازی باید تعریف شود.',
              'تم روشن ارائه شده ولی بازبینی نهایی آن بعد از تأیید تم تیره انجام می‌شود.',
            ].map((x) => (
              <div key={x} className="row sm" style={{ gap: 8, alignItems: 'flex-start' }}>
                <Icon name="alert" size={13} style={{ color: 'var(--warn)', marginTop: 4 }} />
                {x}
              </div>
            ))}
          </div>

          <SectionHead title="فاز ۶ — چیدمان تطبیقی، تجربهٔ نصب‌شده، حرکت و یادداشت" hint="افزودهٔ همین دور" />
          <div className="panel panel--pad" style={{ display: 'grid', gap: 12 }}>
            <div>
              <b className="sm">چیدمان v2 — اندازه‌گیری از قاب، نه از پنجره</b>
              <p className="xs muted" style={{ marginTop: 4 }}>
                کل چیدمان روی <span className="ltr">container query</span> روی <span className="ltr">.frame</span> تصمیم
                می‌گیرد و سقف عرض ثابت برداشته شد. نتیجه: دسکتاپ از تمام عرض استفاده می‌کند (دو ستون، بدون فضای مرده)،
                تبلت ریل آیکنی و دو پنل در حالت افقی دارد، و موبایل ترتیب اطلاعات مخصوص خودش را با{' '}
                <span className="ltr">display: contents</span> می‌گیرد: آزمون بعدی ← ادامهٔ مطالعه ← دسترسی‌ها ←
                هفته ← کارها ← تازه‌ها ← هوشیار. جزئیات و گزارش بازرسی در «ماتریس قابلیت ← چیدمان واکنش‌گرا».
              </p>
            </div>
            <div>
              <b className="sm">حرکت، یک‌جا و کوتاه</b>
              <p className="xs muted" style={{ marginTop: 4 }}>
                ۹۰ms برای بازخورد، ۱۵۰ms برای کنترل کوچک، ۲۰۰–۲۴۰ms برای ورود صفحه و شیت. یک قاب مشترک
                (<span className="ltr">Frame</span>) با کلید مسیر، پس هیچ صفحه‌ای سفید نمی‌زند و اسکرول/ویرایشگر
                بازنشانی نمی‌شود. <span className="ltr">prefers-reduced-motion</span> همه را به ۱ms می‌رساند.
              </p>
            </div>
            <div>
              <b className="sm">شیت پایین ⇄ دیالوگ</b>
              <p className="xs muted" style={{ marginTop: 4 }}>
                یک کامپوننت، دو فرم‌فاکتور: زیر ۸۶۰px شیت پایین با grip و ناحیهٔ امن، بالای آن دیالوگ مرکزی. Escape،
                کلیک پرده، محدودسازی فوکوس و بازگشت فوکوس پیاده شده‌اند.
              </p>
            </div>
            <div>
              <b className="sm">یادداشت‌ها — سه چیدمان، یک محصول</b>
              <p className="xs muted" style={{ marginTop: 4 }}>
                ≥۱۲۰۰: دفترها | فهرست | ویرایشگر (+ سند کنار‌هم). ۷۲۱–۱۱۹۹: فهرست | ویرایشگر با دفترها در شیت.
                ≤۷۲۰: جابه‌جایی push با نوار قالب‌بندی بالای نوار پایین و بالای کیبورد. ویرایش واقعی
                (<span className="ltr">contentEditable</span>)، وضعیت ذخیره، شبیه‌سازی آفلاین، بوم دست‌نویس، لنگر سند.
              </p>
            </div>
            <div>
              <b className="sm">لایهٔ نصب</b>
              <p className="xs muted" style={{ marginTop: 4 }}>
                manifest با آیکن ۱۹۲/۵۱۲ و maskable، متاتگ‌های iOS، service worker با پیش‌بارگذاری پوسته، تنظیم
                <span className="ltr"> start_url</span> و <span className="ltr">scope</span>، مدیریت ناحیهٔ امن و
                تشخیص حالت standalone. مسیرها hash می‌مانند تا ناوبری داخلی هیچ تب Safari باز نکند.
              </p>
            </div>
            <div>
              <b className="sm">یک ایراد واقعی که پیدا و رفع شد</b>
              <p className="xs muted" style={{ marginTop: 4 }}>
                در تم روشن، متن چیپ‌های انتخاب‌شده و برچسب‌های ریز (فیزیولوژی، بیوشیمی، …) محو می‌شد. ریشه: رنگ
                ثابت <span className="ltr">#CFE0FF</span> و <span className="ltr">--text-3</span> با کنتراست ۳٫۲۸:۱.
                توکن‌های <span className="ltr">--chip-on-fg</span>، <span className="ltr">--on-accent</span> و
                پالت روشن اصلاح شدند؛ بازرسی خودکار کنتراست الان در ۱۴ مسیر × ۲ تم صفر مورد زیر آستانه دارد.
              </p>
            </div>
          </div>

          <SectionHead title="ترتیب پیشنهادی پیاده‌سازی" hint="بعد از تأیید طراحی" />
          <div className="panel panel--flush">
            {[
              ['۱', 'توکن‌ها + کامپوننت پایه', 'همان جدول سیستم طراحی؛ بدون صفحه'],
              ['۲', 'پوسته: سایدبار، نوار بالا، نوار پایین، مسیرها', 'ناوبری و حالت‌های احراز'],
              ['۳', 'منابع + جزئیات + قفل اشتراک', 'روی API موجود P2'],
              ['۴', 'بانک سؤال + تمرین + آزمون + کارنامه', 'روی API موجود P5/P5.2'],
              ['۵', 'هوشیار', 'نیازمند قرارداد وب برای ai.py — تصمیم پیش از کد'],
              ['۶', 'برنامه + پیشرفت + اشتراک + تنظیمات', 'روی API موجود schedule/profile/subscription'],
              ['۷', 'یادداشت‌ها: مدل داده، ذخیره‌سازی محلی، همگام‌سازی', 'نیازمند قرارداد بک‌اند — بزرگ‌ترین کار باقی‌مانده'],
              ['۸', 'نمایش‌گر PDF و لنگر پاراگراف', 'pdf.js + نگاشت صفحه/بازهٔ متن'],
              ['۹', 'نصب PWA، ناحیهٔ امن، آزمون دستگاه واقعی', 'HTTPS روی Railway + آزمون iOS/Android'],
              ['۱۰', 'تم روشن، بازبینی دسترس‌پذیری، بازبینی حرکت', 'پایان فاز'],
            ].map(([n, t, d]) => (
              <div key={n} className="rrow" style={{ gridTemplateColumns: '32px minmax(0,1fr) minmax(0,1.2fr)' }}>
                <span className="num sm" style={{ color: 'var(--cyan-400)' }}>{n}</span>
                <span className="rrow__t">{t}</span>
                <span className="xs muted">{d}</span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 16 }}>
            <Note icon="shield">
              <b>هیچ بخشی از این کار تولید نیست.</b> تا تأیید صریح تو، کدنویسی محصول شروع نمی‌شود؛ این
              این نسخه فقط برای بازبینی طراحی است.
            </Note>
          </div>

          <div className="row" style={{ marginTop: 16, gap: 8, flexWrap: 'wrap' }}>
            <Link to="/" className="btn btn--primary btn--sm">
              شروع بازبینی از خانه
            </Link>
            <Link to="/system" className="btn btn--ghost btn--sm">
              دیدن سیستم طراحی
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
