/* Sift service worker: cachet alleen statische bestanden en de pagina's; /api nooit. */
const CACHE = 'sift-static-v1';
const ASSETS = ['/static/app.css', '/static/app.js', '/static/logo.svg', '/static/icon-192.png', '/static/icon-512.png', '/manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS).catch(() => {})).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  // netwerk eerst (zodat updates meteen zichtbaar zijn), cache als de server even niet bereikbaar is
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest')) {
      const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy));
    }
    return r;
  }).catch(() => caches.match(e.request)));
});
