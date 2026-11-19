/*
  static/js/graficos.js
  Desenha os gráficos (Chart.js) de qualquer tela.

  No template:
    <canvas data-grafico="area|barra|barra-horizontal|rosca" data-fonte="id-do-json" data-moeda="1"></canvas>
    {{ dados|json_script:"id-do-json" }}

  O JSON tem o formato: {"rotulos": [...], "series": [{"rotulo": "...", "dados": [...]}]}
  Os dados chegam pelo json_script do Django (protegido contra XSS), nunca escritos direto no JS.
*/
(function () {
  "use strict";
  if (typeof Chart === "undefined") { return; }

  var CORES = ["#1d4e9e", "#f5c518", "#dc3545", "#4a90e2", "#20c997", "#6f42c1", "#6c757d", "#fd7e14"];
  var formatoMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  var formatoNumero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

  function transparente(hex, alfa) {
    var n = parseInt(hex.slice(1), 16);
    return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + alfa + ")";
  }

  document.querySelectorAll("canvas[data-grafico]").forEach(function (canvas) {
    var fonte = document.getElementById(canvas.getAttribute("data-fonte"));
    if (!fonte) { return; }
    var dados = JSON.parse(fonte.textContent);
    var tipo = canvas.getAttribute("data-grafico");
    var moeda = canvas.getAttribute("data-moeda") === "1";
    var formatar = function (v) { return moeda ? formatoMoeda.format(v) : formatoNumero.format(v); };
    var rosca = tipo === "rosca";

    var datasets = dados.series.map(function (serie, i) {
      var cor = CORES[i % CORES.length];
      return {
        label: serie.rotulo,
        data: serie.dados,
        borderColor: rosca ? "#fff" : cor,
        backgroundColor: rosca ? CORES : (tipo === "area" ? transparente(cor, 0.25) : transparente(cor, 0.8)),
        fill: tipo === "area",
        tension: 0.35,
        borderWidth: rosca ? 2 : 2,
        pointRadius: tipo === "area" ? 3 : 0
      };
    });

    new Chart(canvas, {
      type: rosca ? "doughnut" : (tipo === "area" ? "line" : "bar"),
      data: { labels: dados.rotulos, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: tipo === "barra-horizontal" ? "y" : "x",
        plugins: {
          legend: { display: rosca || datasets.length > 1, position: "bottom" },
          tooltip: { callbacks: { label: function (ctx) {
            var valor = ctx.parsed !== null && typeof ctx.parsed === "object" ? (tipo === "barra-horizontal" ? ctx.parsed.x : ctx.parsed.y) : ctx.parsed;
            return (ctx.dataset.label || ctx.label) + ": " + formatar(valor);
          } } }
        },
        scales: rosca ? {} : {
          y: { beginAtZero: true, ticks: { callback: function (v) { return tipo === "barra-horizontal" ? this.getLabelForValue(v) : formatar(v); } } },
          x: { ticks: { callback: function (v) { return tipo === "barra-horizontal" ? formatar(v) : this.getLabelForValue(v); } } }
        }
      }
    });
  });
})();
