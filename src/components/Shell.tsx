import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Icon, type IconName } from './Icon';
import { Drawer, Toasts } from './ui';
import { useProto, type PreviewWidth, type VisualDirection } from '../lib/store';
import { notifications, student } from '../data/demo';
import emblem from '../assets/emblem.png';

/* ═══════════════════════════════════════════════════════════════════
   پوسته — سایدبار دسکتاپ، نوار بالا، سربرگ و نوار پایین موبایل.
   ترتیب ناوبری از نیاز واقعی دانشجو می‌آید:
   خانه ← منابع ← بانک سؤال ← هوشیار ← برنامه ← پیشرفت
   ═══════════════════════════════════════════════════════════════════ */

const NAV: { to: string; label: string; icon: IconName; tag?: string }[] = [
  { to: '/', label: 'خانه', icon: 'home' },
  { to: '/library', label: 'منابع درسی', icon: 'library' },
  { to: '/notes', label: 'یادداشت‌ها', icon: 'note' },
  { to: '/exam', label: 'بانک سؤال', icon: 'question' },
  { to: '/ai', label: 'هوشیار', icon: 'sparkle', tag: 'AI' },
  { to: '/plan', label: 'برنامهٔ مطالعه', icon: 'calendar' },
  { to: '/me', label: 'پیشرفت من', icon: 'chart' },
];

const NAV_MORE: { to: string; label: string; icon: IconName }[] = [
  { to: '/me/subscription', label: 'اشتراک و پرداخت', icon: 'card' },
  { to: '/me/settings', label: 'تنظیمات حساب', icon: 'settings' },
];

/* مستندات طراحی، بخشی از تجربهٔ دانشجو نیست؛ در ناوبری جدا نگه داشته می‌شود. */
const NAV_DOCS: { to: string; label: string; icon: IconName }[] = [
  { to: '/system', label: 'سیستم طراحی', icon: 'layers' },
  { to: '/capability', label: 'ماتریس قابلیت', icon: 'shield' },
  { to: '/handoff', label: 'سند تحویل', icon: 'book-open' },
];

const TITLES: Record<string, string> = {
  '/': 'خانه',
  '/library': 'منابع درسی',
  '/notes': 'یادداشت‌ها',
  '/exam': 'بانک سؤال',
  '/ai': 'هوشیار',
  '/plan': 'برنامهٔ مطالعه',
  '/me': 'پیشرفت من',
  '/me/subscription': 'اشتراک',
  '/me/settings': 'تنظیمات',
  '/system': 'سیستم طراحی',
  '/capability': 'ماتریس قابلیت',
  '/handoff': 'سند تحویل',
};

