// Service Worker for rekapimutasi (Offline PWA support)
const CACHE_NAME = 'rekapimutasi-pages-cfcc111ac5';

const PRECACHE_URLS = [
  './',
  './index.html',
  './worker.js?v=cfcc111ac5',
  './rekapimutasi_pkg.zip?v=cfcc111ac5',
  './favicon.svg',
  './favicon.png',
  './favicon.ico',
  './manifest.webmanifest'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('Pre-cache error (non-fatal):', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Network-first for HTML pages so latest version loads if online, fallback to cache if offline
  if (req.mode === 'navigate' || req.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          if (resp && resp.status === 200) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return resp;
        })
        .catch(() => caches.match(req).then((cached) => cached || caches.match('./index.html')))
    );
    return;
  }

  // Cache-first for Pyodide, WebAssembly, fonts, and local assets
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;

      return fetch(req)
        .then((resp) => {
          if (!resp || resp.status !== 200) return resp;

          // Cache same-origin assets, CDN Pyodide files, and fonts
          const shouldCache =
            url.origin === self.location.origin ||
            url.hostname === 'cdn.jsdelivr.net' ||
            url.hostname === 'fonts.googleapis.com' ||
            url.hostname === 'fonts.gstatic.com';

          if (shouldCache) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return resp;
        })
        .catch(() => cached || Response.error());
    })
  );
});
