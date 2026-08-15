import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, errText } from './api.js';
import { ErrorState, Loading, Palette, ToastHost, toast } from './ui.jsx';
import Login from './pages/Login.jsx';

const Dashboard = lazy(() => import('./pages/Dashboard.jsx'));
const Users = lazy(() => import('./pages/Users.jsx'));
const Tickets = lazy(() => import('./pages/Tickets.jsx'));
const Subscriptions = lazy(() => import('./pages/Subscriptions.jsx'));
const Rbac = lazy(() => import('./pages/Rbac.jsx'));
const Audit = lazy(() => import('./pages/Audit.jsx'));
const Content = lazy(() => import('./pages/Content.jsx'));
const Questions = lazy(() => import('./pages/Questions.jsx'));
const Exams = lazy(() => import('./pages/Exams.jsx'));
const Notify = lazy(() => import('./pages/Notify.jsx'));
const AiAdmin = lazy(() => import('./pages/AiAdmin.jsx'));
const System = lazy(() => import('./pages/System.jsx'));
const Settings = lazy(() => import('./pages/Settings.jsx'));
const Analytics = lazy(() => import('./pages/Analytics.jsx'));
const TransferCenter = lazy(() => import('./pages/TransferCenter.jsx'));

const NAV_GROUPS = [
  { sec: 'نمای کلی', items: [
    { path: '/dashboard', icon: '📊', label: 'داشبورد' },
  ] },
  { sec: 'افراد', items: [
    { path: '/users', icon: '👥', label: 'کاربران', any: ['users.view', 'users.manage'] },
    { path: '/rbac', icon: '🛡', label: 'نقش‌ها و مجوزها', any: ['roles.manage'] },
  ] },
  { sec: 'آموزش', items: [
    { path: '/content', icon: '📚', label: 'محتوا', any: ['content.manage', 'content.scoped', 'reports.review'], content: true },
    { path: '/questions', icon: '🧪', label: 'سؤال‌ها', any: ['questions.review', 'questions.review_scoped'] },
    { path: '/exams', icon: '📝', label: 'آزمون‌ها', any: ['schedules.manage'] },
    { path: '/exams?tab=grades', icon: '📊', label: 'نمرات', any: ['grades.manage', 'grades.scoped'] },
    { path: '/content?tab=schedule', icon: '🗓', label: 'برنامه', any: ['schedules.manage'] },
  ] },
  { sec: 'هوش مصنوعی', items: [
    { path: '/ai', icon: '🤖', label: 'هوشیار', any: ['ai.manage'] },
  ] },
  { sec: 'ارتباطات', items: [
    { path: '/tickets', icon: '🎫', label: 'تیکت‌ها', any: ['tickets.reply', 'tickets.manage'] },
    { path: '/notify', icon: '🔔', label: 'اعلان‌ها', any: ['notifications.manage', 'broadcast.send'] },
  ] },
  { sec: 'مالی', items: [
    { path: '/subscriptions', icon: '💎', label: 'اشتراک‌ها', any: ['subscription.manage'] },
    { path: '/subscriptions?tab=payments', icon: '🧾', label: 'رسیدها', any: ['subscription.manage'] },
    { path: '/subscriptions?tab=discounts', icon: '🎁', label: 'تخفیف‌ها', any: ['subscription.manage'] },
  ] },
  { sec: 'سیستم', items: [
    { path: '/analytics', icon: '📈', label: 'تحلیل‌ها', any: ['stats.view'] },
    { path: '/audit', icon: '🧭', label: 'حسابرسی', any: ['audit.view'] },
    { path: '/system', icon: '🖥', label: 'سلامت و پشتیبان', any: ['system.manage', 'backup.manage', 'prestige.manage', 'notifications.manage'] },
    { path: '/settings', icon: '⚙️', label: 'تنظیمات', any: ['settings.manage', 'notifications.manage', 'backup.manage'] },
    { path: '/transfer', icon: '↕️', label: 'انتقال داده', any: ['users.view', 'questions.review', 'questions.review_scoped', 'grades.manage', 'grades.scoped', 'backup.manage', 'audit.view'] },
  ] },
];

