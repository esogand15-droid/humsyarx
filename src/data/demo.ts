/* ═══════════════════════════════════════════════════════════════════════
   دادهٔ نمایشی پروتوتایپ
   ⚠ هر عدد و نام این فایل نمونهٔ ساختگی برای بررسی طراحی است — نه رکورد
   واقعی دانشجو، نه دادهٔ تولیدی. در رابط کاربری هم با نشان «نمایشی» و
   نوار بالای صفحه مشخص می‌شود.
   ساختار داده‌ها عمداً به شکل قراردادهای واقعی موجود در مخزن است
   (`/api/web/library`, `/api/web/exam`, `/api/schedule`, `/api/subscription`)
   تا هنگام پیاده‌سازی، جایگزینی mock با API یک‌به‌یک باشد.
   ═══════════════════════════════════════════════════════════════════════ */

export const DEMO = true;

export const student = {
  name: 'علی احمدی',
  initials: 'ع ا',
  username: 'ali_ahmadi',
  studentId: '۴۰۲۱۳۴۵۶',
  major: 'پزشکی',
  intake: 'مهر ۱۴۰۲',
  stage: 'علوم پایه',
  term: 'نیم‌سال دوم ۱۴۰۴–۱۴۰۵',
  subscription: {
    active: true,
    plan: 'پلن دانشجویی — سال تحصیلی',
    daysLeft: 126,
    endsAt: '۱۲ آذر ۱۴۰۵',
    features: ['resources', 'references', 'question_bank', 'mock_exam', 'ai_chat'],
    aiDailyUsed: 7,
    aiDailyLimit: 25,
  },
};

export type StudyDay = { label: string; minutes: number; target: number };
export const weekStudy: StudyDay[] = [
  { label: 'شنبه', minutes: 96, target: 120 },
  { label: 'یک‌شنبه', minutes: 142, target: 120 },
  { label: 'دوشنبه', minutes: 64, target: 120 },
  { label: 'سه‌شنبه', minutes: 128, target: 120 },
  { label: 'چهارشنبه', minutes: 88, target: 120 },
  { label: 'پنج‌شنبه', minutes: 156, target: 120 },
  { label: 'جمعه', minutes: 42, target: 120 },
];

export const progressSummary = {
  questionsAnswered: 412,
  questionsCorrect: 318,
  accuracy: 77,
  streakDays: 9,
  weeklyMinutes: 716,
  weeklyTarget: 840,
  rank: 148,
  rankOf: 2140,
};

export type ResourceKind = 'pdf' | 'video' | 'audio' | 'slide';
export interface ResourceItem {
  id: string;
  title: string;
  lesson: string;
  topic: string;
  kind: ResourceKind;
  size?: string;
  duration?: string;
  pages?: number;
  teacher: string;
  updatedAt: string;
  locked?: boolean;
  tags?: string[];
  description: string;
}

export const lessons = [
  { id: 'L1', name: 'فیزیولوژی', teacher: 'دکتر نیکومنش', resources: 34, questions: 168, progress: 62 },
  { id: 'L2', name: 'بیوشیمی', teacher: 'دکتر رستمی', resources: 28, questions: 142, progress: 48 },
  { id: 'L3', name: 'آناتومی', teacher: 'دکتر کاظمی', resources: 41, questions: 205, progress: 71 },
  { id: 'L4', name: 'بافت‌شناسی', teacher: 'دکتر سلیمی', resources: 19, questions: 96, progress: 35 },
  { id: 'L5', name: 'ایمونولوژی', teacher: 'دکتر فراهانی', resources: 16, questions: 84, progress: 22 },
];

