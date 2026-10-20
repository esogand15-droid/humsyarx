/* ──────────────────────────────────────────────────────────────────
   دادهٔ نمایشی «یادداشت‌ها» — شکل آن با مدل پیشنهادی سمت سرور هم‌خوان است
   (NOTEBOOK / NOTE / NOTE_VERSION / DOC_ANCHOR) و هیچ قرارداد موجودی را
   تغییر نمی‌دهد. همه‌چیز محلی است.
   ────────────────────────────────────────────────────────────────── */

export type Notebook = {
  id: string;
  title: string;
  parent?: string;
  count: number;
  depth: 0 | 1;
};

export type NoteBlockKind = 'h2' | 'p' | 'list' | 'check' | 'callout' | 'quote' | 'table' | 'ink' | 'link';

export type Note = {
  id: string;
  title: string;
  notebook: string;
  tags: string[];
  pinned?: boolean;
  starred?: boolean;
  updated: string;
  words: number;
  /** لنگر سند: صفحهٔ PDF و منبع مرتبط */
  anchor?: { resourceId: string; page: number; label: string };
  blocks: { kind: NoteBlockKind; text?: string; items?: string[]; rows?: string[][]; checked?: boolean[] }[];
};

export const notebooks: Notebook[] = [
  { id: 'nb-all', title: 'همهٔ یادداشت‌ها', count: 34, depth: 0 },
  { id: 'nb-physio', title: 'فیزیولوژی', count: 12, depth: 0 },
  { id: 'nb-physio-cv', title: 'قلب و گردش خون', parent: 'nb-physio', count: 6, depth: 1 },
  { id: 'nb-physio-resp', title: 'تنفس', parent: 'nb-physio', count: 3, depth: 1 },
  { id: 'nb-biochem', title: 'بیوشیمی', count: 9, depth: 0 },
  { id: 'nb-anatomy', title: 'آناتومی', count: 7, depth: 0 },
  { id: 'nb-pharma', title: 'داروشناسی', count: 6, depth: 0 },
];

export const noteTags = [
  { tag: 'جلسهٔ ۷', count: 4 },
  { tag: 'چرخهٔ قلبی', count: 3 },
  { tag: 'آزمون میان‌ترم', count: 5 },
  { tag: 'نکتهٔ ترکیبی', count: 2 },
  { tag: 'فلش‌کارت', count: 6 },
];

