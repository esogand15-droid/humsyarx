import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, errText, exportCSV } from '../api.js';
import { DataTable, Drawer, Loading, ErrorState, B, DiffViewer, FaDate, FaDateTime, RelativeTime, FilterBar, PageHeader, toast, Confirm, Modal, Empty, Switch } from '../ui.jsx';
import { queryNumber, readHashQuery, writeHashQuery } from '../urlState.js';
import SavedViews from '../SavedViews.jsx';
import SmartQueryBuilder from '../SmartQueryBuilder.jsx';
import { fileDateStamp } from '../time.js';

const STATUS = { '': 'همه', pending: 'در انتظار تأیید', suspended: 'تعلیق‌شده', active: 'فعال' };
const faNum = (n) => Number(n ?? 0).toLocaleString('fa-IR');
const USER360_STALE_MS = 60_000;
const USER360_CACHE_LIMIT = 20;

function mergeUserSnapshot(row, snapshot) {
  const user = snapshot?.user;
  if (!row || !user || Number(row.id) !== Number(user.id)) return row;
  const roleRows = snapshot.section_errors?.roles ? null : (snapshot.roles || []);
  return {
    ...row,
    name: user.name ?? row.name,
    nickname: user.nickname ?? row.nickname,
    display_name: user.display_name || user.nickname || user.name || row.display_name,
    username: user.username ?? row.username,
    student_id: user.student_id ?? row.student_id,
    intake: user.intake ?? row.intake,
    group: user.group ?? row.group,
    role: user.role ?? row.role,
    approved: user.approved ?? row.approved,
    suspended: user.suspended ?? row.suspended,
    registered_at: user.registered_at ?? row.registered_at,
    last_active: user.last_active ?? row.last_active,
    total_answers: user.total_answers ?? row.total_answers,
    correct_answers: user.correct_answers ?? row.correct_answers,
    accuracy: user.accuracy ?? row.accuracy,
    rank: user.prestige_rank ?? row.rank,
    div: user.prestige_div ?? row.div,
    streak: user.streak_current ?? row.streak,
    ai_usage: snapshot.ai?.total_usage ?? row.ai_usage,
    exam_count: snapshot.counts?.exams ?? row.exam_count,
    roles: roleRows ? roleRows.map(role => role.key) : row.roles,
    role_scope: roleRows ? (roleRows.find(role => role.scope)?.scope || null) : row.role_scope,
    subscription: snapshot.section_errors?.subscription ? row.subscription : snapshot.subscription,
  };
}

// 🌊 WA3 — اکشن‌های تکی (دقیقاً معادل دکمه‌های پنل مدیریت داخل ربات)
const USER_ACTIONS = {
  approve:    { icon: '✅', label: 'تأیید حساب', perm: 'users.manage' },
  reject:     { icon: '✖️', label: 'رد و حذف درخواست', perm: 'users.manage', danger: true },
  suspend:    { icon: '⏸', label: 'تعلیق', perm: 'users.suspend', danger: true },
  unsuspend:  { icon: '🔓', label: 'رفع تعلیق', perm: 'users.suspend' },
  block:      { icon: '⛔', label: 'مسدود (لیست سیاه)', perm: 'users.delete', danger: true },
  unblock:    { icon: '🕊', label: 'رفع مسدودیت', perm: 'users.delete' },
  delete:     { icon: '🗑', label: 'حذف کامل حساب', perm: 'users.delete', danger: true },
};

