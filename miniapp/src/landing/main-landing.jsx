import React from 'react';
import ReactDOM from 'react-dom/client';
import Landing from './Landing';
import './landing.css';

/* ─────────────────────────────────────────────────────────────
   🏠 لندینگ (صفحهٔ ریشهٔ دامنه) — ورودی جدا از اپ

   چرا جدا؟ لندینگ نه روتر دارد نه وضعیت احراز؛ و مهم‌تر: نباید
   هیچ‌کدام از چیزهای اپ (تشخیص تلگرام، کوکی نشست، سرویس‌ورکر) را
   اجرا کند. فقط HTML + CSS + یک کامپوننت استاتیک.
   ───────────────────────────────────────────────────────────── */

ReactDOM.createRoot(document.getElementById('landing-root')).render(
  <React.StrictMode>
    <Landing />
  </React.StrictMode>
);
