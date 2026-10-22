import { useCallback, useEffect, useState } from 'react';

import { AppBar, Card, EmptyState, SkeletonStack } from '../components';
import { Icon } from '../icons';
import { schedule } from '../lib/schedule';
import type { ScheduleItem } from '../lib/schedule';
import { errorText } from '../lib/api';
import { fa } from '../lib/library';

const TYPE_LABELS: Record<string, string> = {
  class: 'کلاس',
  exam: 'امتحان',
  makeup: 'جبرانی',
};

const TYPE_ICONS: Record<string, string> = {
  class: 'i-book-open',
  exam: 'i-award',
  makeup: 'i-clock',
};

function ScheduleRow({ item }: { item: ScheduleItem }) {
  const isExam = item.type === 'exam';
  const label = item.days_left !== null
    ? item.days_left === 0 ? 'امروز' : `${fa(item.days_left)} روز دیگر`
    : item.date;

  return (
    <div className="list__item" style={{ alignItems: 'flex-start', padding: '14px 16px' }}>
      <div
        className="ibox"
        style={{
          width: 44,
          height: 44,
          borderRadius: 14,
          marginTop: 2,
          background: isExam ? 'var(--danger-soft)' : 'var(--cyan-soft)',
          color: isExam ? 'var(--danger)' : 'var(--cyan)',
        }}
      >
        <Icon name={TYPE_ICONS[item.type] as any || 'i-calendar'} size={20} />
      </div>
      <span className="grow">
        <span className="h3" style={{ display: 'block' }}>{item.lesson}</span>
        <span className="small" style={{ display: 'block', marginTop: 4 }}>
          {item.teacher} · {item.time}
          {item.location ? ` · ${item.location}` : ''}
        </span>
        {item.note && (
          <span className="tiny" style={{ display: 'block', marginTop: 4, color: 'var(--ink-3)' }}>
            {item.note}
          </span>
        )}
      </span>
      <div style={{ textAlign: 'left', flexShrink: 0 }}>
        <span
          style={{
            fontSize: 10,
            padding: '3px 8px',
            borderRadius: 999,
            background: isExam ? 'var(--danger-soft)' : 'var(--paper-3)',
            color: isExam ? 'var(--danger)' : 'var(--ink-3)',
            whiteSpace: 'nowrap',
            display: 'inline-block',
          }}
        >
          {TYPE_LABELS[item.type] || item.type}
        </span>
        <div className="small mt-4" style={{ textAlign: 'left', direction: 'ltr' }}>{label}</div>
      </div>
    </div>
  );
}

/** برنامهٔ هفتگی — کلاس‌ها و امتحانات */
export function ScheduleScreen() {
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [days, setDays] = useState(7);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await schedule.list(days);
      setItems(res.items || []);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const exams = items.filter((i) => i.type === 'exam');
  const classes = items.filter((i) => i.type === 'class');

  return (
    <>
      <AppBar title="برنامه هفتگی" sub="کلاس‌ها و امتحانات پیش‌رو" />
      <div className="page">
        {/* فیلتر بازه */}
        <div className="row gap-8 mt-8" style={{ overflowX: 'auto', paddingBottom: 4 }}>
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className="btn btn--sm"
              style={{
                background: days === d ? 'var(--brand)' : 'var(--paper-3)',
                color: days === d ? 'var(--on-brand)' : 'var(--ink)',
                borderColor: days === d ? 'var(--brand)' : 'var(--line)',
                whiteSpace: 'nowrap',
              }}
            >
              {d === 7 ? 'هفته' : d === 14 ? '۲ هفته' : 'ماه'}
            </button>
          ))}
        </div>

        {loading && <div className="mt-8"><SkeletonStack rows={5} /></div>}

        {error && !loading && (
          <div className="mt-16" style={{ textAlign: 'center' }}>
            <p className="body">{error}</p>
            <button className="btn mt-8" onClick={load}>تلاش دوباره</button>
          </div>
        )}

        {!loading && !error && items.length === 0 && (
          <div className="mt-16">
            <EmptyState
              icon="i-calendar"
              title="برنامه‌ای نیست"
              text="در این بازه هیچ کلاس یا امتحانی ثبت نشده."
            />
          </div>
        )}

        {/* امتحان‌ها */}
        {!loading && !error && exams.length > 0 && (
          <>
            <div className="row row--between mt-16">
              <div className="h3">امتحان‌ها</div>
              <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 999, background: 'var(--danger-soft)', color: 'var(--danger)', fontWeight: 700 }}>
                {fa(exams.length)}
              </span>
            </div>
            <Card variant="flush" className="mt-8">
              {exams.map((item) => (
                <ScheduleRow key={item.id} item={item} />
              ))}
            </Card>
          </>
        )}

        {/* کلاس‌ها */}
        {!loading && !error && classes.length > 0 && (
          <>
            <div className="row row--between mt-16">
              <div className="h3">کلاس‌ها</div>
              <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 999, background: 'var(--paper-3)', color: 'var(--ink-3)', fontWeight: 700 }}>
                {fa(classes.length)}
              </span>
            </div>
            <Card variant="flush" className="mt-8">
              {classes.map((item) => (
                <ScheduleRow key={item.id} item={item} />
              ))}
            </Card>
          </>
        )}
      </div>
    </>
  );
}