export const resources: ResourceItem[] = [
  {
    id: 'R1', title: 'جزوهٔ فیزیولوژی قلب — جلسهٔ ۷', lesson: 'فیزیولوژی', topic: 'قلب و گردش خون',
    kind: 'pdf', pages: 42, size: '۳٫۲ مگابایت', teacher: 'دکتر نیکومنش', updatedAt: '۲ روز پیش',
    tags: ['چرخهٔ قلبی', 'برون‌ده قلبی'], description:
      'یادداشت کلاسی جلسهٔ هفتم: چرخهٔ قلبی، حجم ضربه‌ای، برون‌ده قلبی و تنظیم عصبی ضربان. با نمودارهای فشار–حجم.',
  },
  {
    id: 'R2', title: 'ویدیو جلسهٔ ۷ — چرخهٔ قلبی', lesson: 'فیزیولوژی', topic: 'قلب و گردش خون',
    kind: 'video', duration: '۵۴:۱۲', size: '۲۶۸ مگابایت', teacher: 'دکتر نیکومنش', updatedAt: '۲ روز پیش',
    description: 'ضبط کامل کلاس: مراحل چرخهٔ قلبی، صداهای قلب و ارتباط آن با دریچه‌ها.',
  },
  {
    id: 'R3', title: 'اسیلوسکوپ قلبی — نمودارهای کلیدی', lesson: 'فیزیولوژی', topic: 'قلب و گردش خون',
    kind: 'pdf', pages: 12, size: '۸۴۰ کیلوبایت', teacher: 'دکتر نیکومنش', updatedAt: '۵ روز پیش',
    description: 'خلاصهٔ نمودارهای فشار–حجم و منحنی‌های Starling برای مرور سریع پیش از آزمون.',
  },
  {
    id: 'R4', title: 'پادکست مرور — فیزیولوژی تنفس', lesson: 'فیزیولوژی', topic: 'تنفس',
    kind: 'audio', duration: '۲۲:۴۰', size: '۹ مگابایت', teacher: 'دکتر نیکومنش', updatedAt: '۱ هفته پیش',
    description: 'جمع‌بندی صوتی مکانیک تنفس، حجم‌های ریوی و تبادل گاز.',
  },
  {
    id: 'R5', title: 'اسلایدهای بیوشیمی — متابولیسم کربوهیدرات', lesson: 'بیوشیمی', topic: 'متابولیسم',
    kind: 'slide', pages: 58, size: '۱۲ مگابایت', teacher: 'دکتر رستمی', updatedAt: '۴ روز پیش',
    description: 'گلیکولیز، چرخهٔ کربس و زنجیرهٔ انتقال الکترون با نکات آزمونی.',
  },
  {
    id: 'R6', title: 'جزوهٔ آناتومی — اندام فوقانی', lesson: 'آناتومی', topic: 'اندام فوقانی',
    kind: 'pdf', pages: 76, size: '۵٫۱ مگابایت', teacher: 'دکتر کاظمی', updatedAt: '۳ روز پیش',
    description: 'عضلات، عروق و اعصاب اندام فوقانی همراه با تصاویر تشریح.',
  },
  {
    id: 'R7', title: 'ویدیو تشریح — مدیاستن', lesson: 'آناتومی', topic: 'قفسهٔ سینه',
    kind: 'video', duration: '۳۸:۰۵', size: '۱۹۴ مگابایت', teacher: 'دکتر کاظمی', updatedAt: '۲ هفته پیش',
    description: 'مرور ساختارهای مدیاستن و ارتباط آن‌ها با فیزیولوژی قلب.',
  },
  {
    id: 'R8', title: 'ایمونولوژی — پاسخ ایمنی هومورال', lesson: 'ایمونولوژی', topic: 'ایمنی هومورال',
    kind: 'pdf', pages: 31, size: '۲٫۱ مگابایت', teacher: 'دکتر فراهانی', updatedAt: '۶ روز پیش',
    locked: true, description:
      'این فایل در پلن فعلی تو موجود نیست. با ارتقای اشتراک باز می‌شود؛ حذف یا دستکاری از سمت سرور کنترل می‌شود.',
  },
];

export const resourceFilters = {
  lessons: ['همه', 'فیزیولوژی', 'بیوشیمی', 'آناتومی', 'بافت‌شناسی', 'ایمونولوژی'],
  kinds: [
    { key: 'pdf', label: 'جزوه (PDF)' },
    { key: 'video', label: 'ویدیو' },
    { key: 'audio', label: 'صوت' },
    { key: 'slide', label: 'اسلاید' },
  ],
};

