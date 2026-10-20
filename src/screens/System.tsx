import { useState } from 'react';
import { Icon } from '../components/Icon';
import { Badge, Chip, Dialog, Drawer, Empty, Note, Progress, Ring, SectionHead, Skeleton } from '../components/ui';
import { PageTitle } from '../components/Shell';
import { fa, useProto } from '../lib/store';

/* ═══════════════════════════════════════════════════════════════════
   SC-090 — سیستم طراحی
   همهٔ توکن‌ها و کامپوننت‌ها در یک صفحه، تا صفحه‌ها نتوانند ظاهر مستقل
   بسازند. همین صفحه مرجع بازبینی و پیاده‌سازی است.
   ═══════════════════════════════════════════════════════════════════ */

const COLORS: [string, string, string][] = [
  ['--bg-1', '#080F1E', 'پس‌زمینهٔ برنامه'],
  ['--surface-1', '#0C1526', 'سطح کارت'],
  ['--surface-2', '#111C30', 'سطح دوم'],
  ['--surface-3', '#16233A', 'سطح سوم / ورودی'],
  ['--brand-800', '#0B3DC2', 'آبی لوگو'],
  ['--brand-600', '#1F6BFF', 'کنش اصلی'],
  ['--cyan-400', '#2ADAD7', 'فیروزه‌ای لوگو'],
  ['--teal-500', '#14CDB5', 'سبزآبی کتاب'],
  ['--ok', '#2FD09A', 'موفق'],
  ['--warn', '#F2B24B', 'هشدار'],
  ['--danger', '#FF6B7A', 'خطا'],
  ['--text', '#F2F6FC', 'متن اصلی'],
  ['--text-2', '#9AABC2', 'متن ثانویه'],
  ['--text-3', '#6E7F98', 'متن سوم'],
];

const TYPE: [string, string, string][] = [
  ['display / 30', 'نمایش — عنوان صفحهٔ اصلی', 'display'],
  ['h1 / 23', 'عنوان صفحه و کارت قهرمان', 'h1'],
  ['h2 / 19', 'عنوان بخش', 'h2'],
  ['h3 / 16', 'عنوان کارت و گروه', 'h3'],
  ['body / 14.5', 'متن اصلی و گزینه‌های سؤال', 'body'],
  ['sm / 13', 'توضیح، فراداده', 'sm'],
  ['xs / 11.5', 'برچسب، یادداشت', 'xs'],
];

