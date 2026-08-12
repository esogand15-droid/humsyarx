import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Drawer, Loading, ErrorState, B, toast, Confirm } from '../ui.jsx';

const STATUS = { '': 'همه', pending: 'در انتظار تأیید', suspended: 'تعلیق‌شده', active: 'فعال' };

export default function Users({ go }) {
  const [q, setQ] = useState('');
  const [q2, setQ2] = useState('');
  const [status, setStatus] = useState(new URLSearchParams(location.hash.split('?')[1] || '').get('status') || '');
  const [intake, setIntake] = useState('');
  const [intakes, setIntakes] = useState([]);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [data, setData] = useState({ users: [], total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [sel, setSel] = useState([]);
  const [detail, setDetail] = useState(null);
  const [confirm, setConfirm] = useState(null);

  useEffect(() => { api.intakes().then(r => setIntakes(r.intakes || [])).catch(() => {}); }, []);
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

  const bulk = async (action) => {
    if (!sel.length) return toast('ابتدا کاربران را انتخاب کنید', 'err');
    try {
      const r = await api.usersBulk(action, sel);
      toast(`${r.done} کاربر به‌روزرسانی شد`);
      setSel([]); load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  const cols = [
    { k: 'sel2', label: '', width: 30 },
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
          ? <button className="btn sm ok" onClick={() => act(r.id, 'unblock' in r ? 'unblock' : 'suspend')}>🔓</button>
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
          <div className="sub">جست‌وجو، فیلتر، pagination سرورساید و اکشن گروهی</div></div>
        <span className="spacer" />
        {sel.length > 0 && <>
          <span className="badge acc">{sel.length} انتخاب‌شده</span>
          <button className="btn sm ok" onClick={() => setConfirm({ action: 'approve', text: `تأیید ${sel.length} کاربر؟` })}>✅ تأیید گروهی</button>
          <button className="btn sm danger" onClick={() => setConfirm({ action: 'suspend', text: `تعلیق ${sel.length} کاربر؟` })}>⏸ تعلیق گروهی</button>
          <button className="btn sm" onClick={() => setConfirm({ action: 'unsuspend', text: `رفع تعلیق ${sel.length} کاربر؟` })}>🔓 رفع تعلیق</button>
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
      </div>

      <DataTable columns={cols.slice(1)} rows={data.users} selectable onSelect={setSel}
                 loading={loading} onRow={r => openDetail(r.id, setDetail)}
                 pager={{ page, pages: data.pages, total: data.total, onPage: setPage }} />

      {detail && <UserDrawer uid={detail} onClose={() => { setDetail(null); load(); }} />}
      {confirm && (
        <Confirm text={confirm.text} danger={confirm.action === 'suspend'}
                 onYes={async () => { await bulk(confirm.action); setConfirm(null); }}
                 onNo={() => setConfirm(null)} />
      )}
    </>
  );
}

async function openDetail(uid, setDetail) { setDetail(uid); }

function UserDrawer({ uid, onClose }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    let on = true;
    api.userDetail(uid).then(r => on && setD(r.user || r)).catch(() => on && setD({ error: true }));
    return () => { on = false; };
  }, [uid]);
  return (
    <Drawer title={`کاربر #${uid}`} onClose={onClose}>
      {!d && <Loading />}
      {d && d.error && <ErrorState error="خطا در دریافت جزئیات" />}
      {d && !d.error && (
        <dl className="kv">
          {Object.entries({
            'نام': d.name, 'نام‌نما': d.nickname, 'یوزرنیم': d.username && '@' + d.username,
            'شماره دانشجویی': d.student_id, 'ورودی': d.intake, 'گروه': d.group,
            'نقش': d.role, 'وضعیت': d.suspended ? 'تعلیق‌شده' : d.approved ? 'فعال' : 'در انتظار',
            'ثبت‌نام': d.registered_at, 'اشتراک': d.subscription || undefined,
          }).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => (
            <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
          ))}
        </dl>
      )}
    </Drawer>
  );
}
