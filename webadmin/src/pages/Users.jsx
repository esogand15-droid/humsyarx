import React, { useEffect, useMemo, useState } from 'react';
import { api, errText, exportCSV } from '../api.js';
import { DataTable, Drawer, Loading, ErrorState, B, toast, Confirm, Modal } from '../ui.jsx';

const STATUS = { '': 'همه', pending: 'در انتظار تأیید', suspended: 'تعلیق‌شده', active: 'فعال' };

// 👥 WA2.4/2.8 — فیلتر ذخیره‌شده + bulk گسترده (تغییر ورودی/CSV) + دراور ۳۶۰ کاربر
export default function Users({ go }) {
  const [q, setQ] = useState('');
  const [q2, setQ2] = useState(new URLSearchParams(location.hash.split('?')[1] || '').get('q') || '');
  const [status, setStatus] = useState(new URLSearchParams(location.hash.split('?')[1] || '').get('status') || '');
  const [intake, setIntake] = useState('');
  const [intakes, setIntakes] = useState([]);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [data, setData] = useState({ users: [], total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [sel, setSel] = useState([]);
  const [detail, setDetail] = useState(null);       // row کاربر
  const [confirm, setConfirm] = useState(null);
  const [intakeModal, setIntakeModal] = useState(false);
  const [intakeVal, setIntakeVal] = useState('');
  const [filters, setFilters] = useState(null);
  const [saveModal, setSaveModal] = useState(false);
  const [filterName, setFilterName] = useState('');

  useEffect(() => { api.intakes().then(r => setIntakes(r.intakes || [])).catch(() => {}); }, []);
  useEffect(() => { api.savedFilters('users').then(r => setFilters(r.filters || [])).catch(() => setFilters([])); }, []);
  useEffect(() => { const t = setTimeout(() => setQ(q2), 350); return () => clearTimeout(t); }, [q2]);

  const load = async () => {
    setLoading(true); setErr('');
    try {
      setData(await api.users({ page, per_page: perPage, q, intake, status }));
    } catch (e) { setErr(errText(e)); }
    setLoading(false);
  };
  useEffect(() => { load(); }, [page, perPage, q, intake, status]);
  useEffect(() => { setSel([]); }, [page, q, intake, status]);

  const bulk = async (action, value) => {
    if (!sel.length) return toast('ابتدا کاربران را انتخاب کنید', 'err');
    try {
      const r = await api.usersBulk(action, sel, value);
      toast(`${r.done} کاربر به‌روزرسانی شد`);
      setSel([]); load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  const applyFilter = (f) => {
    const flt = f.filters || {};
    setQ2(flt.q || ''); setQ(flt.q || '');
    setStatus(flt.status || ''); setIntake(flt.intake || ''); setPage(1);
    toast(`فیلتر «${f.name}» اعمال شد ⏱`);
  };
  const saveFilter = async () => {
    if (!filterName.trim()) return;
    try {
      await api.saveFilter({ name: filterName.trim(), scope: 'users',
        filters: { q, status, intake } });
      toast('فیلتر ذخیره شد ✅'); setSaveModal(false); setFilterName('');
      setFilters((await api.savedFilters('users')).filters || []);
    } catch (e) { toast(errText(e), 'err'); }
  };
  const removeFilter = async (id) => {
    try { await api.delFilter(id); setFilters((await api.savedFilters('users')).filters || []); }
    catch (e) { toast(errText(e), 'err'); }
  };

  const exportSel = () => {
    const rows = (data.users || []).filter(u => sel.includes(u.id));
    exportCSV(`users-${Date.now()}.csv`, [
      { label: 'id', v: 'id' }, { label: 'name', v: 'name' },
      { label: 'student_id', v: 'student_id' }, { label: 'intake', v: 'intake' },
      { label: 'group', v: 'group' },
      { label: 'status', v: r => r.suspended ? 'suspended' : r.approved ? 'active' : 'pending' },
    ], rows);
    toast(`خروجی ${rows.length} کاربر دانلود شد 📥`);
  };

  const cols = [
    { k: 'display_name', label: 'نام', render: r => (
      <div><b style={{ color: 'var(--txt)' }}>{r.display_name || r.name}</b>
      <div className="muted">@{r.username || '—'} · <span className="code">{r.id}</span></div></div>) },
    { k: 'student_id', label: 'شماره دانشجویی', render: r => <span className="code">{r.student_id || '—'}</span> },
    { k: 'intake', label: 'ورودی' },
    { k: 'group', label: 'گروه' },
    { k: 'total_answers', label: 'پاسخ‌ها', render: r => Number(r.total_answers || 0).toLocaleString('fa') },
    { k: 'rank', label: 'رنک', render: r => r.rank ? <B kind="purple">{r.rank}</B> : '—' },
    { k: 'st', label: 'وضعیت', render: r => r.suspended
      ? <B kind="bad">تعلیق</B> : r.approved ? <B kind="ok">فعال</B> : <B kind="warn">در انتظار</B> },
    { k: 'ops', label: '', stop: true, render: r => (
      <div className="row" style={{ gap: 4 }}>
        {!r.approved && !r.suspended && <button className="btn sm ok" onClick={() => act(r.id, 'approve')}>✅</button>}
        {r.suspended
          ? <button className="btn sm ok" title="رفع تعلیق" onClick={() => act(r.id, 'suspend')}>🔓</button>
          : <button className="btn sm danger" onClick={() => act(r.id, 'suspend')}>⏸</button>}
      </div>) },
  ];

  const act = async (uid, action) => {
    try { await api.userAction(uid, action); toast('انجام شد'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  if (err) return <ErrorState error={err} onRetry={load} />;

  return (
    <>
      <div className="row">
        <div><div className="h1">مدیریت کاربران</div>
          <div className="sub">جست‌وجو، فیلتر ذخیره‌شده، pagination سرورساید و اکشن گروهی</div></div>
        <span className="spacer" />
        {sel.length > 0 && <>
          <span className="badge acc">{sel.length} انتخاب‌شده</span>
          <button className="btn sm ok" onClick={() => setConfirm({ action: 'approve', text: `تأیید ${sel.length} کاربر؟` })}>✅ تأیید</button>
          <button className="btn sm danger" onClick={() => setConfirm({ action: 'suspend', text: `تعلیق ${sel.length} کاربر؟` })}>⏸ تعلیق</button>
          <button className="btn sm" onClick={() => setConfirm({ action: 'unsuspend', text: `رفع تعلیق ${sel.length} کاربر؟` })}>🔓 رفع تعلیق</button>
          <button className="btn sm" onClick={() => { setIntakeVal(''); setIntakeModal(true); }}>🏷 تغییر ورودی</button>
          <button className="btn sm" onClick={exportSel}>📥 CSV</button>
        </>}
      </div>

      <div className="panel panel-pad row" style={{ marginBottom: 12 }}>
        <input className="inp" style={{ flex: 1, minWidth: 200 }} placeholder="🔎 نام، شماره دانشجویی، آیدی…"
               value={q2} onChange={e => { setQ2(e.target.value); setPage(1); }} />
        <select className="inp" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="inp" value={intake} onChange={e => { setIntake(e.target.value); setPage(1); }}>
          <option value="">همه‌ی ورودی‌ها</option>
          {intakes.map(i => <option key={i.code || i} value={i.code || i}>{i.label || i.code || i}</option>)}
        </select>
        <select className="inp" value={perPage} onChange={e => { setPerPage(+e.target.value); setPage(1); }}>
          {[10, 25, 50, 100].map(n => <option key={n} value={n}>{n} در صفحه</option>)}
        </select>
        <button className="btn sm" title="ذخیره‌ی فیلتر فعلی" onClick={() => setSaveModal(true)}>💾 ذخیره فیلتر</button>
      </div>

      {/* ⏱ WA2.4 — فیلترهای ذخیره‌شده */}
      {filters && filters.length > 0 && (
        <div className="row" style={{ marginBottom: 12, gap: 6 }}>
          <span className="muted">⏱ فیلترهای ذخیره:</span>
          {filters.map(f => (
            <span key={f.id} className="chip">
              <a onClick={() => applyFilter(f)}>{f.name}</a>
              <button className="chip-x" onClick={() => removeFilter(f.id)}>✕</button>
            </span>
          ))}
        </div>
      )}

      <DataTable columns={cols} rows={data.users} selectable onSelect={setSel}
                 loading={loading} onRow={r => setDetail(r)}
                 pager={{ page, pages: data.pages, total: data.total, onPage: setPage }} />

      {detail && <UserDrawer row={detail} go={go} onClose={() => { setDetail(null); load(); }} />}
      {confirm && (
        <Confirm text={confirm.text} danger={confirm.action === 'suspend'}
                 onYes={async () => { await bulk(confirm.action); setConfirm(null); }}
                 onNo={() => setConfirm(null)} />
      )}
      {intakeModal && (
        <Modal title={`🏷 تغییر ورودی ${sel.length} کاربر`} onClose={() => setIntakeModal(false)}>
          <select className="inp" style={{ width: '100%' }} value={intakeVal} onChange={e => setIntakeVal(e.target.value)}>
            <option value="">(بدون ورودی)</option>
            {intakes.map(i => <option key={i.code || i} value={i.code || i}>{i.label || i.code || i}</option>)}
          </select>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" onClick={async () => { setIntakeModal(false); await bulk('set_intake', intakeVal); }}>اعمال</button>
            <button className="btn" onClick={() => setIntakeModal(false)}>انصراف</button>
          </div>
        </Modal>
      )}
      {saveModal && (
        <Modal title="💾 ذخیره‌ی فیلتر فعلی" onClose={() => setSaveModal(false)}>
          <p className="muted" style={{ marginBottom: 10 }}>
            وضعیت فعلی: {q ? `جست‌وجو: «${q}» · ` : ''}{STATUS[status] || 'همه'}{intake ? ` · ورودی: ${intake}` : ''}
          </p>
          <input className="inp" style={{ width: '100%' }} placeholder="نام فیلتر (مثلاً: دانشجویان بهمن در انتظار)…"
                 value={filterName} onChange={e => setFilterName(e.target.value)} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={!filterName.trim()} onClick={saveFilter}>ذخیره</button>
            <button className="btn" onClick={() => setSaveModal(false)}>انصراف</button>
          </div>
        </Modal>
      )}
    </>
  );
}

/* ── 👤 WA2.8 — User 360: کانتکست کامل بدون ترک صفحه ─────────── */
function UserDrawer({ row, go, onClose }) {
  const [d, setD] = useState(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState('overview');
  useEffect(() => {
    let on = true;
    api.user360(row.id)
      .then(r => on && setD(r))
      .catch(() => on && setFailed(true));
    return () => { on = false; };
  }, [row.id]);

  const TABS = [['overview', '👤 نمای کلی'], ['sub', '💎 اشتراک'], ['tickets', '🎫 تیکت‌ها'], ['audit', '🧭 رویدادها']];

  return (
    <Drawer wide title={`👤 ${row.display_name || row.name} · #${row.id}`} onClose={onClose}>
      <div className="tabs" style={{ marginBottom: 10 }}>
        {TABS.map(([k, v]) => (
          <button key={k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{v}</button>
        ))}
      </div>
      {failed && (
        <dl className="kv">
          {Object.entries({
            'نام': row.name, 'یوزرنیم': row.username && '@' + row.username,
            'شماره دانشجویی': row.student_id, 'ورودی': row.intake, 'گروه': row.group,
          }).filter(([, v]) => v).map(([k, v]) => (
            <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
          ))}
        </dl>
      )}
      {!failed && !d && <Loading />}
      {d && tab === 'overview' && (
        <>
          <dl className="kv">
            {Object.entries({
              'نام': d.user.name, 'نام‌نما': d.user.nickname,
              'یوزرنیم': d.user.username && '@' + d.user.username,
              'شماره دانشجویی': d.user.student_id, 'ورودی': d.user.intake,
              'گروه': d.user.group, 'نقش': d.user.role,
              'وضعیت': d.user.suspended ? 'تعلیق‌شده' : d.user.approved ? 'فعال' : 'در انتظار',
              'ثبت‌نام': d.user.registered_at,
              'پاسخ‌ها': Number(d.user.total_answers || 0).toLocaleString('fa'),
              'رنک': [d.user.prestige_rank, d.user.prestige_div].filter(Boolean).join(' / '),
            }).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => (
              <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
            ))}
          </dl>
          {d.admin_role && (
            <div className="panel panel-pad" style={{ marginTop: 8, background: 'var(--bg)' }}>
              <b>🛡 نقش مدیریتی</b>
              <div style={{ marginTop: 6 }}>{d.admin_role.role}
                {d.admin_role.scope ? <B kind="purple">scope: {d.admin_role.scope}</B> : null}</div>
            </div>
          )}
          {!!(d.perms || []).length && (
            <div className="row" style={{ marginTop: 10, gap: 4 }}>
              {(d.perms || []).slice(0, 10).map(p => <B key={p} kind="acc">{p}</B>)}
              {d.perms.length > 10 && <B>+{d.perms.length - 10}</B>}
            </div>
          )}
        </>
      )}
      {d && tab === 'sub' && (
        d.subscription ? (
          <dl className="kv">
            <dt>وضعیت</dt><dd>{d.subscription.status === 'active' ? '✅ فعال' : d.subscription.status || '—'}</dd>
            <dt>پلن</dt><dd>{d.subscription.plan || '—'}</dd>
            <dt>پایان</dt><dd>{d.subscription.end_date || '—'}</dd>
            <dt>روزهای باقی</dt><dd>{d.subscription.days_left ?? '—'}</dd>
          </dl>
        ) : <div className="center-state">اشتراک فعالی ندارد</div>
      )}
      {d && tab === 'tickets' && (
        <>
          <div className="muted" style={{ marginBottom: 8 }}>مجموع: {Number(d.counts.tickets || 0).toLocaleString('fa')} تیکت</div>
          {(d.recent_tickets || []).length === 0 && <div className="center-state">تیکتی نیست</div>}
          {(d.recent_tickets || []).map(t => (
            <div key={t.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line)', cursor: 'pointer' }}
                 onClick={() => go('/tickets')}>
              <span>🎫</span>
              <span style={{ flex: 1 }}>{t.subject}</span>
              <B kind={t.status === 'open' ? 'bad' : t.status === 'answered' ? 'warn' : 'ok'}>
                {t.status === 'open' ? 'باز' : t.status === 'answered' ? 'پاسخ' : 'بسته'}</B>
              <span className="muted">{t.at}</span>
            </div>
          ))}
        </>
      )}
      {d && tab === 'audit' && (
        <>
          {(d.recent_audit || []).length === 0 && <div className="center-state">رویدادی ثبت نشده</div>}
          {(d.recent_audit || []).map((l, i) => (
            <div key={i} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
              <span className={`sev ${(l.severity || '').toLowerCase()}`} />
              <span style={{ flex: 1 }}>{l.action}</span>
              <B>{l.module}</B>
              <span className="muted">{l.at}</span>
            </div>
          ))}
        </>
      )}
    </Drawer>
  );
}