/* ── بانک سؤال ─────────────────────────────────────────────────────── */
export interface Question {
  id: string;
  lesson: string;
  topic: string;
  difficulty: 'آسان' | 'متوسط' | 'سخت';
  source: string;
  year: string;
  stem: string;
  options: string[];
  answer: number;
  explanation: string;
}

export const questions: Question[] = [
  {
    id: 'Q1', lesson: 'فیزیولوژی', topic: 'قلب و گردش خون', difficulty: 'متوسط', source: 'آزمون جامع علوم پایه', year: '۱۴۰۲',
    stem: 'در یک دانشجوی سالم، افزایش ناگهانی بازگشت وریدی به قلب، در گام نخست کدام پاسخ را برمی‌انگیزد؟',
    options: [
      'افزایش برون‌ده قلبی از طریق مکانیسم فرانک–استارلینگ',
      'کاهش حجم ضربه‌ای به دلیل کاهش زمان پرشدن',
      'افزایش مقاومت عروق محیطی به‌طور اولیه',
      'کاهش ضربان قلب از طریق مهار سمپاتیک',
    ],
    answer: 0,
    explanation:
      'افزایش بازگشت وریدی، کشش فیبرهای میوکارد را بیشتر می‌کند و بر پایهٔ رابطهٔ فرانک–استارلینگ، نیروی انقباض و حجم ضربه‌ای بالا می‌رود. پاسخ‌های رفلکسی (سمپاتیک/پاراسمپاتیک) با تأخیر رخ می‌دهند و «گام نخست» نیستند.',
  },
  {
    id: 'Q2', lesson: 'فیزیولوژی', topic: 'تنفس', difficulty: 'متوسط', source: 'آزمون جامع علوم پایه', year: '۱۴۰۱',
    stem: 'در یک فرد سالم که به‌طور ارادی تهویه را کاهش داده است، کدام تغییر اولین بار در گازهای خون شریانی دیده می‌شود؟',
    options: ['کاهش PaO₂', 'افزایش PaCO₂', 'کاهش pH بدون تغییر PaCO₂', 'کاهش بیکربنات'],
    answer: 1,
    explanation:
      'کاهش تهویه، ابتدا دفع CO₂ را کم می‌کند و PaCO₂ بالا می‌رود؛ کاهش PaO₂ دیرتر و با شیب کمتری رخ می‌دهد چون منحنی تفکیک هموگلوبین در محدودهٔ اشباع بالا مسطح است.',
  },
  {
    id: 'Q3', lesson: 'بیوشیمی', topic: 'متابولیسم', difficulty: 'سخت', source: 'آزمون جامع علوم پایه', year: '۱۴۰۲',
    stem: 'کمبود تیامین در یک فرد با رژیم نامناسب، کدام آنزیم‌های چرخهٔ کربس را مستقیماً تحت تأثیر قرار می‌دهد؟',
    options: [
      'سیترات سینتاز و آکونیتاز',
      'پیروات دهیدروژناز و آلفاکتوگلوتارات دهیدروژناز',
      'فوماراز و مالات دهیدروژناز',
      'هگزوکیناز و فسفوفروکتوکیناز',
    ],
    answer: 1,
    explanation:
      'تیامین پیروفسفات (TPP) کوآنزیم پیروات دهیدروژناز، آلفاکتوگلوتارات دهیدروژناز، ترانس‌کتولاز و شاخهٔ کتوگلوتارات است. کمبود آن بیشتر این نقاط را درگیر می‌کند.',
  },
  {
    id: 'Q4', lesson: 'آناتومی', topic: 'اندام فوقانی', difficulty: 'آسان', source: 'آزمون جامع علوم پایه', year: '۱۴۰۰',
    stem: 'آسیب عصب رادیال در بخش میانی بازو، بیشتر کدام حرکت را از دست می‌دهد؟',
    options: ['فلکسیون آرنج', 'اکستنشن مچ و انگشتان', 'اداکشن شانه', 'پروناسیون ساعد'],
    answer: 1,
    explanation:
      'عصب رادیال گروه اکستنسور را عصب‌دهی می‌کند؛ آسیب آن به افتادگی مچ (wrist drop) می‌انجامد. فلکسیون آرنج با musculocutaneous و پروناسیون با median است.',
  },
  {
    id: 'Q5', lesson: 'ایمونولوژی', topic: 'ایمنی هومورال', difficulty: 'متوسط', source: 'آزمون جامع علوم پایه', year: '۱۴۰۳',
    stem: 'جهش در CD40L در سندرم هیپر–IgM، کدام مرحله را مختل می‌کند؟',
    options: [
      'سوئیچ کلاس ایمونوگلوبولین در لنفوسیت B',
      'پردازش آنتی‌ژن در سلول دندریتیک',
      'تشکیل کمپلکس MHC کلاس I',
      'فعال‌سازی سیستم کمپلمان از راه کلاسیک',
    ],
    answer: 0,
    explanation:
      'برهم‌کنش CD40 (روی B) با CD40L (روی Th) برای سوئیچ کلاس و بلوغ پاسخ وابسته به T ضروری است؛ ژن CD40L روی کروموزوم X است و بیماری وابسته به X ظاهر می‌شود.',
  },
  {
    id: 'Q6', lesson: 'فیزیولوژی', topic: 'قلب و گردش خون', difficulty: 'سخت', source: 'آزمون جامع علوم پایه', year: '۱۴۰۳',
    stem: 'کدام مورد افزایش جریان خون کرونری در پاسخ به افزایش مصرف اکسیژن را بهتر توضیح می‌دهد؟',
    options: [
      'گشادشدن عروق کرونری به‌واسطهٔ متابولیت‌های موضعی',
      'افزایش مستقیم سمپاتیک با واسطهٔ گیرندهٔ آلفا',
      'کاهش فشار انتهای دیاستول در آئورت',
      'افزایش ویسکوزیتهٔ خون',
    ],
    answer: 0,
    explanation:
      'جریان کرونری عمدتاً به‌طور متابولیک تنظیم می‌شود (آدنوزین و سایر متابولیت‌ها) و کمبود اکسیژن میوکارد، محرک اصلی گشاد شدن شریان‌های کوچک است.',
  },
];