export function Shell({ children }: { children: ReactNode }) {
  const { theme, toggleTheme, preview, setPreview, direction, setDirection } = useProto();
  const [bellOpen, setBellOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const navigate = useNavigate();
  const unread = notifications.filter((n) => n.unread).length;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const standalone = document.documentElement.dataset.standalone === 'true';
  const { pathname } = useLocation();
  /* ابزار بازبینی فقط روی مسیرهای تحویل/سیستم دیده می‌شود، نه در تجربهٔ محصول */
  const reviewSurface = /^\/(handoff|system|capability)/.test(pathname);

  return (
    <>
    <div className="frame" data-preview={preview}>
    <div className="app app-bg">
      {/* ── سایدبار دسکتاپ ─────────────────────────────────── */}
      <aside className="sidebar" aria-label="ناوبری اصلی">
        <NavLink to="/" className="brand" aria-label="هامزیار — خانه">
          <span className="brand__mark">
            <img src={emblem} alt="" />
          </span>
          <span className="brand__txt">
            <span className="brand__name">
              Hums<b>Yar</b>
            </span>
            <span className="brand__sub">دستیار هوشمند دانشجویان پزشکی</span>
          </span>
        </NavLink>

        <nav className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'} className="nav__item">
              <Icon name={n.icon} size={19} className="ico" />
              <span>{n.label}</span>
              {n.tag && <span className="tag">{n.tag}</span>}
            </NavLink>
          ))}
          <div className="nav__label">بیشتر</div>
          {NAV_MORE.map((n) => (
            <NavLink key={n.to} to={n.to} className="nav__item">
              <Icon name={n.icon} size={19} className="ico" />
              <span>{n.label}</span>
            </NavLink>
          ))}
          <div className="nav__label nav__label--docs">مستندات طراحی</div>
          {NAV_DOCS.map((n) => (
            <NavLink key={n.to} to={n.to} className="nav__item nav__item--doc">
              <Icon name={n.icon} size={17} className="ico" />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__foot">
          <NavLink to="/me/settings" className="mini-profile">
            <span className="avatar">{student.initials}</span>
            <div style={{ minWidth: 0 }}>
              <div className="sm" style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                {student.name}
              </div>
              <div className="xs muted-2">
                {student.major} · {student.intake}
              </div>
            </div>
          </NavLink>
        </div>
      </aside>

      <div className="app__main">
        {/* ── نوار بالا ─────────────────────────────────────── */}
        <header className="topbar">
          <button type="button" className="search" onClick={() => setSearchOpen(true)} aria-label="جست‌وجو در منابع و سؤال‌ها">
            <Icon name="search" size={16} />
            <input readOnly placeholder="جست‌وجو در منابع، سؤال‌ها و هوشیار…" tabIndex={-1} aria-hidden="true" />
            <span className="kbd">Ctrl K</span>
          </button>

          <span className="grow" />
          <span className="demo-pill" title="محتوای این نسخه نمونه است">
            <span className="dot" /> دادهٔ نمونه
          </span>

          <button type="button" className="iconbtn" onClick={toggleTheme} aria-label={theme === 'dark' ? 'تم روشن' : 'تم تیره'} title="تغییر تم">
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          </button>

          <button type="button" className="iconbtn" onClick={() => setBellOpen(true)} aria-label={`اعلان‌ها — ${unread} خوانده‌نشده`}>
            <Icon name="bell" />
            {unread > 0 && <span className="iconbtn__dot" />}
          </button>

          <NavLink to="/ai" className="btn btn--ghost btn--sm" aria-label="گفتگو با هوشیار">
            <Icon name="sparkle" size={15} style={{ color: 'var(--cyan-400)' }} />
            هوشیار
          </NavLink>
        </header>

        {/* ── سربرگ موبایل ──────────────────────────────────── */}
        <div className="mobile-head">
          <span className="brand__mark" style={{ width: 30, height: 30 }}>
            <img src={emblem} alt="" />
          </span>
          <span className="mobile-head__t">هامزیار</span>
          <span className="demo-mini" title="محتوای این نسخه نمونه است">
            <span className="dot" /> نمونه
          </span>
          <span className="grow" />
          <button type="button" className="iconbtn" onClick={toggleTheme} aria-label="تغییر تم">
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          </button>
          <button type="button" className="iconbtn" onClick={() => setBellOpen(true)} aria-label="اعلان‌ها">
            <Icon name="bell" />
            {unread > 0 && <span className="iconbtn__dot" />}
          </button>
        </div>

        <main id="main">{children}</main>
      </div>

      {/* ── نوار پایین موبایل ─────────────────────────────── */}
      <nav className="tabbar" aria-label="ناوبری موبایل">
        {NAV.filter((n) => ['/', '/library', '/notes', '/exam', '/ai'].includes(n.to)).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'}>
            <Icon name={n.icon} size={20} />
            <span>{n.label.split(' ')[0]}</span>
          </NavLink>
        ))}
      </nav>

      {/* ── کشوی اعلان‌ها ──────────────────────────────────── */}
      <Drawer open={bellOpen} title="اعلان‌ها" onClose={() => setBellOpen(false)}>
        {notifications.map((n) => (
          <div key={n.id} className="panel panel--quiet" style={{ padding: 12 }}>
            <div className="row" style={{ gap: 8 }}>
              <Icon
                name={n.kind === 'ai' ? 'sparkle' : n.kind === 'exam' ? 'calendar' : 'file'}
                size={15}
                style={{ color: n.kind === 'ai' ? 'var(--cyan-400)' : 'var(--text-3)' }}
              />
              <b className="sm grow" style={{ fontWeight: 600 }}>
                {n.title}
              </b>
              {n.unread && <span className="dot" style={{ color: 'var(--cyan-400)' }} />}
            </div>
            <p className="xs muted" style={{ marginTop: 4 }}>
              {n.body}
            </p>
            <p className="xs muted-2" style={{ marginTop: 6 }}>
              {n.when}
            </p>
          </div>
        ))}
        <p className="xs muted-2">اعلان‌ها بر پایهٔ فعالیت همین هفته‌ات ساخته می‌شوند.</p>
      </Drawer>

      {/* ── جست‌وجوی سراسری ────────────────────────────────── */}
      <Drawer open={searchOpen} title="جست‌وجوی سراسری" onClose={() => setSearchOpen(false)}>
        <div className="search" style={{ minWidth: 0, maxWidth: 'none', flex: 'none' }}>
          <Icon name="search" size={16} />
          <input autoFocus placeholder="مثلاً «چرخهٔ قلبی» یا «تیامین»" aria-label="عبارت جست‌وجو" />
        </div>
        <p className="xs muted-2">در منابع، بانک سؤال و گفتگوهای هوشیار جست‌وجو کن.</p>
        {['جزوهٔ فیزیولوژی قلب — جلسهٔ ۷', 'چرخهٔ قلبی', 'سؤال: مکانیسم فرانک–استارلینگ'].map((s) => (
          <button
            key={s}
            type="button"
            className="rrow"
            style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)' }}
            onClick={() => {
              setSearchOpen(false);
              navigate('/library');
            }}
          >
            <span className="rrow__ic">
              <Icon name="search" size={16} />
            </span>
            <span className="rrow__t" style={{ textAlign: 'start' }}>
              {s}
            </span>
            <span />
            <span className="rrow__go">
              <Icon name="back" size={15} />
            </span>
          </button>
        ))}
      </Drawer>

      <Toasts />
    </div>
    </div>
      {!standalone && reviewSurface && (
        <PreviewDock preview={preview} setPreview={setPreview} direction={direction} setDirection={setDirection} />
      )}
    </>
  );
}

