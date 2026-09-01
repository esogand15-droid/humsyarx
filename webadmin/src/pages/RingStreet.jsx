import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import {
  B, Confirm, DataTable, Empty, ErrorState, Field, FaDateTime, Loading, Modal,
  NoPerm, PageHeader, SectionHeader, StatusBadge, Switch, Tabs, toast,
} from '../ui.jsx';

// 💍 رینگ استریت — پنل نظارت (§۳۲، §۶۶..§۷۴)
// همه‌ی داده‌ها از /api/ring/* می‌آیند و همه‌ی اکشن‌ها در بک‌اند با مجوز
// ring.manage + audit دوبل (ring_admin_audit + audit_logs) ثبت می‌شوند.
// این صفحه عمداً هیچ محتوای گفت‌وگویی نشان نمی‌دهد؛ فقط شواهدِ گزارش‌ها.

const TABS = [
  ['overview', '📊 نمای کلی'], ['queue', '⏳ صف'], ['chats', '💬 گفت‌وگوها'],
  ['reports', '🚩 گزارش‌ها'], ['users', '👤 کاربران'], ['settings', '⚙️ تنظیمات'],
  ['analytics', '📈 تحلیل'], ['audit', '🧭 حسابرسی'],
];

const fa = (n) => Number(n || 0).toLocaleString('fa-IR');
const MODE = { serious: '💍 جدی', fun: '🎭 فان' };
const PSTATUS = { active: 'فعال', paused: 'مکث', banned: 'بن', deleted: 'حذف‌شده' };

function Kpi({ icon, label, value, hint }) {
  return <div className="panel panel-pad" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
    <div style={{ fontSize: 22 }}>{icon}</div>
    <div style={{ minWidth: 0 }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 19, fontWeight: 700 }}>{value}</div>
      {hint && <div className="muted" style={{ fontSize: 11.5 }}>{hint}</div>}
    </div>
  </div>;
}

function Stat({ label, value }) {
  return <div className="muted" style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
    <span>{label}</span><b style={{ color: 'var(--txt)' }}>{value}</b>
  </div>;
}

