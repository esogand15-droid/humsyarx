import { useState } from 'react';
import { Icon, type IconName } from '../components/Icon';
import { Badge, Chip, Note as NoteBox, SectionHead } from '../components/ui';

/* ═══════════════════════════════════════════════════════════════════
   ماتریس قابلیت، ماتریس آزمون و الزامات نصب
   هدف: هیچ کنترل نمونه‌ای با قابلیت تولیدی اشتباه گرفته نشود.
   پنج رده: ۱) پیاده و راستی‌آزمایی‌شده ۲) در پروتوتایپ نمایش داده شده
   ۳) نیازمند مهندسی بیشتر ۴) نیازمند قابلیت بومی ۵) به نسخهٔ بعد موکول
   ═══════════════════════════════════════════════════════════════════ */

type Class = 1 | 2 | 3 | 4 | 5;

const CLASSES: Record<Class, { label: string; tone: 'ok' | 'info' | 'warn' | 'danger' | 'locked'; short: string }> = {
  1: { label: 'پیاده و راستی‌آزمایی‌شده', tone: 'ok', short: 'راستی‌آزمایی‌شده' },
  2: { label: 'در نسخهٔ طراحی نشان داده شده', tone: 'info', short: 'نمونه' },
  3: { label: 'نیازمند مهندسی بیشتر', tone: 'warn', short: 'مهندسی' },
  4: { label: 'نیازمند قابلیت بومی', tone: 'danger', short: 'بومی' },
  5: { label: 'به نسخهٔ بعد موکول', tone: 'locked', short: 'بعداً' },
};

type Row = { group: string; name: string; cls: Class; note: string };

const ROWS: Row[] = [
  { group: 'سازمان‌دهی', name: 'دفترها و پوشه‌های تودرتو', cls: 2, note: 'درخت در رابط؛ ذخیره‌سازی سمت سرور ندارد' },
  { group: 'سازمان‌دهی', name: 'برچسب، نشان، سنجاق', cls: 2, note: 'وضعیت محلی، بدون همگام‌سازی' },
  { group: 'سازمان‌دهی', name: 'جست‌وجو و فیلتر', cls: 2, note: 'روی دادهٔ محلی همان نشست' },
  { group: 'سازمان‌دهی', name: 'یادداشت‌های اخیر و آرشیو', cls: 3, note: 'نیازمند مدل داده و endpoint' },
  { group: 'ویرایش', name: 'متن ساختاریافته، فهرست، جدول', cls: 2, note: 'contentEditable واقعی؛ رفتن به تولید با ویرایشگر بالغ' },
  { group: 'ویرایش', name: 'واگرد/ازنو', cls: 2, note: 'تاریخچهٔ بومی مرورگر' },
  { group: 'ویرایش', name: 'ذخیرهٔ خودکار + وضعیت', cls: 2, note: 'شبیه‌سازی زمانی؛ ذخیرهٔ پایدار ندارد' },
  { group: 'ویرایش', name: 'بازیابی از قطع ویرایش', cls: 3, note: 'IndexedDB + journal لازم است' },
  { group: 'ویرایش', name: 'ویرایش هم‌زمان دو دستگاه', cls: 3, note: 'CRDT/OT + سرویس همگام‌سازی' },
  { group: 'سند', name: 'نمای PDF و پیمایش صفحه', cls: 3, note: 'نمایش‌گر واقعی (pdf.js) و لینک به فایل موجود لازم است' },
  { group: 'سند', name: 'جست‌وجو در متن سند', cls: 3, note: 'در نمونه روی متن ساختگی؛ نیازمند ایندکس متن PDF' },
  { group: 'سند', name: 'هایلایت و پیوند به پاراگراف', cls: 2, note: 'رابط پیوند ساخته شده؛ لنگر پایدار در تولید لازم است' },
  { group: 'سند', name: 'بازگشت به محل مطالعه', cls: 3, note: 'ذخیرهٔ موقعیت در سرور' },
  { group: 'دست‌نویس', name: 'قلم، هایلایتر، پاک‌کن', cls: 2, note: 'بوم Canvas با pointer events' },
  { group: 'دست‌نویس', name: 'حساسیت به فشار', cls: 4, note: 'فقط جایی که مرورگر pressure می‌دهد؛ یکنواخت نیست' },
  { group: 'دست‌نویس', name: 'رد کف دست', cls: 4, note: 'در وب تضمین‌شده نیست؛ به لایهٔ بومی/StylusKit نیاز دارد' },
  { group: 'دست‌نویس', name: 'جوهر کم‌تأخیر', cls: 4, note: 'Predictive inking در مرورگر iOS در دسترس نیست' },
  { group: 'هوش مطالعه', name: 'الگوی یادداشت پزشکی', cls: 3, note: 'قالب‌ها تعریف نشده‌اند؛ محتوا باید با تیم آموزشی نهایی شود' },
  { group: 'هوش مطالعه', name: 'فلش‌کارت و مرور فاصله‌دار', cls: 3, note: 'الگوریتم و مدل داده لازم است' },
  { group: 'هوش مطالعه', name: 'کنش زمینه‌ای هوشیار', cls: 2, note: 'رابط درج خلاصه؛ سرویس واقعی وصل نیست' },
  { group: 'قابلیت اطمینان', name: 'پیش‌نویس محلی بادوام', cls: 3, note: 'IndexedDB + SW + صف ارسال' },
  { group: 'قابلیت اطمینان', name: 'حالت آفلاین و در انتظار همگام‌سازی', cls: 2, note: 'وضعیت در رابط؛ منطق همگام‌سازی ندارد' },
  { group: 'قابلیت اطمینان', name: 'خروجی و پشتیبان‌گیری', cls: 3, note: 'تولید PDF/MD سمت سرور یا کارگر مرورگر' },
  { group: 'نصب', name: 'نصب روی صفحهٔ خانه (PWA)', cls: 2, note: 'manifest و SW ساخته شده؛ HTTPS و آزمون دستگاه واقعی لازم است' },
  { group: 'نصب', name: 'ورود به کلاس بدون کد QR/NFC', cls: 5, note: 'خارج از دامنهٔ این مرحله' },
];