/* ── آزمون زمان‌دار ─────────────────────────────────────────────────── */
export const examConfig = {
  countOptions: [10, 20, 30, 50],
  minuteOptions: [0, 10, 15, 20, 30, 45, 60],
  availableCount: 6,
};

export const examHistory = [
  { id: 'E-9', lesson: 'فیزیولوژی', topic: 'قلب', date: '۲۶ مهر', total: 20, correct: 16, pct: 80, status: 'تمام‌شده' },
  { id: 'E-8', lesson: 'بیوشیمی', topic: 'متابولیسم', date: '۲۳ مهر', total: 20, correct: 11, pct: 55, status: 'تمام‌شده' },
  { id: 'E-7', lesson: 'آناتومی', topic: 'اندام فوقانی', date: '۲۰ مهر', total: 15, correct: 13, pct: 87, status: 'تمام‌شده' },
  { id: 'E-6', lesson: 'فیزیولوژی', topic: 'تنفس', date: '۱۸ مهر', total: 10, correct: 6, pct: 60, status: 'رها‌شده' },
];

/* ── هوشیار ─────────────────────────────────────────────────────────── */
export interface AiMsg {
  id: string;
  role: 'me' | 'ai';
  text?: string;
  paragraphs?: string[];
  bullets?: string[];
  sources?: { label: string; ref: string }[];
  time: string;
  pending?: boolean;
}

export const aiThreads = [
  { id: 'T1', title: 'چرخهٔ قلبی و برون‌ده', when: 'امروز', active: true },
  { id: 'T2', title: 'تیامین و چرخهٔ کربس', when: 'دیروز' },
  { id: 'T3', title: 'عصب رادیال — تست بالینی', when: '۲ روز پیش' },
  { id: 'T4', title: 'برنامهٔ مرور ۷ روزه', when: 'هفتهٔ پیش' },
];

export const aiPrompts = [
  'تفاوت فشار انتهای دیاستول و تاکی‌کاردی را ساده توضیح بده',
  'از جزوهٔ فیزیولوژی قلب یک سؤال مفهومی بساز',
  'برنامهٔ مرور ۷ روزه برای ایمونولوژی بچین',
];

