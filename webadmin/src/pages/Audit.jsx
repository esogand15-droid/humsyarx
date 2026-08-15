import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, B, FilterBar, PageHeader, Drawer, NoPerm, Empty } from '../ui.jsx';
import SavedViews from '../SavedViews.jsx';

const fa = (n) => Number(n ?? 0).toLocaleString('fa-IR');

// 🧭 لاگ حسابرسی + 🌊 موج Audit-Diff: کشوی «قبل/بعد» برای رویدادهای دارای
// changes (db.log_action از همیشه آن‌ها را ذخیره می‌کرد؛ حالا پنل وب هم
// می‌نویسد و هم اینجا به‌صورت بصری نمایش می‌دهد). FIX: متادیتای تو در تو
// (actor/target/timestamp) — قبلاً فیلدهای تخت خوانده می‌شد و خالی می‌ماند.
const SEV = { INFO: '', WARNING: 'warn', HIGH: 'bad', CRITICAL: 'bad' };
const SEV_RANK = { INFO: 0, WARNING: 1, HIGH: 2, CRITICAL: 3 };
const SEV_ICON = { INFO: 'ℹ️', WARNING: '⚠️', HIGH: '🔥', CRITICAL: '⛔' };
const MOD_FA = {
  Users: 'کاربران', Roles: 'نقش‌ها', Settings: 'تنظیمات', Questions: 'سوالات',
  Content: 'محتوا', Schedules: 'برنامه کلاسی', Tickets: 'تیکت‌ها', Reports: 'گزارش‌ها',
  Notifications: 'اعلان‌ها', Backup: 'بکاپ', System: 'سیستم', Auth: 'ورود/خروج',
  Subscription: 'اشتراک', Grades: 'نمرات', WebAdmin: 'پنل وب',
};
const CAT_FA = { admin: 'مدیریت', content: 'محتوا', user: 'کاربر' };

const actorName = (r) => r.actor?.name ?? r.actor_name ?? '—';
const actorRole = (r) => r.actor?.role ?? r.actor_role ?? '';
const actorId = (r) => r.actor?.id ?? r.actor_id ?? '';
const targetLabel = (r) => r.target?.label ?? r.target_label ?? '';
const targetId = (r) => r.target?.id ?? r.target_id ?? '';
const targetType = (r) => r.target?.type ?? r.target_type ?? '';
const atOf = (r) => r.timestamp ?? r.at ?? r.created_at ?? '';

const valText = (v) => {
  if (v === null || v === undefined) return '—';
  if (v === true) return 'فعال';
  if (v === false) return 'غیرفعال';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v) === '' ? '(خالی)' : String(v);
};

