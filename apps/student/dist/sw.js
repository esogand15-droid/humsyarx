/* هامزیار — service worker پوستهٔ دانشجو
   هدف: پس از جای‌گزینی طراحی، نسخهٔ کهنهٔ کش‌شده در مرورگر کاربر پاک شود
   و پوستهٔ تازه سرو شود. هیچ دادهٔ کاربری کش نمی‌شود. */
const VERSION = 'humsyar-student-v2';
const KEEP = new Set([VERSION]);

self.addEventListener('install', (e) => {
  e.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !KEEP.has(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

/* شبکه اول: طراحی همیشه تازه دیده شود؛ فقط در حالت آفلاین از کش پاسخ می‌دهد. */
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  if (new URL(req.url).pathname.startsWith('/api/')) return;

  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy)).catch(() => undefined);
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match('./index.html'))),
  );
});
