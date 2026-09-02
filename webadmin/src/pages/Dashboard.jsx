import React, { useEffect, useRef, useState } from 'react';
import { api, errText } from '../api.js';
import { Stat, Loading, ErrorState, B, FaDateTime, RelativeTime, PageHeader, toast } from '../ui.jsx';

// 📊 داشبورد عملیات + ⚠️ نیازمند اقدام (WA2.7) + 🕓 فید فعالیت واقعی (WA2.7)
// 🌊 موج Dash-Personalize — نمایش/پنهان بخش‌ها (ترجیح محلی هر مرورگر، localStorage)
const WKEY = 'wa_dash_widgets';
const WIDGETS = [
  ['attn', '⚠️ نیازمند اقدام'],
  ['insights', '🧠 مرکز هوش'],
  ['kpis', '📊 کارت‌های عملیات'],
  ['sys', '📈 شاخص‌های سامانه'],
  ['feed', '🕓 جریان فعالیت'],
];

// 🌊 موج Parity-Final — نگاشت اکشن‌های هشدار ربات به مسیرهای SPA
const ALERT_GO = {
  'admin:pending': '/users?status=pending',
  'ticket:manage': '/tickets',
  'admin:stats_questions': '/analytics',
  'admin:stats_users': '/analytics',
  'admin:cat_users': '/users',
  'admin:cat_content': '/content',
  'report:manage:all': '/content',
};
const faW = ['این هفته', '۱ هفته پیش', '۲ هفته پیش', '۳ هفته پیش'];

