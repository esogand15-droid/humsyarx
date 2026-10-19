import type { ReactNode } from 'react';
import { TabBar } from './TabBar';

/** پوستهٔ اپ — container query روی همین قاب، نه روی صفحه (design-system/05). */
export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="app-frame">
      <div className="app">
        <main className="content">{children}</main>
        <TabBar />
      </div>
    </div>
  );
}
