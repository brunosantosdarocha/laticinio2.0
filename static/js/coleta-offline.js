/*
  static/js/coleta-offline.js
  ===========================
  Deixa a página de Coleta diária funcionar SEM INTERNET.

  1. Registra o service worker (sw.js), que guarda a página para abrir offline.
  2. Ao tocar em "Lançar leite", o lançamento vai para a FILA do celular (coleta-fila.js)
     com um código único e a data do celular. Depois tenta enviar na hora.
  3. Quando a internet volta (evento "online", a cada minuto ou no botão "Enviar agora"),
     a fila é enviada. O servidor responde item por item:
       aceito/repetido -> sai da fila;  recusado -> aparece em "Não aceitos" com o motivo.
  4. As listas "Falta lançar" e "Lançados hoje" são montadas aqui, juntando o que o servidor
     informou (guardado no celular) com o que ainda está na fila.

  Tudo que vem do servidor é escrito com textContent (nunca innerHTML), para evitar XSS.
*/
(function () {
  "use strict";

  var app = document.getElementById("coleta-app");
  if (!app || !("indexedDB" in window) || !window.FilaColeta || !window.fetch) { return; }

  var Fila = window.FilaColeta;
  var cfg = { usuario: app.dataset.usuario, sw: app.dataset.sw, login: app.dataset.login };
  var CHAVE_ESTADO = "coleta-estado:" + cfg.usuario;

  var form = document.getElementById("form-coleta");
  var campoProdutor = document.getElementById("id_produtor");
  var campoLitros = document.getElementById("id_litros");
  var aviso = document.getElementById("aviso-coleta");
  var statusConexao = document.getElementById("status-conexao");

  var estado = carregarEstado();
  var fila = [];
  var precisaLogin = false;

  // ------------------------------------------------------------------ utilidades
  function dois(n) { return (n < 10 ? "0" : "") + n; }
  function hojeLocal() {
    var d = new Date();
    return d.getFullYear() + "-" + dois(d.getMonth() + 1) + "-" + dois(d.getDate());
  }
  function litrosBr(valor) {
    return Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " L";
  }
  function dataCurta(iso) { var p = iso.split("-"); return p[2] + "/" + p[1]; }
  function horaDe(isoDataHora) {
    var d = new Date(isoDataHora);
    return dois(d.getHours()) + ":" + dois(d.getMinutes());
  }
  function criar(tag, classes, texto) {
    var e = document.createElement(tag);
    if (classes) { e.className = classes; }
    if (texto !== undefined) { e.textContent = texto; }
    return e;
  }
  function icone(nome) { return criar("i", "bi " + nome + " me-1"); }

  function mostrarAviso(tipo, texto) {
    aviso.textContent = "";
    var caixa = criar("div", "alert alert-" + tipo + " alert-dismissible fade show");
    caixa.appendChild(document.createTextNode(texto));
    var fechar = criar("button", "btn-close");
    fechar.type = "button";
    fechar.setAttribute("data-bs-dismiss", "alert");
    fechar.setAttribute("aria-label", "Fechar");
    caixa.appendChild(fechar);
    aviso.appendChild(caixa);
  }

  // ------------------------------------------------------------------ estado (produtores e lançados)
  function carregarEstado() {
    var inicial = null, guardado = null;
    try { inicial = JSON.parse(document.getElementById("estado-inicial").textContent); } catch (e) { inicial = null; }
    try { guardado = JSON.parse(localStorage.getItem(CHAVE_ESTADO)); } catch (e) { guardado = null; }
    // Usa o mais recente: o da página (pode ter vindo do cache) ou o salvo no celular.
    if (guardado && (!inicial || guardado.gerado_em > inicial.gerado_em)) { return guardado; }
    return inicial || { produtores: [], lancados_hoje: [], hoje: "", gerado_em: "" };
  }

  function guardarEstado(novo) {
    var copia = {};
    Object.keys(novo).forEach(function (k) { if (k !== "csrf") { copia[k] = novo[k]; } });
    estado = copia;
    try { localStorage.setItem(CHAVE_ESTADO, JSON.stringify(copia)); } catch (e) { /* sem espaço: segue sem guardar */ }
  }

  function atualizarEstadoDoServidor() {
    return fetch(Fila.URLS.estado, { credentials: "same-origin", cache: "no-store" }).then(function (r) {
      if (r.ok) { return r.json().then(guardarEstado); }
      if (r.status === 401 || r.status === 403) { precisaLogin = true; }
    }).catch(function () { /* offline: fica com o que tem */ });
  }

  // ------------------------------------------------------------------ desenho da tela
  function desenhar() {
    var hoje = hojeLocal();
    var pendentesFila = fila.filter(function (i) { return i.situacao === "pendente"; });
    var recusados = fila.filter(function (i) { return i.situacao === "recusado"; });
    var lancadosServidor = estado.hoje === hoje ? (estado.lancados_hoje || []) : [];
    var filaHoje = pendentesFila.filter(function (i) { return i.data === hoje; });

    // Data do cabeçalho: sempre a do celular (a página pode ter vindo do cache de outro dia)
    var titulo = new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
    document.getElementById("data-hoje").textContent = titulo.charAt(0).toUpperCase() + titulo.slice(1);

    desenharConexao(pendentesFila.length);
    desenharSelect();

    // Fila do celular
    var cardFila = document.getElementById("card-fila");
    var listaFila = document.getElementById("lista-fila");
    listaFila.textContent = "";
    document.getElementById("qtd-fila").textContent = pendentesFila.length;
    cardFila.classList.toggle("d-none", pendentesFila.length === 0);
    pendentesFila.forEach(function (item) {
      var li = criar("li", "list-group-item d-flex justify-content-between align-items-center");
      var info = criar("div");
      info.appendChild(criar("div", "fw-semibold", item.nome));
      var detalhe = dataCurta(item.data) + " · " + (item.forma === "COLETADO" ? "Coletado" : "Entregue") + " · " + horaDe(item.criado_em);
      if (item.usuario !== cfg.usuario) { detalhe += " · aguardando o login de " + item.usuario; }
      info.appendChild(criar("small", "text-body-secondary", detalhe));
      li.appendChild(info);
      li.appendChild(criar("span", "fw-bold", litrosBr(item.litros)));
      listaFila.appendChild(li);
    });

    // Recusados
    var cardRec = document.getElementById("card-recusados");
    var listaRec = document.getElementById("lista-recusados");
    listaRec.textContent = "";
    cardRec.classList.toggle("d-none", recusados.length === 0);
    recusados.forEach(function (item) {
      var li = criar("li", "list-group-item");
      var topo = criar("div", "d-flex justify-content-between align-items-center");
      topo.appendChild(criar("strong", "", item.nome + " · " + dataCurta(item.data) + " · " + litrosBr(item.litros)));
      var botao = criar("button", "btn btn-sm btn-outline-secondary", "Descartar");
      botao.type = "button";
      botao.setAttribute("data-descartar", item.codigo);
      topo.appendChild(botao);
      li.appendChild(topo);
      li.appendChild(criar("div", "small text-danger", item.mensagem || "Recusado."));
      listaRec.appendChild(li);
    });

    // Falta lançar hoje
    var jaLancados = {};
    lancadosServidor.forEach(function (l) { jaLancados[l.produtor] = true; });
    filaHoje.forEach(function (i) { jaLancados[i.produtor] = true; });
    var faltam = (estado.produtores || []).filter(function (p) { return !jaLancados[p.id]; });
    var listaPend = document.getElementById("lista-pendentes");
    listaPend.textContent = "";
    document.getElementById("qtd-pendentes").textContent = faltam.length;
    document.getElementById("card-pendentes").classList.toggle("d-none", faltam.length === 0);
    faltam.forEach(function (p) {
      var botao = criar("button", "list-group-item list-group-item-action produtor-pendente d-flex justify-content-between align-items-center");
      botao.type = "button";
      botao.setAttribute("data-escolher-produtor", p.id);
      var nome = criar("span", "", p.nome);
      if (p.propriedade) { nome.appendChild(criar("small", "text-body-secondary", " · " + p.propriedade)); }
      botao.appendChild(nome);
      botao.appendChild(criar("i", "bi bi-chevron-right"));
      listaPend.appendChild(botao);
    });

    // Lançados hoje (fila do celular + servidor)
    var listaLanc = document.getElementById("lista-lancados");
    listaLanc.textContent = "";
    var total = 0;
    filaHoje.forEach(function (item) {
      total += Number(item.litros);
      listaLanc.appendChild(linhaLancado(item.nome, item.forma, horaDe(item.criado_em), item.litros, true));
    });
    lancadosServidor.forEach(function (l) {
      total += Number(l.litros);
      listaLanc.appendChild(linhaLancado(l.nome, l.forma, l.hora, l.litros, false));
    });
    if (!filaHoje.length && !lancadosServidor.length) {
      listaLanc.appendChild(criar("li", "list-group-item text-body-secondary", "Nenhum leite lançado hoje ainda."));
    }
    document.getElementById("total-hoje").textContent = litrosBr(total);
    document.getElementById("info-atualizado").textContent =
      estado.gerado_em ? "Lista do escritório atualizada às " + horaDe(estado.gerado_em) + ". " : "";
  }

  function linhaLancado(nome, forma, hora, litros, naFila) {
    var li = criar("li", "list-group-item d-flex justify-content-between align-items-center");
    var info = criar("div");
    info.appendChild(criar("div", "fw-semibold", nome));
    var detalhe = criar("small", "text-body-secondary");
    var nomes = { COLETADO: ["bi-truck", "Coletado"], ENTREGUE: ["bi-house-door", "Entregue"], ESCRITORIO: ["bi-building", "Escritório"] };
    var f = nomes[forma] || nomes.ESCRITORIO;
    detalhe.appendChild(icone(f[0]));
    detalhe.appendChild(document.createTextNode(f[1] + " · " + hora));
    info.appendChild(detalhe);
    if (naFila) {
      var selo = criar("span", "badge text-bg-warning ms-1");
      selo.appendChild(icone("bi-phone"));
      selo.appendChild(document.createTextNode("no celular"));
      detalhe.appendChild(selo);
    }
    li.appendChild(info);
    var quantidade = Number(litros) === 0 ? "Falta" : litrosBr(litros);
    li.appendChild(criar("span", "fs-5 fw-bold" + (Number(litros) === 0 ? " text-danger" : ""), quantidade));
    return li;
  }

  function desenharConexao(qtdFila) {
    statusConexao.textContent = "";
    statusConexao.classList.remove("d-none", "alert-success", "alert-warning", "alert-danger", "alert-info");
    if (precisaLogin) {
      statusConexao.classList.add("alert-danger");
      statusConexao.appendChild(icone("bi-person-lock"));
      statusConexao.appendChild(document.createTextNode("Sua sessão expirou. Os lançamentos continuam guardados no celular. "));
      var link = criar("a", "alert-link", "Entrar de novo");
      link.href = cfg.login;
      statusConexao.appendChild(link);
    } else if (!navigator.onLine) {
      statusConexao.classList.add("alert-warning");
      statusConexao.appendChild(icone("bi-wifi-off"));
      statusConexao.appendChild(document.createTextNode(
        "Sem internet. Pode continuar lançando: fica guardado no celular e é enviado quando a conexão voltar."));
    } else if (qtdFila) {
      statusConexao.classList.add("alert-info");
      statusConexao.appendChild(icone("bi-arrow-repeat"));
      statusConexao.appendChild(document.createTextNode("Online. Enviando os lançamentos guardados..."));
    } else {
      statusConexao.classList.add("alert-success");
      statusConexao.appendChild(icone("bi-wifi"));
      var texto = "Online. Tudo enviado.";
      if (!window.isSecureContext || !("serviceWorker" in navigator)) {
        texto += " (Para abrir esta página SEM internet o sistema precisa estar em https.)";
      }
      statusConexao.appendChild(document.createTextNode(texto));
    }
  }

  // Refaz as opções do select se a lista de produtores mudou (mantém o selecionado).
  function desenharSelect() {
    var produtores = estado.produtores || [];
    var atuais = Array.prototype.slice.call(campoProdutor.options, 1).map(function (o) { return o.value; }).join(",");
    var novos = produtores.map(function (p) { return String(p.id); }).join(",");
    if (!produtores.length || atuais === novos) { return; }
    var escolhido = campoProdutor.value;
    while (campoProdutor.options.length > 1) { campoProdutor.remove(1); }
    produtores.forEach(function (p) { campoProdutor.add(new Option(p.nome, p.id)); });
    campoProdutor.value = escolhido;
  }

  // ------------------------------------------------------------------ fila
  function recarregarFila() {
    return Fila.listar().then(function (itens) { fila = itens; desenhar(); });
  }

  function enviar(mostrarResultado) {
    if (!navigator.onLine) { desenhar(); return Promise.resolve(); }
    return Fila.sincronizar().then(function (r) {
      precisaLogin = r.erro === "login";
      if (r.estado) { guardarEstado(r.estado); }
      var depois = r.enviados ? atualizarEstadoDoServidor() : Promise.resolve();
      return depois.then(recarregarFila).then(function () {
        var partes = [];
        if (r.enviados) { partes.push(r.enviados + " lançamento(s) enviado(s) ao escritório."); }
        if (r.recusados) { partes.push(r.recusados + " não foram aceitos: veja o motivo abaixo."); }
        if (partes.length) { mostrarAviso(r.recusados ? "warning" : "success", partes.join(" ")); }
        if (mostrarResultado && r.erro === "servidor") { mostrarAviso("warning", "O servidor não respondeu. Tentaremos de novo em instantes."); }
        if (mostrarResultado && r.erro === "rede") { mostrarAviso("warning", "Sem conexão com o servidor. Os lançamentos continuam guardados."); }
      });
    });
  }

  function pedirEnvioEmSegundoPlano() {
    if (!("serviceWorker" in navigator)) { return; }
    navigator.serviceWorker.ready.then(function (reg) {
      if (reg.sync) { return reg.sync.register("enviar-coletas"); }
    }).catch(function () { /* navegador sem Background Sync (ex.: iPhone): envia quando abrir a página */ });
  }

  // ------------------------------------------------------------------ lançar leite
  form.addEventListener("submit", function (evento) {
    evento.preventDefault();
    evento.stopPropagation(); // não deixa o sistema.js travar o botão: aqui não há recarga de página

    var produtorId = parseInt(campoProdutor.value, 10);
    var forma = (form.querySelector("input[name=forma]:checked") || {}).value;
    var litros = Math.round(parseFloat(String(campoLitros.value).replace(",", ".")) * 10) / 10;
    var hoje = hojeLocal();

    if (!produtorId) { mostrarAviso("danger", "Escolha o produtor."); campoProdutor.focus(); return; }
    if (forma !== "COLETADO" && forma !== "ENTREGUE") { mostrarAviso("danger", "Escolha se o leite foi coletado ou entregue."); return; }
    if (!(litros > 0) || litros > 99999.9) { mostrarAviso("danger", "Informe a quantidade de litros (maior que zero)."); campoLitros.focus(); return; }

    var nome = campoProdutor.options[campoProdutor.selectedIndex].text;
    var naFila = fila.some(function (i) { return i.produtor === produtorId && i.data === hoje && i.situacao === "pendente"; });
    var noServidor = estado.hoje === hoje && (estado.lancados_hoje || []).some(function (l) { return l.produtor === produtorId; });
    if (naFila || noServidor) {
      mostrarAviso("danger", nome + " já tem leite lançado hoje. Para corrigir, peça ao escritório.");
      return;
    }

    var item = {
      codigo: Fila.novoCodigo(), produtor: produtorId, nome: nome, forma: forma,
      litros: litros.toFixed(1), data: hoje, usuario: cfg.usuario,
      criado_em: new Date().toISOString(), situacao: "pendente"
    };
    Fila.salvar(item).then(function () {
      mostrarAviso("success", litrosBr(item.litros) + " de " + nome + " guardados" + (navigator.onLine ? ". Enviando..." : " no celular."));
      campoLitros.value = "";
      campoProdutor.value = "";
      pedirEnvioEmSegundoPlano();
      return recarregarFila();
    }).then(function () { return enviar(false); }).catch(function () {
      mostrarAviso("danger", "Não foi possível guardar no celular. Verifique o espaço de armazenamento do navegador.");
    });
  });

  // Tocar num produtor pendente seleciona ele no formulário
  document.getElementById("lista-pendentes").addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-escolher-produtor]");
    if (!botao) { return; }
    campoProdutor.value = botao.getAttribute("data-escolher-produtor");
    campoLitros.focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // Descartar um recusado (depois de avisar o escritório)
  document.getElementById("lista-recusados").addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-descartar]");
    if (!botao || !window.confirm("Descartar este lançamento do celular? Ele NÃO foi gravado no sistema.")) { return; }
    Fila.remover(botao.getAttribute("data-descartar")).then(recarregarFila);
  });

  document.getElementById("btn-enviar").addEventListener("click", function () { enviar(true); });
  window.addEventListener("online", function () { enviar(false); });
  window.addEventListener("offline", desenhar);
  setInterval(function () {
    if (fila.some(function (i) { return i.situacao === "pendente"; })) { enviar(false); }
  }, 60000);

  // ------------------------------------------------------------------ service worker
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register(cfg.sw).catch(function () { /* sem modo offline, mas a fila continua */ });
    // O service worker avisa quando enviou a fila em segundo plano.
    navigator.serviceWorker.addEventListener("message", function (evento) {
      if (evento.data && evento.data.tipo === "fila-atualizada") {
        atualizarEstadoDoServidor().then(recarregarFila);
      }
    });
  }

  // Início: mostra a fila e tenta enviar o que estiver pendente
  recarregarFila().then(function () { return enviar(false); });
})();
