import { useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import Header from '../../components/layout/Header';
import { haptic, openExternalLink } from '../../lib/telegram';

/* مسیرهای شناخته‌شده‌ی مینی‌اپ به همان صفحه‌ی میز فرماندهی.
   ترتیب مهم است: پیشوند خاص قبل از پیشوند عمومی. */
const RULES = [
  { prefix: '/admin/content/qbank', hash: '/questions', title: 'سؤال‌ها' },
  { prefix: '/admin/content/questions', hash: '/questions', title: 'سؤال‌ها' },
  { prefix: '/admin/content/grades', hash: '/exams?tab=grades', title: 'نمرات' },
  { prefix: '/admin/content/schedule', hash: '/content?tab=schedule', title: 'برنامه' },
  { prefix: '/admin/content/faq', hash: '/content', title: 'محتوا' },
  { prefix: '/admin/content/basic-science', hash: '/content', title: 'محتوا' },
  { prefix: '/admin/content/references', hash: '/content', title: 'محتوا' },
  { prefix: '/admin/content/url-import', hash: '/content', title: 'محتوا' },
  { prefix: '/admin/content/reports', hash: '/content', title: 'محتوا' },
  { prefix: '/admin/content', hash: '/content', title: 'محتوا' },
  { prefix: '/admin/subscription', hash: '/subscriptions', title: 'اشتراک‌ها' },
  { prefix: '/admin/ai', hash: '/ai', title: 'هوشیار' },
  { prefix: '/admin/analytics', hash: '/analytics', title: 'تحلیل‌ها' },
  { prefix: '/admin/audit', hash: '/audit', title: 'حسابرسی' },
  { prefix: '/admin/settings', hash: '/settings', title: 'تنظیمات' },
  { prefix: '/admin/roles', hash: '/rbac', title: 'نقش‌ها' },
  { prefix: '/admin/content-admins', hash: '/rbac', title: 'نقش‌ها' },
  { prefix: '/admin/users', hash: '/users', title: 'کاربران' },
  { prefix: '/admin/intakes', hash: '/users', title: 'کاربران' },
  { prefix: '/admin/blacklist', hash: '/users', title: 'کاربران' },
  { prefix: '/admin/tickets', hash: '/tickets', title: 'تیکت‌ها' },
  { prefix: '/admin/broadcast', hash: '/notify', title: 'اعلان‌ها' },
  { prefix: '/admin/poll', hash: '/notify', title: 'اعلان‌ها' },
  { prefix: '/admin/notifications', hash: '/notify', title: 'اعلان‌ها' },
  { prefix: '/admin', hash: '/dashboard', title: 'داشبورد' },
];

function deskTarget(pathname) {
  const path = String(pathname || '/admin').replace(/\/+$/, '') || '/admin';
  for (const rule of RULES) {
    if (path === rule.prefix || path.startsWith(`${rule.prefix}/`)) {
      return rule;
    }
  }
  return RULES[RULES.length - 1];
}

function deskUrl(hash) {
  const origin = typeof window === 'undefined' ? '' : window.location.origin;
  return `${origin}/admin/#${hash}`;
}

export default function AdminDesk() {
  const { pathname } = useLocation();
  const target = useMemo(() => deskTarget(pathname), [pathname]);
  const url = deskUrl(target.hash);
  const [note, setNote] = useState('');

  const openDesk = () => {
    haptic('light');
    const opened = openExternalLink(url);
    setNote(opened
      ? 'میز فرماندهی در حال باز شدن است. اگر پرسید، وارد همان حساب مدیر شو.'
      : 'از اینجا باز نشد. لینک پایین را در مرورگر باز کن.');
  };

  const copyLink = async () => {
    haptic('light');
    try {
      await navigator.clipboard.writeText(url);
      setNote('لینک میز کپی شد.');
    } catch {
      setNote(url);
    }
  };

  return (
    <main className="page">
      <Header
        title="میز فرماندهی"
        subtitle={target.title}
        backTo="/me"
      />

      <section className="card" style={{ marginTop: 8, padding: 18 }}>
        <div style={{ fontSize: 36, lineHeight: 1 }} aria-hidden="true">🧭</div>
        <h2 style={{ margin: '10px 0 8px', fontSize: 20 }}>
          یک میز، نه دو تا
        </h2>
        <p style={{ margin: 0, color: 'var(--tx2)', lineHeight: 1.75 }}>
          مدیریت ربات فقط از میز فرماندهی وب انجام می‌شود.
          این صفحه میز دوم نیست؛ تو را به همان میز می‌برد،
          مستقیم روی «{target.title}».
        </p>
        <button
          type="button"
          className="btn btn-p btn-full"
          style={{ marginTop: 16 }}
          onClick={openDesk}
        >
          باز کردن میز فرماندهی
        </button>
        <button
          type="button"
          className="btn btn-g btn-full"
          style={{ marginTop: 8 }}
          onClick={copyLink}
        >
          کپی لینک
        </button>
        {note ? (
          <p style={{ margin: '12px 0 0', color: 'var(--txm)', lineHeight: 1.6 }}>
            {note}
          </p>
        ) : null}
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          style={{
            display: 'block',
            marginTop: 12,
            color: 'var(--acc2)',
            wordBreak: 'break-all',
            fontSize: 13,
          }}
        >
          {url}
        </a>
      </section>
    </main>
  );
}
