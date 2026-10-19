import { NavLink } from 'react-router-dom';
import { Icon } from '../icons/Icon';
import type { IconName } from '../icons/sprite';

const TABS: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: 'خانه', icon: 'i-home' },
  { to: '/library', label: 'کتابخانه', icon: 'i-book' },
  { to: '/search', label: 'جستجو', icon: 'i-search' },
  { to: '/schedule', label: 'برنامه', icon: 'i-calendar' },
  { to: '/me', label: 'من', icon: 'i-user' },
];

/** تب‌بار پایین — پنج ناحیهٔ سطح اول، بدون تب ششم (design/10). */
export function TabBar() {
  return (
    <nav className="tabbar" aria-label="ناوبری اصلی">
      {TABS.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.to === '/'} className="tab">
          <Icon name={t.icon} size={22} />
          <span>{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
