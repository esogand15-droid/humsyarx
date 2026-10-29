/* ─────────────────────────────────────────────────────────────
   📲 سرویس‌ورکر نسخهٔ نصب‌شدنی (PWA) — /pwa/

   تفاوت مهم با نسخهٔ مینی‌اپ:
   • نسخهٔ قبلی برای فایل‌های استاتیک «cache-first» بود؛ اگر بیلد
     تازه دیپلوی می‌شد، index.html قدیمی سرو می‌شد و کاربر نسخهٔ
     کهنه را می‌دید (باگ کلاسیک PWA). این‌جا:
       – ناوبری‌ها (HTML): network-first با سقف زمانی ← کش ← صفحهٔ آفلاین
       – دارایی‌های هش‌دار (js/css/فونت): stale-while-revalidate
   • پاسخ‌های /api هرگز کش نمی‌شوند (دادهٔ شخصی روی دستگاه مشترک).
   ───────────────────────────────────────────────────────────── */

const VERSION = 'humsyar-pwa-v1-20261029';
const SHELL = `${VERSION}-shell`;
const ASSETS = `${VERSION}-assets`;
const OFFLINE_URL = './offline.html';

const PRECACHE = [
  './',
  './manifest.webmanifest',
  './offline.html',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/maskable-512.png',
  './icons/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => Promise.all(
        PRECACHE.map((url) => cache.add(new Request(url, { cache: 'reload' })).catch(() => null)),
      ))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => !key.startsWith(VERSION)).map((key) => caches.delete(key)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('message', (event) => {
  if (event.data === 'skip-waiting') self.skipWaiting();
});

const isAsset = (url) => /\.(?:js|mjs|css|woff2?|ttf|otf|png|jpe?g|svg|webp|ico)$/i.test(url.pathname);

/** ناوبری: شبکه اول، کش پشتیبان، در نهایت صفحهٔ آفلاین. */
async function handleNavigate(request) {
  const cache = await caches.open(SHELL);
  try {
    const fresh = await Promise.race([
      fetch(request),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 6000)),
    ]);
    if (fresh && fresh.ok) cache.put('./', fresh.clone()).catch(() => {});
    return fresh;
  } catch (_) {
    const cached = await cache.match('./', { ignoreSearch: true });
    if (cached) return cached;
    const offline = await cache.match(OFFLINE_URL);
    if (offline) return offline;
    return new Response('آفلاین — اتصال اینترنت را بررسی کنید.', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    });
  }
}

/** دارایی: کش فوری + تازه‌سازی در پس‌زمینه. */
async function handleAsset(request) {
  const cache = await caches.open(ASSETS);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response && response.ok) cache.put(request, response.clone()).catch(() => {});
      return response;
    })
    .catch(() => null);
  return cached || (await network) || new Response('', { status: 504 });
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  let url;
  try {
    url = new URL(request.url);
  } catch (_) {
    return;
  }

  // مبدأ دیگر (CDN تلگرام/فونت) — اصلاً دخالت نمی‌کنیم
  if (url.origin !== self.location.origin) return;

  // دادهٔ کاربر: هرگز کش نمی‌شود
  if (url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(handleNavigate(request));
    return;
  }

  if (isAsset(url)) {
    event.respondWith(handleAsset(request));
  }
});