const PAGES = {
  '/dashboard': Dashboard, '/users': Users, '/tickets': Tickets,
  '/subscriptions': Subscriptions, '/rbac': Rbac, '/audit': Audit,
  '/content': Content, '/questions': Questions, '/exams': Exams, '/notify': Notify,
  '/ai': AiAdmin, '/system': System, '/settings': Settings, '/analytics': Analytics,
  '/transfer': TransferCenter,
};

const routeBase = route => route.split('?')[0];
const canSee = (item, me) => {
  if (me?.is_owner || !item.any?.length) return true;
  if (item.content && me?.is_content_admin) return true;
  const perms = new Set(me?.perms || []);
  return item.any.some(p => perms.has(p));
};

function visibleGroups(me) {
  return NAV_GROUPS.map(g => ({ ...g, items: g.items.filter(i => canSee(i, me)) })).filter(g => g.items.length);
}

function crumbFor(route, groups) {
  for (const group of groups) {
    const exact = group.items.find(n => n.path === route);
    if (exact) return { sec: group.sec, ...exact };
  }
  for (const group of groups) {
    const base = group.items.find(n => n.path === routeBase(route));
    if (base) return { sec: group.sec, ...base };
  }
  return { sec: 'نمای کلی', label: 'داشبورد', icon: '📊' };
}

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash.replace(/^#/, '') || '/dashboard');
  useEffect(() => {
    const handler = () => setHash(window.location.hash.replace(/^#/, '') || '/dashboard');
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);
  const go = useCallback(path => { window.location.hash = path; }, []);
  return [hash, go];
}

export default function App() {
  const [me, setMe] = useState(undefined);
  const [route, go] = useHashRoute();
  const [mini, setMini] = useState(() => localStorage.getItem('wa_mini') === '1');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [attention, setAttention] = useState(0);
  const [system, setSystem] = useState(null);
  const shortcutPrefix = useRef(false);

  const loadMe = useCallback(() => {
    setMe(undefined);
    api.me().then(setMe).catch(() => setMe(null));
  }, []);
  useEffect(loadMe, [loadMe]);
  useEffect(() => {
    const unauthorized = () => setMe(null);
    window.addEventListener('wa:unauthorized', unauthorized);
    return () => window.removeEventListener('wa:unauthorized', unauthorized);
  }, []);
  useEffect(() => { localStorage.setItem('wa_mini', mini ? '1' : '0'); }, [mini]);

  const groups = useMemo(() => visibleGroups(me), [me]);
  const flatNav = useMemo(() => groups.flatMap(g => g.items), [groups]);
  const hasAny = useCallback((...keys) => !!me?.is_owner || keys.some(k => (me?.perms || []).includes(k)), [me]);

  useEffect(() => {
    if (!me) return;
    api.attention().then(r => setAttention((r.items || []).reduce((a, i) => a + Number(i.count || 0), 0))).catch(() => setAttention(0));
    if (hasAny('system.manage', 'backup.manage', 'prestige.manage', 'settings.manage', 'notifications.manage')) {
      api.botStatus().then(setSystem).catch(() => setSystem(null));
    }
  }, [!!me, route, hasAny]);

  useEffect(() => {
    const map = { d: '/dashboard', u: '/users', c: '/content', q: '/questions', e: '/exams',
      g: '/exams?tab=grades', t: '/tickets', n: '/notify', s: '/subscriptions', a: '/analytics' };
    let timer;
    const handler = e => {
      const tag = e.target?.tagName?.toLowerCase();
      if (['input', 'textarea', 'select'].includes(tag) || e.ctrlKey || e.metaKey || e.altKey) return;
      if (shortcutPrefix.current && map[e.key.toLowerCase()]) {
        e.preventDefault(); shortcutPrefix.current = false; go(map[e.key.toLowerCase()]); return;
      }
      if (e.key.toLowerCase() === 'g') {
        shortcutPrefix.current = true; window.clearTimeout(timer);
        timer = window.setTimeout(() => { shortcutPrefix.current = false; }, 900);
      }
    };
    window.addEventListener('keydown', handler);
    return () => { window.removeEventListener('keydown', handler); window.clearTimeout(timer); };
  }, [go]);

  useEffect(() => {
    const tabKeys = e => {
      const tab = e.target?.closest?.('[role="tab"]');
      if (!tab || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
      const list = tab.closest('[role="tablist"]');
      const tabs = [...(list?.querySelectorAll('[role="tab"]') || [])].filter(x => !x.disabled);
      if (!tabs.length) return;
      const current = tabs.indexOf(tab);
      const rtl = getComputedStyle(list).direction === 'rtl';
      let next = current;
      if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = tabs.length - 1;
      else if (e.key === 'ArrowRight') next = (current + (rtl ? -1 : 1) + tabs.length) % tabs.length;
      else if (e.key === 'ArrowLeft') next = (current + (rtl ? 1 : -1) + tabs.length) % tabs.length;
      e.preventDefault(); tabs[next].focus(); tabs[next].click();
    };
    document.addEventListener('keydown', tabKeys);
    return () => document.removeEventListener('keydown', tabKeys);
  }, []);

  const commands = useMemo(() => {
    const list = flatNav.map(n => ({ icon: n.icon, label: `رفتن به ${n.label}`, hint: n.path, run: () => go(n.path) }));
    if (hasAny('content.manage', 'content.scoped')) list.push({ icon: '➕', label: 'محتوای جدید', hint: 'آموزش', run: () => go('/content') });
    if (hasAny('questions.review', 'questions.review_scoped')) list.push({ icon: '🧪', label: 'ساخت سؤال جدید', hint: 'آموزش', run: () => go('/questions?create=1') });
    if (hasAny('schedules.manage')) list.push({ icon: '📝', label: 'آزمون جدید', hint: 'آموزش', run: () => go('/exams?new=exam') });
    if (hasAny('grades.manage', 'grades.scoped')) list.push({ icon: '📊', label: 'ثبت نمره جدید', hint: 'آموزش', run: () => go('/exams?tab=grades&new=grade') });
    if (hasAny('broadcast.send')) list.push({ icon: '📢', label: 'ارسال همگانی جدید', hint: 'ارتباطات', run: () => go('/notify?new=1') });
    list.push({ icon: '🚪', label: 'خروج از حساب', hint: 'logout', run: async () => { try { await api.logout(); } catch {} setMe(null); } });
    return list;
  }, [flatNav, go, hasAny]);

  const paletteSearch = useCallback(async q => {
    const r = await api.waSearch(q); const out = [];
    (r.users || []).forEach(u => out.push({ id: `u-${u.id}`, group: 'کاربران', icon: '👤', label: `${u.name || '—'} · ${u.student_id || u.id}`, hint: u.intake || '', go: '/users' }));
    (r.content || []).forEach(c => out.push({ id: `c-${c.path || c.title}`, group: 'محتوا', icon: '📚', label: c.title || '—', hint: c.type, go: '/content' }));
    (r.questions || []).forEach(x => out.push({ id: `q-${x.id}`, group: 'سؤال‌ها', icon: '🧪', label: x.text, hint: `${x.lesson} · ${x.topic}`, go: '/questions' }));
    (r.exams || []).forEach(x => out.push({ id: `e-${x.id}`, group: 'آزمون‌ها', icon: '📝', label: x.lesson, hint: `${x.date} · گروه ${x.group}`, go: '/exams' }));
    (r.tickets || []).forEach(t => out.push({ id: `t-${t.id}`, group: 'تیکت‌ها', icon: '🎫', label: `#${t.id} ${t.subject}`, hint: t.status, go: '/tickets' }));
    (r.payments || []).forEach(p => out.push({ id: `p-${p.id}`, group: 'پرداخت‌ها', icon: '🧾', label: `${p.plan} · #${p.user_id}`, hint: p.status, go: '/subscriptions?tab=payments' }));
    (r.subscriptions || []).forEach(s => out.push({ id: `s-${s.user_id}`, group: 'اشتراک‌ها', icon: '💎', label: `${s.plan} · #${s.user_id}`, hint: s.status, go: '/subscriptions?tab=subscribers' }));
    (r.notifications || []).forEach(n => out.push({ id: `n-${n.id}`, group: 'اعلان‌ها', icon: '🔔', label: n.text, hint: n.type, go: '/notify' }));
    (r.audit || []).forEach(a => out.push({ id: `a-${a.id}`, group: 'حسابرسی', icon: '🧭', label: `${a.actor} — ${a.action}`, hint: a.at, go: '/audit' }));
    return out;
  }, []);

  if (me === undefined) return <div className="login-hero"><Loading rows={1} variant="kpi" label="در حال بررسی نشست" /></div>;
  if (me === null) return <><Login onDone={loadMe} /><ToastHost /></>;

  const base = routeBase(route);
  const Page = PAGES[base] || Dashboard;
  const crumb = crumbFor(route, groups);
  const systemOk = system && system.bot_ok === true && system.db_ok === true && system.api_ok === true;

  return <><a className="skip-link" href="#main-content" onClick={e => {
    e.preventDefault(); document.getElementById('main-content')?.focus();
  }}>پرش به محتوای اصلی</a><div className="shell">
    <aside className={`sidebar ${mini ? 'mini' : ''}`} aria-label="ناوبری اصلی">
      <a className="brand" href="#/dashboard" aria-label="هامزیار — داشبورد">
        <div className="logo" aria-hidden="true">🏥</div>
        <div className="brand-txt"><b>هامزیار</b><small>مرکز فرماندهی</small></div>
      </a>
      <nav>
        {groups.map(group => <React.Fragment key={group.sec}>
          <div className="nav-sec">{group.sec}</div>
          {group.items.map(n => <a key={n.path} className={`nav-item ${route === n.path || (routeBase(route) === n.path && !route.includes('?')) ? 'on' : ''}`}
            href={`#${n.path}`} title={mini ? n.label : undefined} aria-current={route === n.path ? 'page' : undefined}>
            <span className="ic" aria-hidden="true">{n.icon}</span><span className="nl">{n.label}</span>
            {n.path === '/dashboard' && attention > 0 && <span className="nav-badge">{attention > 99 ? '۹۹+' : attention.toLocaleString('fa')}</span>}
          </a>)}
        </React.Fragment>)}
      </nav>
      <div className="sidebar-toggle"><button className="btn sm" aria-label={mini ? 'بازکردن سایدبار' : 'جمع‌کردن سایدبار'}
        title={mini ? 'بازکردن سایدبار' : 'جمع‌کردن سایدبار'} onClick={() => setMini(v => !v)}>{mini ? '⇤' : '⇥ جمع‌کردن'}</button></div>
    </aside>

    <div className="main">
      <div className="topbar">
        <div className="crumb" aria-label="مسیر صفحه"><span className="c-sec">{crumb.sec}</span><span className="c-sep">‹</span><span className="c-page">{crumb.icon} {crumb.label}</span></div>
        <button className="btn sm topbar-search" onClick={() => setPaletteOpen(true)} aria-label="جست‌وجو و فرمان">
          <span>🔎 جست‌وجو و فرمان</span><span className="kbd">Ctrl K</span>
        </button>
        <div className="topbar-actions">
          {system && <button className={`btn sm topbar-action system-pill ${systemOk ? 'ok' : 'bad'}`} onClick={() => go('/system')} title="سلامت سامانه"><span>{systemOk ? 'سالم' : 'نیازمند بررسی'}</span></button>}
          <button className="btn sm topbar-action" onClick={() => go('/dashboard')} aria-label="موارد نیازمند اقدام" title="موارد نیازمند اقدام">🔔{attention > 0 && <span className="topbar-count">{attention > 99 ? '99+' : attention}</span>}</button>
          {me.is_owner && <span className="badge purple">مالک</span>}
          <div className="who"><div className="profile-meta"><div className="profile-name">{me.nickname || me.name}</div><div className="muted">{me.role_label || ''}</div></div>
            <div className="avatar" aria-hidden="true">{(me.name || '?')[0]}</div>
            <button className="btn sm topbar-action" title="خروج از حساب" aria-label="خروج از حساب" onClick={async () => { try { await api.logout(); } catch {} setMe(null); }}>🚪</button>
          </div>
        </div>
      </div>
      <main className="content" id="main-content" tabIndex={-1}>
        <Suspense fallback={<Loading rows={5} variant="tree" label="در حال بارگذاری صفحه" />}>
          <Page me={me} go={go} route={route} />
        </Suspense>
      </main>
    </div>

    <Palette open={paletteOpen} onClose={setPaletteOpen} commands={commands} search={paletteSearch} go={go} />
    <ToastHost />
  </div></>;
}

export { toast, errText };
