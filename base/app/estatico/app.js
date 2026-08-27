/* A casca, do lado do navegador: abrir/fechar a gaveta, o tema e o app de celular.
   Sem biblioteca, sem CDN — a VPS pode estar sem saída e isso tem que abrir. */
(function () {
  "use strict";

  /* ---------------- gaveta ---------------- */
  var gaveta = document.getElementById("gaveta");
  var botao = document.getElementById("abregaveta");

  function abre() {
    if (!gaveta) return;
    gaveta.classList.add("on");
    document.body.style.overflow = "hidden";
  }
  function fecha() {
    if (!gaveta) return;
    gaveta.classList.remove("on");
    document.body.style.overflow = "";
  }

  if (botao) botao.addEventListener("click", abre);
  if (gaveta) {
    gaveta.addEventListener("click", function (e) {
      if (e.target.hasAttribute("data-fecha")) fecha();
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") fecha();
  });

  /* arrastar da borda esquerda pra abrir, e arrastar pra esquerda pra fechar */
  var x0 = null, y0 = null;
  document.addEventListener("touchstart", function (e) {
    var t = e.touches[0];
    x0 = t.clientX; y0 = t.clientY;
  }, { passive: true });
  document.addEventListener("touchend", function (e) {
    if (x0 === null) return;
    var t = e.changedTouches[0];
    var dx = t.clientX - x0, dy = Math.abs(t.clientY - y0);
    if (dy < 60) {
      if (x0 < 28 && dx > 60) abre();
      else if (gaveta && gaveta.classList.contains("on") && dx < -60) fecha();
    }
    x0 = null;
  }, { passive: true });

  /* ---------------- tema ---------------- */
  window.nxTema = function (valor) {           /* 'claro' | 'escuro' | 'auto' */
    var d = document.documentElement;
    try {
      if (valor === "auto") { localStorage.removeItem("nx-tema"); delete d.dataset.tema; }
      else { localStorage.setItem("nx-tema", valor); d.dataset.tema = valor; }
    } catch (e) {}
    var escuro = d.dataset.tema === "escuro" ||
      (d.dataset.tema !== "claro" && matchMedia("(prefers-color-scheme:dark)").matches);
    var m = document.querySelector("meta[name=theme-color]");
    if (m) m.content = escuro ? "#171a1f" : "#ffffff";
  };

  window.nxFonte = function (valor) {           /* '1' normal | '2' grande */
    var d = document.documentElement;
    try {
      if (valor === "2") { localStorage.setItem("nx-fonte", "2"); d.dataset.fs = "2"; }
      else { localStorage.removeItem("nx-fonte"); delete d.dataset.fs; }
    } catch (e) {}
  };

  /* ---------------- app de celular ---------------- */
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  /* ---------------- recadinho de canto ---------------- */
  window.nxAviso = function (texto) {
    var d = document.getElementById("nx-recado");
    if (!d) {
      d = document.createElement("div");
      d.id = "nx-recado";
      d.style.cssText = "position:fixed;left:50%;top:14px;transform:translateX(-50%);" +
        "background:var(--painel);border:1px solid var(--linha);color:var(--texto);" +
        "padding:9px 16px;border-radius:12px;font-size:14px;z-index:60;box-shadow:var(--sombra)";
      document.body.appendChild(d);
    }
    d.textContent = texto;
    d.style.display = "block";
    clearTimeout(d._t);
    d._t = setTimeout(function () { d.style.display = "none"; }, 2600);
  };
})();
