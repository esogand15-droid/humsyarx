import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat, B, NoPerm, Empty, toast } from '../ui.jsx';

// 📈🌊 WA2.6 + موج Analytics-Filters — تحلیل پیشرفته با فیلتر بازه‌ی زمانی واقعی
// (days به بک‌اند می‌رود) + بخش «تحلیل عمیق» با گیت جداگانه‌ی stats.deep.
// هر چارت به یک سؤال مدیریتی پاسخ می‌دهد؛ هیچ متریک ساختگی نیست.
const TINTS = ['var(--acc)', 'var(--ok)', 'var(--warn)', 'var(--purple)', 'var(--teal)', 'var(--bad)'];
const RANGES = [7, 14, 30, 90];
const fa = (n) => Number(n ?? 0).toLocaleString('fa-IR');

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
          <B kind="acc">{fa(v)}</B>
        </div>
      ))}
    </div>
  );
}

// 🌊 چارت میله‌ای سری روزانه — سبک، بدون وابستگی، با tooltip کامل
function DailyBars({ data, tint = 'var(--acc)', question, note }) {
  const rows = (data || []).filter(d => d && d.date);
  if (!rows.length) return <Empty icon="📭" text="داده‌ای در این بازه نیست" />;
  const max = Math.max(1, ...rows.map(d => d.count || 0));
  return (
    <div>
      {question && <div className="chart-q">❔ {question}</div>}
      <div className="dbars" dir="ltr">
        {rows.map(d => (
          <div key={d.date} className="dbar-col" title={`${d.date} — ${fa(d.count)}`}>
            <div className="dbar" style={{ height: `${Math.max(3, Math.round((d.count || 0) * 100 / max))}%`, background: tint }} />
          </div>
        ))}
      </div>
      <div className="row" style={{ marginTop: 6 }}>
        <span className="muted code" style={{ fontSize: 10 }}>{rows[rows.length - 1].date.slice(5)}</span>
        <span className="spacer" />
        {note && <span className="muted">{note}</span>}
        <span className="spacer" />
        <span className="muted code" style={{ fontSize: 10 }}>{rows[0].date.slice(5)}</span>
      </div>
    </div>
  );
}

