import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Stat, Loading, ErrorState, B } from '../ui.jsx';

// 📊 داشبورد عملیات + ⚠️ نیازمند اقدام (WA2.7) + 🕓 فید فعالیت واقعی (WA2.7)
export default function Dashboard({ me, go }) {
  const [ov, setOv] = useState(null);
  const [stats, setStats] = useState(null);
  const [attn, setAttn] = useState(null);
  const [feed, setFeed] = useState(null);
  const [err, setErr] = useState('');

  const load = async () => {
    setErr('');
    try { setOv(await api.overview()); } catch (e) { setErr(e.message); }
    try { setStats(await api.stats()); } catch { /* owner-only */ }
    try { setAttn(await api.attention()); } catch { setAttn(null); }
    try { setFeed((await api.activity(30)).items || []); } catch { setFeed([]); }
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
  const attnItems = (attn?.items || []).filter(i => i.count > 0);
  return (
    <>
      <div className="h1">داشبورد عملیات</div>
      <div className="sub">نمای زنده‌ی صف‌های عملیاتی سامانه</div>

      {/* ⚠️ WA2.7 — نیازمند اقدام (کلیک → مستقیم به همان صف) */}
      {attn && (
        <div className="panel panel-pad" style={{ marginBottom: 14, borderColor: attnItems.length ? 'rgba(251,191,36,.35)' : 'rgba(52,211,153,.35)' }}>
          <div className="row">
            <b>⚠️ نیازمند اقدام</b>
            <span className="spacer" />
            {attn.backup && (
              <B kind={attn.backup.enabled ? 'ok' : 'warn'}>
                💾 بکاپ خودکار {attn.backup.enabled ? 'فعال' : 'غیرفعال'}
                {attn.backup.last_run ? ` · آخرین: ${String(attn.backup.last_run).slice(0, 16).replace('T', ' ')}` : ''}
              </B>
            )}
            {!attnItems.length && <B kind="ok">همه‌ی صف‌ها خالی‌اند 🎉</B>}
          </div>
          {attnItems.length > 0 && (
            <div className="attn-grid" style={{ marginTop: 12 }}>
              {attnItems.map(i => (
                <div key={i.key} className="attn-item" onClick={() => i.go && go(i.go)}>
                  <span style={{ fontSize: 20 }}>{i.icon}</span>
                  <div style={{ flex: 1 }}>
                    <b style={{ color: 'var(--txt)', fontSize: 15 }}>{Number(i.count).toLocaleString('fa')}</b>
                    <div className="muted">{i.label}</div>
                  </div>
                  <span className="muted">‹</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid g4">
        {cards.map((c, i) => (
          <div key={i} onClick={() => c.go && go(c.go)} style={{ cursor: c.go ? 'pointer' : 'default' }}>
            <Stat icon={c.icon} label={c.label} value={Number(c.v ?? 0).toLocaleString('fa')} tint={c.tint} />
          </div>
        ))}
      </div>

      {stats && (() => {
        // 🌊 W-Design 4 — ترند امروز نسبت به میانگین ۶ روز قبلِ هفته (client-side، بدون API جدید)
        const today = Number(stats.active_today ?? 0);
        const othersAvg = Math.max(0, (Number(stats.active_week ?? 0) - today)) / 6;
        const delta = othersAvg > 0 ? Math.round((today - othersAvg) / othersAvg * 100) : null;
        return (
        <>
          <div className="h1" style={{ marginTop: 22, fontSize: 15 }}>شاخص‌های سامانه</div>
          <div className="grid g4" style={{ marginTop: 10 }}>
            <Stat icon="📡" label="کاربران فعال امروز" delta={delta} hint="نسبت به میانگین ۶ روز قبل"
                  value={today.toLocaleString('fa')} tint="var(--ok)" />
            <Stat icon="📅" label="کاربران فعال هفته" value={Number(stats.active_week ?? 0).toLocaleString('fa')} tint="var(--ok)" />
            <Stat icon="🆕" label="ثبت‌نام‌های امروز" value={Number(stats.new_today ?? stats.today_new ?? 0).toLocaleString('fa')} tint="var(--acc)" />
            <Stat icon="📥" label="کل پاسخ‌های ثبت‌شده" value={Number(stats.total_answers ?? 0).toLocaleString('fa')} tint="var(--purple)" />
          </div>
        </>
        );
      })()}

      {/* 🕓 WA2.7 — فید فعالیت واقعی */}
      {feed !== null && (
        <>
          <div className="h1" style={{ marginTop: 22, fontSize: 15 }}>🕓 جریان فعالیت</div>
          <div className="panel" style={{ marginTop: 10 }}>
            {feed.length === 0 && <div className="center-state">رویدادی نیست</div>}
            {feed.slice(0, 14).map(f => (
              <div key={f.id} className="feed-row">
                <span className="muted" style={{ minWidth: 104, direction: 'ltr', textAlign: 'right' }}>{f.at}</span>
                <span className={`sev ${(f.severity || '').toLowerCase()}`} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ color: 'var(--txt)' }}>{f.actor_name}</span>
                  {f.actor_role ? <span className="muted"> ({f.actor_role})</span> : null}
                  <span> — {f.action}</span>
                  {f.target_label ? <span className="hl"> · {f.target_label}</span> : null}
                </div>
                {f.module && <B>{f.module}</B>}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
