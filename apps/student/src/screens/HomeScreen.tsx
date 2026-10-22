import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { AppBar, Card, Chip, ListRow, ProgressBar, SkeletonStack } from '../components';
import { Icon } from '../icons';
import { dashboard } from '../lib/dashboard';
import type { DashboardPayload, UpcomingExam } from '../lib/dashboard';
import { reader, readerPath } from '../lib/reader';
import type { ContinueItem } from '../lib/reader';
import { useSession } from '../lib/session';
import { errorText } from '../lib/api';
import { fa } from '../lib/library';

function ExamRow({ exam }: { exam: UpcomingExam }) {
  const label = exam.days_left !== null
    ? exam.days_left === 0 ? 'امروز' : `${fa(exam.days_left)} روز دیگر`
    : exam.date;
  return (
    <div className="row gap-10" style={{ padding: '10px 0' }}>
      <div className="ibox ibox--cyan" style={{ width: 44, height: 44, borderRadius: 14 }}>
        <Icon name="i-calendar" size={20} />
      </div>
      <div className="grow">
        <div className="h3">{exam.lesson}</div>
        <div className="small">{exam.time} · {label}</div>
      </div>
      {exam.days_left !== null && exam.days_left <= 3 && (
        <Chip variant="danger">نزدیک</Chip>
      )}
    </div>
  );
}

function ContinueCard({ item }: { item: ContinueItem }) {
  const path = readerPath(item.scope, item.id);
  const subtitle = `صفحه ${fa(item.page)} از ${fa(item.total)}`;
  return (
    <Link to={path} style={{ display: 'block' }}>
      <Card className="mt-8" style={{ borderInlineStart: '3px solid var(--brand)' }}>
        <div className="row gap-10">
          <div className="ibox" style={{ width: 44, height: 44, borderRadius: 14 }}>
            <Icon name="i-book-open" size={20} />
          </div>
          <div className="grow">
            <div className="h3">{item.name}</div>
            <div className="small mt-4">{subtitle}</div>
            <div className="mt-8">
              <ProgressBar value={item.percent || 0} />
            </div>
          </div>
        </div>
      </Card>
    </Link>
  );
}

function StatCard({ icon, value, label, color }: { icon: string; value: string; label: string; color?: string }) {
  const bg = color === 'cyan' ? 'var(--cyan-soft)' : color === 'ok' ? 'var(--ok-soft)' : 'var(--amber-soft)';
  const fg = color === 'cyan' ? 'var(--cyan)' : color === 'ok' ? 'var(--ok)' : 'var(--amber-ink)';
  return (
    <Card className="mt-8" style={{ textAlign: 'center', padding: 20 }}>
      <div style={{ width: 40, height: 40, borderRadius: 12, background: bg, color: fg, display: 'grid', placeItems: 'center', margin: '0 auto' }}>
        <Icon name={icon as any} size={20} />
      </div>
      <div className="h2 mt-8">{value}</div>
      <div className="small mt-4">{label}</div>
    </Card>
  );
}

/** داشبورد کامل — ویجت‌های داده‌محور */
export function HomeScreen() {
  const { user } = useSession();
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [recent, setRecent] = useState<ContinueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [d, r] = await Promise.all([
        dashboard.overview(),
        reader.recent().catch(() => ({ items: [] })),
      ]);
      setData(d);
      setRecent(r.items);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const displayName = data?.user?.display_name || user?.name || 'دانشجوی عزیز';
  const stats = data?.stats;

  if (loading) {
    return (
      <>
        <AppBar title="هامزیار" sub="در حال بارگذاری…" />
        <div className="page">
          <SkeletonStack rows={6} />
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <AppBar title="هامزیار" sub="خطا در دریافت اطلاعات" />
        <div className="page" style={{ textAlign: 'center', paddingTop: 60 }}>
          <div style={{ color: 'var(--danger)', opacity: 0.6 }}>
            <Icon name="i-alert-circle" size={48} />
          </div>
          <p className="body mt-16">{error}</p>
          <button className="btn mt-16" onClick={load}>تلاش دوباره</button>
        </div>
      </>
    );
  }

  return (
    <>
      <AppBar
        title={`سلام، ${displayName.split(' ')[0]}`}
        sub="همراه تو، از ترم یک تا پای تخته"
        actions={
          <Link to="/search" style={{ color: 'inherit' }}>
            <Icon name="i-search" size={22} />
          </Link>
        }
      />
      <div className="page">
        {/* ادامه مطالعه */}
        {recent.length > 0 && (
          <>
            <div className="row row--between mt-8">
              <div className="h3">ادامه بده</div>
              <Link to="/library" className="small" style={{ color: 'var(--brand)' }}>همه</Link>
            </div>
            {recent.slice(0, 1).map((item) => (
              <ContinueCard key={item.id} item={item} />
            ))}
          </>
        )}

        {/* آمار سریع */}
        <div className="row row--between mt-16">
          <div className="h3">آمار تو</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
          <StatCard
            icon="i-flask"
            value={stats ? fa(stats.total_answers) : '۰'}
            label="سؤال حل‌شده"
            color="cyan"
          />
          <StatCard
            icon="i-target"
            value={stats ? `${fa(stats.accuracy)}٪` : '۰٪'}
            label="درستی"
            color="ok"
          />
        </div>

        {/* امتحان‌های پیش‌رو */}
        {data && data.upcoming_exams.length > 0 && (
          <>
            <div className="row row--between mt-16">
              <div className="h3">امتحان‌های پیش‌رو</div>
              <Link to="/schedule" className="small" style={{ color: 'var(--brand)' }}>برنامه</Link>
            </div>
            <Card className="mt-8">
              {data.upcoming_exams.slice(0, 3).map((exam) => (
                <ExamRow key={exam.id} exam={exam} />
              ))}
            </Card>
          </>
        )}

        {/* دسترسی سریع */}
        <div className="h3 mt-16">دسترسی سریع</div>
        <Card variant="flush" className="mt-8">
          <Link to="/library">
            <ListRow icon="i-book" title="کتابخانه" sub="جزوه، ویدیو و مرجع درسی" chevron />
          </Link>
          <Link to="/exam">
            <ListRow icon="i-flask" title="بانک سؤال" sub="تمرین و آزمون" chevron />
          </Link>
          <Link to="/me/notes">
            <ListRow icon="i-pen" title="دفتر من" sub="یادداشت‌های روی جزوه‌ها" chevron />
          </Link>
          <Link to="/schedule">
            <ListRow icon="i-calendar" title="برنامه هفتگی" sub="کلاس‌ها و امتحانات" chevron />
          </Link>
        </Card>

        {/* تاپیک‌های ضعیف */}
        {stats && stats.weak_topics.length > 0 && (
          <>
            <div className="h3 mt-16">نیاز به تمرین بیشتر</div>
            <div className="row gap-8 mt-8" style={{ flexWrap: 'wrap' }}>
              {stats.weak_topics.map((topic) => (
                <Chip key={topic} variant="quiet">{topic}</Chip>
              ))}
            </div>
          </>
        )}

        {/* اشتراک */}
        <Card className="mt-16" style={{ background: 'var(--brand-soft)', borderColor: 'transparent' }}>
          <div className="row gap-10">
            <div className="grow">
              <div className="h3" style={{ color: 'var(--brand-ink)' }}>اشتراک پلاس</div>
              <div className="small mt-4" style={{ color: 'var(--brand-ink)' }}>
                دسترسی نامحدود به همه منابع و آزمون‌ها
              </div>
            </div>
            <Chip variant="cyan">فعال</Chip>
          </div>
        </Card>
      </div>
    </>
  );
}
