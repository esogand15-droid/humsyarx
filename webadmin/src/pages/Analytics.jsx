import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat, B, NoPerm } from '../ui.jsx';

// 📈🌊 WA2.6 — تحلیل پیشرفته: متحد از داده‌های واقعی db (کارت + مینی‌چارت میله‌ای)
const TINTS = ['var(--acc)', 'var(--ok)', 'var(--warn)', 'var(--purple)', 'var(--teal)', 'var(--bad)'];

function MiniBars({ obj, limit = 10 }) {
  const entries = Object.entries(obj || {}).filter(([, v]) => typeof v === 'number').slice(0, limit);
  const max = Math.max(1, ...entries.map(([, v]) => Math.abs(v)));
  if (!entries.length) return null;
  return (
    <div className="grid" style={{ gap: 6, marginTop: 10 }}>
      {entries.map(([k, v]) => (
        <div key={k} className="minibar-row">
          <span className="muted" style={{ minWidth: 130, textAlign: 'left', direction: 'ltr' }}>{k}</span>
          <div className="minibar-track">
            <div className="minibar-fill" style={{ width: `${Math.round(Math.abs(v) * 100 / max)}%` }} />
          </div>
          <B kind="acc">{Number(v).toLocaleString('fa')}</B>
        </div>
      ))}
    </div>
  );
}

export default function Analytics() {
  const [an, setAn] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);

  const load = async () => {
    setErr('');
    try { setAn(await api.waAnalytics()); }
    catch (e) {
      if (e.status === 403) {
        // fallback همان مسیر قدیمی owner
        try { setAn(await api.analytics()); return; } catch (e2) { setPermErr(true); return; }
      }
      setErr(errText(e));
    }
  };
  useEffect(() => { load(); }, []);

  if (permErr) return <NoPerm text="تحلیل‌ها نیازمند مجوز «آمار و داشبورد مدیریتی» (stats.view) است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!an) return <Loading rows={6} />;

  const SECTIONS = [
    ['users', '👥 کاربران', 'var(--acc)'],
    ['content', '📚 محتوا', 'var(--ok)'],
    ['questions', '🧪 سؤال‌ها', 'var(--purple)'],
    ['tickets', '🎫 تیکت‌ها', 'var(--warn)'],
    ['notif', '🔔 اعلان‌ها', 'var(--teal)'],
    ['sub', '💎 اشتراک‌ها', 'var(--acc)'],
    ['pulse', '📡 نبض فعالیت', 'var(--bad)'],
  ];
  const hasNewShape = SECTIONS.some(([k]) => an[k] !== undefined);

  // fallback حالت قدیمی (owner endpoint) — رندر عمومی
  if (!hasNewShape) {
    const flat = Object.entries(an).filter(([, v]) => typeof v === 'number');
    const nested = Object.entries(an).filter(([, v]) => typeof v === 'object' && v !== null);
    return (
      <>
        <div className="h1">تحلیل‌های سامانه</div>
        <div className="sub">متحد از داده‌های واقعی answers/downloads/subscriptions</div>
        <div className="grid g4">
          {flat.map(([k, v]) => <Stat key={k} icon="📊" label={k} value={Number(v).toLocaleString('fa')} tint="var(--acc)" />)}
        </div>
        {nested.map(([k, obj]) => (
          <div key={k} className="panel panel-pad" style={{ marginTop: 14 }}>
            <b>{k}</b><MiniBars obj={obj} />
          </div>
        ))}
      </>
    );
  }

  return (
    <>
      <div className="h1">تحلیل‌های سامانه</div>
      <div className="sub">🌊 WA2.6 — داده‌های واقعی داشبوردهای آماری db؛ هیچ متریک ساختگی نیست</div>
      <div className="grid g4" style={{ marginBottom: 14 }}>
        <Stat icon="🗄" label="منابع جدید (۷ روز)" value={Number(an.new_resources_7d ?? 0).toLocaleString('fa')} tint="var(--ok)" />
        <Stat icon="📡" label="کاربران فعال امروز" value={Number(an.active_today ?? 0).toLocaleString('fa')} tint="var(--acc)" />
      </div>
      <div className="grid g2">
        {SECTIONS.filter(([k]) => an[k] && typeof an[k] === 'object').map(([k, title, tint], i) => {
          const obj = an[k];
          const nums = Object.entries(obj).filter(([, v]) => typeof v === 'number');
          const nested = Object.entries(obj).filter(([, v]) => typeof v === 'object' && v !== null);
          return (
            <div key={k} className="panel panel-pad">
              <div className="row"><b>{title}</b><span className="spacer" />
                <B kind="acc">{nums.length} شاخص</B></div>
              <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(130px,1fr))', gap: 8, marginTop: 10 }}>
                {nums.slice(0, 8).map(([kk, vv]) => (
                  <div key={kk} className="panel panel-pad" style={{ background: 'var(--bg)', padding: 10 }}>
                    <div style={{ fontSize: 17, fontWeight: 800, color: TINTS[i % TINTS.length] }}>{Number(vv).toLocaleString('fa')}</div>
                    <div className="muted" style={{ direction: 'ltr', textAlign: 'right' }}>{kk}</div>
                  </div>
                ))}
              </div>
              {nested.map(([kk, vv]) => typeof vv === 'object' && vv !== null && !Array.isArray(vv) && (
                <div key={kk} style={{ marginTop: 10 }}>
                  <div className="muted">{kk}</div>
                  <MiniBars obj={vv} limit={8} />
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </>
  );
}