export default function RingStreet({ me }) {
  const [tab, setTab] = useState('overview');
  const [ov, setOv] = useState(null);
  const [box, setBox] = useState({});
  const [err, setErr] = useState('');
  const [noPerm, setNoPerm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [rStat, setRStat] = useState('pending');
  const [drawer, setDrawer] = useState(null);
  const [edit, setEdit] = useState(null);
  const [force, setForce] = useState(null);
  const [confirmEnd, setConfirmEnd] = useState(null);
  const [killMode, setKillMode] = useState('soft');

  const load = useCallback(async () => {
    setErr('');
    try {
      const o = await api.ringOverview();
      setOv(o);
      if (tab === 'queue') setBox(await api.ringQueue({ limit: 120 }));
      else if (tab === 'chats') setBox(await api.ringSessions({ status: 'active', page, size: 25 }));
      else if (tab === 'reports') setBox(await api.ringReports({ status: rStat || '', page, size: 25 }));
      else if (tab === 'users') setBox(await api.ringProfiles({ q, page, size: 25 }));
      else if (tab === 'settings') setBox(await api.ringSettings());
      else if (tab === 'analytics') setBox(await api.ringAnalytics(7));
      else if (tab === 'audit') setBox(await api.ringAuditList(120));
      else setBox({});
      setEdit(null);
    } catch (e) {
      if (e.status === 403) setNoPerm(true); else setErr(errText(e));
    }
  }, [tab, page, q, rStat]);

  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); if (ok) toast(ok); await load(); }
    catch (e) { toast(errText(e), 'bad'); }
    finally { setBusy(false); }
  };

  const rows = box.sessions || box.reports || box.profiles || box.queue || box.audit || [];

  const cols = useMemo(() => {
    if (tab === 'queue') return [
      { k: 'uid', label: 'کاربر', render: r => <span className="code">{fa(r.uid)}</span> },
      { k: 'anon', label: 'ناشناس', render: r => <B kind="acc">#{r.anon || '—'}</B> },
      { k: 'mode', label: 'حالت', render: r => MODE[r.mode] || r.mode || '—' },
      { k: 'status', label: 'وضعیت', render: r => <B>{r.status}</B> },
      { k: 'wait', label: 'انتظار', render: r => (r.wait_s == null ? '—' : `${fa(Math.round(r.wait_s / 60))} دقیقه`) },
    ];
    if (tab === 'chats') return [
      { k: 'sid', label: 'جلسه', render: r => <span className="code">{r.session_id}</span> },
      { k: 'mode', label: 'حالت', render: r => MODE[r.mode] || r.mode },
      { k: 'users', label: 'دو کاربر', render: r => <div className="row" style={{ gap: 4 }}>
        {(r.slots || []).map(u => <B key={u} className="code">{fa(u)}</B>)}</div> },
      { k: 'msgs', label: 'پیام/مدیا', render: r => `${fa(r.messages_count)} / ${fa(r.media_count)}` },
      { k: 'at', label: 'آخرین فعالیت', render: r => <FaDateTime value={r.last_activity_at} /> },
      { k: 'x', label: 'اقدام', render: r => <button className="btn sm" disabled={busy}
        onClick={() => setConfirmEnd(r.session_id)}>⛔ بستن</button> },
    ];
    if (tab === 'reports') return [
      { k: 'id', label: 'کد', render: r => <span className="code">R{fa(r.report_id)}</span> },
      { k: 'why', label: 'دلیل', render: r => <B kind={r.severity >= 3 ? 'bad' : 'warn'}>{r.reason}</B> },
      { k: 'sev', label: 'شدت', render: r => fa(r.severity) },
      { k: 'target', label: 'مظنون', render: r => <span className="code">{fa(r.reported_uid)}</span> },
      { k: 'status', label: 'وضعیت', render: r => <StatusBadge status={r.status === 'pending' ? 'pending' : 'active'}
        label={r.status === 'pending' ? 'در انتظار' : r.status} /> },
      { k: 'at', label: 'زمان', render: r => <FaDateTime value={r.created_at} /> },
      { k: 'x', label: 'بررسی', render: r => <button className="btn sm" disabled={busy}
        onClick={() => act(async () => setDrawer({ kind: 'report', body: await api.ringReport(r.report_id) }), '')}>🔎</button> },
    ];
    if (tab === 'users') return [
      { k: 'uid', label: 'آیدی تلگرام', render: r => <span className="code">{fa(r.user_id ?? r._id)}</span> },
      { k: 'anon', label: 'ناشناس', render: r => <B kind="acc">#{r.anon_id || '—'}</B> },
      { k: 'mode', label: 'حالت', render: r => MODE[r.mode] || '—' },
      { k: 'status', label: 'وضعیت', render: r => <B kind={r.status === 'active' ? 'ok' : 'warn'}>{PSTATUS[r.status] || r.status || 'active'}</B> },
      { k: 'score', label: 'امتیاز گزارش', render: r => (r.report_score ? <B kind="bad">{fa(r.report_score)}</B> : '—') },
      { k: 'at', label: 'آخرین فعالیت', render: r => <FaDateTime value={r.updated_at || r.created_at} /> },
      { k: 'x', label: 'پرونده', render: r => <button className="btn sm" disabled={busy}
        onClick={() => act(async () => setDrawer({ kind: 'profile', body: await api.ringProfile(r.user_id ?? r._id) }), '')}>🗂</button> },
    ];
    return [
      { k: 'at', label: 'زمان', render: r => <FaDateTime value={r.created_at} /> },
      { k: 'who', label: 'توسط', render: r => <span className="code">{fa(r.admin_id)}</span> },
      { k: 'action', label: 'اقدام', render: r => <B kind="acc">{r.action}</B> },
      { k: 'target', label: 'هدف', render: r => <span className="code">{String(r.target ?? '—')}</span> },
      { k: 'note', label: 'یادداشت', render: r => <span className="muted">{r.note || '—'}</span> },
    ];
  }, [tab, busy]);

  if (noPerm) return <NoPerm text="مدیریت رینگ استریت نیازمند مجوز «ring.manage» است." />;
  if (err) return <ErrorState title="بارگذاری داده‌های رینگ ناموفق بود" error={err} onRetry={load} />;
  if (!ov) return <Loading rows={5} />;

  const live = ov.live || {};
  const qs = ov.queue || {};

  return <>
    <PageHeader
      eyebrow="💍 ماژول گفت‌وگوی ناشناس"
      title="رینگ استریت"
      description="صف تطبیق، گفت‌وگوها، نظارت و تنظیمات. هیچ پیام گفت‌وگویی اینجا نمایش داده نمی‌شود."
      actions={<div className="row" style={{ gap: 8 }}>
        <Field label="فیچر فعال"><Switch on={!!ov.flag} disabled={busy}
          onChange={v => act(() => api.ringFlag(v, killMode), v ? 'رینگ روشن شد' : `رینگ خاموش شد (${killMode})`)} /></Field>
        <Field label="نوع خاموشی"><select value={killMode} onChange={e => setKillMode(e.target.value)}>
          <option value="soft">soft — جلسات موجود تمام شوند</option>
          <option value="hard">hard — همه را ببند</option>
        </select></Field>
      </div>}
    />

    <Tabs items={TABS} value={tab} onChange={t => { setTab(t); setPage(1); setDrawer(null); }} />

    {tab === 'overview' && <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))' }}>
      <Kpi icon="⏳" label="در صف" value={fa(qs.waiting || live.waiting)} hint={`claim‌شده: ${fa(qs.claimed)}`} />
      <Kpi icon="💬" label="گفت‌وگوی فعال" value={fa(live.in_chat)} hint={`RAM: ${fa(ov.ram?.in_chat)}`} />
      <Kpi icon="👤" label="پروفایل‌ها" value={fa(live.active_profiles || live.profiles)} hint={`مکث: ${fa(live.paused)} · بن: ${fa(live.banned)}`} />
      <Kpi icon="🚩" label="گزارش باز" value={fa(live.reports_pending)} hint={`امروز: ${fa(live.reports_today)}`} />
      <Kpi icon="🧱" label="بلاک‌ها" value={fa(live.blocks)} />
      <Kpi icon="📅" label="جلسه‌ی امروز" value={fa(live.sessions_today)} hint={`کل: ${fa(live.sessions_total)}`} />
      <div className="panel panel-pad" style={{ gridColumn: '1 / -1' }}>
        <div className="row" style={{ gap: 14, flexWrap: 'wrap' }}>
          <Stat label="حالت جدی" value={ov.settings?.serious_enabled ? '✅' : '⛔'} />
          <Stat label="حالت فان" value={ov.settings?.fun_enabled ? '✅' : '⛔'} />
          <Stat label="کمترین سن" value={fa(ov.settings?.min_age)} />
          <Stat label="سقف پیام/دقیقه" value={fa(ov.settings?.max_msg_per_min)} />
          <Stat label="ثبت محتوا" value={ov.settings?.evidence_mode} />
          <Stat label="به‌روزرسانی" value={<FaDateTime value={live.last_updated} />} />
        </div>
        <div className="row" style={{ gap: 8, marginTop: 10 }}>
          <button className="btn sm" disabled={busy} onClick={() => setForce({})}>🎯 force match</button>
          <button className="btn sm" disabled={busy} onClick={() => act(api.ringReconcile, 'ناهمانگی‌ها ترمیم شد')}>🧩 reconcile</button>
          <button className="btn sm" disabled={busy} onClick={() => act(api.ringPurge, 'شواهد منقضی پاک شد')}>🧹 پاک‌سازی شواهد</button>
          <button className="btn sm danger" disabled={busy}
            onClick={() => act(async () => { await api.ringFlag(false, 'hard'); }, 'رینگ با زور خاموش شد')}>
            🛑 خاموشی اضطراری</button>
        </div>
      </div>
    </div>}

    {(tab === 'queue' || tab === 'chats' || tab === 'reports' || tab === 'users' || tab === 'audit') && <>
      <div className="row" style={{ gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        {tab === 'users' && <input style={{ minWidth: 200 }} placeholder="جست‌وجو با آیدی تلگرام یا #ناشناس"
          value={q} onChange={e => { setQ(e.target.value); setPage(1); }} />}
        {tab === 'reports' && <select value={rStat} onChange={e => { setRStat(e.target.value); setPage(1); }}>
          <option value="pending">در انتظار</option><option value="reviewing">در حال بررسی</option>
          <option value="action_taken">اقدام شد</option><option value="resolved">حل‌شده</option>
          <option value="dismissed">رد‌شده</option><option value="">همه</option>
        </select>}
        {['users', 'reports'].includes(tab) && <Stat label="کل" value={fa(box.total)} />}
      </div>
      <DataTable columns={cols} rows={rows} rowKey={r => r.session_id || r.report_id || r._id || r.uid || r.user_id || Math.random()}
        loading={!box} onRow={tab === 'chats' ? (r => setDrawer({ kind: 'session', body: r })) : undefined}
        pager={{ page, pages: Math.max(1, Math.ceil((box.total || rows.length) / (box.size || 25))), total: fa(box.total || rows.length), onPage: setPage }} />
    </>}

    {tab === 'settings' && <SettingsPanel box={box} edit={edit} setEdit={setEdit} busy={busy}
      onSave={() => act(() => api.ringSaveSettings(edit), 'تنظیمات ذخیره شد')} />}

    {tab === 'analytics' && <AnalyticsPanel box={box} />}

    {confirmEnd && <Confirm text={`جلسه‌ی ${confirmEnd} بسته شود؟ هر دو طرف اطلاع می‌گیرند.`}
      onYes={() => { act(() => api.ringEndSession(confirmEnd, 'admin_panel'), 'جلسه بسته شد'); setConfirmEnd(null); }}
      onNo={() => setConfirmEnd(null)} danger />}

    {force && <ForceMatch busy={busy} onClose={() => setForce(null)}
      onSubmit={(a, b) => act(() => api.ringForceMatch(a, b), 'match دستی ساخته شد')} />}

    {drawer && <Modal title={drawer.kind === 'report' ? `گزارش R${fa(drawer.body.report?.report_id)}`
                    : drawer.kind === 'profile' ? `پرونده‌ی ${fa(drawer.body.profile?._id)}` : 'جلسه'}
      onClose={() => setDrawer(null)} wide>
      <ReportDrawerBody drawer={drawer} busy={busy}
        onReview={a => act(() => api.ringReview(drawer.body.report.report_id, a, ''), `اقدام «${a}» ثبت شد`)}
        onBan={uid => act(() => api.ringBan({ user_id: uid, kind: 'temporary', hours: 24, reason: 'report' }), '۲۴ ساعت بن شد')}
        onLift={uid => act(() => api.ringUnban(uid), 'محدودیت برداشته شد')}
        onPause={uid => act(() => api.ringPause(uid), 'کاربر به مکث رفت')}
        onResume={uid => act(() => api.ringResume(uid), 'کاربر برگشت')}
        onEnd={sid => act(() => api.ringEndSession(sid, 'admin_panel'), 'جلسه بسته شد')} />
    </Modal>}
  </>;
}

function SettingsPanel({ box, edit, setEdit, onSave, busy }) {
  const settings = box.settings || {};
  const labels = box.labels || {};
  const draft = edit || {};
  const val = k => (k in draft ? draft[k] : settings[k]);
  const set = (k, v) => setEdit({ ...(edit || {}), [k]: v });
  const keys = Object.keys(labels);
  const isNum = v => typeof v === 'number';
  return <div className="panel panel-pad">
    <SectionHeader title="تنظیمات رینگ استریت" description="هر تغییر بلافاصله در دیتابیس نوشته می‌شود و ربات آن را تا چند ثانیه بعد می‌خواند." />
    <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))' }}>
      {keys.map(k => <Field key={k} label={labels[k]}>
        {typeof val(k) === 'boolean'
          ? <Switch on={!!val(k)} onChange={v => set(k, v)} />
          : isNum(val(k))
            ? <input type="number" value={val(k)} onChange={e => set(k, Number(e.target.value))} />
            : ['report_only', 'all', 'off'].includes(val(k))
              ? <select value={val(k)} onChange={e => set(k, e.target.value)}>
                <option value="report_only">فقط هنگام گزارش</option>
                <option value="all">همه (برای تست)</option>
                <option value="off">هیچ</option>
              </select>
              : <input value={val(k) ?? ''} onChange={e => set(k, e.target.value)} />}
      </Field>)}
    </div>
    <div className="row" style={{ gap: 8, marginTop: 10 }}>
      <button className="btn" disabled={busy || !Object.keys(draft).length} onClick={onSave}>
        💾 ذخیره‌ی {fa(Object.keys(draft).length)} تغییر</button>
      {Object.keys(draft).length > 0 && <button className="btn ghost sm" onClick={() => setEdit(null)}>لغو</button>}
    </div>
  </div>;
}