export function System() {
  const { toast, toggleTheme } = useProto();
  const [dlg, setDlg] = useState(false);
  const [drw, setDrw] = useState(false);

  return (
    <div className="page">
      <PageTitle
        title="سیستم طراحی"
        sub="توکن‌ها، تایپوگرافی و همهٔ کامپوننت‌های مشترک — مرجع بازبینی و پیاده‌سازی"
        actions={
          <button type="button" className="btn btn--ghost btn--sm" onClick={toggleTheme}>
            <Icon name="sun" size={14} />
            بررسی تم روشن
          </button>
        }
      />

      {/* ── رنگ ─────────────────────────────────────────────── */}
      <SectionHead title="۱. رنگ" hint="لنگر: نمونه‌برداری مستقیم از لوگو" />
      <div className="swatches">
        {COLORS.map(([tok, hex, label]) => (
          <div key={tok} className="swatch">
            <i style={{ background: `var(${tok})` }} />
            <div style={{ padding: '6px 8px', background: 'var(--surface-1)' }}>
              <div className="xs" style={{ direction: 'ltr', textAlign: 'left', fontFamily: 'var(--font-num)' }}>
                {tok}
              </div>
              <div className="xs muted-2" style={{ direction: 'rtl', textAlign: 'right' }}>
                {label} · <span className="ltr" style={{ display: 'inline' }}>{hex}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="row" style={{ marginTop: 12, gap: 10, flexWrap: 'wrap' }}>
        <Chip ai>
          <Icon name="sparkle" size={12} /> فیروزه‌ای = هوشیار و کنش‌های AI
        </Chip>
        <Chip>
          <span className="dot" style={{ color: 'var(--brand-600)' }} /> آبی = کنش اصلی و ناوبری فعال
        </Chip>
        <Chip ghost>پس‌زمینهٔ گرم/سرد: تیره برای مطالعهٔ طولانی</Chip>
      </div>

      {/* ── تایپوگرافی ──────────────────────────────────────── */}
      <SectionHead title="۲. تایپوگرافی" hint="Vazirmatn — ارقام فارسی، متن لاتین جدا" />
      <div className="panel panel--pad">
        {TYPE.map(([scale, sample, cls]) => (
          <div key={scale} className="type-row">
            <span>{scale}</span>
            <span className={cls}>{sample}</span>
          </div>
        ))}
        <div className="type-row">
          <span>mixed</span>
          <span>
            هورمون <span className="ltr">TSH</span> از هیپوفیز قدامی ترشح می‌شود؛ مقدار نرمال{' '}
            <span className="num">۰٫۴–۴٫۰</span> <span className="ltr">mIU/L</span> است.
          </span>
        </div>
        <div className="type-row" style={{ borderBottom: 0 }}>
          <span>numeric</span>
          <span className="num">۱۴۰۵/۰۷/۲۶ · ۰۹:۵۹ · ۷۷٪ · ۴۰۲۱۳۴۵۶</span>
        </div>
      </div>

      {/* ── دکمه‌ها ─────────────────────────────────────────── */}
      <SectionHead title="۳. دکمه‌ها" hint="یک اندازه به‌ازای هر نقش؛ نه بیشتر" />
      <div className="panel panel--pad" style={{ display: 'grid', gap: 14 }}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn btn--primary">کنش اصلی</button>
          <button type="button" className="btn btn--accent">
            <Icon name="sparkle" size={14} /> کنش هوشیار
          </button>
          <button type="button" className="btn btn--ghost">ثانویه</button>
          <button type="button" className="btn btn--quiet">آرام</button>
          <button type="button" className="btn btn--danger">خطرناک</button>
          <button type="button" className="btn btn--primary" disabled>غیرفعال</button>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn btn--primary btn--sm">کوچک</button>
          <button type="button" className="btn btn--ghost btn--sm">کوچک ثانویه</button>
          <button type="button" className="btn btn--primary btn--lg">بزرگ</button>
          <button type="button" className="iconbtn"><Icon name="bell" /></button>
          <button type="button" className="iconbtn"><Icon name="settings" /></button>
        </div>
      </div>

      {/* ── ورودی‌ها ────────────────────────────────────────── */}
      <SectionHead title="۴. ورودی‌ها" hint="ارتفاع لمسی ≥ ۴۰px، برچسب همیشه دیده می‌شود" />
      <div className="ds-grid">
        <label className="field">
          <span className="field__l">ورودی متنی</span>
          <input className="input" placeholder="مثلاً «چرخهٔ قلبی»" />
          <span className="field__hint">راهنمای کوتاه، نه تکرار برچسب</span>
        </label>
        <label className="field field--error">
          <span className="field__l">حالت خطا</span>
          <input className="input" defaultValue="۱۲۳" aria-invalid />
          <span className="field__err">
            <Icon name="alert" size={12} /> شمارهٔ دانشجویی ۸ رقم است.
          </span>
        </label>
        <div className="field">
          <span className="field__l">جست‌وجو</span>
          <div className="search" style={{ minWidth: 0, maxWidth: 'none', flex: 'none' }}>
            <Icon name="search" size={15} />
            <input placeholder="جست‌وجو…" />
            <span className="kbd">Ctrl K</span>
          </div>
        </div>
        <div className="field">
          <span className="field__l">انتخاب چندگانه (چیپ)</span>
          <div className="filters">
            <Chip active>فیزیولوژی</Chip>
            <Chip>بیوشیمی</Chip>
            <Chip>آناتومی</Chip>
          </div>
        </div>
      </div>

      {/* ── چیپ، برچسب، پیشرفت ──────────────────────────────── */}
      <SectionHead title="۵. برچسب و پیشرفت" />
      <div className="panel panel--pad" style={{ display: 'grid', gap: 16 }}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <Badge>پیش‌فرض</Badge>
          <Badge tone="ok">فعال</Badge>
          <Badge tone="warn">نزدیک</Badge>
          <Badge tone="danger">غلط</Badge>
          <Badge tone="info">نمونه</Badge>
          <Badge tone="locked">قفل</Badge>
        </div>
        <div style={{ display: 'grid', gap: 10, maxWidth: 520 }}>
          <Progress value={72} />
          <Progress value={48} tone="ok" />
          <div className="row" style={{ gap: 16 }}>
            <Ring value={77} label="دقت" />
            <Ring value={43} label="هفته" />
          </div>
        </div>
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <span className="timer">
            <Icon name="clock" size={14} /> <span className="num">۰۹:۵۹</span>
          </span>
          <span className="timer timer--urgent">
            <Icon name="clock" size={14} /> <span className="num">۰۰:۴۲</span>
          </span>
          <span className="countdown">
            <b className="num">۳</b>
            <span>روز</span>
          </span>
          <span className="countdown countdown--urgent">
            <b className="num">۱</b>
            <span>روز</span>
          </span>
        </div>
      </div>

      {/* ── فهرست، تب، جدول ─────────────────────────────────── */}
      <SectionHead title="۶. فهرست و تب" hint="فهرست جای شبکهٔ کارت — تراکم اطلاعات بیشتر، خوانایی بهتر" />
      <div className="panel panel--flush" style={{ marginBottom: 12 }}>
        {[
          ['جزوهٔ فیزیولوژی قلب — جلسهٔ ۷', 'pdf', '۳٫۲ مگابایت · ۴۲ صفحه'],
          ['ویدیو جلسهٔ ۷ — چرخهٔ قلبی', 'video', '۵۴:۱۲ · ۲۶۸ مگابایت'],
          ['پادکست مرور — تنفس', 'audio', '۲۲:۴۰ · ۹ مگابایت'],
        ].map(([t, k, m]) => (
          <button key={t} type="button" className="rrow" onClick={() => toast('نمونهٔ فهرست', 'info')}>
            <span className={`rrow__ic rrow__ic--${k}`}>
              <Icon name={k === 'pdf' ? 'file' : k === 'video' ? 'video' : 'audio'} size={18} />
            </span>
            <span>
              <span className="rrow__t">{t}</span>
              <span className="rrow__m">
                <span>{m}</span>
              </span>
            </span>
            <Badge tone="ok">فعال</Badge>
            <span className="rrow__go">
              <Icon name="back" size={16} />
            </span>
          </button>
        ))}
      </div>
      <div className="tabs">
        <button type="button" role="tab" aria-selected className="tab">همه</button>
        <button type="button" role="tab" aria-selected={false} className="tab">تازه‌ها</button>
        <button type="button" role="tab" aria-selected={false} className="tab">در دسترس من</button>
      </div>

      {/* ── دیالوگ، کشو، توست ──────────────────────────────── */}
      <SectionHead title="۷. لایه‌های روی صفحه" />
      <div className="panel panel--pad row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDlg(true)}>
          دیالوگ
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDrw(true)}>
          کشوی کنار
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => toast('توست موفق', 'ok')}>
          توست موفق
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => toast('توست خطا', 'err')}>
          توست خطا
        </button>
      </div>

      {/* ── حالت‌ها ─────────────────────────────────────────── */}
      <SectionHead title="۸. حالت‌های صفحه" hint="هر صفحه باید هر پنج حالت را داشته باشد" />
      <div className="ds-grid">
        <div className="panel panel--pad">
          <div className="xs muted-2" style={{ marginBottom: 10 }}>loading</div>
          <Skeleton rows={3} />
        </div>
        <div className="panel">
          <div className="xs muted-2" style={{ padding: '12px 16px 0' }}>empty</div>
          <Empty icon="layers" title="چیزی اینجا نیست" text="وقتی داده‌ای نیست، دلیلش و راه بعدی گفته می‌شود." />
        </div>
        <div className="panel panel--pad">
          <div className="xs muted-2" style={{ marginBottom: 10 }}>error / locked</div>
          <Note tone="danger">
            <b>اتصال برقرار نشد.</b> پاسخ‌های ثبت‌شده حفظ می‌شوند.
          </Note>
          <div style={{ height: 10 }} />
          <Note tone="warn" icon="lock">
            <b>در پلن تو نیست.</b> با ارتقا باز می‌شود.
          </Note>
        </div>
      </div>

      {/* ── کامپوننت سؤال ──────────────────────────────────── */}
      <SectionHead title="۹. کامپوننت سؤال" hint="همان چیزی که در تمرین و آزمون دیده می‌شود" />
      <div className="qcard">
        <div className="qmeta">
          <Chip ghost>فیزیولوژی</Chip>
          <Chip ghost>قلب</Chip>
          <Badge tone="warn">متوسط</Badge>
          <span className="grow" />
          <span className="xs muted-2">سؤال ۱ از ۶</span>
        </div>
        <p className="qstem">
          در یک دانشجوی سالم، افزایش ناگهانی بازگشت وریدی به قلب، در گام نخست کدام پاسخ را برمی‌انگیزد؟
        </p>
        <div className="qopts">
          <button type="button" className="qopt qopt--ok">
            <span className="qopt__l">الف</span>
            <span>افزایش برون‌ده قلبی از طریق مکانیسم فرانک–استارلینگ</span>
          </button>
          <button type="button" className="qopt">
            <span className="qopt__l">ب</span>
            <span>کاهش حجم ضربه‌ای به دلیل کاهش زمان پرشدن</span>
          </button>
          <button type="button" className="qopt qopt--bad">
            <span className="qopt__l">ج</span>
            <span>افزایش مقاومت عروق محیطی به‌طور اولیه</span>
          </button>
        </div>
      </div>

      {/* ── کامپوننت‌های هوشیار ─────────────────────────────── */}
      <SectionHead title="۱۰. کامپوننت‌های هوشیار" hint="پیام، منبع، کنش — بدون افکت تزئینی" />
      <div className="panel panel--pad" style={{ display: 'grid', gap: 12 }}>
        <div className="msg msg--me">
          <span className="avatar">ع ا</span>
          <div className="msg__b">
            <p>چرخهٔ قلبی را ساده توضیح بده.</p>
          </div>
        </div>
        <div className="msg">
          <span className="avatar avatar--ai">
            <Icon name="sparkle" size={16} />
          </span>
          <div className="msg__b">
            <p className="sm">مهم‌ترین نکته این است که بیشتر پرشدن بطن در دیاستول و به‌صورت غیرفعال رخ می‌دهد.</p>
            <ul>
              <li className="sm">دیاستول کوتاه ← پرشدن کمتر ← حجم ضربه‌ای کمتر.</li>
            </ul>
            <div className="msg__src">
              <Chip ghost>
                <Icon name="file" size={12} /> جزوهٔ جلسهٔ ۷
              </Chip>
            </div>
            <div className="msg__acts">
              <button type="button" className="btn btn--quiet btn--sm">
                <Icon name="copy" size={13} /> کپی
              </button>
              <button type="button" className="btn btn--quiet btn--sm">
                <Icon name="question" size={13} /> سؤال تمرینی
              </button>
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        <Note tone="ai" icon="layers">
          <b>قاعدهٔ اجرا:</b> هر کامپوننت تازه باید همین‌جا (با همهٔ حالت‌ها) اضافه شود، بعد در صفحه‌ها استفاده
          شود. صفحه‌ای که کامپوننتش این‌جا نیست، بازبینی نمی‌شود.
        </Note>
      </div>

      <Dialog
        open={dlg}
        title="نمونهٔ دیالوگ"
        onClose={() => setDlg(false)}
        actions={
          <>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => setDlg(false)}>
              تأیید
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDlg(false)}>
              انصراف
            </button>
          </>
        }
      >
        دیالوگ فقط برای تصمیم‌های کوتاه و بازگشت‌پذیر است؛ جریان‌های بلند در صفحه یا کشو انجام می‌شوند.
        فوکوس روی اولین دکمه می‌رود و Escape می‌بندد.
      </Dialog>
      <Drawer open={drw} title="نمونهٔ کشو" onClose={() => setDrw(false)}>
        <p className="sm muted">
          کشو برای محتوای مکمل (اعلان‌ها، جست‌وجو، جزئیات فیلتر) استفاده می‌شود و در موبایل تمام‌عرض است.
        </p>
        <div className="panel panel--quiet" style={{ padding: 12 }}>
          <div className="row">
            <Icon name="bell" size={15} />
            <span className="sm">اعلان نمونه</span>
          </div>
        </div>
      </Drawer>

      <div className="trace trace--node" />
      <p className="xs muted-2">
        ارقام فارسی از یک نگاشت واحد ({fa('0-9')}) می‌آیند؛ چیدمان عددی چپ‌به‌راست و متن راست‌به‌چپ است.
      </p>
    </div>
  );
}
