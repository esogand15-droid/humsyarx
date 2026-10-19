import type { ReactNode } from 'react';
import { TabBar } from './TabBar';

export type ShellVariant = 'default' | 'bare' | 'reader';

/** پوستهٔ اپ — سه حالت، هر کدام یک قرارداد چیدمان روشن:
    - default: محتوای اسکرول‌شو + تب‌بار پایین
    - bare:    صفحه‌های ورود/گیت (بدون تب‌بار، محتوا وسط‌چین)
    - reader:  فضای خواندن تمام‌قد (بدون تب‌بار، محتوا کل فضا را می‌گیرد) */
export function Shell({
  children,
  tabs,
  variant = 'default',
}: {
  children: ReactNode;
  tabs?: boolean;
  variant?: ShellVariant;
}) {
  const showTabs = tabs ?? true;
  const cls = ['app', variant === 'bare' && 'app--bare', variant === 'reader' && 'app--reader']
    .filter(Boolean)
    .join(' ');
  return (
    <div className="app-frame">
      <div className={cls}>
        <main className="content">{children}</main>
        {showTabs && <TabBar />}
      </div>
    </div>
  );
}