function AnalyticsPanel({ box }) {
  const f = box.funnel || {}, m = box.modes || {}, mo = box.moderation || {};
  const pct = x => `${fa(Math.round((x || 0) * 100))}٪`;
  return <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))' }}>
    <div className="panel panel-pad">
      <SectionHeader title="قیف (§۳۶)" description="پروفایل ← صف ← match ← گفت‌وگو" />
      <Stat label="پروفایل‌ها" value={fa(f.profiles)} />
      <Stat label="ورود به صف" value={fa(f.joins)} />
      <Stat label="matchها" value={fa(f.matches)} />
      <Stat label="نرخ match" value={pct(f.match_rate)} />
      <Stat label="میانگین انتظار" value={`${fa(Math.round(f.avg_wait_s || 0))} ثانیه`} />
      <Stat label="میانگین طول گفت‌وگو" value={`${fa(Math.round(f.avg_session_s || 0))} ثانیه`} />
      <Stat label="پیام به ازای match" value={fa(f.msgs_per_match)} />
    </div>
    <div className="panel panel-pad">
      <SectionHeader title="حالت‌ها" description="تقسیم جدی/فان" />
      {Object.keys(m).length === 0 && <Empty icon="📭" text="داده‌ای نیست" />}
      {Object.entries(m).map(([k, v]) => <div key={k} style={{ marginBottom: 8 }}>
        <b>{MODE[k] || k}</b>
        <div className="muted">جلسه: {fa(v.sessions)} · پیام: {fa(v.messages)} · مدت: {fa(v.avg_duration_s)}s</div>
      </div>)}
    </div>
    <div className="panel panel-pad">
      <SectionHeader title="مدیریت ریسک" description="گزارش‌ها، تکراری‌ها و بن‌ها" />
      <Stat label="گزارش‌ها" value={fa(mo.total)} />
      <Stat label="تکراری" value={pct(mo.dup_share)} />
      <Stat label="بن‌ها" value={fa(mo.bans)} />
      <div style={{ marginTop: 8 }}>{Object.entries(mo.by_reason || {}).map(([k, v]) =>
        <div key={k} className="muted">{k}: {fa(v.n)}</div>)}</div>
    </div>
    <div className="panel panel-pad">
      <SectionHeader title="موضوع‌های داغ" description="ترجیحات ثبت‌شده در پروفایل‌ها" />
      {(box.topics || []).length === 0 && <Empty icon="🏷" text="موضوعی ثبت نشده" />}
      {(box.topics || []).map(t => <div key={t.topic} className="row" style={{ justifyContent: 'space-between' }}>
        <span>{t.topic}</span><B kind="acc">{fa(t.users)}</B></div>)}
    </div>
  </div>;
}