// 👥 WA2.4/2.8 — فیلتر ذخیره‌شده + bulk گسترده (تغییر ورودی/CSV) + دراور ۳۶۰ کاربر
export default function Users({ go, me, route = '' }) {
  const initial = readHashQuery();
  const [q, setQ] = useState(initial.get('q') || '');
  const [q2, setQ2] = useState(initial.get('q') || '');
  const [status, setStatus] = useState(initial.get('status') || '');
  const [intake, setIntake] = useState(initial.get('intake') || '');
  const [intakes, setIntakes] = useState([]);
  const [group, setGroup] = useState(initial.get('group') || '');
  const [role, setRole] = useState(initial.get('role') || '');
  const [roles, setRoles] = useState([]);
  const [activity, setActivity] = useState(initial.get('activity') || '');
  const [accuracyMax, setAccuracyMax] = useState(initial.get('accuracy_max') || '');
  const [subDays, setSubDays] = useState(initial.get('sub_expiring_days') || '');
  const [openTicket, setOpenTicket] = useState(initial.get('has_open_ticket') || '');
  const [smart, setSmart] = useState(() => { try { return initial.get('smart') ? JSON.parse(initial.get('smart')) : null; } catch { return null; } });
  const [smartOpen, setSmartOpen] = useState(false);
  const [sortBy, setSortBy] = useState(initial.get('sort_by') || 'registered_at');
  const [sortDir, setSortDir] = useState(initial.get('sort_dir') || 'desc');
  const [advanced, setAdvanced] = useState([...initial.keys()].some(k => !['q', 'status', 'intake', 'page', 'per_page'].includes(k)));
  const [page, setPage] = useState(queryNumber(initial, 'page', 1));
  const [perPage, setPerPage] = useState(queryNumber(initial, 'per_page', 25));
  const [data, setData] = useState({ users: [], total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [sel, setSel] = useState([]);
  const [detail, setDetail] = useState(null);       // row کاربر
  const [confirm, setConfirm] = useState(null);
  const [intakeModal, setIntakeModal] = useState(false);
  const [intakeVal, setIntakeVal] = useState('');
  const [bulkModal, setBulkModal] = useState(null); // group | add_role | remove_role | message
  const [bulkValue, setBulkValue] = useState('');
  const [bulkResult, setBulkResult] = useState(null);
  const [largeBatch, setLargeBatch] = useState(new URLSearchParams(route.split('?')[1] || '').get('batch') === '1');
  const [visibleColumns, setVisibleColumns] = useState([]);
  const [blOpen, setBlOpen] = useState(false);      // 🌊 WA3 — مودال لیست سیاه
  const [intOpen, setIntOpen] = useState(false);    // 🌊 WA4 — مدیریت ورودی‌ها
  const [caOpen, setCaOpen] = useState(false);      // 🌊 WA4 — ادمین‌های محتوا
  const user360Cache = useRef(new Map());
  const closeUserDrawer = useCallback(() => setDetail(null), []);
  const rememberUser360 = useCallback((uid, snapshot) => {
    const cache = user360Cache.current;
    cache.delete(uid);
    cache.set(uid, { data: snapshot, at: performance.now() });
    while (cache.size > USER360_CACHE_LIMIT) cache.delete(cache.keys().next().value);
  }, []);
  const updateUserFromSnapshot = useCallback((uid, snapshot) => {
    rememberUser360(uid, snapshot);
    setData(previous => ({
      ...previous,
      users: (previous.users || []).map(row => Number(row.id) === Number(uid) ? mergeUserSnapshot(row, snapshot) : row),
    }));
    setDetail(previous => Number(previous?.id) === Number(uid) ? mergeUserSnapshot(previous, snapshot) : previous);
  }, [rememberUser360]);
  const removeUserLocally = useCallback(uid => {
    user360Cache.current.delete(uid);
    setData(previous => ({
      ...previous,
      total: Math.max(0, Number(previous.total || 0) - 1),
      users: (previous.users || []).filter(row => Number(row.id) !== Number(uid)),
    }));
    setSel(previous => previous.filter(id => Number(id) !== Number(uid)));
  }, []);
  const has = permission => !!me?.is_owner || (me?.perms || []).includes(permission);
  const canAnyBatch = ['users.manage', 'users.suspend', 'users.message', 'users.delete'].some(has);

  useEffect(() => { api.intakes().then(r => setIntakes(r.intakes || [])).catch(() => {}); }, []);
  useEffect(() => { api.rolesPicker().then(r => setRoles(r.roles || [])).catch(() => setRoles([])); }, []);
  useEffect(() => { const t = setTimeout(() => setQ(q2), 350); return () => clearTimeout(t); }, [q2]);
  useEffect(() => {
    writeHashQuery('/users', { q: q2, status, intake, group, role, activity,
      accuracy_max: accuracyMax, sub_expiring_days: subDays,
      has_open_ticket: openTicket, smart: smart ? JSON.stringify(smart) : '',
      sort_by: sortBy !== 'registered_at' ? sortBy : '',
      sort_dir: sortDir !== 'desc' ? sortDir : '', page: page > 1 ? page : '',
      per_page: perPage !== 25 ? perPage : '' });
  }, [q2, status, intake, group, role, activity, accuracyMax, subDays, openTicket, smart, sortBy, sortDir, page, perPage]);

  const load = async () => {
    setLoading(true); setErr('');
    try {
      setData(await api.users({
        page, per_page: perPage, q, intake, status, group, role, activity,
        accuracy_max: accuracyMax, sub_expiring_days: subDays,
        has_open_ticket: openTicket, smart: smart ? JSON.stringify(smart) : '',
        sort_by: sortBy, sort_dir: sortDir,
      }));
    } catch (e) { setErr(errText(e)); }
    setLoading(false);
  };
  useEffect(() => { load(); }, [page, perPage, q, intake, status, group, role, activity, accuracyMax, subDays, openTicket, smart, sortBy, sortDir]);
  useEffect(() => { setSel([]); }, [page, q, intake, status, group, role, activity, accuracyMax, subDays, openTicket, smart]);

  const bulk = async (action, value, ids = sel) => {
    if (!ids.length) return toast('ابتدا کاربران را انتخاب کنید', 'err');
    try {
      const r = await api.usersBulk(action, ids, value);
      setBulkResult({ ...r, action, value });
      toast(`${faNum(r.done)} موفق · ${faNum(r.skipped?.length || 0)} ردشده · ${faNum(r.failed?.length || 0)} ناموفق`, r.failed?.length ? 'err' : 'ok');
      setSel([]); load();
      return r;
    } catch (e) { toast(errText(e), 'err'); return null; }
  };

  const applyFilter = (f) => {
    const flt = f.filters || {};
    setQ2(flt.q || ''); setQ(flt.q || '');
    setStatus(flt.status || ''); setIntake(flt.intake || ''); setGroup(flt.group || '');
    setRole(flt.role || ''); setActivity(flt.activity || '');
    setAccuracyMax(flt.accuracyMax ?? ''); setSubDays(flt.subDays ?? '');
    setOpenTicket(flt.openTicket || ''); setSmart(flt.smart || null); setSortBy(flt.sortBy || 'registered_at');
    setSortDir(flt.sortDir || 'desc'); setAdvanced(!!(flt.group || flt.role || flt.activity || flt.accuracyMax !== undefined || flt.subDays || flt.openTicket || flt.smart));
    setPage(1);
    toast(`نمای «${f.name}» اعمال شد ⏱`);
  };
  const exportSel = () => {
    const rows = (data.users || []).filter(u => sel.includes(u.id));
    exportCSV(`users-${fileDateStamp()}.csv`, [
      { label: 'id', v: 'id' }, { label: 'name', v: 'name' },
      { label: 'username', v: 'username' }, { label: 'student_id', v: 'student_id' },
      { label: 'intake', v: 'intake' }, { label: 'group', v: 'group' },
      { label: 'roles', v: r => (r.roles || []).join('|') },
      { label: 'subscription', v: r => r.subscription?.status || '' },
      { label: 'subscription_end', v: r => r.subscription?.end_date || '' },
      { label: 'accuracy', v: 'accuracy' }, { label: 'answers', v: 'total_answers' },
      { label: 'exams', v: 'exam_count' }, { label: 'ai_usage', v: 'ai_usage' },
      { label: 'last_active', v: 'last_active' }, { label: 'registered_at', v: 'registered_at' },
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
    { k: 'roles', label: 'نقش‌ها', render: r => (r.roles || []).length
      ? <div className="row" style={{ gap: 3 }}>{r.roles.slice(0, 2).map(x => <B key={x} kind="acc">{x}</B>)}{r.roles.length > 2 && <B>+{r.roles.length - 2}</B>}</div>
      : <span className="muted">دانشجو</span> },
    { k: 'subscription', label: 'اشتراک هامزیار', render: r => r.subscription?.status === 'active'
      ? <div><B kind="ok">{r.subscription.plan || 'فعال'}</B><div className="muted">{faNum(r.subscription.days_left)} روز</div></div>
      : <span className="muted">—</span> },
    { k: 'accuracy', label: 'دقت', render: r => <B kind={r.accuracy >= 70 ? 'ok' : r.accuracy < 50 && r.total_answers ? 'warn' : ''}>{faNum(r.accuracy)}٪</B> },
    { k: 'total_answers', label: 'پاسخ‌ها', render: r => faNum(r.total_answers) },
    { k: 'exam_count', label: 'آزمون', render: r => faNum(r.exam_count) },
    { k: 'ai_usage', label: 'هوشیار', render: r => faNum(r.ai_usage) },
    { k: 'streak', label: 'استریک', render: r => r.streak ? `🔥 ${faNum(r.streak)}` : '—' },
    { k: 'rank', label: 'رنک', render: r => r.rank ? <B kind="purple">{r.rank}{r.div ? ` / ${r.div}` : ''}</B> : '—' },
    { k: 'last_active', label: 'آخرین فعالیت', render: r => <RelativeTime value={r.last_active} /> },
    { k: 'registered_at', label: 'ثبت‌نام', render: r => <FaDateTime value={r.registered_at} /> },
    { k: 'st', label: 'وضعیت', render: r => <div className="row" style={{ gap: 3 }}>{r.suspended
      ? <B kind="bad">تعلیق</B> : r.approved ? <B kind="ok">فعال</B> : <B kind="warn">در انتظار</B>}{r.has_open_ticket && <B kind="warn">🎫 باز</B>}</div> },
    { k: 'ops', label: '', stop: true, render: r => (
      <div className="row" style={{ gap: 4 }}>
        {has('users.manage') && !r.approved && !r.suspended && <button className="btn sm ok" onClick={() => setConfirm({ uid: r.id, action: 'approve', text: `تأیید حساب «${r.display_name || r.name}»؟ وضعیت: در انتظار ← فعال` })} aria-label="تأیید کاربر">✅</button>}
        {has('users.suspend') && (r.suspended
          ? <button className="btn sm ok" title="رفع تعلیق" aria-label="رفع تعلیق کاربر" onClick={() => setConfirm({ uid: r.id, action: 'unsuspend', text: `رفع تعلیق «${r.display_name || r.name}»؟ وضعیت: تعلیق ← فعال` })}>🔓</button>
          : <button className="btn sm danger" onClick={() => setConfirm({ uid: r.id, action: 'suspend', text: `تعلیق «${r.display_name || r.name}»؟ وضعیت: فعال ← تعلیق` })} aria-label="تعلیق کاربر">⏸</button>)}
      </div>) },
  ];

  const act = async (uid, action) => {
    try {
      await api.waUserAction(uid, action);
      const updates = action === 'approve' || action === 'unsuspend'
        ? { approved: true, suspended: false }
        : action === 'suspend' ? { approved: false, suspended: true } : null;
      if (updates) {
        user360Cache.current.delete(uid);
        setData(previous => ({ ...previous, users: previous.users.map(row => Number(row.id) === Number(uid) ? { ...row, ...updates } : row) }));
        setDetail(previous => Number(previous?.id) === Number(uid) ? { ...previous, ...updates } : previous);
      }
      toast('انجام شد');
    } catch (e) { toast(errText(e), 'err'); }
  };

  if (err) return <ErrorState error={err} onRetry={load} />;

  return (
    <>
      <PageHeader title="مدیریت کاربران" description="جست‌وجو، فیلتر ذخیره‌شده، صفحه‌بندی سرورساید و عملیات گروهی" actions={<>
        {me?.is_owner && <button className="btn sm" title="مدیریت ورودی‌ها (افزودن/فعال‌سازی/حذف)" onClick={() => setIntOpen(true)}>📅 ورودی‌ها</button>}
        {me?.is_owner && <button className="btn sm" title="ادمین‌های محتوا" onClick={() => setCaOpen(true)}>🎓 ادمین‌های محتوا</button>}
        {has('users.view') && <button className="btn sm" title="کاربران مسدودشده" onClick={() => setBlOpen(true)}>⛔ لیست سیاه</button>}
        <button className="btn sm" onClick={() => api.exportUsersCsv({ q, intake, status, group, role, activity,
          accuracy_max: accuracyMax, sub_expiring_days: subDays, has_open_ticket: openTicket,
          smart: smart ? JSON.stringify(smart) : '', sort_by: sortBy, sort_dir: sortDir })}>📥 CSV همه نتایج</button>
        {canAnyBatch && <button className="btn sm" onClick={() => setLargeBatch(true)}>⚡ Batch با فهرست ID</button>}
        {sel.length > 0 && <>
          <span className="badge acc">{sel.length} انتخاب‌شده</span>
          {has('users.manage') && <button className="btn sm ok" onClick={() => setConfirm({ action: 'approve', text: `تأیید ${sel.length} کاربر؟` })}>✅ تأیید</button>}
          {has('users.suspend') && <button className="btn sm danger" onClick={() => setConfirm({ action: 'suspend', text: `تعلیق ${sel.length} کاربر؟` })}>⏸ تعلیق</button>}
          {has('users.suspend') && <button className="btn sm" onClick={() => setConfirm({ action: 'unsuspend', text: `رفع تعلیق ${sel.length} کاربر؟` })}>🔓 رفع تعلیق</button>}
          {has('users.manage') && <button className="btn sm" onClick={() => { setIntakeVal(''); setIntakeModal(true); }}>🏷 تغییر ورودی</button>}
          {has('users.manage') && <button className="btn sm" onClick={() => { setBulkValue(''); setBulkModal('set_group'); }}>👥 تغییر گروه</button>}
          {has('users.manage') && <button className="btn sm" onClick={() => { setBulkValue(''); setBulkModal('add_role'); }}>🛡 افزودن نقش</button>}
          {has('users.manage') && <button className="btn sm" onClick={() => { setBulkValue(''); setBulkModal('remove_role'); }}>➖ حذف نقش</button>}
          {has('users.message') && <button className="btn sm" onClick={() => { setBulkValue(''); setBulkModal('message'); }}>📨 پیام</button>}
          {has('users.delete') && <button className="btn sm danger" onClick={() => { setBulkValue(''); setBulkModal('block'); }}>⛔ مسدودسازی</button>}
          <button className="btn sm" onClick={exportSel}>📥 CSV انتخاب</button>
        </>}
      </>} />

      <FilterBar>
        <input className="inp" style={{ flex: 1, minWidth: 200 }} placeholder="🔎 نام، نام‌نما، یوزرنیم، شماره دانشجویی یا Telegram ID…"
               value={q2} onChange={e => { setQ2(e.target.value); setPage(1); }} />
        <select className="inp" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="inp" value={intake} onChange={e => { setIntake(e.target.value); setPage(1); }}>
          <option value="">همه‌ی ورودی‌ها</option>
          {intakes.map(i => <option key={i.code || i} value={i.code || i}>{i.label || i.code || i}</option>)}
        </select>
        <button className={`btn sm ${advanced ? 'primary' : ''}`} aria-expanded={advanced} onClick={() => setAdvanced(x => !x)}>⚙ فیلترهای سریع</button>
        <button className={`btn sm ${smart ? 'primary' : ''}`} onClick={() => setSmartOpen(true)}>🧠 Query Builder{smart ? ' · فعال' : ''}</button>
      </FilterBar>
      {advanced && <FilterBar className="advanced-filter-bar">
        <select className="inp" value={group} onChange={e => { setGroup(e.target.value); setPage(1); }}>
          <option value="">همه گروه‌ها</option><option value="1">گروه ۱</option><option value="2">گروه ۲</option>
        </select>
        <select className="inp" value={role} onChange={e => { setRole(e.target.value); setPage(1); }}>
          <option value="">همه نقش‌ها</option>{roles.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
        <select className="inp" value={activity} onChange={e => { setActivity(e.target.value); setPage(1); }}>
          <option value="">هر فعالیتی</option><option value="never">بدون اولین فعالیت</option>
          <option value="inactive_14">غیرفعال بیش از ۱۴ روز</option><option value="inactive_30">غیرفعال بیش از ۳۰ روز</option>
        </select>
        <label className="row"><span className="muted">دقت ≤</span><input className="inp" type="number" min="0" max="100" style={{ width: 76 }} value={accuracyMax}
          onChange={e => { setAccuracyMax(e.target.value); setPage(1); }} placeholder="٪" /></label>
        <label className="row"><span className="muted">انقضا تا</span><input className="inp" type="number" min="1" max="365" style={{ width: 76 }} value={subDays}
          onChange={e => { setSubDays(e.target.value); setPage(1); }} placeholder="روز" /></label>
        <select className="inp" value={openTicket} onChange={e => { setOpenTicket(e.target.value); setPage(1); }}>
          <option value="">هر وضعیت تیکت</option><option value="true">دارای تیکت باز</option><option value="false">بدون تیکت باز</option>
        </select>
        <select className="inp" value={sortBy} onChange={e => { setSortBy(e.target.value); setPage(1); }}>
          <option value="registered_at">مرتب‌سازی: ثبت‌نام</option><option value="last_active">آخرین فعالیت</option>
          <option value="name">نام</option><option value="total_answers">پاسخ‌ها</option>
          <option value="correct_answers">پاسخ صحیح</option><option value="streak_current">استریک</option><option value="ai_total_usage">مصرف هوشیار</option>
        </select>
        <select className="inp" value={sortDir} onChange={e => { setSortDir(e.target.value); setPage(1); }}>
          <option value="desc">نزولی</option><option value="asc">صعودی</option>
        </select>
        <select className="inp" value={perPage} onChange={e => { setPerPage(+e.target.value); setPage(1); }}>
          {[10, 25, 50, 100].map(n => <option key={n} value={n}>{n} در صفحه</option>)}
        </select>
        <button className="btn sm" onClick={() => { setGroup(''); setRole(''); setActivity(''); setAccuracyMax(''); setSubDays(''); setOpenTicket(''); setSortBy('registered_at'); setSortDir('desc'); setPage(1); }}>پاک‌کردن پیشرفته</button>
      </FilterBar>}

      {smart && <div className="row" style={{ marginBottom: 8 }}><B kind="acc">🧠 Query ترکیبی فعال</B><button className="btn sm" onClick={() => { setSmart(null); setPage(1); }}>حذف Query</button></div>}
      <SavedViews scope="users" filters={{ q, status, intake, group, role, activity, accuracyMax,
        subDays, openTicket, smart, sortBy, sortDir }} columns={visibleColumns} sort={{ key: sortBy, dir: sortDir }}
        onApply={(flt, item) => { applyFilter({ ...item, filters: flt }); setVisibleColumns(item.columns || []); }} label="نماهای کاربران" />

      <DataTable columns={cols} rows={data.users} selectable onSelect={setSel}
                 loading={loading} onRow={r => setDetail(r)} colToggle visibleColumns={visibleColumns}
                 onColumnsChange={setVisibleColumns}
                 pager={{ page, pages: data.pages, total: data.total, onPage: setPage }} />

      {detail && <UserDrawer row={detail} me={me} go={go} onClose={closeUserDrawer}
        initialData={(() => { const cached = user360Cache.current.get(detail.id); return cached && performance.now() - cached.at < USER360_STALE_MS ? cached.data : null; })()}
        onSnapshot={updateUserFromSnapshot}
        onRemoved={removeUserLocally} />}
      {blOpen && <BlacklistModal me={me} onClose={() => { setBlOpen(false); load(); }} />}
      {intOpen && <IntakesModal onClose={(ch) => { setIntOpen(false); if (ch) api.intakes().then(r => setIntakes(r.intakes || [])).catch(() => {}); }} />}
      {caOpen && <ContentAdminsModal onClose={() => { setCaOpen(false); load(); }} />}
      {confirm && (
        <Confirm text={confirm.text} danger={!!USER_ACTIONS[confirm.action]?.danger || confirm.action === 'suspend'}
                 onYes={async () => {
                   const c = confirm; setConfirm(null);
                   if (c.uid) { try { await api.waUserAction(c.uid, c.action); toast('انجام شد'); load(); } catch (e) { toast(errText(e), 'err'); } }
                   else await bulk(c.action);
                 }}
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
      {bulkModal && (
        <Modal title={{ set_group: '👥 تغییر گروه گروهی', add_role: '🛡 افزودن نقش گروهی', remove_role: '➖ حذف نقش گروهی', message: '📨 پیام به کاربران انتخاب‌شده', block: '⛔ مسدودسازی کاربران انتخاب‌شده' }[bulkModal]} onClose={() => setBulkModal(null)}>
          <p className="muted" style={{ marginBottom: 10 }}>{faNum(sel.length)} کاربر انتخاب شده‌اند. نتیجه‌ی هر کاربر جداگانه گزارش می‌شود.</p>
          {bulkModal === 'set_group' && <select className="inp" style={{ width: '100%' }} value={bulkValue} onChange={e => setBulkValue(e.target.value)}>
            <option value="">انتخاب گروه…</option><option value="1">گروه ۱</option><option value="2">گروه ۲</option>
          </select>}
          {(bulkModal === 'add_role' || bulkModal === 'remove_role') && <select className="inp" style={{ width: '100%' }} value={bulkValue} onChange={e => setBulkValue(e.target.value)}>
            <option value="">انتخاب نقش…</option>{roles.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>}
          {(bulkModal === 'message' || bulkModal === 'block') && <textarea className="inp" rows={5} maxLength={1500} style={{ width: '100%' }}
            placeholder={bulkModal === 'block' ? 'دلیل مسدودسازی — کاربران از دیتابیس فعال حذف و به لیست سیاه منتقل می‌شوند…' : 'متن پیام از سمت پشتیبانی هامزیار…'} value={bulkValue} onChange={e => setBulkValue(e.target.value)} />}
          <div className="row" style={{ marginTop: 12 }}>
            <button className={`btn ${bulkModal === 'remove_role' || bulkModal === 'block' ? 'danger' : 'primary'}`} disabled={!bulkValue.trim()} onClick={async () => {
              const action = bulkModal; const value = bulkValue; setBulkModal(null); await bulk(action, value);
            }}>بازبینی شد؛ اجرا</button>
            <button className="btn" onClick={() => setBulkModal(null)}>انصراف</button>
          </div>
        </Modal>
      )}
      {largeBatch && <LargeBatchModal has={has} intakes={intakes} roles={roles} onClose={() => setLargeBatch(false)} onDone={result => { setLargeBatch(false); setBulkResult(result); load(); }} />}
      {smartOpen && <SmartQueryBuilder value={smart} onClose={() => setSmartOpen(false)} onApply={value => { setSmart(value); setSmartOpen(false); setPage(1); }} />}
      {bulkResult && (
        <Modal title="گزارش عملیات گروهی" onClose={() => setBulkResult(null)}>
          <div className="grid g3">
            <div className="panel panel-pad"><b className="ok-text">{faNum(bulkResult.succeeded?.length || 0)}</b><div className="muted">موفق</div></div>
            <div className="panel panel-pad"><b>{faNum(bulkResult.skipped?.length || 0)}</b><div className="muted">ردشده/بدون تغییر</div></div>
            <div className="panel panel-pad"><b className="bad-text">{faNum(bulkResult.failed?.length || 0)}</b><div className="muted">ناموفق</div></div>
          </div>
          {!!bulkResult.skipped?.length && <div className="grid" style={{ marginTop: 10, gap: 4 }}><b>ردشده‌ها</b>
            {bulkResult.skipped.slice(0, 20).map(x => <div key={`s-${x.id}`} className="row"><span className="code">{x.id}</span><span className="muted">{x.reason}</span></div>)}</div>}
          {!!bulkResult.failed?.length && <div className="grid" style={{ marginTop: 10, gap: 4 }}><b>ناموفق‌ها</b>
            {bulkResult.failed.slice(0, 20).map(x => <div key={`f-${x.id}`} className="row"><span className="code">{x.id}</span><span className="muted">{x.error}</span></div>)}
            <button className="btn" onClick={() => bulk(bulkResult.action, bulkResult.value, bulkResult.failed.map(x => x.id))}>↻ تلاش مجدد ناموفق‌ها</button></div>}
        </Modal>
      )}
    </>
  );
}


function LargeBatchModal({ has, intakes, roles, onClose, onDone }) {
  const actions = [
    ['approve', 'تأیید', 'users.manage'], ['suspend', 'تعلیق', 'users.suspend'], ['unsuspend', 'رفع تعلیق', 'users.suspend'],
    ['set_intake', 'تغییر ورودی', 'users.manage'], ['set_group', 'تغییر گروه', 'users.manage'],
    ['add_role', 'افزودن نقش', 'users.manage'], ['remove_role', 'حذف نقش', 'users.manage'],
    ['message', 'ارسال اعلان', 'users.message'], ['block', 'مسدودسازی', 'users.delete'],
  ].filter(([, , permission]) => has(permission));
  const [text, setText] = useState(''); const [action, setAction] = useState(actions[0]?.[0] || ''); const [value, setValue] = useState('');
  const [confirmed, setConfirmed] = useState(false); const [busy, setBusy] = useState(false); const [progress, setProgress] = useState(0);
  const ids = useMemo(() => [...new Set(text.split(/[\s,،;]+/).map(x => x.trim()).filter(x => /^\d+$/.test(x)).map(Number))].slice(0, 2000), [text]);
  const needsValue = ['set_intake', 'set_group', 'add_role', 'remove_role', 'message', 'block'].includes(action);
  const run = async () => {
    if (!ids.length || (needsValue && !value.trim()) || !confirmed) return;
    setBusy(true); const result = { action, value, succeeded: [], skipped: [], failed: [], done: 0 };
    const chunks = Array.from({ length: Math.ceil(ids.length / 100) }, (_, index) => ids.slice(index * 100, index * 100 + 100));
    for (let index = 0; index < chunks.length; index += 1) {
      try { const response = await api.usersBulk(action, chunks[index], value); result.succeeded.push(...(response.succeeded || [])); result.skipped.push(...(response.skipped || [])); result.failed.push(...(response.failed || [])); }
      catch (e) { result.failed.push(...chunks[index].map(id => ({ id, error: errText(e) }))); }
      setProgress(index + 1);
    }
    result.done = result.succeeded.length; result.ok = !result.failed.length; setBusy(false); onDone(result);
  };
  return <Modal wide title="⚡ Batch Engine کاربران" onClose={busy ? () => {} : onClose}>
    <div className="panel panel-pad" style={{ background: 'var(--bg)' }}><b>اجرای chunked روی domain API موجود</b><div className="muted">حداکثر ۲۰۰۰ ID؛ هر chunk حداکثر ۱۰۰ رکورد، با audit و نتیجه per-record. این UI mutation مستقیم یا background job جعلی نمی‌سازد.</div></div>
    <textarea className="inp" rows={7} style={{ width: '100%', marginTop: 10 }} placeholder="Telegram IDها؛ هر خط یا با ویرگول…" value={text} onChange={e => { setText(e.target.value); setConfirmed(false); }} />
    <div className="row"><B kind={ids.length ? 'acc' : 'warn'}>{faNum(ids.length)} ID معتبر</B><B>{faNum(Math.ceil(ids.length / 100))} chunk</B>{text.trim() && !ids.length && <B kind="bad">ID معتبری تشخیص داده نشد</B>}</div>
    <div className="row" style={{ marginTop: 10 }}><select className="inp" value={action} onChange={e => { setAction(e.target.value); setValue(''); setConfirmed(false); }}>{actions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      {action === 'set_intake' ? <select className="inp" value={value} onChange={e => setValue(e.target.value)}><option value="">انتخاب ورودی…</option>{intakes.map(item => <option key={item.code || item} value={item.code || item}>{item.label || item.code || item}</option>)}</select>
        : ['add_role', 'remove_role'].includes(action) ? <select className="inp" value={value} onChange={e => setValue(e.target.value)}><option value="">انتخاب نقش…</option>{roles.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select>
        : needsValue && <input className="inp" style={{ flex: 1 }} value={value} onChange={e => setValue(e.target.value)} placeholder={action === 'message' ? 'متن اعلان…' : action === 'block' ? 'دلیل مسدودسازی…' : 'مقدار…'} />}</div>
    <label className="row" style={{ marginTop: 12 }}><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /><span>پیش‌نمایش تعداد و عملیات را بررسی کردم و اجرای {faNum(ids.length)} رکورد را تأیید می‌کنم.</span></label>
    {busy && <div style={{ marginTop: 10 }}><progress max={Math.max(1, Math.ceil(ids.length / 100))} value={progress} style={{ width: '100%' }} /><div className="muted">chunk {faNum(progress)} از {faNum(Math.ceil(ids.length / 100))}</div></div>}
    <div className="row" style={{ marginTop: 12 }}><button className={`btn ${['block', 'suspend', 'remove_role'].includes(action) ? 'danger' : 'primary'}`} disabled={busy || !ids.length || !confirmed || (needsValue && !value.trim())} onClick={run}>اجرای Batch</button><button className="btn" disabled={busy} onClick={onClose}>انصراف</button></div>
  </Modal>;
}

/* ── 👤 WA2.8 — User 360: کانتکست کامل بدون ترک صفحه ─────────── */
function UserDrawer({ row, me, go, onClose, initialData, onSnapshot, onRemoved }) {
  const [d, setD] = useState(initialData || null);
  const [failed, setFailed] = useState('');
  const [loading, setLoading] = useState(!initialData);
  const [tab, setTab] = useState('overview');
  const [relation, setRelation] = useState(null);
  const requestSeq = useRef(0);

  const fetchSnapshot = useCallback(async ({ keepData = true } = {}) => {
    const uid = row.id;
    const seq = ++requestSeq.current;
    setFailed('');
    if (!keepData) setD(null);
    setLoading(true);
    try {
      const snapshot = await api.user360(uid);
      if (seq !== requestSeq.current) return null;
      setD(snapshot);
      onSnapshot?.(uid, snapshot);
      return snapshot;
    } catch (error) {
      if (seq === requestSeq.current) setFailed(errText(error));
      return null;
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [row.id, onSnapshot]);

  useEffect(() => {
    requestSeq.current += 1;
    setTab('overview'); setRelation(null); setFailed('');
    if (initialData) { setD(initialData); setLoading(false); }
    else { setD(null); fetchSnapshot({ keepData: false }); }
    return () => { requestSeq.current += 1; };
  }, [row.id]);

  const refetch = useCallback(() => fetchSnapshot({ keepData: true }), [fetchSnapshot]);

  const has = permission => !!me?.is_owner || (me?.perms || []).includes(permission);
  const canAct = ['users.manage', 'users.suspend', 'users.message', 'users.delete'].some(has);
  const unavailable = section => d?.section_errors?.[section]
    ? <div className="panel panel-pad"><B kind="warn">⚠️ اطلاعات فعلاً در دسترس نیست</B><button className="btn sm" onClick={refetch}>Retry</button></div>
    : null;
  const TABS = [
    ['overview', '📊 نمای کلی'], ['identity', '👤 هویت'], ['academic', '📚 یادگیری و نمرات'],
    ['questions', '🧪 سؤال‌ها'], ['exams', '📝 آزمون‌ها'], ['ai', '🤖 هوشیار'],
    ['notifications', '🔔 اعلان‌ها'], ['tickets', '🎫 تیکت‌ها'], ['sub', '💎 اشتراک'],
    ['prestige', '🏆 افتخار'], ['roles', '🛡 نقش‌ها'], ['activity', '🕓 فعالیت'],
    ['audit', '🧭 حسابرسی'], ['actions', '⚙️ اقدامات'],
  ];

  return (
    <Drawer wide title={`👤 ${row.display_name || row.name} · #${row.id}`} onClose={onClose}>
      <div className="tabs" style={{ marginBottom: 10 }} role="tablist" aria-label="بخش‌های پرونده کاربر">
        {TABS.filter(([k]) => k !== 'actions' || canAct).map(([k, v]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{v}</button>
        ))}
      </div>
      {failed && <div className="user-drawer-error"><ErrorState title="اطلاعات کاربر بارگذاری نشد" error={failed} onRetry={() => fetchSnapshot({ keepData: Boolean(d) })} />
        {!d && <dl className="kv">
          {Object.entries({
            'نام': row.name, 'یوزرنیم': row.username && '@' + row.username,
            'شماره دانشجویی': row.student_id, 'ورودی': row.intake, 'گروه': row.group,
          }).filter(([, v]) => v).map(([k, v]) => (
            <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
          ))}
        </dl>}
      </div>}
      {loading && !d && tab !== 'actions' && <Loading label="در حال بارگذاری پرونده کاربر" />}
      {tab === 'actions' && (
        <UserActions row={row} d={d} me={me} onChanged={refetch} onClose={onClose} onRemoved={onRemoved} />
      )}
      {d && tab === 'overview' && (
        <>
          <div className="grid g4">
            <div className="panel panel-pad"><b>{faNum(d.user.total_answers)}</b><div className="muted">پاسخ · دقت {faNum(d.user.accuracy)}٪</div></div>
            <div className="panel panel-pad"><b>{faNum(d.counts.exams)}</b><div className="muted">آزمون</div></div>
            <div className="panel panel-pad"><b>{faNum(d.counts.tickets)}</b><div className="muted">تیکت</div></div>
            <div className="panel panel-pad"><b>{faNum(d.ai?.total_usage)}</b><div className="muted">استفاده از هوشیار</div></div>
          </div>
          <div className="grid g2" style={{ marginTop: 10 }}>
            <div className="panel panel-pad"><b>وضعیت حساب</b><div style={{ marginTop: 6 }}>
              {d.user.suspended ? <B kind="bad">تعلیق‌شده</B> : d.user.approved ? <B kind="ok">فعال</B> : <B kind="warn">در انتظار تأیید</B>}
              <span className="muted"> · آخرین فعالیت: </span><RelativeTime value={d.user.last_active} fallback="ثبت نشده" />
            </div></div>
            <div className="panel panel-pad"><b>اشتراک هامزیار</b><div style={{ marginTop: 6 }}>
              {d.subscription?.status === 'active' ? <><B kind="ok">{d.subscription.plan}</B><span className="muted"> {faNum(d.subscription.days_left)} روز باقی</span></> : <span className="muted">اشتراک فعال ندارد</span>}
            </div></div>
          </div>
        </>
      )}
      {d && tab === 'identity' && (
        <dl className="kv">
          {Object.entries({
            'نام کامل': d.user.name, 'نام‌نما': d.user.nickname,
            'یوزرنیم': d.user.username && '@' + d.user.username,
            'Telegram ID': d.user.id, 'شماره دانشجویی': d.user.student_id,
            'ورودی': d.user.intake, 'گروه': d.user.group, 'نقش قدیمی': d.user.role,
            'ثبت‌نام': d.user.registered_at, 'آخرین فعالیت': d.user.last_active,
          }).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => (
            <React.Fragment key={k}><dt>{k}</dt><dd className={k === 'Telegram ID' || k === 'یوزرنیم' ? 'code' : ''}>{k === 'ثبت‌نام' || k === 'آخرین فعالیت' ? <FaDateTime value={v} /> : String(v)}</dd></React.Fragment>
          ))}
        </dl>
      )}
      {/* 🌊 W-Admin — تب‌های جدید User 360 */}
      {d && tab === 'academic' && (
        <>
          {unavailable('academic') || unavailable('academic_counts')}
          <div className="row" style={{ marginBottom: 8 }}><span className="muted">نمرات ثبت‌شده: {Number(d.counts.grades || 0).toLocaleString('fa')}</span><span className="spacer" /><button className="btn sm" onClick={() => setRelation('grades')}>مشاهده همه</button></div>
          {(d.academic?.grades_recent || []).length === 0 &&
            <div className="center-state">نمره‌ای ثبت نشده</div>}
          {(d.academic?.grades_recent || []).map((g, i) => (
            <div key={i} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
              <span>📚</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ color: 'var(--txt)' }}>{g.lesson}</b>
                <div className="muted">{g.exam_title} · <FaDate value={g.exam_date} /></div>
              </div>
              <B kind={g.score >= 10 ? 'ok' : 'bad'}>{Number(g.score).toLocaleString('fa')}</B>
            </div>
          ))}
        </>
      )}
      {d && tab === 'questions' && (
        <>
          {unavailable('questions')}
          <div className="row" style={{ marginBottom: 8 }}><span className="muted">سؤال‌های طراحی‌شده: {faNum(d.counts.questions)}</span><span className="spacer" /><button className="btn sm" onClick={() => setRelation('questions')}>مشاهده همه</button></div>
          {!(d.recent_questions || []).length && <Empty icon="🧪" text="سؤالی طراحی نکرده است" />}
          {(d.recent_questions || []).map(x => <div key={x.id} className="panel panel-pad" style={{ marginBottom: 6 }}>
            <div className="row"><b className="text-truncate">{x.question || '—'}</b><span className="spacer" />
              <B kind={x.approved ? 'ok' : 'warn'}>{x.approved ? 'تأییدشده' : 'در انتظار'}</B></div>
            <div className="muted">{x.lesson} · {x.topic} · {faNum(x.attempts)} تلاش · دقت {faNum(x.accuracy)}٪</div>
          </div>)}
        </>
      )}
      {d && tab === 'exams' && (
        <>
          {unavailable('exams')}
          <div className="row" style={{ marginBottom: 8 }}><span className="muted">آزمون‌ها: {faNum(d.counts.exams)}</span><span className="spacer" /><button className="btn sm" onClick={() => setRelation('exams')}>مشاهده همه</button></div>
          {!(d.recent_exams || []).length && <Empty icon="📝" text="آزمونی ثبت نشده است" />}
          {(d.recent_exams || []).map(x => <div key={x.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
            <div style={{ flex: 1 }}><b>{x.lesson || 'آزمون سفارشی'}</b><div className="muted">{x.topic || 'همه مباحث'} · <FaDateTime value={x.started_at} /></div></div>
            <B kind={x.status === 'finished' ? 'ok' : 'warn'}>{x.status}</B><B kind="acc">{faNum(x.percentage)}٪</B>
          </div>)}
        </>
      )}
      {d && tab === 'prestige' && (
        <> {unavailable('prestige') || unavailable('prestige_history')}<div className="row"><span className="spacer" /><button className="btn sm" onClick={() => setRelation('prestige')}>مشاهده تاریخچه کامل</button></div><dl className="kv">
          {Object.entries({
            'رنک': d.prestige?.rank, 'دسته (Division)': d.prestige?.div,
            'XP افتخار': d.prestige?.prestige_xp, 'XP مؤثر': d.prestige?.effective_xp,
            'XP هفتگی': d.prestige?.weekly_xp, 'XP ماهانه': d.prestige?.monthly_xp,
            'XP امروز': d.prestige?.daily_xp_amount,
            '🔥 استریک فعلی': d.prestige?.streak_current, '🥇 بهترین استریک': d.prestige?.streak_best,
          }).filter(([, v]) => v !== undefined && v !== '' && v !== null).map(([k, v]) => (
            <React.Fragment key={k}><dt>{k}</dt>
              <dd>{typeof v === 'number' ? Number(v).toLocaleString('fa') : String(v)}</dd></React.Fragment>
          ))}
        </dl>
        {!!(d.prestige_history || []).length && <div style={{ marginTop: 12 }}><b>تاریخچه Prestige</b>
          {(d.prestige_history || []).map(x => <div key={x.id} className="row" style={{ padding: '6px 0', borderBottom: '1px solid var(--line)' }}>
            <span style={{ flex: 1 }}>{x.title || x.kind || 'رویداد'}</span><B kind={x.xp >= 0 ? 'ok' : 'warn'}>{x.xp >= 0 ? '+' : ''}{faNum(x.xp)} XP</B><FaDateTime value={x.at} />
          </div>)}</div>}
        </>
      )}
      {d && tab === 'ai' && (
        <>
          {unavailable('ai')}
          <dl className="kv">
            <dt>پرسش کل</dt><dd>{Number(d.ai?.total_usage || 0).toLocaleString('fa')}</dd>
            <dt>پرسش امروز</dt><dd>{Number(d.ai?.today || 0).toLocaleString('fa')}</dd>
            <dt>توکن مصرفی</dt><dd>{Number(d.ai?.total_tokens || 0).toLocaleString('fa')}</dd>
            <dt>وضعیت دسترسی</dt>
            <dd>{d.ai?.banned ? <B kind="bad">⛔ مسدود از هوشیار</B> : <B kind="ok">✅ آزاد</B>}</dd>
            <dt>اعلان‌های خوانده‌نشده</dt>
            <dd>{Number(d.notifs?.unread || 0).toLocaleString('fa')} از {Number(d.notifs?.total || 0).toLocaleString('fa')}</dd>
          </dl>
          {d.ai?.banned && (
            <p className="muted">رفع مسدودیت از صفحه‌ی «هوشیار ← دسترسی» انجام می‌شود.</p>
          )}
        </>
      )}
      {d && tab === 'notifications' && (
        <>
          {unavailable('notifications')}
          <div className="row" style={{ marginBottom: 8 }}><B kind="warn">خوانده‌نشده: {faNum(d.notifs?.unread)}</B><B>کل: {faNum(d.notifs?.total)}</B><span className="spacer" /><button className="btn sm" onClick={() => setRelation('notifications')}>مشاهده همه</button></div>
          {!(d.recent_notifications || []).length && <Empty icon="🔔" text="اعلانی ثبت نشده است" />}
          {(d.recent_notifications || []).map(x => <div key={x.id} className="panel panel-pad" style={{ marginBottom: 6 }}>
            <div className="row"><b>{x.title || x.type || 'اعلان'}</b><span className="spacer" />
              <B kind={x.read ? '' : 'acc'}>{x.read ? 'خوانده‌شده' : 'جدید'}</B></div>
            {x.body && <div className="muted">{x.body}</div>}<div className="muted"><FaDateTime value={x.at} /></div>
          </div>)}
        </>
      )}
      {d && tab === 'roles' && (
        <>
          {unavailable('roles') || unavailable('permissions')}
          {!(d.roles || []).length && <Empty icon="🛡" text="نقش مدیریتی ندارد" />}
          {(d.roles || []).map(r => <div key={r.key} className="panel panel-pad" style={{ marginBottom: 6 }}>
            <div className="row"><b>{r.label || r.key}</b><span className="code">{r.key}</span><span className="spacer" />
              <B kind={r.active ? 'ok' : 'bad'}>{r.active ? 'فعال' : 'غیرفعال'}</B>{r.scope && <B kind="purple">{r.scope}</B>}</div>
          </div>)}
          {!!(d.perms || []).length && <div className="row" style={{ marginTop: 10, gap: 4 }}>
            {d.perms.map(p => <B key={p} kind="acc">{p}</B>)}</div>}
        </>
      )}
      {d && tab === 'sub' && (<>
        {unavailable('subscription')}
        {d.subscription ? (
          <dl className="kv">
            <dt>وضعیت</dt><dd>{d.subscription.status === 'active' ? '✅ فعال' : d.subscription.status || '—'}</dd>
            <dt>پلن</dt><dd>{d.subscription.plan || '—'}</dd>
            <dt>پایان</dt><dd><FaDateTime value={d.subscription.end_date} /></dd>
            <dt>روزهای باقی</dt><dd>{d.subscription.days_left ?? '—'}</dd>
          </dl>
        ) : <div className="center-state">اشتراک فعالی ندارد</div>}
      </>)}
      {d && tab === 'tickets' && (
        <>
          {unavailable('tickets')}
          <div className="row" style={{ marginBottom: 8 }}><span className="muted">مجموع: {Number(d.counts.tickets || 0).toLocaleString('fa')} تیکت</span><span className="spacer" /><button className="btn sm" onClick={() => setRelation('tickets')}>مشاهده همه</button></div>
          {(d.recent_tickets || []).length === 0 && <div className="center-state">تیکتی نیست</div>}
          {(d.recent_tickets || []).map(t => (
            <div key={t.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line)', cursor: 'pointer' }}
                 onClick={() => go('/tickets')}>
              <span>🎫</span>
              <span style={{ flex: 1 }}>{t.subject}</span>
              <B kind={t.status === 'open' ? 'bad' : t.status === 'answered' ? 'warn' : 'ok'}>
                {t.status === 'open' ? 'باز' : t.status === 'answered' ? 'پاسخ' : 'بسته'}</B>
              <FaDateTime value={t.at} />
            </div>
          ))}
        </>
      )}
      {d && tab === 'activity' && (
        <>
          {unavailable('answers')}
          {!(d.activity || []).length && <Empty icon="🕓" text="فعالیتی ثبت نشده است" />}
          {(d.activity || []).map(event => <button key={event.id} className="panel panel-pad row" style={{ width: '100%', marginBottom: 6, color: 'inherit', textAlign: 'right' }}
            onClick={() => event.go && go(event.go)}>
            <span style={{ fontSize: 18 }}>{event.icon || '•'}</span>
            <span style={{ flex: 1 }}><b>{event.title}</b>{event.description && <span className="muted" style={{ display: 'block' }}>{event.description}</span>}</span>
            <FaDateTime value={event.at} /><span className="muted">‹</span>
          </button>)}
        </>
      )}
      {d && tab === 'audit' && (
        <>
          {unavailable('audit')}<div className="row"><span className="spacer" /><button className="btn sm" onClick={() => setRelation('audit')}>مشاهده همه</button></div>
          {(d.recent_audit || []).length === 0 && <div className="center-state">رویدادی ثبت نشده</div>}
          {(d.recent_audit || []).map((l, i) => (
            <div key={i} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
              <span className={`sev ${(l.severity || '').toLowerCase()}`} />
              <span style={{ flex: 1 }}>{l.action}<div className="muted">{l.relation === 'target' ? 'عملیات روی این کاربر' : 'عملیات انجام‌شده توسط کاربر'}</div></span>
              {!!l.changes?.length && <B kind="acc">Δ {faNum(l.changes.length)}</B>}
              <B>{l.module}</B>
              {l.correlation_id && <span className="code">{l.correlation_id}</span>}
              <FaDateTime value={l.at} />
            </div>
          ))}
        </>
      )}
      {relation && <UserRelationModal uid={row.id} section={relation} onClose={() => setRelation(null)} />}
    </Drawer>
  );
}

function UserRelationModal({ uid, section, onClose }) {
  const [page, setPage] = useState(1); const [data, setData] = useState(null); const [err, setErr] = useState(''); const limit = 30;
  const load = async () => { setData(null); setErr(''); try { setData(await api.userRelations(uid, section, { skip: (page - 1) * limit, limit })); } catch (e) { setErr(errText(e)); } };
  useEffect(() => { load(); }, [page, section]);
  return <Modal wide title={`تاریخچه کامل · ${section}`} onClose={onClose}>{err ? <ErrorState error={err} onRetry={load} /> : !data ? <Loading rows={6} /> : <>
    {!data.items?.length ? <Empty text="رکوردی ثبت نشده" /> : <div className="grid" style={{ gap: 6 }}>{data.items.map(x => <div key={x.id} className="panel panel-pad"><div className="row"><b className="text-wrap">{x.title || '—'}</b>{x.status && <B>{x.status}</B>}<span className="spacer" /><FaDateTime value={x.at} /></div>{x.detail && <div className="muted text-wrap">{typeof x.detail === 'object' ? JSON.stringify(x.detail) : x.detail}</div>}{x.value !== undefined && <B kind="acc">{String(x.value)}</B>}</div>)}</div>}
    <div className="row" style={{ justifyContent: 'center', marginTop: 10 }}><button className="btn sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>قبلی</button><B>{page.toLocaleString('fa')}</B><button className="btn sm" disabled={page * limit >= (data.total || 0)} onClick={() => setPage(p => p + 1)}>بعدی</button></div>
  </>}</Modal>;
}

/* ── ⚙️🌊 WA3 — تب اقدامات: DM + ویرایش پروفایل + اکشن‌های مدیریتی ─────
   دقیقاً معادل دکمه‌های پنل مدیریت داخل ربات؛ همه از API /api/web-admin
   با guard سمت سرور و audit رد می‌شوند (سینک کامل با ربات/مینی‌اپ). */
function UserActions({ row, d, me, onChanged, onClose, onRemoved }) {
  const u = d?.user || row;
  const has = permission => !!me?.is_owner || (me?.perms || []).includes(permission);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [intakes, setIntakes] = useState([]);
  const [form, setForm] = useState({
    name: u.name || '', student_id: u.student_id || '',
    group: u.group || '', intake: u.intake || '', nickname: u.nickname || '',
  });
  const [confirm, setConfirm] = useState(null);   // {action,text,danger}
  const [pendingPatch, setPendingPatch] = useState(null);
  const [blockModal, setBlockModal] = useState(false);
  const [reason, setReason] = useState('');
  useEffect(() => { api.intakes().then(r => setIntakes(r.intakes || [])).catch(() => {}); }, []);

  const sendDM = async () => {
    if (!msg.trim()) return;
    setBusy(true);
    try { await api.waUserMessage(row.id, msg.trim()); toast('پیام در صف ارسال به کاربر قرار گرفت 📨'); setMsg(''); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const proposeSave = () => {
    const body = {};
    ['name', 'student_id', 'group', 'intake', 'nickname'].forEach(k => {
      if (String(form[k] || '') !== String(u[k] || '')) body[k] = form[k];
    });
    if (!Object.keys(body).length) return toast('تغییری اعمال نشده است', 'err');
    setPendingPatch(body);
  };
  const applySave = async () => {
    const body = pendingPatch; setPendingPatch(null); setBusy(true);
    try {
      const r = await api.waUserPatch(row.id, body);
      toast(`ذخیره شد ✅ (${(r.changed || []).length} فیلد)`);
      await onChanged();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const runAction = async (action, rs = '') => {
    setBusy(true);
    try {
      await api.waUserAction(row.id, action, rs);
      toast(`${USER_ACTIONS[action].icon} ${USER_ACTIONS[action].label} — انجام شد`);
      if (action === 'delete' || action === 'reject') {
        onRemoved?.(row.id);
        onClose();
        return;
      }
      await onChanged();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const ask = (action, text) => setConfirm({ action, text, danger: USER_ACTIONS[action].danger });

  return (
    <div className="grid" style={{ gap: 12 }}>
      {/* 📨 پیام مستقیم — همان ارسال پیام پنل ربات (outbox → ربات می‌فرستد) */}
      {has('users.message') && <div className="panel panel-pad" style={{ background: 'var(--bg)' }}>
        <b>📨 ارسال پیام مستقیم (از سمت ربات)</b>
        <textarea className="inp" rows={3} style={{ width: '100%', marginTop: 8, resize: 'vertical' }}
                  placeholder="متن پیام برای کاربر… (حداکثر ۱۵۰۰ کاراکتر)"
                  maxLength={1500} value={msg} onChange={e => setMsg(e.target.value)} />
        <div className="row" style={{ marginTop: 8 }}>
          <span className="muted">{Number(msg.length).toLocaleString('fa')} / ۱۵۰۰</span>
          <span className="spacer" />
          <button className="btn primary sm" disabled={busy || !msg.trim()} onClick={sendDM}>ارسال 📨</button>
        </div>
      </div>}

      {/* ✏️ ویرایش پروفایل */}
      {has('users.manage') && <div className="panel panel-pad" style={{ background: 'var(--bg)' }}>
        <b>✏️ ویرایش پروفایل</b>
        <div className="grid g2" style={{ gap: 8, marginTop: 10 }}>
          <label className="fld"><span>نام</span>
            <input className="inp" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
          <label className="fld"><span>نام‌نما (نمایش به دیگران)</span>
            <input className="inp" value={form.nickname} onChange={e => setForm({ ...form, nickname: e.target.value })} /></label>
          <label className="fld"><span>شماره دانشجویی</span>
            <input className="inp" style={{ direction: 'ltr' }} value={form.student_id}
                   onChange={e => setForm({ ...form, student_id: e.target.value })} /></label>
          <label className="fld"><span>گروه</span>
            <select className="inp" value={form.group} onChange={e => setForm({ ...form, group: e.target.value })}>
              <option value="">(بدون گروه)</option>
              <option value="1">گروه ۱</option>
              <option value="2">گروه ۲</option>
              {!['', '1', '2'].includes(String(form.group)) &&
                <option value={form.group}>مقدار قدیمی: {form.group}</option>}
            </select></label>
          <label className="fld"><span>ورودی</span>
            <select className="inp" value={form.intake} onChange={e => setForm({ ...form, intake: e.target.value })}>
              <option value="">(بدون ورودی)</option>
              {intakes.map(i => <option key={i.code || i} value={i.code || i}>{i.label || i.code || i}</option>)}
            </select></label>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn primary sm" disabled={busy} onClick={proposeSave}>بازبینی و ذخیره تغییرات</button>
          <span className="muted">تاریخچه‌ی تغییر نام‌نما در پروفایل کاربر ثبت می‌شود</span>
        </div>
      </div>}

      {/* 🎛 اکشن‌های مدیریتی — همان دکمه‌های ربات */}
      <div className="panel panel-pad" style={{ background: 'var(--bg)' }}>
        <b>🎛 اکشن‌های مدیریتی</b>
        <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: 'wrap' }}>
          {has('users.manage') && !u.approved && !u.suspended && <>
            <button className="btn ok sm" disabled={busy}
                    onClick={() => ask('approve', `تأیید حساب «${u.name || row.id}»؟ به کاربر اطلاع‌رسانی می‌شود.`)}>✅ تأیید حساب</button>
            <button className="btn danger sm" disabled={busy}
                    onClick={() => ask('reject', `رد و حذف درخواست «${u.name || row.id}»؟`)}>✖️ رد درخواست</button>
          </>}
          {has('users.suspend') && (u.suspended
            ? <button className="btn ok sm" disabled={busy}
                      onClick={() => ask('unsuspend', `رفع تعلیق «${u.name || row.id}»؟`)}>🔓 رفع تعلیق</button>
            : <button className="btn danger sm" disabled={busy}
                      onClick={() => ask('suspend', `تعلیق «${u.name || row.id}»؟ به کاربر اطلاع‌رسانی می‌شود.`)}>⏸ تعلیق</button>)}
          {has('users.delete') && <button className="btn danger sm" disabled={busy} onClick={() => { setReason(''); setBlockModal(true); }}>⛔ مسدود</button>}
          {has('users.delete') && <button className="btn sm" disabled={busy}
                  onClick={() => ask('unblock', `رفع مسدودیت «${u.name || row.id}» از لیست سیاه؟`)}>🕊 رفع مسدودیت</button>}
          {has('users.delete') && <button className="btn danger sm" disabled={busy}
                  onClick={() => ask('delete', `حذف کامل حساب «${u.name || row.id}»؟ این عمل برگشت‌پذیر نیست.`)}>🗑 حذف حساب</button>}
        </div>
      </div>

      {pendingPatch && <Modal title="بازبینی تغییرات کاربر" onClose={() => setPendingPatch(null)}>
        <p className="muted" style={{ marginBottom: 10 }}>مقادیر زیر پس از تأیید ذخیره و در حسابرسی ثبت می‌شوند.</p>
        <DiffViewer
          before={Object.fromEntries(Object.keys(pendingPatch).map(k => [k, u[k] ?? '']))}
          after={Object.fromEntries(Object.keys(pendingPatch).map(k => [k, pendingPatch[k]]))} />
        <div className="row" style={{ marginTop: 12 }}><button className="btn primary" onClick={applySave}>تأیید و ذخیره</button>
          <button className="btn" onClick={() => setPendingPatch(null)}>بازگشت</button></div>
      </Modal>}
      {confirm && (
        <Confirm text={confirm.text} danger={confirm.danger}
                 onYes={async () => { await runAction(confirm.action); setConfirm(null); }}
                 onNo={() => setConfirm(null)} />
      )}
      {blockModal && (
        <Modal title={`⛔ مسدودسازی «${u.name || row.id}»`} onClose={() => setBlockModal(false)}>
          <p className="muted" style={{ marginBottom: 8 }}>
            کاربر به لیست سیاه اضافه می‌شود و دسترسی‌اش به ربات/مینی‌اپ قطع خواهد شد.</p>
          <input className="inp" style={{ width: '100%' }} placeholder="دلیل مسدودسازی (در لیست سیاه نمایش داده می‌شود)…"
                 value={reason} onChange={e => setReason(e.target.value)} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn danger" disabled={busy} onClick={async () => {
              setBlockModal(false); await runAction('block', reason.trim());
            }}>⛔ مسدود کن</button>
            <button className="btn" onClick={() => setBlockModal(false)}>انصراف</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ── ⛔🌊 WA3 — لیست سیاه + رفع مسدودیت ─────────────────────── */
function BlacklistModal({ me, onClose }) {
  const canDelete = !!me?.is_owner || (me?.perms || []).includes('users.delete');
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const load = async () => {
    setErr('');
    try { setItems((await api.blacklist()).blacklist || []); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);
  const unblock = async (uid) => {
    try { await api.waUserAction(uid, 'unblock'); toast('رفع مسدودیت شد 🕊'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return (
    <Modal title="⛔ لیست سیاه — کاربران مسدودشده" onClose={onClose}>
      {err ? <ErrorState error={err} onRetry={load} /> : !items ? <Loading /> : (
        <div className="grid" style={{ gap: 6, maxHeight: '60vh', overflowY: 'auto' }}>
          {items.length === 0 && <Empty icon="🕊" text="هیچ کاربر مسدودشده‌ای نیست" />}
          {items.map(b => (
            <div key={b.id} className="row" style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 10 }}>
              <span>⛔</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ color: 'var(--txt)' }}>{b.name || `#${b.id}`}</b>{' '}
                <span className="code muted">{b.id}</span>
                <div className="muted">{b.blocked_by_name ? `توسط ${b.blocked_by_name}` : ''} {b.blocked_at || ''}</div>
              </div>
              {canDelete && <button className="btn sm ok" onClick={() => unblock(b.id)}>🕊 رفع مسدودیت</button>}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

/* ── 📅🌊 مودال مدیریت ورودی‌ها (موج Intakes-CA) — همان امکانات admin:intakes ربات ── */
function IntakesModal({ onClose }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const [code, setCode] = useState('');
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const [delCode, setDelCode] = useState(null);
  const load = async () => {
    setErr('');
    try { setItems((await api.intakes()).intakes || []); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);
  const add = async () => {
    if (!code.trim() || !label.trim()) return;
    setBusy(true);
    try { await api.intakeAdd(code.trim(), label.trim()); toast('ورودی افزوده شد 📅'); setCode(''); setLabel(''); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const toggle = async (c) => {
    try { const r = await api.intakeToggle(c); toast(r.active ? 'فعال شد ✅' : 'غیرفعال شد'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const del = async (c) => {
    try { await api.intakeDel(c); toast('ورودی حذف شد 🗑'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return (
    <Modal title="📅 مدیریت ورودی‌ها" onClose={() => onClose(true)}>
      {err ? <ErrorState error={err} onRetry={load} /> : !items ? <Loading /> : (<>
        <div className="grid" style={{ gap: 6, maxHeight: '46vh', overflowY: 'auto' }}>
          {items.length === 0 && <Empty icon="📅" text="هنوز ورودی‌ای تعریف نشده" />}
          {items.map(i => (
            <div key={i.code} className="intake-row">
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ color: 'var(--txt)' }}>{i.label || i.code}</b>{' '}
                <span className="code muted">{i.code}</span>
                <div className="muted">
                  👥 {faNum(i.total ?? 0)} دانشجو
                  {i.groups && Object.keys(i.groups).length > 0 &&
                    ` · ${Object.entries(i.groups).map(([g, c]) => `گروه ${faNum(g)}: ${faNum(c)}`).join(' | ')}`}
                </div>
              </div>
              <label className="row" style={{ gap: 5 }} title="پذیرش ورودی">
                <Switch on={i.active !== false} onChange={() => toggle(i.code)} />
                <span className="muted" style={{ fontSize: 11 }}>{i.active !== false ? 'فعال' : 'متوقف'}</span>
              </label>
              <button className="btn sm danger" onClick={() => setDelCode(i.code)} aria-label={`حذف ورودی ${i.label || i.code}`}>🗑</button>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 12, flexWrap: 'wrap', gap: 6 }}>
          <input className="inp" style={{ flex: 1, minWidth: 110 }} dir="ltr" placeholder="کد (مثل mehr_1405)"
                 value={code} onChange={e => setCode(e.target.value)} />
          <input className="inp" style={{ flex: 1, minWidth: 110 }} placeholder="برچسب (مهر ۱۴۰۵)"
                 value={label} onChange={e => setLabel(e.target.value)} />
          <button className="btn primary sm" disabled={busy || !code.trim() || !label.trim()} onClick={add}>
            {busy ? '⏳' : '➕ افزودن'}
          </button>
        </div>
        <div className="muted" style={{ marginTop: 6 }}>غیرفعال‌سازی = توقف پذیرش جدید؛ داده‌های ورودی حفظ می‌شود.</div>
      </>)}
      {delCode && (
        <Confirm text={`حذف ورودی «${delCode}»؟ (کاربرانش حذف نمی‌شوند ولی کد ورودی آزاد می‌شود)`} danger
                 onYes={async () => { const c = delCode; setDelCode(null); await del(c); }}
                 onNo={() => setDelCode(null)} />
      )}
    </Modal>
  );
}

/* ── 🎓🌊 مودال ادمین‌های محتوا (موج Intakes-CA) — همان admin:content_admins ربات ── */
function ContentAdminsModal({ onClose }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const [uid, setUid] = useState('');
  const [busy, setBusy] = useState(false);
  const [revoke, setRevoke] = useState(null);
  const load = async () => {
    setErr('');
    try { setItems((await api.contentAdmins()).admins || []); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);
  const grant = async () => {
    const id = parseInt(uid, 10);
    if (!id) return;
    setBusy(true);
    try { await api.contentAdminAdd(id); toast('دسترسی ادمین محتوا داده شد 🎓'); setUid(''); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const doRevoke = async (id) => {
    try { await api.contentAdminDel(id); toast('دسترسی لغو شد'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return (
    <Modal title="🎓 ادمین‌های محتوا (scope ورودی)" onClose={onClose}>
      {err ? <ErrorState error={err} onRetry={load} /> : !items ? <Loading /> : (<>
        <div className="grid" style={{ gap: 6, maxHeight: '46vh', overflowY: 'auto' }}>
          {items.length === 0 && <Empty icon="🎓" text="هنوز ادمین محتوایی تعریف نشده" />}
          {items.map(a => (
            <div key={a.id} className="row" style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 10 }}>
              <span>🎓</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ color: 'var(--txt)' }}>{a.name || `#${a.id}`}</b>{' '}
                <span className="code muted">{a.id}</span>
              </div>
              <button className="btn sm danger" onClick={() => setRevoke(a)}>لغو دسترسی</button>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 12, gap: 6 }}>
          <input className="inp" style={{ flex: 1 }} dir="ltr" inputMode="numeric"
                 placeholder="Telegram ID کاربر (عددی)…" value={uid} onChange={e => setUid(e.target.value)} />
          <button className="btn primary sm" disabled={busy || !/^\d+$/.test(uid.trim())} onClick={grant}>
            {busy ? '⏳' : '➕ اعطای دسترسی'}
          </button>
        </div>
        <div className="muted" style={{ marginTop: 6 }}>اعطا ⇒ نقش content_admin + اطلاع‌رسانی خودکار در ربات · لغو ⇒ بازگشت به دانشجو. هر دو در audit ثبت می‌شوند.</div>
      </>)}
      {revoke && (
        <Confirm text={`لغو دسترسی ادمین محتوای «${revoke.name || revoke.id}»؟ (به نقش دانشجو برمی‌گردد)`} danger
                 onYes={async () => { const a = revoke; setRevoke(null); await doRevoke(a.id); }}
                 onNo={() => setRevoke(null)} />
      )}
    </Modal>
  );
}
