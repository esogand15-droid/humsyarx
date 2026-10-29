import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';

/* ─────────────────────────────────────────────────────────────
   📲 بیلد PWA — بازنویسی «پوستهٔ نصب» روی خروجی

   `public/` بین دو بیلد مشترک است (فونت و آیکون)، پس manifest و
   سرویس‌ورکرِ مخصوص PWA باید از جای دیگری روی خروجی کپی شوند؛
   وگرنه مسیرها می‌شوند /pwa/pwa/... (تجربه‌شده و اصلاح شد).
   ───────────────────────────────────────────────────────────── */
function pwaShell() {
  return {
    name: 'humsyar-pwa-shell',
    apply: 'build',
    closeBundle() {
      const from = path.resolve(process.cwd(), 'public-pwa');
      const to = path.resolve(process.cwd(), 'dist-pwa');
      if (!fs.existsSync(from) || !fs.existsSync(to)) return;
      fs.cpSync(from, to, { recursive: true, force: true });
      // آیکون‌های PWA زیر /pwa/icons/ باشند (manifest نسبی می‌خواندشان)
      const iconsFrom = path.join(from, 'icons');
      const iconsTo = path.join(to, 'icons');
      if (fs.existsSync(iconsFrom)) fs.cpSync(iconsFrom, iconsTo, { recursive: true, force: true });
    },
  };
}

/* ─────────────────────────────────────────────────────────────
   🚂 مهاجرت Railway — مینی‌اپ به‌عنوان زیرمسیر /app/ سرو می‌شود

   چرا /app/ و نه ریشه؟
   همان دامنه‌ی Railway سه namespace مستقل دارد:
     /app/*   → Telegram Mini App (این بیلد)
     /admin/* → Web Admin (webadmin/dist، base خودش /admin/)
     /api/*   → FastAPI

   مینی‌اپ خودش routeهایی مثل /admin و /me دارد؛ اگر روی ریشه
   سرو می‌شد با Web Admin تداخل (shadow) پیدا می‌کرد.

   base از VITE_BASE خوانده می‌شود؛ پیش‌فرض /app/ است.
   برای `npm run dev` محلی می‌توان VITE_BASE=/ داد.
   ───────────────────────────────────────────────────────────── */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const rawBase = (env.VITE_BASE || '/app/').trim();
  // Vite به base با اسلش پایانی نیاز دارد؛ /app → /app/
  const base = rawBase === '/' ? '/' : rawBase.replace(/\/+$/, '') + '/';

  return {
    base,
    plugins: [react(), ...(env.VITE_APP_MODE === 'pwa' ? [pwaShell()] : [])],
    server: {
      host: true,
      port: 5173,
      // در dev، API روی همان origin شبیه‌سازی می‌شود تا رفتار
      // production (same-origin) در dev هم دیده شود.
      proxy: {
        '/api': {
          target: env.VITE_DEV_API_PROXY || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      // 📲 بیلد PWA جدا و بی‌خطر در پوشهٔ خودش؛ بیلد تلگرام دست‌نخورده می‌ماند
      outDir: (env.VITE_OUT_DIR || 'dist'),
      emptyOutDir: true,
      sourcemap: false,
    },
  };
});
