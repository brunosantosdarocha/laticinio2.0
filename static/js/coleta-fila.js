/*
  static/js/coleta-fila.js
  ========================
  FILA de lançamentos de leite guardada NO CELULAR (IndexedDB, um banco de dados do navegador).

  Este arquivo é usado em dois lugares:
  - na página de Coleta diária (coleta-offline.js);
  - no service worker (sw.js), para enviar a fila em segundo plano quando a internet volta.
  Por isso ele não mexe na tela: só guarda, lista e envia.

  Cada item da fila:
    { codigo, produtor, nome, forma, litros, data, usuario, criado_em, situacao, mensagem }
    situacao = "pendente" (esperando envio) ou "recusado" (o servidor não aceitou; o coletor precisa ver)
*/
(function (escopo) {
  "use strict";

  var NOME_BANCO = "laticinio-coleta";
  var LOJA = "fila";
  var URLS = {
    estado: "/leite/api/coleta/estado/",
    sincronizar: "/leite/api/coleta/sincronizar/"
  };
  var MAX_POR_ENVIO = 200;

  // Abre (ou cria na primeira vez) o banco do navegador.
  function abrir() {
    return new Promise(function (resolver, rejeitar) {
      var pedido = indexedDB.open(NOME_BANCO, 1);
      pedido.onupgradeneeded = function () {
        pedido.result.createObjectStore(LOJA, { keyPath: "codigo" });
      };
      pedido.onsuccess = function () { resolver(pedido.result); };
      pedido.onerror = function () { rejeitar(pedido.error); };
    });
  }

  // Executa uma operação na loja "fila" e devolve o resultado como Promise.
  function operar(modo, acao) {
    return abrir().then(function (banco) {
      return new Promise(function (resolver, rejeitar) {
        var transacao = banco.transaction(LOJA, modo);
        var pedido = acao(transacao.objectStore(LOJA));
        transacao.oncomplete = function () { resolver(pedido ? pedido.result : undefined); banco.close(); };
        transacao.onerror = function () { rejeitar(transacao.error); banco.close(); };
      });
    });
  }

  function salvar(item) { return operar("readwrite", function (loja) { return loja.put(item); }); }
  function remover(codigo) { return operar("readwrite", function (loja) { return loja.delete(codigo); }); }
  function listar() {
    return operar("readonly", function (loja) { return loja.getAll(); }).then(function (itens) {
      return (itens || []).sort(function (a, b) { return a.criado_em < b.criado_em ? -1 : 1; });
    });
  }

  // Código único do lançamento (o servidor usa para não gravar duas vezes).
  function novoCodigo() {
    if (escopo.crypto && escopo.crypto.randomUUID) { return escopo.crypto.randomUUID(); }
    var b = escopo.crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  }

  var enviando = false;

  /*
    Envia os itens "pendentes" para o servidor.
    Devolve um resumo: { enviados, recusados, aguardandoOutroUsuario, erro, estado }
      erro = "rede" (sem internet), "login" (precisa entrar), "servidor" (outro problema)
  */
  function sincronizar() {
    var resumo = { enviados: 0, recusados: 0, aguardandoOutroUsuario: 0, erro: null, estado: null };
    if (enviando) { return Promise.resolve(resumo); }
    enviando = true;

    return listar().then(function (itens) {
      var pendentes = itens.filter(function (i) { return i.situacao === "pendente"; });
      // Mesmo sem pendentes, buscamos o estado para atualizar a lista de produtores.
      return fetch(URLS.estado, { credentials: "same-origin", cache: "no-store" }).then(function (resposta) {
        if (resposta.status === 401 || resposta.status === 403) { resumo.erro = "login"; return resumo; }
        var tipo = resposta.headers.get("Content-Type") || "";
        if (!resposta.ok || tipo.indexOf("application/json") === -1) { resumo.erro = "servidor"; return resumo; }
        return resposta.json().then(function (estado) {
          resumo.estado = estado;
          // Só envia o que foi lançado pelo usuário que está logado agora.
          var meus = pendentes.filter(function (i) { return i.usuario === estado.usuario; });
          resumo.aguardandoOutroUsuario = pendentes.length - meus.length;
          if (!meus.length) { return resumo; }
          return enviarLotes(meus.slice(0, MAX_POR_ENVIO), estado.csrf, resumo);
        });
      });
    }).catch(function () {
      resumo.erro = "rede";
      return resumo;
    }).then(function (r) {
      enviando = false;
      return r;
    });
  }

  function enviarLotes(itens, csrf, resumo) {
    var corpo = {
      itens: itens.map(function (i) {
        return { codigo: i.codigo, produtor: i.produtor, forma: i.forma, litros: i.litros, data: i.data };
      })
    };
    return fetch(URLS.sincronizar, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(corpo)
    }).then(function (resposta) {
      if (resposta.status === 401 || resposta.status === 403) { resumo.erro = "login"; return resumo; }
      if (!resposta.ok) { resumo.erro = "servidor"; return resumo; }
      return resposta.json().then(function (dados) {
        var porCodigo = {};
        itens.forEach(function (i) { porCodigo[i.codigo] = i; });
        var operacoes = (dados.resultados || []).map(function (r) {
          var item = porCodigo[r.codigo];
          if (!item) { return null; }
          if (r.status === "ok" || r.status === "repetido") {
            resumo.enviados += 1;
            return remover(item.codigo);
          }
          resumo.recusados += 1;
          item.situacao = "recusado";
          item.mensagem = r.mensagem;
          return salvar(item);
        });
        return Promise.all(operacoes).then(function () { return resumo; });
      });
    });
  }

  escopo.FilaColeta = {
    salvar: salvar,
    remover: remover,
    listar: listar,
    novoCodigo: novoCodigo,
    sincronizar: sincronizar,
    URLS: URLS
  };
})(self);