type TestRow = { id: string; what: string; how: string; result: 'pass' | 'manual' | 'na' };

const TESTS: TestRow[] = [
  { id: 'T1', what: 'ناوبری اصلی و مسیرهای تودرتو', how: 'E2E خودکار (۲۵ بررسی)', result: 'pass' },
  { id: 'T2', what: 'جست‌وجو و فیلتر منابع', how: 'E2E خودکار', result: 'pass' },
  { id: 'T3', what: 'تمرین، بازخورد، آزمون و تایمر', how: 'E2E خودکار', result: 'pass' },
  { id: 'T4', what: 'هوشیار: حالت فکر کردن، پاسخ، منابع', how: 'E2E خودکار', result: 'pass' },
  { id: 'T5', what: 'کنتراست در تم تیره و روشن', how: 'بازرسی WCAG در ۱۱ مسیر × ۲ تم', result: 'pass' },
  { id: 'T6', what: 'ویرایش یادداشت و ذخیرهٔ خودکار', how: 'دستی + بازرسی DOM', result: 'manual' },
  { id: 'T7', what: 'دست‌نویس با ماوس/لمس', how: 'دستی روی بوم', result: 'manual' },
  { id: 'T8', what: 'حساسیت فشار قلم', how: 'نیازمند دستگاه با قلم', result: 'na' },
  { id: 'T9', what: 'رد کف دست', how: 'نیازمند دستگاه با قلم', result: 'na' },
  { id: 'T10', what: 'نصب PWA روی iOS و اندروید', how: 'نیازمند دستگاه واقعی + HTTPS', result: 'na' },
  { id: 'T11', what: 'رفتار کیبورد مجازی و ناحیهٔ امن', how: 'نیازمند شبیه‌ساز/دستگاه واقعی', result: 'na' },
  { id: 'T12', what: 'صفحه‌خوان (VoiceOver/TalkBack)', how: 'نیازمند آزمون دستی', result: 'na' },
];

