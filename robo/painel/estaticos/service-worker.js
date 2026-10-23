// Service worker do app do celular. Só funciona em HTTPS (ou 127.0.0.1): pelo Wi-Fi de casa em http o navegador
// nem o registra, e o app continua funcionando normalmente, só sem a tela offline.
// Regras: os DADOS (/api/...) nunca ficam guardados no aparelho; só a "casca" do app (página, estilo, ícones).
"use strict";
const VERSAO = "robo-celular-v1";
const CASCA = ["/", "/celular.css", "/celular.js", "/offline.html", "/robo.svg", "/icone-192.png", "/manifest.webmanifest"];

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(VERSAO).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys()
    .then((nomes) => Promise.all(nomes.filter((n) => n !== VERSAO).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (ev) => {
  const url = new URL(ev.request.url);
  if (ev.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // dado sempre ao vivo, nunca do cache
  // rede primeiro (o app nunca fica velho); sem rede, a cópia guardada; página sem cópia → tela offline
  ev.respondWith(fetch(ev.request).then((resp) => {
    if (resp.ok && CASCA.includes(url.pathname)) {
      const copia = resp.clone();
      caches.open(VERSAO).then((c) => c.put(ev.request, copia));
    }
    return resp;
  }).catch(() => caches.match(ev.request).then((guardado) =>
    guardado || (ev.request.mode === "navigate" ? caches.match("/offline.html") : Response.error()))));
});
