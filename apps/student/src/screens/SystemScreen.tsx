import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AppBar, Brand, Button, Card, Chip, EmptyState, IconButton, Input, ListRow,
  ProgressBar, ReaderToolbar, Sheet, SkeletonStack, Stat, Switch, Toast,
} from '../components';
import type { ReaderTool } from '../components';
import { Icon, ICON_NAMES } from '../icons';
import { useTheme, type ThemeMode } from '../lib/theme';

const SWATCHES: { token: string; label: string; css: string }[] = [
  { token: '--paper', label: 'کاغذ', css: 'var(--paper)' },
  { token: '--paper-2', label: 'سطح کارت', css: 'var(--paper-2)' },
  { token: '--paper-3', label: 'سطح آرام', css: 'var(--paper-3)' },
  { token: '--ink', label: 'مرکب', css: 'var(--ink)' },
  { token: '--ink-3', label: 'مرکب کم‌رنگ', css: 'var(--ink-3)' },
  { token: '--brand', label: 'آبی برند (کنش)', css: 'var(--brand)' },
  { token: '--amber', label: 'عسلی (گرمی)', css: 'var(--amber)' },
  { token: '--cyan', label: 'فیروزه‌ای', css: 'var(--cyan)' },
  { token: '--ok', label: 'تأیید', css: 'var(--ok)' },
  { token: '--danger', label: 'خطا', css: 'var(--danger)' },
  { token: '--midnight', label: 'سرمه‌ای نشان', css: 'var(--midnight)' },
];

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: 30 }}>
      <h2 className="h2">{title}</h2>
      {sub && <p className="small" style={{ marginBottom: 12 }}>{sub}</p>}
      <div style={{ marginTop: 12 }}>{children}</div>
    </section>
  );
}

