// Service worker mínimo: permite instalar a PWA e abrir a tela mesmo com a rede instável.
// Rede primeiro (para pegar versões novas); o cache só entra quando a rede falha.
const CACHE = "biony-v3";
const SHELL = ["./", "index.html", "app.js", "face.js", "rosto.html", "style.css", "manifest.webmanifest", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isShell = event.request.method === "GET" && url.origin === location.origin &&
    SHELL.some((path) => url.pathname.endsWith(path.replace("./", "/")));
  if (!isShell) return; // API: sempre direto na rede
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