export const notes: Note[] = [
  {
    id: 'N1',
    title: 'چرخهٔ قلبی — خلاصهٔ جلسهٔ ۷',
    notebook: 'nb-physio-cv',
    tags: ['جلسهٔ ۷', 'چرخهٔ قلبی'],
    pinned: true,
    starred: true,
    updated: '۱۲ دقیقه پیش',
    words: 640,
    anchor: { resourceId: 'R1', page: 18, label: 'جزوهٔ فیزیولوژی قلب — جلسهٔ ۷' },
    blocks: [
      { kind: 'h2', text: 'ساختار کلی چرخه' },
      {
        kind: 'p',
        text: 'چرخهٔ قلبی از یک سیستول و یک دیاستول تشکیل می‌شود. در حالت استراحت، طول کل چرخه حدود ۸۰۰ میلی‌ثانیه است: سیستول دهلیزی ۱۲۰ms، سیستول بطنی ۲۸۰ms و دیاستول ۴۰۰ms.',
      },
      {
        kind: 'list',
        items: [
          'فاز ۱ — انقباض دهلیزی (Atrial systole)',
          'فاز ۲ — انقباض بطنی هم‌حجم (Isovolumetric contraction)',
          'فاز ۳ — تخلیهٔ بطنی (Ejection)',
          'فاز ۴ — استراحت هم‌حجم (Isovolumetric relaxation)',
          'فاز ۵ — پر شدن بطنی',
        ],
      },
      {
        kind: 'callout',
        text: 'نکتهٔ مهم: بسته شدن دریچهٔ میترال (S1) آغاز سیستول بطنی است، نه پایان آن. این سؤال در آزمون‌های سال قبل دو بار تکرار شده است.',
      },
      {
        kind: 'p',
        text: 'حجم ضربه‌ای (SV) تفاضل حجم پایان دیاستول (EDV) و پایان سیستول (ESV) است؛ کسر تخلیه در فرد سالم ۵۵٪ تا ۷۰٪ است.',
      },
      { kind: 'table', rows: [['فاز', 'دریچه‌ها', 'زمان'], ['هم‌حجم انقباضی', 'بسته', '≈۵۰ms'], ['تخلیه', 'آئورت باز', '≈۲۰۰ms']] },
    ],
  },
  {
    id: 'N2',
    title: 'مسیرهای گلیکولیز و تنظیم آن',
    notebook: 'nb-biochem',
    tags: ['آزمون میان‌ترم', 'فلش‌کارت'],
    updated: '۲ ساعت پیش',
    words: 410,
    anchor: { resourceId: 'R1', page: 42, label: 'جزوهٔ بیوشیمی — متابولیسم' },
    blocks: [
      { kind: 'h2', text: 'سه نقطهٔ کنترل' },
      { kind: 'p', text: 'هگزوکیناز، فسفوفروکتوکیناز-۱ و پیروات‌کیناز؛ سرعت‌ساز گلیکولیز PFK-1 است و توسط ATP و سیترات مهار می‌شود.' },
      { kind: 'check', items: ['مرور مسیر از گلوکز تا پیروات', 'حفظ آنزیم‌های تنظیمی', 'حل ۱۰ سؤال از این مبحث'], checked: [true, true, false] },
      { kind: 'quote', text: 'متن کتاب: «فسفوفروکتوکیناز-۱ گلوگاه اصلی و نقطهٔ اصلی تنظیم گلیکولیز است.» — ص ۴۲' },
    ],
  },
  {
    id: 'N3',
    title: 'دریچه‌های قلب — سمع و محل',
    notebook: 'nb-physio-cv',
    tags: ['جلسهٔ ۷'],
    updated: 'دیروز',
    words: 180,
    anchor: { resourceId: 'R1', page: 9, label: 'جزوهٔ فیزیولوژی قلب — جلسهٔ ۷' },
    blocks: [
      { kind: 'h2', text: 'چهار نقطهٔ سمع' },
      { kind: 'p', text: 'آئورت: فضای بین‌دندهٔ دوم راست. ریوی: دوم چپ. تری‌کوسپید: چهارم چپ. میترال: پنجم چپ در خط میدکلاویکولار.' },
      { kind: 'ink' },
    ],
  },
  {
    id: 'N4',
    title: 'تنظیم تنفس — نکات ترکیبی',
    notebook: 'nb-physio-resp',
    tags: ['نکتهٔ ترکیبی'],
    updated: '۲ روز پیش',
    words: 320,
    blocks: [
      { kind: 'h2', text: 'مراکز بصل‌النخاعی' },
      { kind: 'p', text: 'گروه تنفسی پشتی (DRG) الگوی پایه و گروه شکمی (VRG) الگوی فعال را می‌سازد؛ مرکز پنوموتاکسیک پونز الگوی تنفس را قطع می‌کند.' },
      { kind: 'link', text: 'پیوند به سؤال ۱۴۲ بانک سؤال — «تنظیم شیمیایی تنفس»' },
    ],
  },
  {
    id: 'N5',
    title: 'فارماکولوژی — بتابلانکرها',
    notebook: 'nb-pharma',
    tags: ['آزمون میان‌ترم'],
    updated: '۴ روز پیش',
    words: 260,
    blocks: [
      { kind: 'h2', text: 'تفکیک گیرنده‌ها' },
      { kind: 'p', text: 'β۱ قلبی، β۲ ریوی و عروقی، β۳ چربی. کارودیلول بلوک ترکیبی α/β دارد و در نارسایی قلبی کاربرد دارد.' },
    ],
  },
];

export const versions = [
  { id: 'v3', when: '۱۲ دقیقه پیش', label: 'نسخهٔ فعلی', size: '۶۴۰ واژه' },
  { id: 'v2', when: '۲۰ دقیقه پیش', label: 'ذخیرهٔ خودکار', size: '۵۹۰ واژه' },
  { id: 'v1', when: 'امروز ۰۸:۴۲', label: 'پیش‌نویس اولیه', size: '۲۱۰ واژه' },
];

/** متن نمایشیِ صفحهٔ PDF برای نمای کنار‌هم */
export const pdfPage = {
  page: 18,
  of: 42,
  src: 'فیزیولوژی — قلب و گردش خون، دکتر نیکومنش',
  paragraphs: [
    'چرخهٔ قلبی به مجموعهٔ رویدادهای الکتریکی، مکانیکی و جریانی گفته می‌شود که از یک ضربان تا ضربان بعدی رخ می‌دهد. در حالت استراحت این چرخه حدود ۰٫۸ ثانیه طول می‌کشد.',
    'در ابتدای چرخه، موج P باعث دپلاریزاسیون دهلیزها و انقباض دهلیزی می‌شود. حدود ۲۰٪ از پر شدن بطنی در این مرحله انجام می‌گیرد و ۸۰٪ به‌صورت غیرفعال در دیاستول.',
    'بسته شدن دریچه‌های میترال و تری‌کوسپید، صدای اول قلب (S1) را ایجاد می‌کند و هم‌زمان با آغاز انقباض هم‌حجم بطنی است. در این فاز فشار بطنی افزایش می‌یابد ولی حجم تغییر نمی‌کند.',
  ],
  highlight: 'در این فاز فشار بطنی افزایش می‌یابد ولی حجم تغییر نمی‌کند.',
};
