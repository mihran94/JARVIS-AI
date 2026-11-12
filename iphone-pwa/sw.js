// The offline shell of the iPhone page.
//
// The shell is cached so the page opens without a network. Nothing that
// carries a secret and no API answer is ever cached: the bridge requests
// always go to the network, and a cached answer could show a stale state or
// leak a message.

const CACHE = 'jarvis-iphone-shell-v2';

const SHELL = [
  './',
  './index.html',
  './style.css',
  './app.js',
  './manifest.webmanifest',
  './js/bridge.js',
  './js/chat.js',
  './js/offline.js',
  './js/pairing.js',
  './js/qr.js',
  './js/speech.js',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))));
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }
  // A bridge answer is never served from the cache.
  if (url.pathname.startsWith('/api/')) {
    return;
  }
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response && response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    }).catch(() => caches.match('./index.html'))));
});
