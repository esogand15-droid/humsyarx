import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { Badge, Chip, Dialog, Note, Progress, SectionHead } from '../components/ui';
import { PageTitle } from '../components/Shell';
import { fa, useProto } from '../lib/store';
import { lessons, payments, plans, progressSummary, student, weekStudy } from '../data/demo';

/* ═══════════════════════════════════════════════════════════════════
   SC-060 — پیشرفت من   SC-061 — اشتراک   SC-062 — تنظیمات
   پیشرفت با زبان آکادمیک (دقت، پیوستگی، سهم مطالعه) — نه بازی‌سازی.
   ═══════════════════════════════════════════════════════════════════ */
export function Profile() {
  return (
    <div className="page">
      <PageTitle title="پیشرفت من" sub="تصویر کلی از مطالعه، دقت پاسخ‌ها و جایگاه علمی" />

      <section className="profile-hero">
        <span className="avatar avatar--lg">{student.initials}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <b className="h2">{student.name}</b>
          <p className="sm muted" style={{ marginTop: 4 }}>
            {student.major} · {student.stage} · ورودی {student.intake} · شمارهٔ دانشجویی{' '}
            <span className="num ltr" style={{ display: 'inline' }}>
              {student.studentId}
            </span>
          </p>
          <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            <Badge tone="ok">
              <span className="dot" /> اشتراک فعال تا {student.subscription.endsAt}
            </Badge>
            <Chip ghost>
              <Icon name="flame" size={12} style={{ color: 'var(--warn)' }} />
              <span className="num">{fa(progressSummary.streakDays)}</span> روز پیوسته
            </Chip>
          </div>
        </div>
        <Link to="/me/settings" className="btn btn--ghost btn--sm">
          <Icon name="settings" size={14} />
          تنظیمات حساب
        </Link>
      </section>

      <div className="metric-group" style={{ marginTop: 18 }}>
        {[
          ['دقت پاسخ‌ها', `${fa(progressSummary.accuracy)}٪`, 'از ۴۱۲ سؤال پاسخ‌داده', 'trend'],
          ['سهم مطالعهٔ هفته', `${fa(Math.round(progressSummary.weeklyMinutes / 60))} ساعت`, `هدف ${fa(progressSummary.weeklyTarget / 60)} ساعت`, 'clock'],
          ['جایگاه در ورودی', `${fa(progressSummary.rank)}`, `از ${fa(progressSummary.rankOf)} نفر`, 'chart'],
        ].map(([t, v, d, ic]) => (
          <div key={String(t)} className="panel panel--pad">
            <div className="row" style={{ gap: 8, color: 'var(--text-3)' }}>
              <Icon name={ic as 'trend'} size={15} />
              <span className="xs">{t}</span>
            </div>
            <div className="stat" style={{ marginTop: 8 }}>
              <span className="stat__v num">{v}</span>
              <span className="stat__l">{d}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="home-grid" style={{ marginTop: 18 }}>
        <div>
          <SectionHead title="پیشرفت درس‌ها" hint="بر پایهٔ محتوای خوانده‌شده و سؤال‌های پاسخ‌داده" />
          <div className="panel panel--pad">
            <div style={{ display: 'grid', gap: 14 }}>
              {lessons.map((l) => (
                <div key={l.id}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
                    <span className="sm" style={{ fontWeight: 500 }}>
                      {l.name}
                      <span className="xs muted-2" style={{ marginInlineStart: 8 }}>
                        {l.teacher}
                      </span>
                    </span>
                    <span className="xs num muted-2">
                      {fa(l.progress)}٪ · {fa(l.questions)} سؤال
                    </span>
                  </div>
                  <Progress value={l.progress} />
                </div>
              ))}
            </div>
          </div>

          <SectionHead title="دستاوردها" hint="بدون امتیازبازی — فقط نشانهٔ کار واقعی" />
          <div className="achievements">
            {[
              ['۹ روز پیوسته', 'بیشترین پیوستگی این ترم', 'flame', 'var(--warn)'],
              ['۳ آزمون بالای ۸۰٪', 'در دو هفتهٔ گذشته', 'target', 'var(--ok)'],
              ['۴۲ سؤال از نقاط ضعف', 'تمرین هدفمند در مهر', 'trend', 'var(--cyan-400)'],
            ].map(([t, d, ic, c]) => (
              <div key={String(t)} className="panel panel--pad">
                <span
                  className="center"
                  style={{ width: 34, height: 34, borderRadius: 10, background: 'var(--surface-3)', color: c as string }}
                >
                  <Icon name={ic as 'flame'} size={17} />
                </span>
                <b className="sm" style={{ display: 'block', marginTop: 10 }}>
                  {t}
                </b>
                <span className="xs muted-2">{d}</span>
              </div>
            ))}
          </div>
        </div>

        <aside style={{ display: 'grid', gap: 16 }}>
          <section className="panel panel--pad">
            <b className="h3">الگوی مطالعه</b>
            <div className="weekbars" style={{ marginTop: 14 }}>
              {weekStudy.map((d) => (
                <div key={d.label} className="weekbars__b" title={`${d.label} — ${fa(d.minutes)} دقیقه`}>
                  <i style={{ height: `${Math.min(100, (d.minutes / 180) * 100)}%` }} />
                  <span>{d.label.slice(0, 3)}</span>
                </div>
              ))}
            </div>
            <p className="xs muted-2" style={{ marginTop: 10, lineHeight: 1.8 }}>
              پرکارترین روز تو پنج‌شنبه است؛ دوشنبه‌ها فاصلهٔ بیشتری با هدف داری.
            </p>
          </section>

          <section className="panel panel--pad">
            <div className="row" style={{ marginBottom: 10 }}>
              <b className="h3">هم‌گروهی‌های تو</b>
              <span className="grow" />
              <Badge>اختیاری</Badge>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {[
                ['۱', 'نگار موسوی', 92],
                ['۲', 'سارا رضایی', 88],
                [`${fa(progressSummary.rank)}`, 'تو', progressSummary.accuracy],
              ].map(([r, n, v]) => (
                <div
                  key={String(r)}
                  className="row"
                  style={{
                    gap: 10,
                    padding: 8,
                    borderRadius: 'var(--r-sm)',
                    background: n === 'تو' ? 'rgba(31,107,255,.10)' : undefined,
                    border: n === 'تو' ? '1px solid var(--line-brand)' : '1px solid transparent',
                  }}
                >
                  <span className="xs num muted-2" style={{ width: 20 }}>
                    {r}
                  </span>
                  <span className="avatar" style={{ width: 24, height: 24, borderRadius: 7, fontSize: 10 }}>
                    {String(n).slice(0, 2)}
                  </span>
                  <span className="sm grow">{n}</span>
                  <span className="xs num muted-2">{fa(Number(v))}٪</span>
                </div>
              ))}
            </div>
            <p className="xs muted-2" style={{ marginTop: 10, lineHeight: 1.8 }}>
              نمایش نام هم‌گروهی‌ها به تنظیم حریم خصوصی هر دانشجو بستگی دارد؛ در تنظیمات قابل خاموش‌کردن است.
            </p>
          </section>

          <Link to="/me/subscription" className="panel panel--pad" style={{ display: 'block' }}>
            <div className="row" style={{ gap: 10 }}>
              <span className="center" style={{ width: 34, height: 34, borderRadius: 10, background: 'var(--ok-soft)', color: 'var(--ok)' }}>
                <Icon name="card" size={17} />
              </span>
              <div className="grow">
                <b className="sm" style={{ display: 'block' }}>
                  {student.subscription.plan}
                </b>
                <span className="xs muted-2">
                  {fa(student.subscription.daysLeft)} روز باقی‌مانده
                </span>
              </div>
              <Icon name="back" size={15} style={{ color: 'var(--text-3)' }} />
            </div>
          </Link>
        </aside>
      </div>
    </div>
  );
}

/* ── اشتراک ──────────────────────────────────────────────────────── */
export function Subscription() {
  const { toast } = useProto();
  const [dlg, setDlg] = useState<string | null>(null);
  /** در موبایل یک پلن در هر لحظه؛ در دسکتاپ هر سه کنار هم دیده می‌شوند */
  const current = plans.find((p) => p.featured) ?? plans[0];
  const [sel, setSel] = useState<string>(current.id);

  return (
    <div className="page page--narrow">
      <PageTitle
        title="اشتراک و پرداخت"
        sub="وضعیت پلن، مقایسهٔ امکانات و تاریخ پرداخت‌ها"
        actions={
          <Link to="/me" className="btn btn--quiet btn--sm">
            <Icon name="forward" size={14} />
            بازگشت
          </Link>
        }
      />

      <section className="panel panel--pad" style={{ borderColor: 'rgba(47,208,154,.3)' }}>
        <div className="row sub-status" style={{ gap: 16, flexWrap: 'wrap' }}>
          <span className="center" style={{ width: 44, height: 44, borderRadius: 12, background: 'var(--ok-soft)', color: 'var(--ok)' }}>
            <Icon name="check" size={20} />
          </span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <b className="h2">اشتراک تو فعال است</b>
            <p className="sm muted" style={{ marginTop: 2 }}>
              {student.subscription.plan} · تا {student.subscription.endsAt}
            </p>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => setDlg('renew')}>
              تمدید
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDlg('family')}>
              <Icon name="user" size={14} />
              اشتراک خانوادگی
            </button>
          </div>
        </div>
        <div className="trace" />
        <div className="row sub-stats" style={{ gap: 24, flexWrap: 'wrap' }}>
          <div className="stat">
            <span className="stat__v num">{fa(student.subscription.daysLeft)}</span>
            <span className="stat__l">روز باقی‌مانده</span>
          </div>
          <div className="stat">
            <span className="stat__v num">{fa(student.subscription.features.length)}</span>
            <span className="stat__l">قابلیت فعال</span>
          </div>
          <div className="stat">
            <span className="stat__v num">
              {fa(student.subscription.aiDailyUsed)}/{fa(student.subscription.aiDailyLimit)}
            </span>
            <span className="stat__l">سهمیهٔ امروز هوشیار</span>
          </div>
        </div>
      </section>

      <SectionHead title="مقایسهٔ پلن‌ها" hint="نام و قیمت نهایی از سرور می‌آید" />

      {/* موبایل: انتخاب‌گر پلن. دسکتاپ: هر سه کارت کنار هم.
          مبنا: در عرض ۳۹۰px سه ستون یعنی متن ستونی؛ الگوی رایج موبایل،
          نمایش یکی‌یکی با امکان جابه‌جایی است. */}
      <div className="plan-switch" role="tablist" aria-label="انتخاب پلن">
        {plans.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            aria-selected={sel === p.id}
            className={`chip${sel === p.id ? ' chip--on' : ''}`}
            onClick={() => setSel(p.id)}
          >
            {p.name}
            {p.featured && <Icon name="check" size={12} />}
          </button>
        ))}
      </div>

      <div className="plans" data-sel={sel}>
        {plans.map((p) => (
          <div
            key={p.id}
            className={`plan${p.featured ? ' plan--featured' : ''}${sel === p.id ? ' plan--sel' : ''}`}
          >
            <div className="row">
              <b className="h3">{p.name}</b>
              <span className="grow" />
              {p.featured && <Badge tone="info">پلن فعلی</Badge>}
            </div>
            <div>
              <span className="plan__price">{p.price}</span>
              <div className="xs muted-2">{p.note}</div>
            </div>
            <ul>
              {p.features.slice(0, 4).map((f) => (
                <li key={f.t} className={f.on ? '' : 'off'}>
                  <Icon name={f.on ? 'check' : 'close'} size={13} />
                  {f.t}
                </li>
              ))}
            </ul>
            {p.features.length > 4 && (
              <details className="plan__more">
                <summary>
                  همهٔ امکانات ({fa(p.features.length)})
                </summary>
                <ul>
                  {p.features.slice(4).map((f) => (
                    <li key={f.t} className={f.on ? '' : 'off'}>
                      <Icon name={f.on ? 'check' : 'close'} size={13} />
                      {f.t}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {p.featured ? (
              <div className="plan__current">
                <span className="xs muted-2">پلن فعال شما — تمدید لازم نیست</span>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDlg(p.name)}>
                  تمدید زودهنگام
                </button>
              </div>
            ) : (
              <button type="button" className="btn btn--primary btn--sm" onClick={() => setDlg(p.name)}>
                انتخاب این پلن
              </button>
            )}
          </div>
        ))}
      </div>

      <SectionHead title="تاریخ پرداخت‌ها" hint="مبلغ از سرور" />
      <div className="panel panel--flush">
        {payments.map((p) => (
          <div key={p.id} className="rrow rrow--pay" style={{ gridTemplateColumns: 'auto minmax(0,1fr) auto' }}>
            <span className="rrow__ic">
              <Icon name="card" size={17} />
            </span>
            <span>
              <span className="rrow__t">{p.title}</span>
              <span className="rrow__m">
                <span>{p.date}</span>
                <span className="num">{p.id}</span>
              </span>
            </span>
            <Badge tone="ok">{p.status}</Badge>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 14 }}>
        <Note icon="info">
          پرداخت در درگاه بانکی انجام می‌شود و وضعیت هر تراکنش از سرور خوانده می‌شود؛ فاکتور رسمی هم در
          همان صفحه قابل دریافت است.
        </Note>
      </div>

      <Dialog
        open={dlg !== null}
        title={dlg === 'renew' ? 'تمدید اشتراک' : dlg === 'family' ? 'اشتراک خانوادگی' : `انتخاب ${dlg ?? ''}`}
        onClose={() => setDlg(null)}
        actions={
          <>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => {
                setDlg(null);
                toast('در نسخهٔ نهایی، انتقال به درگاه پرداخت همین‌جا انجام می‌شود.', 'info');
              }}
            >
              ادامه
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDlg(null)}>
              بستن
            </button>
          </>
        }
      >
        پرداخت واقعی به درگاه نیاز دارد و در این پروتوتایپ وصل نیست. این دیالوگ فقط جریان تجربه را نشان
        می‌دهد: تأیید پلن ← درگاه ← بازگشت به وضعیت اشتراک.
      </Dialog>
    </div>
  );
}

/* ── تنظیمات ─────────────────────────────────────────────────────── */
type Theme = 'dark' | 'light';
type TextSize = 'sm' | 'md' | 'lg';

export function Settings() {
  const { toast, theme, setTheme } = useProto();
  const navigate = useNavigate();
  const [calm, setCalm] = useState(false);
  const [textSize, setTextSize] = useState<TextSize>('md');
  const [prefs, setPrefs] = useState<Record<string, boolean>>({
    examReminder: true,
    newContent: true,
    aiDigest: false,
    privacy: true,
  });

  const rows: [string, string, string][] = [
    ['examReminder', 'یادآوری آزمون', 'دو روز و یک روز قبل از آزمون اطلاع بده'],
    ['newContent', 'محتوای تازه', 'وقتی جزوه یا ویدیوی درس‌های من منتشر شد'],
    ['aiDigest', 'خلاصهٔ هفتگی هوشیار', 'جمع‌بندی مطالعهٔ هفته و پیشنهاد هفتهٔ بعد'],
    ['privacy', 'نمایش نام من در هم‌گروهی‌ها', 'اگر خاموش باشد، فقط درصدهای خودت را می‌بینی'],
  ];

  return (
    <div className="page page--narrow">
      <PageTitle
        title="تنظیمات حساب"
        sub="پروفایل، اعلان‌ها، حریم خصوصی و پشتیبانی"
        actions={
          <button type="button" className="btn btn--quiet btn--sm" onClick={() => navigate('/me')}>
            <Icon name="forward" size={14} />
            بازگشت
          </button>
        }
      />

      <SectionHead title="اطلاعات تحصیلی" hint="تغییر ورودی و گروه، سمت سرور" />
      <section className="panel panel--pad">
        <div className="form-grid">
          <label className="field">
            <span className="field__l">نام برای هم‌گروهی‌ها</span>
            <input className="input" defaultValue={student.name} />
          </label>
          <label className="field">
            <span className="field__l">شمارهٔ دانشجویی</span>
            <input className="input ltr" defaultValue={student.studentId} dir="ltr" />
          </label>
          <label className="field">
            <span className="field__l">ورودی</span>
            <input className="input" defaultValue={student.intake} />
          </label>
          <label className="field">
            <span className="field__l">گروه</span>
            <input className="input" defaultValue={student.major} />
          </label>
        </div>
        <div className="row" style={{ marginTop: 14, gap: 8 }}>
          <button type="button" className="btn btn--primary btn--sm" onClick={() => toast('تغییرات ذخیره شد.', 'ok')}>
            ذخیره
          </button>
          <span className="xs muted-2">تغییر ورودی و گروه سمت سرور اعتبارسنجی می‌شود.</span>
        </div>
      </section>

      <SectionHead title="ظاهر و دسترس‌پذیری" hint="فقط روی این دستگاه" />
      <div className="panel panel--flush">
        <div className="rrow" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }}>
          <span>
            <span className="rrow__t">تم</span>
            <span className="rrow__m">
              <span>تیره برای مطالعهٔ شبانه، روشن برای نور روز</span>
            </span>
          </span>
          <div className="seg" role="group" aria-label="انتخاب تم">
            {([
              ['dark', 'تیره'],
              ['light', 'روشن'],
            ] as [Theme, string][]).map(([k, l]) => (
              <button key={k} type="button" aria-pressed={theme === k} onClick={() => setTheme(k)}>
                {l}
              </button>
            ))}
          </div>
        </div>
        <div className="rrow" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }}>
          <span>
            <span className="rrow__t">کاهش حرکت</span>
            <span className="rrow__m">
              <span>انتقال‌ها و انیمیشن‌ها به حداقل می‌رسند</span>
            </span>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={calm}
            aria-label="کاهش حرکت"
            className="switch"
            onClick={() => {
              const next = !calm;
              setCalm(next);
              document.documentElement.dataset.motion = next ? 'calm' : 'auto';
              toast(next ? 'کاهش حرکت روشن شد.' : 'حرکت عادی برگشت.', 'ok');
            }}
          />
        </div>
        <div className="rrow" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }}>
          <span>
            <span className="rrow__t">اندازهٔ متن یادداشت‌ها</span>
            <span className="rrow__m">
              <span>مستقل از بزرگ‌نمایی مرورگر</span>
            </span>
          </span>
          <div className="seg" role="group" aria-label="اندازهٔ متن">
            {([
              ['sm', 'کوچک'],
              ['md', 'متوسط'],
              ['lg', 'بزرگ'],
            ] as [TextSize, string][]).map(([k, l]) => (
              <button
                key={k}
                type="button"
                aria-pressed={textSize === k}
                onClick={() => {
                  setTextSize(k);
                  document.documentElement.dataset.textsize = k;
                }}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      <SectionHead title="اعلان‌ها و حریم خصوصی" />
      <div className="panel panel--flush">
        {rows.map(([k, t, d]) => (
          <div key={k} className="rrow" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }}>
            <span>
              <span className="rrow__t">{t}</span>
              <span className="rrow__m">
                <span>{d}</span>
              </span>
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={prefs[k]}
              aria-label={t}
              className="switch"
              onClick={() => {
                setPrefs((p) => ({ ...p, [k]: !p[k] }));
                toast('تنظیم ذخیره شد.', 'ok');
              }}
            />
          </div>
        ))}
      </div>

      <SectionHead title="پشتیبانی و امنیت" />
      <div className="panel panel--flush">
        {[
          ['تیکت پشتیبانی', 'پاسخ تیم پشتیبانی در همان صفحه', 'ticket'],
          ['نشست‌های فعال', 'خروج از همهٔ دستگاه‌ها', 'shield'],
          ['خروج از حساب', 'پایان نشست این دستگاه', 'logout'],
        ].map(([t, d, ic]) => (
          <button
            key={String(t)}
            type="button"
            className="rrow"
            style={{ gridTemplateColumns: 'auto minmax(0,1fr) auto' }}
            onClick={() => toast('این بخش در نسخهٔ آزمایشی فعال نیست.', 'info')}
          >
            <span className="rrow__ic">
              <Icon name={ic as 'ticket'} size={17} />
            </span>
            <span>
              <span className="rrow__t">{t}</span>
              <span className="rrow__m">
                <span>{d}</span>
              </span>
            </span>
            <Icon name="back" size={15} style={{ color: 'var(--text-3)' }} />
          </button>
        ))}
      </div>

      <div style={{ marginTop: 14 }}>
        <Note icon="shield">
          <b>دسترسی‌ها سمت سرور کنترل می‌شوند.</b> هیچ تنظیمی در این صفحه گیت اشتراک یا مجوز محتوا را دور
          نمی‌زند؛ فقط ترجیح‌های کاربر است.
        </Note>
      </div>
    </div>
  );
}
