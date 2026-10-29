/* Registro de actividad del panel (auditoria).
   Envia al Worker: inicio de sesion, cambio de modulo, y cada 30 segundos el
   tiempo ACTIVO (pestana visible) en el modulo actual. El correo no lo manda
   esta pagina: lo pone el Worker a partir del token de Cloudflare Access. */
(function () {
  "use strict";
  var CLAVE = "xirin_sesion", PASO = 30000, s, nueva = false;
  try { s = sessionStorage.getItem(CLAVE); } catch (e) {}
  if (!s) {
    s = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : Date.now().toString(36) + Math.random().toString(36).slice(2);
    nueva = true;
    try { sessionStorage.setItem(CLAVE, s); } catch (e) {}
  }

  var HASH = { vigilancia: "03 Vigilancia fiscal", cundinamarca: "03 Vigilancia · Cundinamarca",
    financiadores: "04 Financiadores y contratos", territorio: "05 Territorio y obras",
    ficha: "06 Ficha del contendor" };
  var PAGINA = { "": "Inicio", "index": "Inicio", "resultados-historicos": "01 Resultados históricos",
    "soacha-2027": "02 Pulso social", "municipios": "Municipios de Cundinamarca",
    "vigilancia-fiscal-soacha": "03 Vigilancia fiscal (Soacha)",
    "analisis-electoral-2027": "Análisis electoral 2027", "analisis-electoral-2027-embed": "Análisis electoral 2027",
    "auditoria": "Auditoría" };

  function modulo() {
    var p = location.pathname.replace(/\/+$/, "").split("/").pop().replace(/\.html$/, "");
    if (p === "modulos-3-integrados") return HASH[location.hash.slice(1)] || HASH.vigilancia;
    return PAGINA[p] || p;
  }

  function enviar(ev) {
    ev.sesion = s;
    ev.ruta = location.pathname + location.hash;
    var cuerpo = JSON.stringify(ev);
    try {
      if (navigator.sendBeacon && navigator.sendBeacon("/api/evento",
          new Blob([cuerpo], { type: "application/json" }))) return;
    } catch (e) {}
    try { fetch("/api/evento", { method: "POST", body: cuerpo, keepalive: true,
      headers: { "Content-Type": "application/json" } }); } catch (e) {}
  }

  var actual = modulo(), marca = Date.now();
  var visible = document.visibilityState !== "hidden";

  function corte() {
    if (!visible) return 0;
    var seg = Math.round((Date.now() - marca) / 1000);
    marca = Date.now();
    return Math.max(0, Math.min(120, seg));
  }

  if (nueva) enviar({ tipo: "inicio_sesion", modulo: actual });
  enviar({ tipo: "modulo", modulo: actual });

  setInterval(function () {
    var seg = corte();
    if (seg > 0) enviar({ tipo: "latido", modulo: actual, segundos: seg });
  }, PASO);

  window.addEventListener("hashchange", function () {
    var nuevo = modulo();
    if (nuevo === actual) return;
    var seg = corte();
    if (seg > 0) enviar({ tipo: "latido", modulo: actual, segundos: seg });
    actual = nuevo;
    enviar({ tipo: "modulo", modulo: actual });
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      var seg = corte();
      visible = false;
      enviar({ tipo: "salida", modulo: actual, segundos: seg });
    } else {
      visible = true;
      marca = Date.now();
    }
  });

  // Boton "Auditoria" en el encabezado, solo para administradores. El permiso
  // real lo decide el Worker: aunque alguien fuerce el boton, /api/auditoria
  // le responde "restringido" y deja constancia del intento.
  if (!/\/auditoria(\.html)?$/.test(location.pathname)) {
    fetch("/api/yo", { credentials: "include", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (yo) {
        if (!yo || !yo.admin) return;
        var bar = document.querySelector("header .bar");
        if (!bar || bar.querySelector(".xirin-aud")) return;
        var a = document.createElement("a");
        a.href = "/auditoria.html";
        a.className = "xirin-aud";
        a.textContent = "Auditoría";
        a.title = "Auditoría de accesos (solo administradores)";
        a.style.cssText = "margin-left:auto;color:#FFB020;text-decoration:none;font:600 13px Inter,'Segoe UI',sans-serif;" +
          "border:1px solid rgba(255,176,32,.55);padding:9px 14px;border-radius:8px;white-space:nowrap";
        var back = bar.querySelector(".back");
        if (back) { back.style.marginLeft = "10px"; bar.insertBefore(a, back); } else bar.appendChild(a);
      })
      .catch(function () {});
  }

  // Para que las paginas registren un intento bloqueado en pantalla.
  window.xirinRestringido = function (detalle) {
    enviar({ tipo: "restringido", modulo: actual, detalle: String(detalle || "") });
  };
})();
