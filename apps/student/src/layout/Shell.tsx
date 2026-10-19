import type { ReactNode } from 'react';
import { TabBar } from './TabBar';

/** پوستهٔ اپ — container query روی همین قاب، نه روی صفحه (design-system/05).
    `tabs={false}` برای صفحه‌های ورود/گیت که ناوبری اصلی هنوز معنا ندارد. */
export function Shell({ children, tabs }: { children: ReactNode; tabs?: boolean }) {
  const showTabs = tabs ?? true;
  return (
    <div className="app-frame">
      <div className={`app ${showTabs ? '' : 'app--bare'}`.trim()}>
        <main className="content">{children}</main>
        {showTabs && <TabBar />}
      </div>
    </div>
  );
}
