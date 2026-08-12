import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Stat, Loading, ErrorState } from '../ui.jsx';

export default function Dashboard({ me, go }) {
  const [ov, setOv] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState('');

  const load = async () => {
    setErr('');
    try { setOv(await api.overview()); } catch (e) { setErr(e.message); }
    try { setStats(await api.stats()); } catch { /* owner-only */ }
  };
  useEffect(() => { load(); }, []);

  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!ov) return <Loading rows={5} />;

  const cards = [
    { icon: '👥', label: 'کل کاربران', v: ov.total_users, tint: 'var(--acc)' },
    { icon: '📝', label: 'در انتظار تأیید', v: ov.pending_users, tint: 'var(--warn)', go: '/users?status=pending' },
    { icon: '🧾', label: 'رسیدهای در انتظار', v: ov.pending_payments, tint: 'var(--warn)', go: '/subscriptions' },
    { icon: '🧪', label: 'سوالات در انتظار بازبینی', v: ov.pending_questions, tint: 'var(--purple)', go: '/questions' },
    { icon: '🎫', label: 'تیکت‌های باز', v: ov.open_tickets, tint: 'var(--bad)', go: '/tickets' },
    { icon: '💎', label: 'اشتراک‌های فعال', v: ov.active_subs, tint: 'var(--teal)' },
    { icon: '⏳', label: 'اشتراک‌های نزدیک به پایان', v: ov.expiring_soon, tint: 'var(--warn)' },
  ];
  return (
    <>
      <div className="h1">داشبورد عملیات</div>
      <div className="sub">نمای زنده‌ی صف‌های عملیاتی سامانه</div>
      <div className="grid g4">
        {cards.map((c, i) => (
          <div key={i} onClick={() => c.go && go(c.go)} style={{ cursor: c.go ? 'pointer' : 'default' }}>
            <Stat icon={c.icon} label={c.label} value={Number(c.v ?? 0).toLocaleString('fa')} tint={c.tint} />
          </div>
        ))}
      </div>
      {stats && (
        <>
          <div className="h1" style={{ marginTop: 22, fontSize: 15 }}>شاخص‌های سامانه</div>
          <div className="grid g4" style={{ marginTop: 10 }}>
            <Stat icon="📡" label="کاربران فعال امروز" value={Number(stats.active_today ?? 0).toLocaleString('fa')} tint="var(--ok)" />
            <Stat icon="📅" label="کاربران فعال هفته" value={Number(stats.active_week ?? 0).toLocaleString('fa')} tint="var(--ok)" />
            <Stat icon="🆕" label="ثبت‌نام‌های امروز" value={Number(stats.new_today ?? stats.today_new ?? 0).toLocaleString('fa')} tint="var(--acc)" />
            <Stat icon="📥" label="کل پاسخ‌های ثبت‌شده" value={Number(stats.total_answers ?? 0).toLocaleString('fa')} tint="var(--purple)" />
          </div>
        </>
      )}
    </>
  );
}