export default function Analytics() {
  const [an, setAn] = useState(null);
  const [days, setDays] = useState(14);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);

  const load = async (dy = days) => {
    setErr(''); setLoading(true);
    try { setAn(await api.waAnalytics(dy)); }
    catch (e) {
      if (e.status === 403) {
        // fallback مسیر قدیمی owner (همان endpoint، حالا تک‌منبع)
        try { setAn(await api.analytics(dy)); return; } catch (e2) { setPermErr(true); return; }
      }
      setErr(errText(e));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(days); }, [days]);

  if (permErr) return <NoPerm text="تحلیل‌ها نیازمند مجوز «آمار و داشبورد مدیریتی» (stats.view) است" />;
  if (err) return <ErrorState error={err} onRetry={() => load()} />;
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
  const bundle = an.bundle || (an.kpis ? an : null);   // fallback مسیر مالک هم همان bundle است
  const rangeChip = (
    <div className="row" style={{ gap: 5 }}>
      {RANGES.map(d => (
        <button key={d} className={`btn sm ${days === d ? 'primary' : ''}`} onClick={() => setDays(d)}>
          {fa(d)} روز
        </button>
      ))}
      <button className="btn sm" title="تازه‌سازی" onClick={() => load()}>🔄</button>
      {loading && <span className="muted">⏳</span>}
    </div>
  );

  // fallback حالت قدیمی کاملاً تخت (مسیر owner قدیمیِ بدون kpis — سازگاری)
  if (!hasNewShape && !bundle) {
    const flat = Object.entries(an).filter(([, v]) => typeof v === 'number');
    const nested = Object.entries(an).filter(([, v]) => typeof v === 'object' && v !== null);
    return (
      <>
        <div className="row"><div><div className="h1">تحلیل‌های سامانه</div>
          <div className="sub">متحد از داده‌های واقعی answers/downloads/subscriptions</div></div>
          <span className="spacer" />{rangeChip}</div>
        <div className="grid g4" style={{ marginTop: 12 }}>
          {flat.map(([k, v]) => <Stat key={k} icon="📊" label={k} value={fa(v)} tint="var(--acc)" />)}
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
      <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
        <div>
          <div className="h1">تحلیل‌های سامانه</div>
          <div className="sub">داده‌های واقعی داشبوردهای آماری db · فیلتر بازه مستقیم به بک‌اند می‌رود</div>
        </div>
        <span className="spacer" />
        {rangeChip}
      </div>

      {/* ── تحلیل عمیق بازه‌ای (گیت stats.deep / مسیر مالک) ── */}
      {bundle && (
        <>
          <div className="h1" style={{ marginTop: 16, fontSize: 15 }}>📊 تحلیل {fa(bundle.days || days)} روز‌ی اخیر</div>
          <div className="grid g4" style={{ marginTop: 10 }}>
            <Stat icon="📡" label="کاربران فعال در بازه" value={fa(bundle.kpis?.active_users)} tint="var(--ok)" />
            <Stat icon="🆕" label="ثبت‌نام‌های بازه" value={fa(bundle.kpis?.new_users)} tint="var(--acc)" />
            <Stat icon="⚡" label="کل کنش‌های بازه" value={fa(bundle.kpis?.total_actions)} tint="var(--purple)" />
            <Stat icon="🎫" label="تیکت‌های جدید بازه" value={fa(bundle.kpis?.new_tickets)}
                  tint={(bundle.kpis?.new_tickets || 0) > 0 ? 'var(--warn)' : 'var(--ok)'} />
          </div>
          {(bundle.kpis?.open_reports || 0) > 0 && (
            <div className="row" style={{ marginTop: 8 }}>
              <B kind="warn">🚩 {fa(bundle.kpis.open_reports)} گزارش محتوا/سؤال باز است</B>
            </div>
          )}
          <div className="grid g2" style={{ marginTop: 12 }}>
            <div className="panel panel-pad">
              <b>⚡ کنش‌های روزانه</b>
              <DailyBars data={bundle.daily?.activity} tint="linear-gradient(180deg,var(--acc),var(--teal))"
                         question="روند تعامل کاربران صعودی است یا نزولی؟" />
            </div>
            <div className="panel panel-pad">
              <b>🆕 ثبت‌نام‌های روزانه</b>
              <DailyBars data={bundle.daily?.users} tint="linear-gradient(180deg,var(--ok),var(--teal))"
                         question="قیف جذب کاربر جدید در این بازه چگونه بوده؟" />
            </div>
          </div>
          <div className="grid g2" style={{ marginTop: 12 }}>
            <div className="panel panel-pad">
              <b>🧭 پرکاربردترین عملیات</b>
              <div className="chart-q">❔ کاربران در این بازه بیشتر چه می‌کنند؟</div>
              <MiniBars obj={Object.fromEntries((bundle.top_actions || []).map(t => [t.action, t.count]))} limit={8} />
            </div>
            <div className="panel panel-pad">
              <b>🕐 ساعات اوج فعالیت</b>
              <div className="chart-q">❔ برای ارسال/نگهداری، چه ساعاتی شلوغ‌تر است؟</div>
              <MiniBars obj={Object.fromEntries((bundle.hourly || []).map(h => [`ساعت ${fa(h.hour)}`, h.count]))} limit={6} />
            </div>
          </div>
        </>
      )}
      {hasNewShape && !bundle && an.deep === false && (
        <div className="panel panel-pad" style={{ marginTop: 12, borderColor: 'rgba(77,184,255,.3)' }}>
          <span className="muted">🔒 نمودارهای بازه‌ای با مجوز «تحلیل عمیق بازه‌ای» (stats.deep) فعال می‌شوند — از مالک سامانه بخواهید این مجوز را به نقش شما بیفزاید.</span>
        </div>
      )}

      {hasNewShape && (
        <>
          <div className="h1" style={{ marginTop: 20, fontSize: 15 }}>🧮 داشبوردهای تجمیعی</div>
          <div className="grid g4" style={{ margin: '10px 0 14px' }}>
            <Stat icon="🗄" label={`منابع جدید (${fa(days)} روز)`} value={fa(an.new_resources_in_range ?? an.new_resources_7d)} tint="var(--ok)" />
            <Stat icon="📡" label="کاربران فعال امروز" value={fa(an.active_today)} tint="var(--acc)" />
          </div>
          <div className="grid g2">
            {SECTIONS.filter(([k]) => an[k] && typeof an[k] === 'object').map(([k, title, tint], i) => {
              const obj = an[k];
              const nums = Object.entries(obj).filter(([, v]) => typeof v === 'number');
              const nested = Object.entries(obj).filter(([, v]) => typeof v === 'object' && v !== null);
              return (
                <div key={k} className="panel panel-pad">
                  <div className="row"><b>{title}</b><span className="spacer" />
                    <B kind="acc">{fa(nums.length)} شاخص</B></div>
                  <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(130px,1fr))', gap: 8, marginTop: 10 }}>
                    {nums.slice(0, 8).map(([kk, vv]) => (
                      <div key={kk} className="panel panel-pad" style={{ background: 'var(--bg)', padding: 10 }}>
                        <div style={{ fontSize: 17, fontWeight: 800, color: TINTS[i % TINTS.length] }}>{fa(vv)}</div>
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
      )}
    </>
  );
}
