// ShortsBot: guarda el panel para que la app abra aunque el bot esté apagado (y entonces muestre "apagado").
const CACHE = "shortsbot-v1";
const BASICO = ["/", "/manifest.webmanifest", "/icono-192.png", "/icono-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(BASICO)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/") || url.pathname.startsWith("/media/")) return;
  // Primero la red (datos al día); si el bot no responde, la copia guardada.
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok) caches.open(CACHE).then((c) => c.put(e.request.mode === "navigate" ? "/" : e.request, r.clone()));
        return r;
      })
      .catch(() => caches.match(e.request.mode === "navigate" ? "/" : e.request))
  );
});