export default function Dashboard({ me, go }) {
  const [ov, setOv] = useState(null);
  const [stats, setStats] = useState(null);
  const [attn, setAttn] = useState(null);
  const [feed, setFeed] = useState(null);
  const [ins, setIns] = useState(null);        // 🌊 مرکز هوش (مرکز rule-based واقعی db)
  const [err, setErr] = useState('');
  const [prefsOpen, setPrefsOpen] = useState(false);
  const prefsRef = useRef(null);
  const [wcfg, setWcfg] = useState(() => {
    try { return JSON.parse(localStorage.getItem(WKEY)) || {}; } catch { return {}; }
  });
  const won = (k) => wcfg[k] !== false;
  const toggleW = (k) => setWcfg(s => {
    const n = { ...s, [k]: !(s[k] !== false) };
    try { localStorage.setItem(WKEY, JSON.stringify(n)); } catch { /* حریم خصوصی */ }
    return n;
  });
  useEffect(() => {
    if (!prefsOpen) return;
    const h = (e) => { if (prefsRef.current && !prefsRef.current.contains(e.target)) setPrefsOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setPrefsOpen(false); };
    document.addEventListener('mousedown', h);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', esc); };
  }, [prefsOpen]);

  // CSV به‌صورت stream از سرور می‌آید؛ dataset کامل وارد RAM مرورگر نمی‌شود.
  const [expBusy, setExpBusy] = useState(false);
  const exportUsers = async () => {
    setExpBusy(true);
    try { await api.exportUsersCsv(); toast('خروجی CSV کاربران آماده شد'); }
    catch (e) { toast(errText(e), 'err'); }
    setExpBusy(false);
  };

  const load = async () => {
    setErr('');
    try {
      const bundle = await api.dashboardBundle();
      setOv(bundle.overview || null);
      setStats(bundle.stats || null);
      setAttn(bundle.attention || { items: [], backup: null });
      setFeed(bundle.activity || []);
      setIns(bundle.insights || null);
    } catch (e) { setErr(e); }
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
    { icon: '🚩', label: 'گزارش‌های باز', v: ov.open_reports, tint: 'var(--warn)', go: '/content?tab=reports' },
  ].filter(card => card.v !== null && card.v !== undefined);
  const attnItems = (attn?.items || []).filter(i => i.count > 0);
  return (
    <>
      <PageHeader title="داشبورد عملیات" description="وضعیت سامانه، صف‌های نیازمند اقدام و رخدادهای امروز"
        actions={<div className="menu-anchor" ref={prefsRef}>
          <button className="btn sm" title="سفارشی‌سازی ویجت‌ها" aria-label="سفارشی‌سازی داشبورد"
                  aria-haspopup="true" aria-expanded={prefsOpen ? 'true' : 'false'}
                  onClick={() => setPrefsOpen(x => !x)}>⚙️ ویجت‌ها</button>
          {prefsOpen && (
            <div className="colmenu colmenu--end" role="menu">
              {WIDGETS.map(([k, label]) => (
                <label key={k} className="colmenu-item">
                  <input type="checkbox" checked={won(k)} onChange={() => toggleW(k)} />
                  <span>{label}</span>
                </label>
              ))}
              <div className="muted" style={{ padding: '4px 8px', fontSize: 'var(--fs-caption)' }}>ترجیح فقط روی همین مرورگر ذخیره می‌شود</div>
            </div>
          )}
        </div>} />

      {/* ⚠️ WA2.7 — نیازمند اقدام (کلیک → مستقیم به همان صف) */}
      {attn && won('attn') && (
        <div className={`panel panel-pad ${attnItems.length ? 'panel--attention' : 'panel--clear'}`} style={{ marginBottom: 14 }}>
          <div className="row">
            <b>⚠️ نیازمند اقدام</b>
            <span className="spacer" />
            {attn.backup && (
              <B kind={attn.backup.enabled ? 'ok' : 'warn'}>
                💾 بکاپ خودکار {attn.backup.enabled ? 'فعال' : 'غیرفعال'}
                {attn.backup.last_run ? <> · آخرین: <FaDateTime value={attn.backup.last_run} /></> : null}
              </B>
            )}
            {!attnItems.length && <B kind="ok">همه‌ی صف‌ها خالی‌اند 🎉</B>}
          </div>
          {attnItems.length > 0 && (
            <div className="attn-grid" style={{ marginTop: 12 }}>
              {attnItems.map(i => (
                <button type="button" key={i.key} className={`attn-item ${i.severity || ''}`} onClick={() => i.go && go(i.go)}>
                  <span style={{ fontSize: 'var(--fs-icon)' }}>{i.icon}</span>
                  <div style={{ flex: 1 }}>
                    <div className="row"><b style={{ color: 'var(--txt)', fontSize: 'var(--fs-section)' }}>{Number(i.count).toLocaleString('fa')}</b>
                      {i.severity && <B kind={i.severity === 'critical' ? 'bad' : 'warn'}>{i.severity === 'critical' ? 'بحرانی' : 'هشدار'}</B>}</div>
                    <div className="muted">{i.label}</div>
                    {i.timestamp && <div className="muted" style={{ marginTop: 3 }}><FaDateTime value={i.timestamp} /></div>}
                  </div>
                  <span className="muted">‹</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 🧠🌊 موج Parity-Final — مرکز هوش ربات (داده‌ی واقعی db.admin_insights؛ همان صفحه‌ی ربات) */}
      {ins && won('insights') && (
        <div className="panel panel-pad" style={{ marginBottom: 14 }}>
          <div className="row"><b>🧠 مرکز هوش ربات</b><span className="spacer" />
            {ins.forecast_next_week != null && (
              <B kind="acc">🔮 پیش‌بینی هفته‌ی آینده: ~{Number(ins.forecast_next_week).toLocaleString('fa-IR')} ثبت‌نام</B>)}
          </div>
          <div className="sub" style={{ marginTop: 2 }}>هشدارهای rule-based روی داده‌ی واقعی — کلیک روی هر هشدار می‌برد به محل رسیدگی</div>
          <div className="grid g2" style={{ marginTop: 10 }}>
            <div>
              {(ins.alerts || []).length === 0
                ? <span className="muted">✅ هیچ هشدار فعالی نیست — همه‌چیز مرتب است.</span>
                : (ins.alerts || []).map((a, i) => (
                    <div key={i} className="insight-alert" title="رسیدگی"
                         onClick={() => ALERT_GO[a.action] && go(ALERT_GO[a.action])}>
                      <span>{a.icon}</span>
                      <div style={{ flex: 1 }}>
                        <b style={{ fontSize: 'var(--fs-body)' }}>{a.title}</b>
                        {a.detail && <div className="muted" style={{ fontSize: 'var(--fs-label)' }}>{a.detail}</div>}
                      </div>
                      <span className="muted">‹</span>
                    </div>
                  ))}
            </div>
            <div>
              <div className="muted" style={{ marginBottom: 6 }}>📈 روند ثبت‌نام ۴ هفته‌ی اخیر</div>
              {(ins.week_counts || []).map((c, i) => (
                <div key={i} className="minibar-row">
                  <span className="muted" style={{ minWidth: 76 }}>{faW[i]}</span>
                  <div className="minibar-track">
                    <div className="minibar-fill" style={{
                      width: `${Math.round(c * 100 / Math.max(1, ...(ins.week_counts || [1])))}%` }} />
                  </div>
                  <B kind="acc">{Number(c).toLocaleString('fa-IR')}</B>
                </div>
              ))}
              {(ins.top_admins || []).length > 0 && (<>
                <div className="muted" style={{ margin: '10px 0 6px' }}>👑 پرکارترین ادمین‌های فرعی (۷ روز)</div>
                {ins.top_admins.slice(0, 5).map((a, i) => (
                  <div key={i} className="row" style={{ fontSize: 'var(--fs-body)', padding: '2px 0' }}>
                    <span>{['🥇','🥈','🥉','4️⃣','5️⃣'][i]}</span>
                    <span style={{ flex: 1 }}>{a.name} {a.role ? <span className="muted">({a.role})</span> : ''}</span>
                    <B>{Number(a.count).toLocaleString('fa-IR')} کنش</B>
                  </div>
                ))}
              </>)}
            </div>
          </div>
        </div>
      )}

      {won('kpis') && (
        <div className="grid g4">
          {cards.map((c, i) => (
            <div key={i} onClick={() => c.go && go(c.go)} style={{ cursor: c.go ? 'pointer' : 'default' }}>
              <Stat icon={c.icon} label={c.label} value={Number(c.v ?? 0).toLocaleString('fa')} tint={c.tint} />
            </div>
          ))}
        </div>
      )}

      {stats && won('sys') && (() => {
        // 🌊 W-Design 4 — ترند امروز نسبت به میانگین ۶ روز قبلِ هفته (client-side، بدون API جدید)
        const today = Number(stats.active_today ?? 0);
        const othersAvg = Math.max(0, (Number(stats.active_week ?? 0) - today)) / 6;
        const delta = othersAvg > 0 ? Math.round((today - othersAvg) / othersAvg * 100) : null;
        return (
        <>
          <div className="h1" style={{ marginTop: 22, fontSize: 'var(--fs-section)' }}>شاخص‌های سامانه</div>
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
      {feed !== null && won('feed') && (
        <>
          <div className="h1" style={{ marginTop: 22, fontSize: 'var(--fs-section)' }}>🕓 جریان فعالیت</div>
          <div className="panel" style={{ marginTop: 10 }}>
            {feed.length === 0 && <div className="center-state">رویدادی نیست</div>}
            {feed.slice(0, 14).map(f => (
              <div key={f.id} className="feed-row">
                <span className="muted" style={{ minWidth: 132 }}><RelativeTime value={f.at} /></span>
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

      {/* 🌊 موج Export — خروجی داده (سمت مرورگر، از همان داده‌ی واقعی API) */}
      {me?.is_owner && (
        <>
          <div className="h1" style={{ marginTop: 22, fontSize: 'var(--fs-section)' }}>📥 خروجی داده</div>
          <div className="panel panel-pad" style={{ marginTop: 10 }}>
            <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
              <button className="btn" disabled={expBusy} onClick={exportUsers}>
                {expBusy ? '⏳ در حال آماده‌سازی…' : '⬇️ کاربران (CSV کامل)'}
              </button>
              <span className="muted" style={{ fontSize: 'var(--fs-label)' }}>
                همان داده‌ی واقعی جدول کاربران با صفحه‌بندی خودکار · دانلود مستقیم مرورگر (بدون IDM) — برای خروجی اکسل گروهی، از بخش «سیستم → خروجی اکسل» استفاده کنید.
              </span>
            </div>
          </div>
        </>
      )}
    </>
  );
}
