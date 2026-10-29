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

import { useQuery } from '@tanstack/react-query';

import Icon, { Glyph } from '../ui/Icon';
import api from '../../lib/api';
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
            {stats.level.icon && <Glyph value={stats.level.icon} size={13} />}
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

/* ─────────────────────────────────────────────────────────────
   بلوک‌های «دادهٔ واقعی» — همان سه کارت پروتوتایپ که قبلاً ساخته
   نشده بودند (ادامهٔ مطالعه / هدف هفتگی / یادداشت‌ها).

   قانون آهنین: اگر API داده نداشت، کارت **کامل حذف** می‌شود.
   هیچ عدد یا عنوان ساختگی‌ای برای پر کردن قالب ساخته نمی‌شود.
   منبع داده: /api/me/continue-reading · /api/me/weekly-goal · /api/me/notes
   ───────────────────────────────────────────────────────────── */


/* کارت «ادامهٔ مطالعه» — درصد پیشرفت از progress واقعی ریدر */
export function ContinueCard({ onOpen }) {
  const { data } = useQuery({
    queryKey: ['me-continue'],
    queryFn: () => api.get('/api/me/continue-reading').then((r) => r.data),
    staleTime: 60 * 1000,
    retry: false,
  });

  const item = (data?.items || [])[0];
  if (!item || !item.percent) return null;

  return (
    <button type="button" className="v3-continue" onClick={() => onOpen?.(item)}>
      <span className="v3-continue__top">
        <Icon name="book" size={14} />
        ادامهٔ مطالعه
        <span className="v3-continue__pct">{faNum(item.percent)}٪</span>
      </span>

      <b className="v3-continue__title">{item.name}</b>

      <span className="v3-continue__meta">
        {item.total > 0
          ? `صفحهٔ ${faNum(item.page)} از ${faNum(item.total)}`
          : 'نقطهٔ توقف ذخیره شده'}
      </span>

      <span className="v3-continue__bar">
        <i style={{ width: `${item.percent}%` }} />
      </span>
    </button>
  );
}

/* کارت «هدف هفتگی» — روزهای فعال این هفته نسبت به هدف خودِ کاربر */
export function WeeklyGoalCard({ onSetGoal }) {
  const { data } = useQuery({
    queryKey: ['me-weekly-goal'],
    queryFn: () => api.get('/api/me/weekly-goal').then((r) => r.data),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  if (!data) return null;

  const { goal_days: goal, active_days: active, percent: pct, total_actions: actions } = data;
  if (!goal) return null;

  return (
    <div className="v3-goal">
      <div className="v3-goal__head">
        <span className="v3-panel__title">
          <Icon name="target" size={15} />
          هدف هفتگی
        </span>

        <button type="button" className="v3-goal__edit" onClick={() => onSetGoal?.(goal)}>
          <Icon name="settings" size={13} />
          تنظیم
        </button>
      </div>

      <div className="v3-goal__nums">
        <b>{faNum(active)}</b>
        <span>از {faNum(goal)} روز فعال</span>
        <i>{faNum(pct)}٪</i>
      </div>

      <div className="v3-goal__dots">
        {Array.from({ length: goal }).map((_, index) => (
          <span key={index} className={index < active ? 'is-on' : ''} />
        ))}
      </div>

      <div className="v3-goal__foot">
        {faNum(actions)} فعالیت ثبت‌شده در ۷ روز گذشته
      </div>
    </div>
  );
}

/* کارت «یادداشت‌ها و خط‌کشی‌ها» — از کالکشن واقعی web_ink_pages */
export function NotesCard({ onOpen }) {
  const { data } = useQuery({
    queryKey: ['me-notes'],
    queryFn: () => api.get('/api/me/notes').then((r) => r.data),
    staleTime: 3 * 60 * 1000,
    retry: false,
  });

  const items = data?.items || [];
  if (!items.length) return null;

  const totalPages = items.reduce((sum, it) => sum + (it.pages || 0), 0);

  return (
    <section className="v3-panel">
      <header className="v3-panel__head">
        <span className="v3-panel__title">
          <Icon name="doc" size={15} />
          یادداشت‌ها
        </span>
        <span className="v3-panel__hint">
          {faNum(items.length)} فایل · {faNum(totalPages)} صفحه
        </span>
      </header>

      <div className="v3-ltable">
        {items.slice(0, 4).map((item) => (
          <button
            type="button"
            key={`${item.scope}-${item.id}`}
            className="v3-ltable__row"
            onClick={() => onOpen?.(item)}
          >
            <span className="v3-ltable__name">
              <b className="v3-ltable__dot" style={{ background: '#9CC3FF' }} />
              <span>{item.name}</span>
            </span>

            <span className="v3-ltable__slots">
              <i>{faNum(item.pages)} صفحه</i>
              <i>{faNum(item.strokes)} خط</i>
            </span>

            <span className="v3-ltable__count">{faNum(item.last_page)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
