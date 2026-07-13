/**
 * MyVine OS — security-conscious service worker
 *
 * WHAT WE CACHE (safe to offload to the device):
 *   - Versioned /static/ CSS, JS, images, fonts
 *
 * WHAT WE NEVER CACHE (security / freshness):
 *   - HTML pages (CSRF tokens, user menus, flash messages)
 *   - API / JSON endpoints
 *   - POST / PUT / DELETE / PATCH
 *   - Any non-same-origin request
 *
 * Multi-device logins are unaffected: each browser keeps its own cookies;
 * this SW only stores public static files.
 */
const CACHE_NAME = 'myvine-static-v1';
const PRECACHE = [
  // Keep short — only highly shared shell assets (paths must match production)
  '/static/css/global/theme.css?v=20260710i',
  '/static/css/overhaul.css?v=202608',
  '/static/js/app-shell.js',
  '/static/js/display_prefs.js?v=20260710g',
  '/static/js/global/csrf_autofill.js',
  '/static/manifest.json',
];

function isStaticAsset(url) {
  try {
    const u = new URL(url);
    if (u.origin !== self.location.origin) return false;
    return u.pathname.startsWith('/static/');
  } catch (e) {
    return false;
  }
}

function isNavigationRequest(request) {
  return request.mode === 'navigate' ||
    (request.method === 'GET' && request.headers.get('accept') &&
      request.headers.get('accept').includes('text/html'));
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE).catch(() => undefined))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Never touch non-GET (mutations, CSRF-sensitive)
  if (req.method !== 'GET') return;

  // Never cache HTML navigations — always network
  if (isNavigationRequest(req)) return;

  // Only intercept same-origin static assets
  if (!isStaticAsset(req.url)) return;

  // Cache-first for static; revalidate in background when possible
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(req, { ignoreSearch: false });
      const networkPromise = fetch(req).then((response) => {
        // Only cache solid successful same-origin static responses
        if (response && response.ok && response.type === 'basic') {
          cache.put(req, response.clone());
        }
        return response;
      }).catch(() => cached);

      // Prefer cache for speed; fall back to network
      return cached || networkPromise;
    })
  );
});