export default function Audit() {
  const [filters, setFilters] = useState({ category: '', min_severity: '', q: '', actor: '', actor_role: '', module: '', action: '', target_type: '', target: '', date_from: '', date_to: '', correlation_id: '' });
  const [q2, setQ2] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [skip, setSkip] = useState(0);
  const [rows, setRows] = useState(null);
  const [counters, setCounters] = useState(null);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState('');
  const [denied, setDenied] = useState(false);
  const [detail, setDetail] = useState(null);
  const LIMIT = 25;

  useEffect(() => { const t = setTimeout(() => setFilters(f => ({ ...f, q: q2 })), 350); return () => clearTimeout(t); }, [q2]);

  const load = async () => {
    setErr('');
    try {
      const r = await api.auditLogs({ ...filters, skip, limit: LIMIT });
      setRows(r.logs || r.items || []);
      setCounters(r.counters || null);
      setTotal(r.total || 0);
    } catch (e) {
      if (e.status === 403) setDenied(true);
      else setErr(errText(e));
    }
  };
  useEffect(() => { load(); }, [filters, skip]);

  if (denied) return <NoPerm text="مشاهده‌ی لاگ حسابرسی نیازمند مجوز audit.view است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const setSev = (s) => { setFilters(f => ({ ...f, min_severity: f.min_severity === s ? '' : s })); setSkip(0); };

  const cols = [
    { k: 'at', label: 'زمان', sortable: true, sortVal: r => atOf(r),
      render: r => <span className="muted">{atOf(r).replace('T', ' ').slice(5, 16)}</span> },
    { k: 'actor', label: 'عامل', render: r => (
      <div>{actorName(r)}<div className="muted">{actorRole(r)}</div></div>) },
    { k: 'action', label: 'عمل', render: r => <b style={{ color: 'var(--txt)' }}>{r.action}</b> },
    { k: 'module', label: 'ماژول', render: r => <B>{MOD_FA[r.module] || r.module || '—'}</B> },
    { k: 'target', label: 'هدف', render: r => <span className="muted">{targetLabel(r) || targetId(r) || '—'}</span> },
    { k: 'diff', label: 'Δ', width: 46, render: r =>
      (r.changes || []).length > 0
        ? <B kind="acc" title={`${fa(r.changes.length)} تغییر میدانی`}>Δ {fa(r.changes.length)}</B>
        : <span className="muted">·</span> },
    { k: 'severity', label: 'شدت', sortable: true, sortVal: r => SEV_RANK[r.severity] ?? 0,
      render: r => <B kind={SEV[r.severity] || ''}>{SEV_ICON[r.severity] || ''} {r.severity || 'INFO'}</B> },
  ];

  return (
    <>
      <PageHeader title="لاگ حسابرسی" description="ردیابی اعمال حساس با عامل، هدف، شدت و تغییرات قبل/بعد"
        actions={rows ? <B>{fa(total)} رویداد</B> : null} />

      {/* شمارنده‌ی سطوح (کلیک ⇒ فیلتر سریع) */}
      {counters && (
        <div className="row" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 6 }}>
          {['INFO', 'WARNING', 'HIGH', 'CRITICAL'].map(s => (
            <button key={s}
                    className={`btn sm ${filters.min_severity === s ? 'primary' : ''}`}
                    onClick={() => setSev(s)}>
              {SEV_ICON[s]} {s} <span className="num">{fa(counters[s] || 0)}</span>
            </button>
          ))}
        </div>
      )}

      <FilterBar>
        <input className="inp" style={{ flex: 1, minWidth: 200 }} placeholder="🔎 جست‌وجو در عمل/عامل/هدف…"
               value={q2} onChange={e => { setQ2(e.target.value); setSkip(0); }} />
        <select className="inp" value={filters.category}
                onChange={e => { setFilters(f => ({ ...f, category: e.target.value })); setSkip(0); }}>
          <option value="">همه‌ی دسته‌ها</option>
          <option value="admin">مدیریت</option>
          <option value="content">محتوا</option>
          <option value="user">کاربر</option>
        </select>
        <select className="inp" value={filters.min_severity}
                onChange={e => { setFilters(f => ({ ...f, min_severity: e.target.value })); setSkip(0); }}>
          <option value="">همه‌ی شدت‌ها</option>
          <option value="WARNING">از WARNING</option>
          <option value="HIGH">از HIGH</option>
          <option value="CRITICAL">فقط CRITICAL</option>
        </select>
        <button className={`btn sm ${advanced ? 'primary' : ''}`} aria-expanded={advanced} onClick={() => setAdvanced(x => !x)}>⚙ بررسی پیشرفته</button>
      </FilterBar>
      {advanced && <FilterBar className="advanced-filter-bar">
        <input className="inp" placeholder="عامل یا Actor ID…" value={filters.actor} onChange={e => { setFilters(f => ({ ...f, actor: e.target.value })); setSkip(0); }} />
        <input className="inp" placeholder="نقش عامل…" value={filters.actor_role} onChange={e => { setFilters(f => ({ ...f, actor_role: e.target.value })); setSkip(0); }} />
        <select className="inp" value={filters.module} onChange={e => { setFilters(f => ({ ...f, module: e.target.value })); setSkip(0); }}>
          <option value="">همه ماژول‌ها</option>{Object.keys(MOD_FA).map(m => <option key={m} value={m}>{MOD_FA[m]}</option>)}
        </select>
        <input className="inp" placeholder="عمل مشخص…" value={filters.action} onChange={e => { setFilters(f => ({ ...f, action: e.target.value })); setSkip(0); }} />
        <input className="inp" placeholder="نوع هدف…" value={filters.target_type} onChange={e => { setFilters(f => ({ ...f, target_type: e.target.value })); setSkip(0); }} />
        <input className="inp" placeholder="هدف/شناسه…" value={filters.target} onChange={e => { setFilters(f => ({ ...f, target: e.target.value })); setSkip(0); }} />
        <label className="row"><span className="muted">از</span><input type="date" className="inp" value={filters.date_from} onChange={e => { setFilters(f => ({ ...f, date_from: e.target.value })); setSkip(0); }} /></label>
        <label className="row"><span className="muted">تا</span><input type="date" className="inp" value={filters.date_to} onChange={e => { setFilters(f => ({ ...f, date_to: e.target.value })); setSkip(0); }} /></label>
        <input className="inp code" placeholder="Correlation ID…" value={filters.correlation_id} onChange={e => { setFilters(f => ({ ...f, correlation_id: e.target.value })); setSkip(0); }} />
        <button className="btn sm" onClick={() => { setFilters(f => ({ ...f, actor: '', actor_role: '', module: '', action: '', target_type: '', target: '', date_from: '', date_to: '', correlation_id: '' })); setSkip(0); }}>پاک‌کردن پیشرفته</button>
      </FilterBar>}

      <SavedViews scope="audit" filters={filters} onApply={f => { setFilters(x => ({ ...x, ...f })); setQ2(f.q || ''); setAdvanced(!!(f.actor || f.actor_role || f.module || f.action || f.target || f.date_from || f.date_to || f.correlation_id)); setSkip(0); }} label="تحقیق‌های ذخیره‌شده" />

      {!rows ? <Loading /> : rows.length === 0 ? (
        <Empty icon="🧾" text="رویدادی با این فیلترها نیست" />
      ) : (
        <DataTable columns={cols} rows={rows} rowKey={(r) => r.id || r._id}
                   onRow={setDetail} colToggle
                   pager={{ page: skip / LIMIT + 1, pages: Math.max(1, Math.ceil(total / LIMIT)),
                            total, onPage: p => setSkip((p - 1) * LIMIT) }} />
      )}

      {detail && (
        <Drawer title="🔍 جزئیات و تغییرات رویداد" onClose={() => setDetail(null)} wide>
          <div className="row" style={{ flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            <b style={{ fontSize: 14 }}>{detail.action}</b>
            <B kind={SEV[detail.severity] || ''}>{SEV_ICON[detail.severity] || ''} {detail.severity || 'INFO'}</B>
            <B>{MOD_FA[detail.module] || detail.module || '—'}</B>
            {detail.category && <B kind="purple">{CAT_FA[detail.category] || detail.category}</B>}
          </div>

          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div className="ct3-kv"><span className="muted">زمان</span>
              <span className="num">{atOf(detail).replace('T', ' ').slice(0, 16) || '—'}</span></div>
            <div className="ct3-kv"><span className="muted">عامل</span>
              <span>{actorName(detail)} <span className="muted">{actorRole(detail)}</span>{' '}
                <span className="code">{actorId(detail)}</span></span></div>
            <div className="ct3-kv"><span className="muted">هدف</span>
              <span>{targetLabel(detail) || '—'} {targetType(detail) && <span className="muted">({targetType(detail)})</span>}</span></div>
            <div className="ct3-kv"><span className="muted">شناسه‌ی هدف</span>
              <span className="code" style={{ fontSize: 11 }}>{targetId(detail) || '—'}</span></div>
            <div className="ct3-kv"><span className="muted">Correlation ID</span>
              <span className="code" style={{ fontSize: 11 }}>{detail.correlation_id || '—'}</span></div>
          </div>

          {/* ── Diff قبل/بعد ── */}
          <div style={{ marginTop: 14 }}>
            <b>🧬 تغییرات میدانی</b>
            {(detail.changes || []).length === 0 ? (
              <p className="muted" style={{ marginTop: 8 }}>
                این رویداد تغییر میدانی (before/after) ندارد
                {detail.details ? '' : ' — جزئیات در متن عمل ثبت شده است.'}
              </p>
            ) : (
              <div className="diff-tbl" style={{ marginTop: 8 }}>
                <div className="diff-head">
                  <span>فیلد</span><span>قبل</span><span /><span>بعد</span>
                </div>
                {detail.changes.map((c, i) => {
                  const b = valText(c.before), a = valText(c.after);
                  return (
                    <div key={i} className="diff-row">
                      <span className="diff-f">{c.field}</span>
                      <span className={`diff-v b ${b === '—' ? 'none' : ''}`} title={b}>{b}</span>
                      <span className="diff-arrow">←</span>
                      <span className={`diff-v a ${a === '—' ? 'none' : ''}`} title={a}>{a}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {detail.details && (
            <div style={{ marginTop: 12 }}>
              <b>📝 جزئیات</b>
              <div className="panel panel-pad" style={{ background: 'var(--bg)', marginTop: 6, whiteSpace: 'pre-wrap', fontSize: 12.5 }}>
                {detail.details}
              </div>
            </div>
          )}
          {(detail.tags || []).length > 0 && (
            <div className="row" style={{ marginTop: 12, flexWrap: 'wrap', gap: 5 }}>
              {(detail.tags || []).map(t => <B key={t}>#{t}</B>)}
            </div>
          )}
          {detail.correlation_id && (
            <div className="muted" style={{ marginTop: 10, fontSize: 11 }}>
              Correlation: <span className="code">{detail.correlation_id}</span>
            </div>
          )}
        </Drawer>
      )}
    </>
  );
}