export const aiSeed: AiMsg[] = [
  { id: 'm1', role: 'me', text: 'چرخهٔ قلبی را مفهومی توضیح بده؛ به‌خصوص اینکه چرا حجم ضربه‌ای با تاکی‌کاردی شدید کم می‌شود.', time: '۱۰:۲۴' },
  {
    id: 'm2', role: 'ai', time: '۱۰:۲۴',
    paragraphs: [
      'چرخهٔ قلبی را مثل دو پمپ در نظر بگیر که به‌تناوب پر و خالی می‌شوند. هر چرخه سه بخش دارد: پرشدن (دیاستول)، انقباض دهلیزی، و انقباض بطن (سیستول). مهم‌ترین نکته این است که بیشتر پرشدن بطن «غیرفعال» است و در دیاستول رخ می‌دهد.',
    ],
    bullets: [
      '۷۰٪ پرشدن بطن در دیاستول و به‌صورت غیرفعال انجام می‌شود؛ پس دیاستول کوتاه = پرشدن کمتر.',
      'با تاکی‌کاردی، دیاستول سریع‌تر از سیستول کوتاه می‌شود؛ در نتیجه حجم انتهای دیاستول (EDV) افت می‌کند.',
      'افت EDV، بر پایهٔ رابطهٔ فرانک–استارلینگ، حجم ضربه‌ای را کم می‌کند.',
      'برون‌ده قلبی تقریباً ثابت می‌ماند، ولی در تاکی‌کاردی بسیار شدید (بیش از ۱۵۰) پرشدن جبران نمی‌شود و برون‌ده هم می‌افتد.',
    ],
    sources: [
      { label: 'جزوهٔ جلسهٔ ۷ — چرخهٔ قلبی', ref: 'R1 · ص ۱۲–۱۸' },
      { label: 'بانک سؤال — فیزیولوژی/قلب', ref: '۳ سؤال مرتبط' },
    ],
  },
];

/* ── برنامهٔ درسی و تقویم ──────────────────────────────────────────── */
export const weekDays = [
  { label: 'شنبه', day: '۲۶', today: false },
  { label: 'یک‌شنبه', day: '۲۷', today: false },
  { label: 'دوشنبه', day: '۲۸', today: true },
  { label: 'سه‌شنبه', day: '۲۹', today: false },
  { label: 'چهارشنبه', day: '۳۰', today: false },
  { label: 'پنج‌شنبه', day: '۳۱', today: false },
  { label: 'جمعه', day: '۱', today: false },
];

export const weekSlots: Record<number, { title: string; time: string; kind: 'class' | 'exam' | 'review' }[]> = {
  0: [{ title: 'فیزیولوژی — قلب', time: '۰۸:۰۰–۱۰:۰۰', kind: 'class' }, { title: 'مرور بیوشیمی', time: '۱۸:۰۰', kind: 'review' }],
  1: [{ title: 'آناتومی — اندام فوقانی', time: '۱۰:۰۰–۱۲:۰۰', kind: 'class' }],
  2: [{ title: 'بافت‌شناسی', time: '۰۸:۰۰–۰۹:۳۰', kind: 'class' }, { title: 'مرور بطنی', time: '۱۷:۳۰', kind: 'review' }],
  3: [{ title: 'بیوشیمی — متابولیسم', time: '۱۰:۰۰–۱۲:۰۰', kind: 'class' }, { title: 'آزمون آزمایشی', time: '۲۰:۰۰', kind: 'exam' }],
  4: [{ title: 'ایمونولوژی', time: '۰۹:۰۰–۱۰:۳۰', kind: 'class' }],
  5: [{ title: 'مرور هفتگی', time: '۱۶:۰۰–۱۸:۰۰', kind: 'review' }],
  6: [],
};

export const upcomingExams = [
  { id: 'X1', title: 'میان‌ترم فیزیولوژی', date: '۲۹ مهر', inDays: 3, scope: 'قلب، تنفس، کلیه', kind: 'میان‌ترم' },
  { id: 'X2', title: 'آزمون جامع علوم پایه — مرحلهٔ آزمایشی', date: '۵ آبان', inDays: 10, scope: 'همهٔ دروس', kind: 'آزمون آزمایشی' },
  { id: 'X3', title: 'کوییز ایمونولوژی', date: '۱۲ آبان', inDays: 17, scope: 'ایمنی هومورال', kind: 'کوییز' },
];

