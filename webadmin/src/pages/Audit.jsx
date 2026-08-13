import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, B, Drawer } from '../ui.jsx';

// 🧭 لاگ حسابرسی — فیلتر دسته/شدت/جست‌وجو + جزئیات
const SEV = { INFO: '', WARNING: 'warn', HIGH: 'bad', CRITICAL: 'bad' };

export default function Audit() {
  const [filters, setFilters] = useState({ category: '', min_severity: '', q: '' });
  const [q2, setQ2] = useState('');
  const [skip, setSkip] = useState(0);
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState('');
  const [detail, setDetail] = useState(null);
  const LIMIT = 25;

  useEffect(() => { const t = setTimeout(() => setFilters(f => ({ ...f, q: q2 })), 350); return () => clearTimeout(t); }, [q2]);

  const load = async () => {
    setErr('');
    try {
      const r = await api.auditLogs({ ...filters, skip, limit: LIMIT });
      setRows(r.logs || r.items || []);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [filters, skip]);

  if (err) return <ErrorState error={err} onRetry={load} />;

  const SEv_RANK = { INFO: 0, WARNING: 1, HIGH: 2, CRITICAL: 3 };
  const cols = [
    { k: 'at', label: 'زمان', sortable: true, sortVal: r => r.at || r.created_at || '',
      render: r => <span className="muted">{(r.at || r.created_at || '').replace('T', ' ').slice(5, 16)}</span> },
    { k: 'actor', label: 'عامل', render: r => (
      <div>{r.actor_name || r.actor_id}<div className="muted">{r.actor_role || ''}</div></div>) },
    { k: 'action', label: 'عمل', render: r => <b style={{ color: 'var(--txt)' }}>{r.action}</b> },
    { k: 'module', label: 'ماژول', render: r => <B>{r.module || '—'}</B> },
    { k: 'target', label: 'هدف', render: r => <span className="muted">{r.target_label || r.target_id || '—'}</span> },
    { k: 'severity', label: 'شدت', sortable: true, sortVal: r => SEv_RANK[r.severity] ?? 0,
      render: r => <B kind={SEV[r.severity] || ''}>{r.severity || 'INFO'}</B> },
  ];

  return (
    <>
      <div className="h1">لاگ حسابرسی</div>
      <div className="sub">ردیابی کامل اعمال حساس — عامل، هدف، شدت، همبستگی</div>
      <div className="panel panel-pad row" style={{ marginBottom: 12 }}>
        <input className="inp" style={{ flex: 1, minWidth: 200 }} placeholder="🔎 جست‌وجو در عمل/هدف…"
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
      </div>
      {!rows ? <Loading /> : (
        <>
          <DataTable columns={cols} rows={rows} rowKey={(r) => r.id || r._id || Math.random()}
                     onRow={setDetail} colToggle
                     pager={{ page: skip / LIMIT + 1, pages: rows.length < LIMIT ? skip / LIMIT + 1 : 99,
                              total: '', onPage: p => setSkip((p - 1) * LIMIT) }} />
        </>
      )}
      {detail && (
        <Drawer title="جزئیات رویداد" onClose={() => setDetail(null)} wide>
          <dl className="kv">
            {Object.entries({
              'زمان': detail.at || detail.created_at, 'عامل': `${detail.actor_name || ''} (${detail.actor_id || ''})`,
              'نقش': detail.actor_role, 'عمل': detail.action, 'ماژول': detail.module,
              'هدف': `${detail.target_label || ''} ${detail.target_id || ''}`,
              'نوع هدف': detail.target_type, 'شدت': detail.severity, 'دسته': detail.category,
              'جزئیات': detail.details, 'Correlation': detail.correlation_id,
              'تگ‌ها': (detail.tags || []).join('، '),
            }).filter(([, v]) => v).map(([k, v]) => (
              <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
            ))}
          </dl>
        </Drawer>
      )}
    </>
  );
}
