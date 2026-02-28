/**
 * Service Worker for Property Strategy AI PWA.
 *
 * Strategy:
 * - Cache the app shell (HTML, CSS, JS) on install for offline load.
 * - All API calls (/api/*) go straight to the network — AI responses must be live.
 * - Static assets served from cache-first, falling back to network.
 */

const CACHE_VERSION = 'v1';
const SHELL_CACHE = `app-shell-${CACHE_VERSION}`;

const SHELL_ASSETS = [
  '/',
  '/static/style.css',
  '/static/js/api.js',
  '/static/js/voice.js',
  '/static/js/app.js',
  // marked.js is loaded from CDN — cache it too once fetched
];

// ===== INSTALL: cache the app shell =====
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      cache.addAll(SHELL_ASSETS).catch((e) => {
        // Non-fatal: shell may not be fully available offline on first install
        console.warn('[SW] Shell cache partial:', e);
      })
    )
  );
});

// ===== ACTIVATE: clean up old caches =====
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ===== FETCH: routing strategy =====
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls: always network, no cache
  if (url.pathname.startsWith('/api/')) {
    return; // let browser handle normally
  }

  // CDN resources (marked.js): cache-first
  if (url.hostname !== self.location.hostname) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(SHELL_CACHE).then((c) => c.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // App shell: cache-first, fallback to network, fallback to '/'
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(SHELL_CACHE).then((c) => c.put(event.request, clone));
          }
          return response;
        })
        .catch(() => caches.match('/'));
    })
  );
});

// ===== Push notification support (future) =====
self.addEventListener('push', (event) => {
  const data = event.data?.json() || {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'Property AI', {
      body: data.body || '',
      icon: '/static/icons/icon-192.png',
    })
  );
});
