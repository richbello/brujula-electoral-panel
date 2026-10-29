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
    "auditoria": "Auditoría", "soacha-inversion": "08 Soacha: inversión", "soacha-seguridad": "09 Seguridad y convivencia" };

  function modulo() {
    if (/^\/presupuesto(\/|$)/.test(location.pathname)) return "07 Análisis presupuestal";
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

  /* ---------- Proteccion del contenido (solo para clientes) ----------
     Arranca activa para todos y se retira si el Worker confirma que el
     usuario es administrador; ante cualquier error queda activa.
     Disuade y deja evidencia, pero no impide una captura de pantalla:
     por eso la marca de agua con el correo de quien mira. */
  var esAdmin = false, ultimo = {};
  var raiz = document.documentElement;
  raiz.classList.add("xirin-protegido");

  var css = document.createElement("style");
  css.textContent =
    "html.xirin-protegido body{-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}" +
    "html.xirin-protegido input,html.xirin-protegido textarea,html.xirin-protegido select{-webkit-user-select:text;user-select:text}" +
    "html.xirin-protegido .btn-csv,html.xirin-protegido #pzCsv,html.xirin-protegido #cun-csv{display:none!important}" +
    "#xirin-agua{position:fixed;inset:0;pointer-events:none;z-index:2147483646;background-repeat:repeat}" +
    "#xirin-aviso{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:2147483647;" +
    "background:#150B3D;color:#fff;font:600 13px Inter,'Segoe UI',sans-serif;padding:11px 18px;border-radius:9px;" +
    "box-shadow:0 6px 24px rgba(0,0,0,.25);border-left:4px solid #FFB020;max-width:calc(100% - 32px)}" +
    "@media print{html.xirin-protegido body>*{display:none!important}" +
    "html.xirin-protegido body::after{content:'Contenido confidencial de X-irin Technologies S.A.S. No se permite imprimir este panel.';" +
    "display:block;padding:60px 40px;font:600 18px sans-serif;color:#150B3D}}";
  (document.head || raiz).appendChild(css);

  // Un mismo tipo de intento se registra a lo sumo cada 20 s, para no inundar la auditoria.
  function intento(tipo, texto) {
    if (esAdmin) return;
    aviso(texto);
    var ahora = Date.now();
    if (ultimo[tipo] && ahora - ultimo[tipo] < 20000) return;
    ultimo[tipo] = ahora;
    enviar({ tipo: "restringido", modulo: actual, detalle: "Intento de " + tipo });
  }

  var tAviso = null;
  function aviso(texto) {
    var a = document.getElementById("xirin-aviso");
    if (!a) { a = document.createElement("div"); a.id = "xirin-aviso"; document.body.appendChild(a); }
    a.textContent = texto + " El intento quedó registrado.";
    a.hidden = false;
    clearTimeout(tAviso);
    tAviso = setTimeout(function () { a.hidden = true; }, 3500);
  }

  function enCampo(e) {
    var t = e.target;
    return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
  }

  document.addEventListener("copy", function (e) {
    if (esAdmin || enCampo(e)) return;
    e.preventDefault();
    if (e.clipboardData) e.clipboardData.setData("text/plain", "Contenido confidencial de X-irin Technologies S.A.S.");
    intento("copiar", "Copiar información del panel no está permitido.");
  }, true);
  document.addEventListener("cut", function (e) {
    if (esAdmin || enCampo(e)) return;
    e.preventDefault();
    intento("copiar", "Copiar información del panel no está permitido.");
  }, true);
  document.addEventListener("contextmenu", function (e) {
    if (esAdmin || enCampo(e)) return;
    e.preventDefault();
    intento("clic derecho", "El menú del clic derecho está deshabilitado.");
  }, true);
  document.addEventListener("dragstart", function (e) {
    if (esAdmin) return;
    e.preventDefault();
  }, true);
  document.addEventListener("keydown", function (e) {
    if (esAdmin) return;
    var k = (e.key || "").toLowerCase(), mod = e.ctrlKey || e.metaKey;
    if (mod && k === "p") { e.preventDefault(); intento("imprimir", "Imprimir el panel no está permitido."); }
    else if (mod && k === "s") { e.preventDefault(); intento("guardar la página", "Guardar la página no está permitido."); }
    else if (mod && k === "u") { e.preventDefault(); intento("ver el código fuente", "Ver el código de la página no está permitido."); }
    else if (k === "f12" || (mod && e.shiftKey && (k === "i" || k === "j" || k === "c"))) {
      intento("abrir herramientas de desarrollador", "Las herramientas de desarrollador no están permitidas en este panel.");
    }
    else if (k === "printscreen") { intento("captura de pantalla", "Las capturas de pantalla llevan su correo como marca de agua."); }
  }, true);
  window.addEventListener("beforeprint", function () {
    if (!esAdmin) intento("imprimir", "Imprimir el panel no está permitido.");
  });

  // Descargas que las paginas generan por codigo (CSV y similares).
  var clicOriginal = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (!esAdmin && this.hasAttribute("download")) {
      intento("descargar datos", "La descarga de datos no está habilitada para su usuario.");
      return;
    }
    return clicOriginal.apply(this, arguments);
  };
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest && e.target.closest("a[download]");
    if (a && !esAdmin) { e.preventDefault(); intento("descargar datos", "La descarga de datos no está habilitada para su usuario."); }
  }, true);

  /* Marca de agua con el correo, la fecha y la hora, repetida en diagonal. */
  function marcaDeAgua(email) {
    var f = new Date().toLocaleString("es-CO", { timeZone: "America/Bogota",
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
    var txt = (email || "usuario no identificado") + " · " + f;
    var x = function (s) { return s.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="220">' +
      '<text x="210" y="110" text-anchor="middle" transform="rotate(-24 210 110)" ' +
      'font-family="Inter,Segoe UI,Arial,sans-serif" font-size="14" font-weight="600" fill="#150B3D" fill-opacity="0.09">' +
      x(txt) + "</text></svg>";
    var capa = document.getElementById("xirin-agua");
    if (!capa) { capa = document.createElement("div"); capa.id = "xirin-agua"; capa.setAttribute("aria-hidden", "true"); }
    capa.style.backgroundImage = 'url("data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg) + '")';
    if (!capa.isConnected) document.body.appendChild(capa);
    return capa;
  }

  function vigilarMarca(email) {
    marcaDeAgua(email);
    // Si alguien la borra o la oculta desde las herramientas del navegador, vuelve y queda registrado.
    new MutationObserver(function () {
      var c = document.getElementById("xirin-agua");
      var oculta = c && (c.style.display === "none" || c.style.visibility === "hidden" || c.style.opacity === "0");
      if (!c || oculta) {
        if (c) c.remove();
        marcaDeAgua(email);
        intento("quitar la marca de agua", "La marca de agua no se puede quitar.");
      }
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["style", "class", "hidden"] });
    setInterval(function () { marcaDeAgua(email); }, 60000);   // actualiza la hora
  }

  function botonAuditoria() {
    if (/\/auditoria(\.html)?$/.test(location.pathname)) return;
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
  }

  // El permiso lo decide el Worker con la identidad firmada de Cloudflare Access.
  fetch("/api/yo", { credentials: "include", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (yo) {
      if (yo && yo.admin) {
        esAdmin = true;
        raiz.classList.remove("xirin-protegido");
        botonAuditoria();
      } else {
        vigilarMarca(yo && yo.email);
      }
    });

  // Para que las paginas registren un intento bloqueado en pantalla.
  window.xirinRestringido = function (detalle) {
    enviar({ tipo: "restringido", modulo: actual, detalle: String(detalle || "") });
  };
})();