export const tasks = [
  { id: 'T-1', title: 'حل ۳۰ سؤال قلب از بانک سؤال', due: 'امروز', urgent: true, done: false },
  { id: 'T-2', title: 'مرور جدول داروهای مؤثر بر ضربان', due: 'فردا', urgent: false, done: false },
  { id: 'T-3', title: 'خواندن ۱۲ صفحهٔ اسیلوسکوپ قلبی', due: 'سه‌شنبه', urgent: false, done: true },
];

/* ── اعلان‌ها ──────────────────────────────────────────────────────── */
export const notifications = [
  { id: 'N1', title: 'جزوهٔ جدید فیزیولوژی — تنفس', body: 'دکتر نیکومنش جزوهٔ جلسهٔ ۹ را منتشر کرد.', when: '۲ ساعت پیش', unread: true, kind: 'content' },
  { id: 'N2', title: 'یادآوری آزمون', body: 'میان‌ترم فیزیولوژی ۲۹ مهر — ۳ روز مانده.', when: '۵ ساعت پیش', unread: true, kind: 'exam' },
  { id: 'N3', title: 'هوشیار: پاسخ تمرین آماده است', body: 'تحلیل ۲۰ سؤال آزمون آزمایشی آماده شد.', when: 'دیروز', unread: false, kind: 'ai' },
];

export const announcements = [
  { id: 'A1', day: '۲۶', month: 'مهر', title: 'کلاس جبرانی فیزیولوژی — پنج‌شنبه', body: 'جلسهٔ جبرانی ساعت ۱۶ در کلاس ۲۰۲ برگزار می‌شود.' },
  { id: 'A2', day: '۲۴', month: 'مهر', title: 'انتشار آزمون آزمایشی مرحلهٔ ۲', body: 'آزمون آزمایشی جامع با تحلیل هوشیار در دسترس است.' },
  { id: 'A3', day: '۲۱', month: 'مهر', title: 'به‌روزرسانی بانک سؤال آناتومی', body: '۴۸ سؤال تازه از آزمون‌های ۱۴۰۰ تا ۱۴۰۳ اضافه شد.' },
];

export const plans = [
  {
    id: 'P-basic', name: 'پایه', price: 'رایگان', note: 'دسترسی محدود',
    features: [
      { t: 'کتابخانه نمونه', on: true },
      { t: '۵ سؤال در روز', on: true },
      { t: 'آزمون زمان‌دار', on: false },
      { t: 'هوشیار (گفتگو)', on: false },
    ],
  },
  {
    id: 'P-student', name: 'دانشجویی', price: 'فعال', note: 'سال تحصیلی · تا ۱۲ آذر ۱۴۰۵', featured: true,
    features: [
      { t: 'همهٔ جزوه‌ها و ویدیوها', on: true },
      { t: 'بانک سؤال نامحدود', on: true },
      { t: 'آزمون آزمایشی', on: true },
      { t: 'هوشیار — ۲۵ پیام در روز', on: true },
    ],
  },
  {
    id: 'P-full', name: 'جامع', price: 'ارتقا', note: 'قیمت از سرور می‌آید',
    features: [
      { t: 'همهٔ پلن دانشجویی', on: true },
      { t: 'رفرنس‌های فارسی و لاتین', on: true },
      { t: 'خروجی PDF آزمون', on: true },
      { t: 'پشتیبانی اولویت‌دار', on: true },
    ],
  },
];

export const payments = [
  { id: 'PAY-3', title: 'تمدید اشتراک — پلن دانشجویی', date: '۱۲ شهریور ۱۴۰۵', amount: '—', status: 'پرداخت‌شده' },
  { id: 'PAY-2', title: 'تمدید اشتراک — پلن دانشجویی', date: '۱۲ اسفند ۱۴۰۴', amount: '—', status: 'پرداخت‌شده' },
];
