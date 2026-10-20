import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { ProtoProvider } from './lib/store';
import './styles/tokens.css';
import './styles/base.css';
import './styles/app.css';
import './styles/layout.css';
import './styles/notes.css';
import './styles/motion.css';

/* ── حالت نصب‌شده و ناحیهٔ امن ──────────────────────────────────── */
const standalone =
  window.matchMedia('(display-mode: standalone)').matches ||
  (navigator as unknown as { standalone?: boolean }).standalone === true;
document.documentElement.dataset.standalone = String(standalone);

/* ارتفاع واقعی نمای دیداری را در اختیار CSS می‌گذارد (کیبورد مجازی) */
const vv = window.visualViewport;
if (vv) {
  const sync = () => {
    document.documentElement.style.setProperty('--kb', `${Math.max(0, window.innerHeight - vv.height)}px`);
  };
  vv.addEventListener('resize', sync);
  vv.addEventListener('scroll', sync);
  sync();
}

/* service worker فقط در بیلد تولیدی؛ در dev کش کهنه نمی‌خواهیم */
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => undefined);
  });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ProtoProvider>
      <App />
    </ProtoProvider>
  </StrictMode>,
);
