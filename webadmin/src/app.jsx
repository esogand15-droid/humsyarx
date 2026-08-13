import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from './api.js';
import { ToastHost, Palette, toast } from './ui.jsx';
import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Users from './pages/Users.jsx';
import Tickets from './pages/Tickets.jsx';
import Subscriptions from './pages/Subscriptions.jsx';
import Rbac from './pages/Rbac.jsx';
import Audit from './pages/Audit.jsx';
import Content from './pages/Content.jsx';
import Questions from './pages/Questions.jsx';
import Exams from './pages/Exams.jsx';
import Notify from './pages/Notify.jsx';
import AiAdmin from './pages/AiAdmin.jsx';
import System from './pages/System.jsx';
import Settings from './pages/Settings.jsx';
import Analytics from './pages/Analytics.jsx';

// 🎛🌊 W-Design 2 — ناوبری گروه‌بندی‌شده‌ی Command Center (فقط صفحات واقعی)
const NAV = [
  { sec: 'نمای کلی' },
  { path: '/dashboard', icon: '📊', label: 'داشبورد' },
  { path: '/analytics', icon: '📈', label: 'تحلیل‌ها' },
  { sec: 'افراد' },
  { path: '/users',      icon: '👥', label: 'کاربران' },
  { path: '/rbac',       icon: '🛡', label: 'نقش‌ها و مجوزها' },
  { sec: 'آموزش' },
  { path: '/content',    icon: '📚', label: 'مرکز فرماندهی محتوا' },
  { path: '/questions',  icon: '🧪', label: 'بازبینی سوالات' },
  { path: '/exams',      icon: '📝', label: 'آزمون‌ها و نمرات' },
  { sec: 'هوش مصنوعی' },
  { path: '/ai',         icon: '🤖', label: 'هوشیار' },
  { sec: 'ارتباطات' },
  { path: '/tickets',    icon: '🎫', label: 'تیکت‌ها' },
  { path: '/notify',     icon: '🔔', label: 'اعلان‌ها و همگانی' },
  { sec: 'مالی' },
  { path: '/subscriptions', icon: '💎', label: 'اشتراک‌ها و رسیدها' },
  { sec: 'سیستم' },
  { path: '/settings',   icon: '⚙️', label: 'تنظیمات' },
  { path: '/audit',      icon: '🧭', label: 'لاگ حسابرسی' },
  { path: '/system',     icon: '🖥', label: 'سلامت سامانه' },
];

