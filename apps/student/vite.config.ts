import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/* ─────────────────────────────────────────────────────────────
   مسیر سرو: /student/  (تصمیم D-033)

   چرا نه /app/؟
   در مخزن هامزیار، /app/ از قبل به مینی‌اپ تلگرام (miniapp/dist)
   تعلق دارد. سرو کلاینت وب روی همان پیشوند، مینی‌اپ را shadow
   می‌کرد و کاربر مینی‌اپ صفحهٔ اشتباه می‌دید.

   namespace نهایی روی دامنه:
     /student/*  → کلاینت وب دانشجو (این بیلد)
     /app/*      → مینی‌اپ تلگرام
     /admin/*    → پنل مدیریت
     /api/*      → FastAPI

   base از VITE_BASE قابل تغییر است (مثلاً VITE_BASE=/ برای دامنهٔ جدا).
   ───────────────────────────────────────────────────────────── */
export default defineConfig({
  base: process.env.VITE_BASE || '/student/',
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    // dev: درخواست‌های /api به بک‌اند محلی FastAPI می‌روند تا
    // فرانت و بک روی یک origin دیده شوند (کوکی سشن کار کند).
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  preview: { host: '0.0.0.0', port: 4173, allowedHosts: true },
  build: { target: 'es2020', assetsInlineLimit: 0 },
});
