import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 8_000, toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.015 } },
  use: {
    baseURL: 'http://127.0.0.1:4173',
    locale: 'fa-IR',
    colorScheme: 'dark',
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173/admin/',
    reuseExistingServer: false,
    timeout: 60_000,
  },
  reporter: [['list']],
});