/** صفحهٔ زندهٔ سیستم طراحی — مرجع بصری، همان چیزی که کد از آن می‌آید. */
export function SystemScreen() {
  const { mode, setMode } = useTheme();
  const [tool, setTool] = useState<ReaderTool | null>('pen');
  const [on, setOn] = useState(true);
  const [sheet, setSheet] = useState(false);

  const MODES: { id: ThemeMode; label: string }[] = [
    { id: 'light', label: 'روشن' },
    { id: 'dark', label: 'تاریک' },
    { id: 'system', label: 'سیستم' },
  ];

  return (
    <>
      <AppBar
        title="سیستم طراحی"
        sub="مرکب · v0.1.0"
        back
        actions={<IconButton icon="i-settings" label="تنظیمات" onClick={() => setSheet(true)} />}
      />

      <div className="page">
        <div className="row gap-12" style={{ alignItems: 'center' }}>
          <Brand size="lg" />
          <div className="grow">
            <div className="eyebrow">هویت واحد</div>
            <div className="h1">مرکب</div>
          </div>
        </div>
        <p className="lede mt-12">
          کاغذ گرم، مرکب تیره، آبیِ لوگو فقط روی کنش. بدون شیشه، بدون هاله، بدون ایموجی.
          هر رنگ یک نقش دارد و هیچ صفحه‌ای از این قاعده بیرون نمی‌زند.
        </p>

        <Card variant="quiet" className="mt-16">
          <div className="row gap-8" style={{ justifyContent: 'space-between' }}>
            <span className="small">تم</span>
            <div className="hscroll">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  className="tabchip"
                  aria-selected={mode === m.id}
                  onClick={() => setMode(m.id)}
                  type="button"
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Section title="رنگ" sub="هر توکن یک نقش؛ رنگ تزئینی وجود ندارد.">
          <div className="swatches">
            {SWATCHES.map((s) => (
              <div className="sw" key={s.token}>
                <i style={{ background: s.css }} />
                <span>
                  <b>{s.label}</b>
                  <span className="mono tiny">{s.token}</span>
                </span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="تایپوگرافی" sub="Vazirmatn — ارتفاع خط فارسی هرگز زیر ۱.۷.">
          <Card>
            <div className="h1">تیتر یک — همراه تو، از ترم یک</div>
            <div className="h2 mt-12">تیتر دو — عنوان بخش</div>
            <div className="h3 mt-12">تیتر سه — عنوان کارت</div>
            <p className="mt-12">متن بدنه ۱۴ پیکسل با ارتفاع خط ۱.۹ برای مطالعهٔ طولانی. اصطلاحات لاتین مثل <span className="mono">Sinus Bradycardia</span> دست‌نخورده می‌مانند.</p>
            <p className="small mt-12">متن ثانویه ۱۲.۵ — توضیح زیر عنوان</p>
            <p className="tiny mt-12">متادیتا ۱۱ — ۲۷ مهر ۱۴۰۵ · ٪۴۷ · صفحه ۶۲</p>
            <p className="num mt-12">۰۸:۳۰ — ۱٬۲۴۰ — ٪۴۷</p>
          </Card>
        </Section>

        <Section title="دکمه‌ها" sub="آبی فقط برای کنش اصلی؛ در هر نما یک کنش اصلی.">
          <Card>
            <div className="row gap-10" style={{ flexWrap: 'wrap' }}>
              <Button>شروع مطالعه</Button>
              <Button variant="ghost">انصراف</Button>
              <Button variant="ink" icon="i-pen">نوشتن</Button>
            </div>
            <div className="row gap-10 mt-16" style={{ flexWrap: 'wrap' }}>
              <Button size="sm">کوچک</Button>
              <Button size="sm" variant="ghost">کوچک ثانویه</Button>
              <Button loading>در حال ذخیره</Button>
              <Button disabled>غیرفعال</Button>
            </div>
            <Button block className="mt-16" icon="i-download">تمام‌عرض</Button>
          </Card>
        </Section>

        <Section title="چیپ و وضعیت" sub="وضعیت همیشه متن دارد؛ رنگ تنها حامل معنا نیست.">
          <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
            <Chip>در حال مطالعه</Chip>
            <Chip variant="brand">جدید</Chip>
            <Chip variant="cyan" icon="i-check">تأییدشده</Chip>
            <Chip variant="quiet">آرشیو</Chip>
            <Chip variant="danger">منقضی</Chip>
          </div>
        </Section>

        <Section title="فیلد و کلید">
          <Card>
            <Input label="کد کاربری" placeholder="K7F2-M9XQ" code dir="ltr" />
            <div className="mt-16">
              <Input label="نام درس" defaultValue="" placeholder="مثلاً فیزیولوژی" />
            </div>
            <div className="mt-16">
              <Input label="کد کاربری" defaultValue="K7F2" error="کد باید ۸ کاراکتر باشد" code dir="ltr" />
            </div>
            <div className="setrow mt-16">
              <span className="grow h3">حالت شب خودکار</span>
              <Switch checked={on} onChange={setOn} label="حالت شب خودکار" />
            </div>
          </Card>
        </Section>

        <Section title="کارت و ردیف">
          <div className="sys__grid">
            <Card>
              <div className="h3">کارت ساده</div>
              <p className="small mt-8">سطح کارت با خط مو، سایهٔ فقط برای شناورها.</p>
            </Card>
            <Card variant="rule">
              <div className="h3">کارت با خط کنار</div>
              <p className="small mt-8">برای تأکید بر «مهم / جدید».</p>
            </Card>
          </div>
          <Card variant="flush" className="mt-12">
            <ListRow icon="i-book" title="کتابخانه" sub="جزوه‌ها و منابع" chevron onClick={() => {}} />
            <ListRow icon="i-calendar" title="برنامهٔ هفته" meta="۳ جلسهٔ امروز" chevron onClick={() => {}} />
            <ListRow icon="i-logout" title="خروج از حساب" danger onClick={() => {}} />
          </Card>
        </Section>

        <Section title="بازخورد و بارگذاری">
          <Card>
            <div className="row gap-12" style={{ justifyContent: 'space-between' }}>
              <span className="small">پیشرفت مطالعه</span>
              <span className="tiny num">٪۴۷</span>
            </div>
            <ProgressBar value={47} />
            <div className="row gap-16 mt-16">
              <Stat value="۱۲" label="جلسه" />
              <Stat value="۰۸:۳۰" label="شروع" />
              <Stat value="—" label="نامشخص" />
            </div>
          </Card>
          <div className="mt-12"><SkeletonStack rows={3} /></div>
          <Card className="mt-12">
            <EmptyState
              icon="i-arch"
              title="هنوز چیزی این‌جا نیست"
              text="وقتی محتوایی برای ورودی تحصیلی شما منتشر شود، همین‌جا دیده می‌شود."
              action={<Button size="sm" variant="ghost">راهنما</Button>}
            />
          </Card>
          <div className="row gap-10 mt-12" style={{ flexWrap: 'wrap' }}>
            <Button variant="ghost" size="sm" onClick={() => setSheet(true)}>باز کردن شیت</Button>
            <Toast message={null} />
          </div>
        </Section>

        <Section title="نوار ابزار ریدر" sub="انتخاب ابزار با aria-pressed، نه فقط رنگ.">
          <Card>
            <div className="rtool--static"><ReaderToolbar active={tool} onSelect={setTool} /></div>
          </Card>
        </Section>

        <Section title="آیکون‌ها" sub={`${ICON_NAMES.length} نماد (۳۴ آیکون + نشانهٔ برند) · شبکهٔ ۲۴px · استروک ۱.۷`}>
          <div className="icon-grid">
            {ICON_NAMES.map((n) => (
              <div className="icon-cell" key={n}>
                <Icon name={n} size={24} />
                <span className="mono">{n.replace('i-', '')}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="همیشه / هرگز">
          <div className="sys__grid">
            <Card>
              <div className="h3" style={{ color: 'var(--ok)' }}>همیشه</div>
              <ul className="small mt-8" style={{ paddingInlineStart: 16, listStyle: 'disc' }}>
                <li>سطح کاغذ گرم؛ آبی فقط روی کنش</li>
                <li>جداکنندهٔ ۱px به‌جای سایه</li>
                <li>متن روی چیپ وضعیت</li>
                <li>حالت روشن، تاریک و سیستم</li>
              </ul>
            </Card>
            <Card>
              <div className="h3" style={{ color: 'var(--danger)' }}>هرگز</div>
              <ul className="small mt-8" style={{ paddingInlineStart: 16, listStyle: 'disc' }}>
                <li>ایموجی در رابط</li>
                <li>شیشه و بلور روی محتوا</li>
                <li>هالهٔ نئونی و گرادیان چندرنگ</li>
                <li>عدد ساختگی بدون منبع داده</li>
              </ul>
            </Card>
          </div>
        </Section>

        <Section title="وضعیت‌های سیستمی">
          <Card variant="flush">
            <Link to="/states"><ListRow icon="i-lock" title="خطا، آفلاین، ۴۰۱، ۴۰۳، ۴۰۴" chevron onClick={() => {}} /></Link>
          </Card>
        </Section>

        <Sheet open={sheet} onClose={() => setSheet(false)} title="شیت پایین‌کشیدنی">
          <p className="small">
            شیت برای انتخاب‌های کوتاه و اقدام‌های موقت است، نه برای محتوای اصلی.
            بستن با Esc، کلیک روی پرده یا دکمهٔ بالا.
          </p>
          <div className="mt-16"><Button block onClick={() => setSheet(false)}>باشه</Button></div>
        </Sheet>
      </div>
    </>
  );
}
