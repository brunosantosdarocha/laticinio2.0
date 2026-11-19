/*
  static/js/sistema.js
  Comportamentos usados em várias telas (sem JavaScript dentro do HTML):
  1. <form data-confirmar="texto"> pede confirmação antes de enviar (ações perigosas);
  2. evita clique duplo: desativa o botão depois do primeiro envio;
  3. botão de imprimir (data-imprimir);
  4. pagamento misto: completa o Pix sozinho (total - dinheiro);
  5. calendário: "Falta" trava o campo de litros;
  6. coleta diária: tocar num produtor pendente já seleciona ele no formulário.
*/
(function () {
  "use strict";

  // 1 e 2 - confirmação e proteção contra duplo clique
  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    var texto = form.getAttribute("data-confirmar");
    if (texto && !window.confirm(texto)) {
      evento.preventDefault();
      return;
    }
    if (form.dataset.enviando === "1") {
      evento.preventDefault();
      return;
    }
    form.dataset.enviando = "1";
    // Downloads (PDF/backup) não recarregam a página: libera o formulário de novo depois.
    setTimeout(function () { form.dataset.enviando = "0"; }, 4000);
    form.querySelectorAll("button[type=submit]").forEach(function (botao) {
      botao.classList.add("disabled");
      setTimeout(function () { botao.classList.remove("disabled"); }, 4000);
    });
  });

  // 3 - imprimir
  document.querySelectorAll("[data-imprimir]").forEach(function (botao) {
    botao.addEventListener("click", function () { window.print(); });
  });

  // 4 - pagamento misto (dinheiro + Pix)
  var forma = document.querySelector("[data-pg-forma]");
  if (forma) {
    var total = document.querySelector("[data-pg-total]");
    var dinheiro = document.querySelector("[data-pg-dinheiro]");
    var pix = document.querySelector("[data-pg-pix]");
    var blocoMisto = function () {
      var misto = forma.value === "MISTO";
      [dinheiro, pix].forEach(function (campo) {
        var bloco = campo.closest("[class^=col]") || campo.parentElement;
        bloco.style.display = misto ? "" : "none";
      });
    };
    var completarPix = function () {
      var t = parseFloat(total.value || "0");
      var d = parseFloat(dinheiro.value || "0");
      if (!isNaN(t) && !isNaN(d) && t >= d) {
        pix.value = (Math.round((t - d) * 100) / 100).toFixed(2);
      }
    };
    forma.addEventListener("change", blocoMisto);
    dinheiro.addEventListener("input", completarPix);
    total.addEventListener("input", completarPix);
    blocoMisto();
  }

  // 5 - calendário: falta trava o campo
  document.querySelectorAll("[data-falta]").forEach(function (caixa) {
    var campo = document.getElementById(caixa.getAttribute("data-falta"));
    var celula = caixa.closest(".cal-dia");
    var aplicar = function () {
      if (caixa.checked) {
        campo.dataset.anterior = campo.value;
        campo.value = "";
        campo.readOnly = true;
        campo.placeholder = "falta";
      } else {
        campo.readOnly = false;
        campo.placeholder = "";
        if (campo.dataset.anterior) { campo.value = campo.dataset.anterior; }
      }
      if (celula) { celula.classList.toggle("tem-falta", caixa.checked); }
    };
    caixa.addEventListener("change", aplicar);
    if (caixa.checked) { aplicar(); }
  });

  // 6 - coleta diária: escolher produtor pendente com um toque
  document.querySelectorAll("[data-escolher-produtor]").forEach(function (item) {
    item.addEventListener("click", function () {
      var select = document.getElementById("id_produtor");
      if (!select) { return; }
      select.value = item.getAttribute("data-escolher-produtor");
      var litros = document.getElementById("id_litros");
      if (litros) { litros.focus(); }
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
})();
