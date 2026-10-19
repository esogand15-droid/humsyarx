import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// مسیرهای نسبی: نه VITE_API_URL هارد‌کد، نه دامنهٔ ثابت (D-002)
// allowedHosts فقط برای پیش‌نمایش داخل سندباکس است؛ در استقرار واقعی لازم نیست.
export default defineConfig({
  base: '/app/',
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5173, allowedHosts: true },
  preview: { host: '0.0.0.0', port: 4173, allowedHosts: true },
  build: { target: 'es2020', assetsInlineLimit: 0 },
});
