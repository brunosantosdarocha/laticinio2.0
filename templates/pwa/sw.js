{% load static %}/*
  Service worker da Coleta diária (gerado pelo Django: templates/pwa/sw.js).

  - Guarda no celular a página /leite/coleta-diaria/ e os arquivos CSS/JS/ícones,
    para a página abrir mesmo sem internet.
  - Página: tenta a internet primeiro (dados frescos); sem internet usa a cópia guardada.
  - CSS/JS/ícones: usa a cópia guardada primeiro (mais rápido).
  - API (/leite/api/...): nunca guarda, sempre vai ao servidor.
  - "sync": quando a internet volta, o Android acorda este arquivo para enviar a fila
    mesmo com a página fechada (no iPhone o envio acontece ao abrir a página).

  Mudou JS/CSS da coleta? Aumente VERSAO_PWA em leite/views.py para os celulares atualizarem.
*/
importScripts("{% static 'js/coleta-fila.js' %}");

var CACHE = "coleta-v{{ versao }}";
var PAGINA = "{% url 'leite:coleta_diaria' %}";
var ARQUIVOS = [
  "{% static 'vendor/adminlte/adminlte.min.css' %}",
  "{% static 'vendor/bootstrap-icons/bootstrap-icons.min.css' %}",
  "{% static 'vendor/bootstrap-icons/fonts/bootstrap-icons.woff2' %}",
  "{% static 'vendor/bootstrap-icons/fonts/bootstrap-icons.woff' %}",
  "{% static 'css/sistema.css' %}",
  "{% static 'vendor/bootstrap/bootstrap.bundle.min.js' %}",
  "{% static 'vendor/adminlte/adminlte.min.js' %}",
  "{% static 'js/sistema.js' %}",
  "{% static 'js/coleta-fila.js' %}",
  "{% static 'js/coleta-offline.js' %}",
  "{% static 'img/favicon.svg' %}",
  "{% static 'img/icone-192.png' %}",
  "{% static 'img/icone-512.png' %}"
];

// Guarda a página só se ela veio de verdade (e não a tela de login por sessão expirada).
function guardarPagina(cache, resposta) {
  if (resposta && resposta.ok && !resposta.redirected) {
    return cache.put(PAGINA, resposta.clone());
  }
}

self.addEventListener("install", function (evento) {
  evento.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(ARQUIVOS).then(function () {
        return fetch(PAGINA, { credentials: "same-origin" }).then(function (r) { return guardarPagina(cache, r); });
      });
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (evento) {
  evento.waitUntil(
    caches.keys().then(function (nomes) {
      return Promise.all(nomes.filter(function (n) { return n.indexOf("coleta-") === 0 && n !== CACHE; })
        .map(function (n) { return caches.delete(n); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (evento) {
  var pedido = evento.request;
  if (pedido.method !== "GET") { return; }
  var url = new URL(pedido.url);
  if (url.origin !== self.location.origin) { return; }

  // A página da coleta: internet primeiro, cópia guardada se estiver offline.
  if (url.pathname === PAGINA) {
    evento.respondWith(
      fetch(pedido).then(function (resposta) {
        caches.open(CACHE).then(function (cache) { guardarPagina(cache, resposta); });
        return resposta;
      }).catch(function () {
        return caches.match(PAGINA, { ignoreSearch: true, ignoreVary: true });
      })
    );
    return;
  }

  // Arquivos estáticos: cópia guardada primeiro.
  if (url.pathname.indexOf("{% get_static_prefix %}") === 0) {
    evento.respondWith(
      caches.match(pedido, { ignoreVary: true }).then(function (guardado) {
        return guardado || fetch(pedido);
      })
    );
  }
  // Todo o resto (API, outras telas) vai direto ao servidor.
});

function avisarPaginas() {
  return self.clients.matchAll({ type: "window" }).then(function (paginas) {
    paginas.forEach(function (p) { p.postMessage({ tipo: "fila-atualizada" }); });
  });
}

self.addEventListener("sync", function (evento) {
  if (evento.tag === "enviar-coletas") {
    evento.waitUntil(self.FilaColeta.sincronizar().then(function (r) {
      // "rede": rejeita para o navegador tentar de novo mais tarde.
      if (r.erro === "rede") { throw new Error("sem rede"); }
      return avisarPaginas();
    }));
  }
});