/* ── ابزار بازبینی پروتوتایپ (بیرون از تجربهٔ محصول) ─────────────── */
function PreviewDock({
  preview,
  setPreview,
  direction,
  setDirection,
}: {
  preview: PreviewWidth;
  setPreview: (v: PreviewWidth) => void;
  direction: VisualDirection;
  setDirection: (v: VisualDirection) => void;
}) {
  const [open, setOpen] = useState(false);
  const W: [PreviewWidth, string][] = [
    ['desktop', '۱۴۴۰'],
    ['tablet', '۷۶۸'],
    ['mobile', '۳۹۰'],
  ];
  const D: [VisualDirection, string][] = [
    ['intelligent', 'هوشمند'],
    ['quiet', 'آکادمیک'],
  ];

  return (
    <div
      className="review-dock"
      style={{ direction: 'rtl' }}
    >
      {open && (
        <div className="panel" style={{ padding: 12, width: 246, display: 'grid', gap: 10, boxShadow: 'var(--e-3)' }}>
          <div>
            <div className="xs muted-2" style={{ marginBottom: 6 }}>
              عرض بازبینی
            </div>
            <div className="seg" style={{ width: '100%' }}>
              {W.map(([k, label]) => (
                <button key={k} type="button" aria-pressed={preview === k} onClick={() => setPreview(k)} style={{ flex: 1 }}>
                  <span className="num">{label}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="xs muted-2" style={{ marginBottom: 6 }}>
              جهت بصری
            </div>
            <div className="seg" style={{ width: '100%' }}>
              {D.map(([k, label]) => (
                <button key={k} type="button" aria-pressed={direction === k} onClick={() => setDirection(k)} style={{ flex: 1 }}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <NavLink to="/handoff" className="btn btn--ghost btn--sm btn--block">
            <Icon name="book-open" size={14} />
            سند تحویل و IA
          </NavLink>
          <p className="xs muted-2" style={{ lineHeight: 1.6 }}>
            این ابزار بخشی از محصول نیست؛ فقط برای بازبینی طراحی است.
          </p>
        </div>
      )}
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="ابزار بازبینی طراحی"
        title="ابزار بازبینی — عرض ۱۴۴۰ / ۷۶۸ / ۳۹۰"
        style={{ boxShadow: 'var(--e-3)', paddingInline: 10 }}
      >
        <Icon name={open ? 'close' : 'eye'} size={14} />
        <span className="xs">{open ? 'بستن' : 'بازبینی'}</span>
      </button>
    </div>
  );
}

export function PageTitle({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div className="hello">
      <div style={{ minWidth: 0 }}>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      <span className="grow" />
      {actions}
    </div>
  );
}

export { TITLES };