function ReportDrawerBody({ drawer, busy, onReview, onBan, onLift, onPause, onResume, onEnd }) {
  if (drawer.kind === 'session') {
    const s = drawer.body || {};
    return <div style={{ padding: 4 }}>
      <Stat label="حالت" value={MODE[s.mode] || s.mode} />
      <Stat label="پیام‌ها" value={fa(s.messages_count)} />
      <Stat label="مدیا" value={fa(s.media_count)} />
      <Stat label="شروع" value={<FaDateTime value={s.created_at} />} />
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button className="btn sm danger" disabled={busy} onClick={() => onEnd(s.session_id)}>⛔ بستن جلسه</button>
      </div>
    </div>;
  }
  if (drawer.kind === 'profile') {
    const p = drawer.body.profile || {}, ban = drawer.body.ban;
    return <div style={{ padding: 4 }}>
      <Stat label="ناشناس" value={`#${p.anon_id || '—'}`} />
      <Stat label="حالت" value={MODE[p.mode] || '—'} />
      <Stat label="امتیاز گزارش" value={fa(p.report_score)} />
      <Stat label="هشدارها" value={fa(p.warnings)} />
      <Stat label="جلسه‌ها" value={fa(drawer.body.sessions?.length)} />
      <Stat label="میانگین امتیاز" value={drawer.body.rating?.avg ?? '—'} />
      {ban && <B kind="bad">بن فعال تا {ban.until || 'همیشه'}</B>}
      <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
        <button className="btn sm" disabled={busy} onClick={() => onPause(p._id)}>⏸ مکث</button>
        <button className="btn sm" disabled={busy} onClick={() => onResume(p._id)}>▶️ بازگشت</button>
        <button className="btn sm danger" disabled={busy} onClick={() => onBan(p._id)}>🚫 بن ۲۴ ساعته</button>
        <button className="btn sm" disabled={busy} onClick={() => onLift(p._id)}>✅ برداشتن محدودیت</button>
      </div>
    </div>;
  }
  const r = drawer.body.report || {}, ev = drawer.body.evidence || [];
  return <div style={{ padding: 4 }}>
    <Stat label="دلیل" value={r.reason} />
    <Stat label="شدت" value={fa(r.severity)} />
    <Stat label="وضعیت" value={r.status} />
    <Stat label="توضیح" value={r.details || '—'} />
    <Stat label="شواهد" value={fa(ev.length)} />
    {ev.length > 0 && <div className="panel" style={{ marginTop: 8, padding: 8 }}>
      {ev.map(e => <div key={e._id} className="muted" style={{ marginBottom: 4 }}>
        <span className="code">{e.alias}</span> · {e.kind} · {e.text ? `«${e.text}»` : '(بدون متن)'}
      </div>)}
    </div>}
    <div className="row" style={{ gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
      {['review', 'resolve', 'dismiss', 'warn', 'temp_ban', 'perm_ban'].map(a =>
        <button key={a} className={`btn sm ${a.includes('ban') ? 'danger' : ''}`} disabled={busy}
          onClick={() => onReview(a)}>{a}</button>)}
    </div>
  </div>;
}

function ForceMatch({ busy, onClose, onSubmit }) {
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  return <Modal title="🎯 force match" onClose={onClose}>
    <div style={{ padding: 8, display: 'grid', gap: 8 }}>
      <Field label="آیدی تلگرام کاربر A"><input value={a} onChange={e => setA(e.target.value)} /></Field>
      <Field label="آیدی تلگرام کاربر B" hint="هر دو باید ۱۸+ و بدون بلاک متقابل باشند."><input value={b} onChange={e => setB(e.target.value)} /></Field>
      <div className="row" style={{ gap: 8 }}>
        <button className="btn" disabled={busy || !a || !b} onClick={() => { onSubmit(Number(a), Number(b)); onClose(); }}>ساخت جلسه</button>
        <button className="btn ghost sm" onClick={onClose}>انصراف</button>
      </div>
    </div>
  </Modal>;
}