const DEVICES = [
  {
    title: 'تلفن (۳۹۰–۴۳۰px)',
    icon: 'device' as IconName,
    points: [
      'یک کار در هر لحظه: فهرست ⇄ یادداشت با جابه‌جایی push',
      'نوار قالب‌بندی پایین صفحه و بالای کیبورد',
      'شیت پایین برای دفترها، نسخه‌ها، خروجی',
      'ناحیهٔ امن پایین در نوار و ویرایشگر',
    ],
  },
  {
    title: 'تبلت (۷۶۸–۱۰۲۴px)',
    icon: 'grid' as IconName,
    points: [
      'دو ستون: فهرست + ویرایشگر',
      'دفترها در شیت؛ نه در ستون باریک',
      'نمای کنار‌هم سند زیر ویرایشگر (نه کنار آن)',
      'کیبورد خارجی: میان‌برهای ذخیره/جست‌وجو',
    ],
  },
  {
    title: 'دسکتاپ (≥۱۲۰۰px)',
    icon: 'columns' as IconName,
    points: [
      'سه ستون پایدار: دفترها | فهرست | سند',
      'سند کنار یادداشت در حالت مطالعهٔ عمیق',
      'پنل زمینه: منبع، فلش‌کارت، هوشیار',
      'میان‌برهای Ctrl/⌘ + S و /',
    ],
  },
];

