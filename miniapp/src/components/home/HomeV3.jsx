/* ─────────────────────────────────────────────────────────────
   🎨 HumsYar v3 — بلوک‌های خانه (هم‌تراز با پروتوتایپ آبی)

   فلسفهٔ چیدمان (از پروتوتایپ):
   ۱) «حالِ امروز» بالا: سلام + هویت تحصیلی، بدون کارت سنگین.
   ۲) «فوری‌ترین چیز» بعدش: آزمون بعدی با شمارش روز و رنگ فوریت.
   ۳) بعد از آن «کار‌های سریع» در شبکهٔ ۲×۲ با آیکون خطی.
   ۴) سپس آمار، پیشرفت و بقیهٔ بخش‌ها.

   همهٔ اعداد از API واقعی می‌آیند؛ اگر داده نبود، بلوک **پنهان**
   می‌شود — هیچ داده‌ی ساختگی‌ای برای پر کردن قالب ساخته نمی‌شود.
   ───────────────────────────────────────────────────────────── */

import Icon from '../ui/Icon';
import { faNum, number, percent } from '../../lib/format';
import { haptic } from '../../lib/telegram';

/* نام کوچکِ امن — «سلام علی» به‌جای «سلام علی رضایی محمدی» */
function firstName(user) {
  const raw = String(
    user?.display_name || user?.nickname || user?.name || ''
  ).trim();

  if (!raw) return '';

  return raw.split(/\s+/)[0];
}

/* هویت تحصیلی: «علوم پایه · پزشکی · نیم‌سال دوم ۱۴۰۴–۱۴۰۵»
   فقط بخش‌های موجود؛ بدون جای‌نگهدار «—» */
function identityLine(user) {
  return [user?.grade, user?.field, user?.group, user?.intake]
    .map((part) => String(part || '').trim())
    .filter(Boolean)
    .join(' · ');
}

export function HomeGreeting({ user, role, stats }) {
  const name = firstName(user);
  const meta = identityLine(user);
  const prep = percent(stats?.percentage);
  const hasPrep = Number.isFinite(Number(stats?.percentage));

  return (
    <section className="v3-greet">
      <h1 className="v3-greet__title">
        {name ? `سلام ${name}` : 'سلام'}
      </h1>

      {meta ? (
        <p className="v3-greet__meta">{meta}</p>
      ) : (
        <p className="v3-greet__meta">
          برای دیدن برنامهٔ درسی‌ات، پروفایل را کامل کن
        </p>
      )}

      <div className="v3-greet__chips">
        {hasPrep && (
          <span className="v3-chip v3-chip--brand">
            <Icon name="target" size={13} />
            آمادگی {faNum(Math.round(prep))}٪
          </span>
        )}

        {stats?.level?.label && (
          <span className="v3-chip">
            {stats.level.icon ? `${stats.level.icon} ` : ''}
            {stats.level.label}
          </span>
        )}

        {role && <span className="v3-chip v3-chip--gold">{role}</span>}
      </div>
    </section>
  );
}

export function NextExamCard({ exam, onOpen }) {
  if (!exam || !exam.lesson) return null;

  const days =
    exam.days_left === null || exam.days_left === undefined
      ? null
      : number(exam.days_left);

  const tone =
    days === null ? 'brand' : days <= 3 ? 'danger' : days <= 7 ? 'warn' : 'ok';

  const label = days === null ? 'آزمون بعدی' : 'آزمون بعدی';

  return (
    <button
      type="button"
      className={`v3-exam v3-exam--${tone}`}
      onClick={() => {
        haptic('light');
        onOpen?.();
      }}
    >
      {days !== null && (
        <span className="v3-exam__count">
          <b className="v3-exam__num">{faNum(days)}</b>
          <span className="v3-exam__unit">روز</span>
        </span>
      )}

      <span className="v3-exam__body">
        <span className="v3-exam__label">
          {label}
          {exam.time ? ` · ساعت ${faNum(exam.time)}` : ''}
        </span>

        <b className="v3-exam__title">{exam.lesson}</b>

        {exam.date && <span className="v3-exam__date">{faNum(exam.date)}</span>}
      </span>

      <span className="v3-exam__icon" aria-hidden="true">
        <Icon name="calendar" size={19} />
      </span>
    </button>
  );
}

/* کارت‌های سریع — همه به مسیرهای واقعیِ موجود وصل‌اند */
const QUICK = [
  {
    key: 'practice',
    icon: 'target',
    title: 'تمرین هدفمند',
    desc: 'سؤال از نقاط ضعف',
    to: '/learn/questions?mode=weak',
  },
  {
    key: 'ai',
    icon: 'sparkle',
    title: 'پرسش از هوشیار',
    desc: 'توضیح، خلاصه، ساخت سؤال',
    to: '/ai',
  },
  {
    key: 'library',
    icon: 'book',
    title: 'منابع و جزوات',
    desc: 'فایل‌های درسی و کتاب‌ها',
    to: '/learn/resources',
  },
  {
    key: 'today',
    icon: 'calendar',
    title: 'برنامهٔ امروز',
    desc: 'کلاس‌ها و آزمون‌ها',
    to: '/schedule',
  },
];

export function QuickGrid({ onNavigate }) {
  return (
    <div className="v3-quick">
      {QUICK.map((item) => (
        <button
          type="button"
          key={item.key}
          className="v3-quick__tile"
          onClick={() => {
            haptic('light');
            onNavigate?.(item.to);
          }}
        >
          <span className="v3-quick__icon">
            <Icon name={item.icon} size={19} />
          </span>

          <span className="v3-quick__text">
            <b className="v3-quick__title">{item.title}</b>
            <span className="v3-quick__desc">{item.desc}</span>
          </span>
        </button>
      ))}
    </div>
  );
}

export default HomeGreeting;