// مسیر فعلی → [گروه، برچسب، آیکون] برای Breadcrumb
function crumbFor(route) {
  const path = route.split('?')[0];
  let sec = 'نمای کلی';
  for (const n of NAV) {
    if (n.sec) sec = n.sec;
    else if (n.path === path) return { sec, label: n.label, icon: n.icon };
  }
  return { sec: 'نمای کلی', label: 'داشبورد', icon: '📊' };
}

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash.replace(/^#/, '') || '/dashboard');
  useEffect(() => {
    const h = () => setHash(window.location.hash.replace(/^#/, '') || '/dashboard');
    window.addEventListener('hashchange', h);
    return () => window.removeEventListener('hashchange', h);
  }, []);
  const go = (p) => { window.location.hash = p; };
  return [hash, go];
}

export default function App() {
  const [me, setMe] = useState(undefined);      // undefined=loading, null=guest
  const [route, go] = useHashRoute();
  const [mini, setMini] = useState(() => localStorage.getItem('wa_mini') === '1');
  const [pal, setPal] = useState(false);
  const [attn, setAttn] = useState(0);          // 🌊 جمع صف‌های نیازمند اقدام

  const loadMe = () => {
    setMe(undefined);
    api.me().then(setMe).catch(() => setMe(null));
  };
  useEffect(loadMe, []);
  useEffect(() => {
    const h = () => setMe(null);
    window.addEventListener('wa:unauthorized', h);
    return () => window.removeEventListener('wa:unauthorized', h);
  }, []);
  useEffect(() => { localStorage.setItem('wa_mini', mini ? '1' : '0'); }, [mini]);
  // نشان توجه: یک‌بار پس از ورود
  useEffect(() => {
    if (!me) return;
    api.attention()
      .then(r => setAttn((r.items || []).reduce((a, i) => a + (i.count || 0), 0)))
      .catch(() => {});
  }, [!!me]);

  const commands = useMemo(() => [
    ...NAV.filter(n => n.path).map(n => ({
      icon: n.icon, label: `رفتن به ${n.label}`, hint: n.path, run: () => go(n.path),
    })),
    { icon: '🚪', label: 'خروج از حساب', hint: 'logout', run: async () => { try { await api.logout(); } catch {} setMe(null); } },
  ], [go]);

  // 🔎🌊 WA2.5 — جست‌وجوی سراسری پالت (گروه‌بندی‌شده → ناوبری مستقیم)
  const paletteSearch = async (q) => {
    const r = await api.waSearch(q);
    const out = [];
    (r.users || []).forEach(u => out.push({
      group: 'کاربران', icon: '👤',
      label: `${u.name || '—'} · ${u.student_id || u.id}`,
      hint: u.intake || '', go: `/users`,
    }));
    (r.tickets || []).forEach(t => out.push({
      group: 'تیکت‌ها', icon: '🎫', label: `#${t.id} ${t.subject}`, hint: t.status, go: '/tickets',
    }));
    (r.questions || []).forEach(x => out.push({
      group: 'سؤال‌ها', icon: '🧪', label: x.text, hint: `${x.lesson} · ${x.topic}`, go: '/questions',
    }));
    (r.content || []).forEach(c => out.push({
      group: 'محتوا', icon: '📚', label: c.title || '—', hint: c.type, go: '/content',
    }));
    (r.audit || []).forEach(a => out.push({
      group: 'رویدادها', icon: '🧭', label: `${a.actor} — ${a.action}`, hint: a.at, go: '/audit',
    }));
    return out;
  };

  if (me === undefined) {
    return <div className="login-hero"><div className="skel" style={{ width: 200, height: 60 }} /></div>;
  }
  if (me === null) {
    return (<>
      <Login onDone={loadMe} />
      <ToastHost />
    </>);
  }

  const Page = {
    '/dashboard': Dashboard, '/users': Users, '/tickets': Tickets,
    '/subscriptions': Subscriptions, '/rbac': Rbac, '/audit': Audit,
    '/content': Content, '/questions': Questions, '/exams': Exams, '/notify': Notify,
    '/ai': AiAdmin, '/system': System, '/settings': Settings, '/analytics': Analytics,
  }[route.split('?')[0]] || Dashboard;
  const crumb = crumbFor(route);

  return (
    <div className="shell">
      <aside className={`sidebar ${mini ? 'mini' : ''}`} aria-label="ناوبری اصلی">
        <div className="brand">
          <div className="logo">🏥</div>
          <div className="brand-txt"><b>هامزیار</b><small>مرکز فرماندهی</small></div>
        </div>
        <nav>
          {NAV.map((n, i) => n.sec
            ? <div key={i} className="nav-sec">{n.sec}</div>
            : (
              <a key={n.path} className={`nav-item ${route.startsWith(n.path) ? 'on' : ''}`}
                 href={`#${n.path}`} title={mini ? n.label : undefined}
                 aria-current={route.startsWith(n.path) ? 'page' : undefined}>
                <span className="ic">{n.icon}</span><span className="nl">{n.label}</span>
                {n.path === '/dashboard' && attn > 0 &&
                  <span className="nav-badge" title="موارد نیازمند اقدام">{attn > 99 ? '۹۹+' : attn.toLocaleString('fa')}</span>}
              </a>
            ))}
        </nav>
        <div style={{ marginTop: 'auto', padding: '8px 2px' }}>
          <button className="btn sm" style={{ width: '100%' }} aria-label="جمع‌کردن سایدبار"
                  title={mini ? 'بازکردن سایدبار' : 'جمع‌کردن سایدبار'}
                  onClick={() => setMini(!mini)}>
            {mini ? '⇤' : '⇥ جمع‌کردن'}
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div className="crumb" aria-label="breadcrumb">
            <span className="c-sec">{crumb.sec}</span>
            <span className="c-sep">‹</span>
            <span className="c-page">{crumb.icon} {crumb.label}</span>
          </div>
          <button className="btn sm" onClick={() => setPal(true)} aria-label="جست‌وجو و فرمان (Ctrl+K)">
            🔎 جست‌وجو / فرمان <span className="kbd">Ctrl K</span>
          </button>
          {me.is_owner && <span className="badge purple">مالک سامانه</span>}
          <div className="who">
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{me.nickname || me.name}</div>
              <div className="muted">{me.role_label || ''}</div>
            </div>
            <div className="avatar">{(me.name || '?')[0]}</div>
            <button className="btn sm" title="خروج از حساب" aria-label="خروج از حساب"
                    onClick={async () => { try { await api.logout(); } catch {} setMe(null); }}>🚪</button>
          </div>
        </div>
        <div className="content">
          <Page me={me} go={go} />
        </div>
      </div>

      <Palette open={pal} onClose={setPal} commands={commands} search={paletteSearch} go={go} />
      <ToastHost />
    </div>
  );
}

export { toast, errText };