export function Capability() {
  const [tab, setTab] = useState<'cap' | 'test' | 'pwa' | 'device' | 'layout' | 'inv'>('inv');
  const [filter, setFilter] = useState<Class | null>(null);

  const rows = filter ? ROWS.filter((r) => r.cls === filter) : ROWS;

  return (
    <div className="page">
      <SectionHead
        title="ماتریس قابلیت و آمادگی"
        hint="تفکیک صریح میان آنچه واقعاً کار می‌کند، آنچه فقط نمایش داده می‌شود و آنچه به مهندسی یا قابلیت بومی نیاز دارد."
        action={<Badge tone="warn">وضعیت: پیش از تأیید طراحی</Badge>}
      />

      <div className="row row-wrap" style={{ gap: 6, marginBottom: 'var(--s-5)' }}>
        <Chip active={tab === 'cap'} onClick={() => setTab('cap')}>
          قابلیت‌ها
        </Chip>
        <Chip active={tab === 'test'} onClick={() => setTab('test')}>
          ماتریس آزمون
        </Chip>
        <Chip active={tab === 'device'} onClick={() => setTab('device')}>
          فرم‌فاکتورها
        </Chip>
        <Chip active={tab === 'pwa'} onClick={() => setTab('pwa')}>
          نصب و PWA
        </Chip>
        <Chip active={tab === 'layout'} onClick={() => setTab('layout')}>
          چیدمان واکنش‌گرا
        </Chip>
        <Chip active={tab === 'inv'} onClick={() => setTab('inv')}>
          فهرست صفحه‌ها
        </Chip>
      </div>

      {tab === 'cap' && (
        <>
          <div className="row row-wrap" style={{ gap: 6, marginBottom: 'var(--s-4)' }}>
            <Chip active={filter === null} onClick={() => setFilter(null)}>
              همه ({ROWS.length})
            </Chip>
            {(Object.keys(CLASSES).map(Number) as Class[]).map((c) => (
              <Chip key={c} active={filter === c} onClick={() => setFilter(filter === c ? null : c)}>
                {CLASSES[c].short} ({ROWS.filter((r) => r.cls === c).length})
              </Chip>
            ))}
          </div>

          <div className="panel panel--flush">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 110 }}>گروه</th>
                  <th>قابلیت</th>
                  <th style={{ width: 170 }}>رده</th>
                  <th>وضعیت واقعی</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name}>
                    <td className="xs muted-2">{r.group}</td>
                    <td className="sm">{r.name}</td>
                    <td>
                      <Badge tone={CLASSES[r.cls].tone}>{CLASSES[r.cls].short}</Badge>
                    </td>
                    <td className="xs muted">{r.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <NoteBox tone="warn" icon="alert">
            تنها ردیف‌های «راستی‌آزمایی‌شده» با آزمون خودکار یا بازرسی سنجیده شده‌اند. ردیف‌های «بومی» با کد وب قابل
            تحویل نیستند و در نقشهٔ راه به لایهٔ Capacitor یا اپ بومی واگذار شده‌اند.
          </NoteBox>
        </>
      )}

      {tab === 'test' && (
        <>
          <div className="panel panel--flush">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 54 }}>#</th>
                  <th>آنچه سنجیده می‌شود</th>
                  <th>روش</th>
                  <th style={{ width: 120 }}>نتیجه</th>
                </tr>
              </thead>
              <tbody>
                {TESTS.map((t) => (
                  <tr key={t.id}>
                    <td className="xs num muted-2">{t.id}</td>
                    <td className="sm">{t.what}</td>
                    <td className="xs muted">{t.how}</td>
                    <td>
                      {t.result === 'pass' && <Badge tone="ok">گذشت</Badge>}
                      {t.result === 'manual' && <Badge tone="info">دستی انجام شد</Badge>}
                      {t.result === 'na' && <Badge tone="locked">راستی‌آزمایی نشده</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <NoteBox tone="ai" icon="info">
            هر ردیف «راستی‌آزمایی نشده» یعنی ادعایی دربارهٔ آن نمی‌کنیم. آزمون دستگاه واقعی (iOS/Android/تبلت + قلم) پیش از
            اعلام آمادگی نسخهٔ نصب‌شدنی الزامی است.
          </NoteBox>
        </>
      )}

      {tab === 'device' && (
        <div className="grid grid--3">
          {DEVICES.map((d) => (
            <section key={d.title} className="panel panel--pad">
              <div className="row" style={{ marginBottom: 'var(--s-3)' }}>
                <span className="iconbox">
                  <Icon name={d.icon} size={16} />
                </span>
                <b className="sm">{d.title}</b>
              </div>
              <ul className="bullets">
                {d.points.map((p) => (
                  <li key={p} className="xs muted">
                    {p}
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <NoteBox tone="warn" icon="device">
            تبلت نسخهٔ بزرگ‌شدهٔ تلفن نیست و تلفن نسخهٔ فشردهٔ دسکتاپ: تفاوت در تعداد پنل‌ها، جای نوار ابزار و رفتار کیبورد
            است، نه فقط اندازهٔ فونت.
          </NoteBox>
        </div>
      )}



      {tab === 'inv' && (
        <div style={{ display: 'grid', gap: 'var(--s-4)' }}>
          <div className="panel panel--flush">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 150 }}>صفحه</th>
                  <th>کارکرد امروز</th>
                  <th style={{ width: 210 }}>موبایل: چه تغییری کرد</th>
                  <th style={{ width: 170 }}>دسکتاپ/تبلت</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['خانه (SC-010)', 'ادامهٔ مطالعه، آزمون بعدی، دسترسی‌ها، وضعیت هفته، کارها، تازه‌ها، هوشیار, درس‌ها، اطلاعیه‌ها',
                    'ترتیب موبایل؛ هفته یک نوار خلاصه + ستون ۵۰px بدون حلقه؛ درس‌ها و اطلاعیه‌ها جمع‌شونده',
                    'دو ستون کامل، حلقه، همهٔ فهرست‌ها باز'],
                  ['منابع (SC-020)', 'جست‌وجو، فیلتر درس/نوع، مرتب‌سازی، تب‌ها، فهرست منابع',
                    'فیلترهای تک‌خطی افقی با محو لبه؛ فهرست ردیفی فشرده؛ متن کوتاه‌تر',
                    'شبکه/فهرست پهن با همهٔ فیلترها'],
                  ['جزئیات منبع (SC-021)', 'پیش‌نمایش صفحه، ورق زدن، قفل اشتراک، دانلود، مرتبط‌ها',
                    'پیش‌نمایش کوتاه‌تر و دکمه‌های چسبیده، فهرست مرتبط فشرده',
                    'پیش‌نمایش بلندتر و ستون مرتبط‌ها'],
                  ['بانک سؤال (SC-030)', 'انتخاب محدوده، شروع تمرین، آزمون زمان‌دار، تاریخچه',
                    'محدوده و مبحث در دو نوار افقی؛ کارت کوتاه‌تر؛ تاریخچه فشرده',
                    'دو ستون با پنل راهنما'],
                  ['تمرین (SC-031)', 'سؤال، گزینه‌ها، بازخورد فوری، توضیح',
                    'خوانایی اولویت دارد: گزینه‌ها بدون فشردگی، پنل سرنخ به شیت',
                    'ستون سرنخ کنار سؤال'],
                  ['آزمون (SC-032/033)', 'تایمر، پیمایش سؤال، دیالوگ خروج، کارنامه',
                    'نوار وضعیت فشرده، بدون قفل اسکرول در کارنامه',
                    'پنل ناوبری سؤال‌ها کنار'],
                  ['هوشیار (SC-040)', 'گفتگو، پیشنهادها، ارسال، منابع پاسخ',
                    'ریل گفتگوها در شیت؛ پیام‌ها تمام‌عرض؛ نوار نوشتن بالای کیبورد',
                    'ریل کنار گفتگو'],
                  ['یادداشت‌ها (SC-070)', 'دفترها، فهرست، ویرایشگر، سند کنار‌هم، دست‌نویس',
                    'جابه‌جایی push، نوار ابزار بالای نوار پایین، دفترها در شیت',
                    'سه ستون + سند کنار‌هم'],
                  ['برنامه (SC-050)', 'تقویم هفته، آزمون‌ها، کارها',
                    'نمای هفته → فهرست روزانه (بدون ۷ ستون باریک)؛ روزهای خالی حذف',
                    'نمای هفته کامل + فهرست'],
                  ['پیشرفت (SC-060)', 'هویت دانشجو، سه شاخص، دروس، دستاوردها',
                    'هویت فشرده؛ سه شاخص یک گروه با جداکننده (نه سه کارت)',
                    'سه کارت جدا با فضای باز'],
                  ['اشتراک (SC-061)', 'پلن، وضعیت، تمدید، پرداخت‌ها',
                    'ردیف‌های فشرده، هشدارها حفظ شده', 'کارت‌های پلن کنار هم'],
                  ['تنظیمات (SC-062)', 'حساب، اعلان، ظاهر، حریم، خروج',
                    'گروه‌بندی فشرده، بدون حذف تأییدیه', 'همان با فاصلهٔ بیشتر'],
                  ['سیستم طراحی (SC-090)', 'توکن‌ها و کامپوننت‌ها', 'فهرست کوتاه‌شده، سواچ‌ها فشرده', 'کامل'],
                  ['ماتریس قابلیت (SC-091)', 'قابلیت، آزمون، فرم‌فاکتور، PWA', 'جدول با اسکرول افقیِ عمدی', 'جدول کامل'],
                ].map(([p1, p2, p3, p4]) => (
                  <tr key={p1}>
                    <td className="xs" style={{ fontWeight: 600 }}>{p1}</td>
                    <td className="xs muted">{p2}</td>
                    <td className="xs">{p3}</td>
                    <td className="xs muted-2">{p4}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="grid grid--2">
            <div className="panel panel--pad">
              <b className="sm">بزرگ‌ترین منابع اسکرول غیرضروری (پیش از اصلاح)</b>
              <ul className="bullets" style={{ marginTop: 8 }}>
                <li className="xs muted">کارت‌های تودرتو: هر ردیف کارت، هر بخش کارت، هر آمار کارت جدا.</li>
                <li className="xs muted">تکرار عنوان: عنوان صفحه + عنوان بخش + عنوان کارت برای یک محتوا.</li>
                <li className="xs muted">نمای هفت‌ستونه در ۳۹۰px: ستون‌ها باریک و متن شکسته، ارتفاع بالا.</li>
                <li className="xs muted">فیلترها در چند ردیف عمودی (سه ردیف چیپ).</li>
                <li className="xs muted">برچسب «دادهٔ نمونه» در سربرگ.</li>
                <li className="xs muted">حلقهٔ هدف بزرگ در موبایل که با متن تکراری همراه بود.</li>
              </ul>
            </div>
            <div className="panel panel--pad">
              <b className="sm">قاعده‌های جدید موبایل (فقط ≤۶۰۰px)</b>
              <ul className="bullets" style={{ marginTop: 8 }}>
                <li className="xs muted">توکن فاصلهٔ فشرده؛ اندازهٔ متن و هدف لمسی دست‌نخورده.</li>
                <li className="xs muted">فیلترها: یک نوار افقی با محو لبه برای نشانهٔ ادامه.</li>
                <li className="xs muted">سنجه‌ها: یک گروه با جداکننده، نه سه کارت.</li>
                <li className="xs muted">بخش‌های ثانویه با «بیشتر» باز می‌شوند؛ در دسکتاپ همیشه باز.</li>
                <li className="xs muted">جدول‌ها اسکرول افقی عمدی دارند (بدون سرریز صفحه).</li>
                <li className="xs muted">برچسب «نمونه» به سربرگ منتقل شد؛ در حالت نصب دیده می‌شود، ابزار بازبینی نه.</li>
              </ul>
            </div>
          </section>
        </div>
      )}

      {tab === 'layout' && (
        <div style={{ display: 'grid', gap: 'var(--s-5)' }}>
          <section className="panel panel--pad">
            <b className="sm">۱) بازرسی: ریشهٔ ایرادها</b>
            <ul className="bullets" style={{ marginTop: 8 }}>
              <li className="xs muted">
                <b>قاب پیش‌نمایش به‌جای چیدمان:</b> عرض جعلی با <span className="ltr">data-preview</span> ساخته می‌شد و
                اندازه‌گیری‌ها به عرض پنجره گره خورده بود؛ نتیجهٔ تصویر تو: کارت پهن، ستون باریک، فضای خالی بزرگ.
              </li>
              <li className="xs muted">
                <b>سقف عرض ثابت:</b> <span className="ltr">--content-max: 1220px</span> روی ۱۹۲۰ فضای مرده می‌ساخت.
              </li>
              <li className="xs muted">
                <b>ترتیب موبایل تصادفی بود:</b> حذف ستون با <span className="ltr">grid-template-columns: 1fr</span> ترتیب
                دسکتاپ را نگه می‌داشت، در حالی که موبایل ترتیب دیگری لازم دارد.
              </li>
              <li className="xs muted">
                <b>نمودار ثابت:</b> ستون‌های هفتگی با ارتفاع ثابت در عرض کم فشرده و در عرض زیاد کشیده می‌شدند.
              </li>
              <li className="xs muted">
                <b>اسکرول دوگانه:</b> پنجره و پوسته هر دو اسکرول می‌کردند؛ در PWA و با کیبورد باز پرش ایجاد می‌کرد.
              </li>
              <li className="xs muted">
                <b>ابزار بازبینی روی محصول:</b> دکمهٔ «بازبینی» در حالت نصب‌شده هم دیده می‌شد.
              </li>
            </ul>
          </section>

          <section className="grid grid--3">
            {[
              {
                t: 'دسکتاپ ≥۱۰۰۰px',
                rows: [
                  ['پوسته', 'سایدبار متنی + نوار بالا، اسکرول تنها در #main'],
                  ['خانه', 'دو ستون ۱٫۵۵ / ۰٫۹۵ — تمام عرض، بدون سقف ثابت'],
                  ['≥۱۵۰۰px', 'ستون کنار پهن‌تر (۳۶۰px+)، padding بازتر'],
                  ['نمودار هفته', 'کامل، با برچسب همهٔ روزها و حلقهٔ هدف'],
                  ['یادداشت', 'سه ستون + سند کنار‌هم'],
                ],
              },
              {
                t: 'تبلت ۶۰۱–۱۲۷۹',
                rows: [
                  ['پوسته', 'ریل آیکنی ۷۶px، نوار بالا فشرده، بدون تب پایین'],
                  ['خانه', 'عمودی؛ در حالت افقی ≥۹۰۰px دو ستون'],
                  ['کارت هفته', 'آمار و نمودار کنار هم (۲ ستون داخلی)'],
                  ['یادداشت', 'فهرست + ویرایشگر، دفترها در شیت'],
                  ['هدف لمسی', 'حداقل ۴۰px برای کنش‌های اصلی'],
                ],
              },
              {
                t: 'موبایل ≤۶۰۰',
                rows: [
                  ['پوسته', 'سربرگ ۵۶px + نوار پایین ۵ مقصد، بدون سایدبار'],
                  ['ترتیب', 'آزمون بعدی ← ادامه ← دسترسی‌ها ← هفته ← کارها ← تازه‌ها ← هوشیار'],
                  ['کارت هفته', 'خلاصهٔ متنی + نمودار ۶۲px با برچسب یک‌درمیان'],
                  ['دسترسی سریع', 'شبکهٔ ۲ ستونه با متن کوتاه'],
                  ['یادداشت', 'جابه‌جایی push، نوار ابزار بالای نوار پایین'],
                ],
              },
            ].map((col) => (
              <section key={col.t} className="panel panel--pad">
                <b className="sm">{col.t}</b>
                <table className="tbl" style={{ marginTop: 10 }}>
                  <tbody>
                    {col.rows.map(([k, v]) => (
                      <tr key={k}>
                        <td className="xs muted-2" style={{ width: 84 }}>{k}</td>
                        <td className="xs">{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
          </section>

          <section className="panel panel--pad">
            <b className="sm">۲) قاعدهٔ فنی — چرا دیگر می‌شکند</b>
            <ul className="bullets" style={{ marginTop: 8 }}>
              <li className="xs muted">
                کل چیدمان با <span className="ltr">container query</span> روی <span className="ltr">.frame</span> تصمیم می‌گیرد؛
                پس قاب پیش‌نمایش و پنجرهٔ واقعی دقیقاً یک رفتار دارند و ایراد «قاب موبایل با محتوای دسکتاپ» تکرار نمی‌شود.
              </li>
              <li className="xs muted">نمودارها <span className="ltr">container-type: inline-size</span> دارند؛ رفتارشان به عرض کارت وابسته است، نه دستگاه.</li>
              <li className="xs muted">شبکهٔ دسترسی سریع با <span className="ltr">auto-fit / minmax(158px)</span> خودش ستون‌بندی می‌کند.</li>
              <li className="xs muted">اسکرول فقط در <span className="ltr">#main</span> است؛ <span className="ltr">body: overflow hidden</span> و ارتفاع از <span className="ltr">100dvh</span>.</li>
              <li className="xs muted">در حالت نصب‌شده (<span className="ltr">display-mode: standalone</span>) ابزار بازبینی رندر نمی‌شود.</li>
            </ul>
          </section>

          <section className="panel panel--flush">
            <table className="tbl">
              <thead>
                <tr><th>قاب</th><th>سرریز افقی</th><th>ناوبری</th><th>نتیجه</th></tr>
              </thead>
              <tbody>
                {[
                  ['۳۶۰×۸۰۰ / ۳۷۵×۸۱۲ / ۳۹۳×۸۵۲ / ۴۳۰×۹۳۲', '۰', 'نوار پایین', 'pass'],
                  ['۷۶۸×۱۰۲۴ / ۸۰۰×۱۲۸۰ (تبلت عمودی)', '۰', 'ریل', 'pass'],
                  ['۱۰۲۴×۷۶۸ (تبلت افقی)', '۰', 'ریل + دو ستون', 'pass'],
                  ['۱۲۸۰×۸۰۰ / ۱۴۴۰×۹۰۰ / ۱۹۲۰×۱۰۸۰', '۰', 'سایدبار', 'pass'],
                  ['کیبورد مجازی باز', '—', '—', 'manual'],
                  ['بزرگ‌نمایی مرورگر ۱۵۰٪', '۰', '—', 'pass'],
                ].map(([a, b2, c, r]) => (
                  <tr key={a}>
                    <td className="xs">{a}</td>
                    <td className="xs num">{b2}</td>
                    <td className="xs muted">{c}</td>
                    <td>{r === 'pass' ? <Badge tone="ok">گذشت</Badge> : <Badge tone="locked">راستی‌آزمایی نشده</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <NoteBox tone="warn" icon="alert">
            باقی‌مانده: آزمون کیبورد مجازی روی دستگاه واقعی (iOS/Android)، چیدمان split-screen در iPad، و مقایسهٔ
            «قبل/بعد» که به همین ترتیب انجام شده است. هیچ‌کدام را ادعای تأییدشده نمی‌کنیم.
          </NoteBox>
        </div>
      )}

      {tab === 'pwa' && (
        <div className="grid grid--2">
          <section className="panel panel--pad">
            <b className="sm">سه حالت اجرا — تفکیک صریح</b>
            <table className="tbl" style={{ marginTop: 10 }}>
              <thead>
                <tr>
                  <th>حالت</th>
                  <th>نتیجهٔ قابل انتظار</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="sm">Safari عادی</td>
                  <td className="xs muted">نوارهای مرورگر دیده می‌شوند؛ ناحیهٔ امن مدیریت می‌شود.</td>
                </tr>
                <tr>
                  <td className="sm">Add to Home Screen</td>
                  <td className="xs muted">
                    اجرای مستقل بدون نوار Safari، به‌شرط manifest درست، `display: standalone` و HTTPS. Dynamic Island و
                    ناحیهٔ امن همچنان وجود دارند.
                  </td>
                </tr>
                <tr>
                  <td className="sm">اپ بومی / پوستهٔ Capacitor</td>
                  <td className="xs muted">کنترل بیشتر روی تجربه و دسترسی به قابلیت بومی؛ با محدودیت‌های iOS.</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section className="panel panel--pad">
            <b className="sm">چیزهایی که پیاده شده‌اند</b>
            <ul className="bullets" style={{ marginTop: 8 }}>
              <li className="xs muted">manifest با نام، رنگ‌ها، `start_url` و آیکن‌های ۱۹۲/۵۱۲</li>
              <li className="xs muted">`display: standalone`، `orientation` و `scope` محدود به ریشهٔ اپ</li>
              <li className="xs muted">متاتگ‌های iOS: `apple-mobile-web-app-capable`، وضعیت نوار، عنوان</li>
              <li className="xs muted">service worker با پیش‌بارگذاری پوسته و پاسخ آفلاین</li>
              <li className="xs muted">مسیرهای داخلی hash؛ هیچ ناوبری داخلی تب Safari باز نمی‌کند</li>
              <li className="xs muted">مدیریت ناحیهٔ امن با `env(safe-area-inset-*)`</li>
            </ul>
          </section>

          <section className="panel panel--pad">
            <b className="sm">چیزهایی که در وب ممکن نیست</b>
            <ul className="bullets" style={{ marginTop: 8 }}>
              <li className="xs muted">CSS نمی‌تواند Safari را مجبور به رفتار کاملاً بومی کند</li>
              <li className="xs muted">نوار وضعیت و Dynamic Island با CSS حذف نمی‌شوند؛ فقط مدیریت می‌شوند</li>
              <li className="xs muted">رد کف دست و جوهر کم‌تأخیر در مرورگر تضمین‌شده نیست</li>
              <li className="xs muted">اعلان push در iOS فقط برای PWA نصب‌شده و با اجازهٔ کاربر</li>
            </ul>
          </section>

          <section className="panel panel--pad">
            <b className="sm">پیش از اعلام آمادگی</b>
            <ul className="bullets" style={{ marginTop: 8 }}>
              <li className="xs muted">HTTPS روی دامنهٔ Railway و بررسی `start_url` نهایی</li>
              <li className="xs muted">آزمون نصب واقعی روی iPhone و Android</li>
              <li className="xs muted">آزمون آفلاین: پوسته بیاید، محتوا پیام روشن بدهد</li>
              <li className="xs muted">حذف کشِ نسخه‌های قبلی SW با استراتژی نسخه‌بندی</li>
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
