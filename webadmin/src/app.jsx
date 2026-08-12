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
import Notify from './pages/Notify.jsx';
import AiAdmin from './pages/AiAdmin.jsx';
import System from './pages/System.jsx';
import Analytics from './pages/Analytics.jsx';

const NAV = [
  { sec: 'کلان' },
  { path: '/dashboard', icon: '📊', label: 'داشبورد' },
  { path: '/analytics', icon: '📈', label: 'تحلیل‌ها' },
  { sec: 'عملیات' },
  { path: '/users',      icon: '👥', label: 'کاربران' },
  { path: '/tickets',    icon: '🎫', label: 'تیکت‌ها' },
  { path: '/subscriptions', icon: '💎', label: 'اشتراک‌ها و رسیدها' },
  { path: '/notify',     icon: '🔔', label: 'اعلان‌ها و همگانی' },
  { sec: 'محتوا' },
  { path: '/content',    icon: '📚', label: 'مدیریت محتوا' },
  { path: '/questions',  icon: '🧪', label: 'بازبینی سوالات' },
  { path: '/ai',         icon: '🤖', label: 'هوشیار' },
  { sec: 'سیستم' },
  { path: '/rbac',       icon: '🛡', label: 'نقش‌ها و مجوزها' },
  { path: '/audit',      icon: '🧭', label: 'لاگ حسابرسی' },
  { path: '/system',     icon: '🖥', label: 'سلامت سامانه' },
];

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
  const [mini, setMini] = useState(false);
  const [pal, setPal] = useState(false);

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

  const commands = useMemo(() => [
    ...NAV.filter(n => n.path).map(n => ({
      icon: n.icon, label: `رفتن به ${n.label}`, hint: n.path, run: () => go(n.path),
    })),
    { icon: '🚪', label: 'خروج از حساب', hint: 'logout', run: async () => { try { await api.logout(); } catch {} setMe(null); } },
  ], [go]);

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
    '/content': Content, '/questions': Questions, '/notify': Notify,
    '/ai': AiAdmin, '/system': System, '/analytics': Analytics,
  }[route.split('?')[0]] || Dashboard;

  return (
    <div className="shell">
      <aside className={`sidebar ${mini ? 'mini' : ''}`}>
        <div className="brand">
          <div className="logo">🏥</div>
          <div className="brand-txt"><b>هامزیار</b><small>مرکز فرماندهی</small></div>
        </div>
        {NAV.map((n, i) => n.sec
          ? <div key={i} className="nav-sec">{n.sec}</div>
          : (
            <a key={n.path} className={`nav-item ${route.startsWith(n.path) ? 'on' : ''}`}
               href={`#${n.path}`}>
              <span className="ic">{n.icon}</span><span className="nl">{n.label}</span>
            </a>
          ))}
        <div style={{ marginTop: 'auto', padding: 8 }}>
          <button className="btn sm" style={{ width: '100%' }} onClick={() => setMini(!mini)}>
            {mini ? '⇤' : '⇥ جمع‌کردن'}
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <button className="btn sm" onClick={() => setPal(true)}>⌘K / Ctrl+K</button>
          <span className="badge acc">وب‌ادمین دسکتاپ</span>
          {me.is_owner && <span className="badge purple">مالک سامانه</span>}
          <div className="who">
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{me.nickname || me.name}</div>
              <div className="muted">{me.role_label || ''}</div>
            </div>
            <div className="avatar">{(me.name || '?')[0]}</div>
            <button className="btn sm" title="خروج"
                    onClick={async () => { try { await api.logout(); } catch {} setMe(null); }}>🚪</button>
          </div>
        </div>
        <div className="content">
          <Page me={me} go={go} />
        </div>
      </div>

      <Palette open={pal} onClose={setPal} commands={commands} />
      <ToastHost />
    </div>
  );
}

export { toast, errText };
