/**
 * Worker del panel Estrategia Electoral 2027 · X-irin Technologies S.A.S.
 *
 * 1. Identifica al usuario con el token que firma Cloudflare Access
 *    (cabecera Cf-Access-Jwt-Assertion o cookie CF_Authorization). La firma
 *    se verifica contra las llaves publicas del equipo, asi que el correo
 *    que se registra no lo puede falsificar el navegador.
 * 2. Bloquea a quien no es administrador los datos y paginas restringidos,
 *    y deja constancia de cada intento.
 * 3. Registra la actividad en D1 (tabla eventos) y la expone, solo a
 *    administradores, en /api/auditoria y /api/auditoria.csv.
 * 4. Modulo 11 Ciberseguridad: alertas, suspension de usuarios, sesion
 *    unica por dispositivo, limite de consultas, evidencia con huella
 *    SHA-256, revision de suplantacion y de correo del dominio, y
 *    retencion programada de registros (Ley 1581 de 2012).
 * 5. Todo lo demas lo sirve tal cual desde los archivos estaticos.
 */

const RESTRINGIDO = [/^\/data\/cundinamarca\//, /^\/auditoria(\.html)?$/, /^\/municipios(\.html)?$/];
const TIPOS = new Set(["inicio_sesion", "modulo", "latido", "salida", "restringido", "aviso_aceptado"]);
const MAX_SEG = 120;   // un latido nunca suma mas de 2 minutos
const AVISO_VERSION = "2026-10";   // si cambia el texto del aviso de privacidad, se vuelve a pedir aceptacion

// Solo administradores. Lo demas de /api/ciber/ lo usa cualquier usuario autenticado.
const CIBER_ADMIN = new Set(["alertas", "usuarios", "bloquear", "desbloquear", "evidencia", "evidencias", "privacidad"]);
// Lo que cuenta para el limite de consultas por minuto (extraccion masiva).
const CUENTA_LIMITE = /^\/(data\/|api\/(auditoria|ciber\/))/;

let JWKS = null, JWKS_EN = 0, ESQUEMA = false;

/* ---------------------------------------------------------- identidad */
const b64 = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")
  .padEnd(Math.ceil(s.length / 4) * 4, "=")), c => c.charCodeAt(0));

async function llaves(env) {
  if (JWKS && Date.now() - JWKS_EN < 3600_000) return JWKS;
  const r = await fetch(`https://${env.TEAM_DOMAIN}/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error("certs " + r.status);
  JWKS = await r.json(); JWKS_EN = Date.now();
  return JWKS;
}

function token(req) {
  const h = req.headers.get("Cf-Access-Jwt-Assertion");
  if (h) return h;
  const m = (req.headers.get("Cookie") || "").match(/(?:^|;\s*)CF_Authorization=([^;]+)/);
  return m ? m[1] : null;
}

async function identidad(req, env) {
  const t = token(req);
  if (!t) return null;
  try {
    const [h, p, s] = t.split(".");
    const cab = JSON.parse(new TextDecoder().decode(b64(h)));
    const datos = JSON.parse(new TextDecoder().decode(b64(p)));
    const jwk = ((await llaves(env)).keys || []).find(k => k.kid === cab.kid);
    if (!jwk) return null;
    const llave = await crypto.subtle.importKey("jwk", jwk,
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", llave, b64(s),
      new TextEncoder().encode(h + "." + p));
    if (!ok) return null;
    if (datos.exp && datos.exp < Date.now() / 1000) return null;
    const aud = Array.isArray(datos.aud) ? datos.aud : [datos.aud];
    if (!aud.includes(env.ACCESS_AUD)) return null;
    const email = String(datos.email || "").toLowerCase().trim();
    return email ? { email } : null;
  } catch (e) {
    return null;
  }
}

const esAdmin = (yo, env) => !!yo && String(env.ADMINS || "").toLowerCase()
  .split(",").map(x => x.trim()).filter(Boolean).includes(yo.email);

/* ---------------------------------------------------------- registro */
async function esquema(env) {
  if (ESQUEMA || !env.DB) return;
  await env.DB.batch([
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS eventos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      email TEXT,
      sesion TEXT,
      tipo TEXT NOT NULL,
      modulo TEXT,
      segundos INTEGER NOT NULL DEFAULT 0,
      ruta TEXT,
      ip TEXT,
      pais TEXT,
      ciudad TEXT,
      agente TEXT,
      detalle TEXT)`),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS ev_email_ts ON eventos(email, ts)"),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS ev_sesion ON eventos(sesion)"),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS ev_tipo_ts ON eventos(tipo, ts)"),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS alertas (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      email TEXT,
      tipo TEXT NOT NULL,
      nivel TEXT NOT NULL,
      detalle TEXT,
      ip TEXT,
      pais TEXT,
      ciudad TEXT,
      notificada INTEGER NOT NULL DEFAULT 0)`),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS al_ts ON alertas(ts)"),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS al_email_tipo ON alertas(email, tipo, ts)"),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS bloqueados (
      email TEXT PRIMARY KEY, ts TEXT NOT NULL, por TEXT, motivo TEXT)`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS dispositivos (
      email TEXT PRIMARY KEY, disp TEXT NOT NULL, ts TEXT NOT NULL, ip TEXT, ciudad TEXT, agente TEXT)`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS ajustes (
      clave TEXT PRIMARY KEY, valor TEXT NOT NULL, ts TEXT NOT NULL)`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS evidencias (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL, por TEXT NOT NULL, desde TEXT, hasta TEXT,
      registros INTEGER NOT NULL, sha256 TEXT NOT NULL)`)
  ]);
  ESQUEMA = true;
}

function contexto(req) {
  const cf = req.cf || {};
  return {
    ip: req.headers.get("CF-Connecting-IP") || "",
    pais: cf.country || "",
    ciudad: cf.city || "",
    agente: (req.headers.get("User-Agent") || "").slice(0, 300)
  };
}

async function registrar(env, req, yo, ev, admin = false) {
  if (!env.DB) return;
  try {
    await esquema(env);
    const c = contexto(req);
    const r = await env.DB.prepare(`INSERT INTO eventos
      (ts, email, sesion, tipo, modulo, segundos, ruta, ip, pais, ciudad, agente, detalle)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
      new Date().toISOString(), yo ? yo.email : "(sin identificar)",
      (ev.sesion || "").slice(0, 64), ev.tipo, (ev.modulo || "").slice(0, 80),
      Math.max(0, Math.min(MAX_SEG, Math.round(Number(ev.segundos) || 0))),
      (ev.ruta || "").slice(0, 300), c.ip, c.pais, c.ciudad, c.agente,
      (ev.detalle || "").slice(0, 300)
    ).run();
    if (!admin) await evaluar(env, yo, ev, c, (r && r.meta && r.meta.last_row_id) || 0);
  } catch (e) {
    console.log("registro fallido", e && e.message);
  }
}

/* ---------------------------------------------------------- alertas
   Se evaluan con cada evento de un usuario que no es administrador. Una
   misma alerta (usuario + tipo) no se repite antes de 10 minutos. Si hay
   bot de Telegram configurado (TELEGRAM_TOKEN y TELEGRAM_CHAT_ID como
   secretos del Worker), las de nivel medio y alto llegan al celular. */
const horaBogota = d => (d.getUTCHours() + 19) % 24;

async function alerta(env, a, c) {
  const email = a.email || "(sin identificar)";
  const hace10 = new Date(Date.now() - 10 * 60000).toISOString();
  const ya = await env.DB.prepare("SELECT 1 FROM alertas WHERE email = ? AND tipo = ? AND ts >= ? LIMIT 1")
    .bind(email, a.tipo, hace10).first();
  if (ya) return;
  let notificada = 0;
  if (a.nivel !== "baja") {
    notificada = await telegram(env, `⚠ ${a.nivel === "alta" ? "ALERTA ALTA" : "Alerta"} · Panel Electoral 2027\n` +
      `${a.tipo}\nUsuario: ${email}\n${a.detalle || ""}\nOrigen: ${[c.ciudad, c.pais].filter(Boolean).join(", ")} ${c.ip}`) ? 1 : 0;
  }
  await env.DB.prepare(`INSERT INTO alertas (ts, email, tipo, nivel, detalle, ip, pais, ciudad, notificada)
    VALUES (?,?,?,?,?,?,?,?,?)`).bind(new Date().toISOString(), email, a.tipo, a.nivel,
    (a.detalle || "").slice(0, 300), c.ip, c.pais, c.ciudad, notificada).run();
}

async function telegram(env, texto) {
  if (!env.TELEGRAM_TOKEN || !env.TELEGRAM_CHAT_ID) return false;
  try {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: texto.slice(0, 3500) }) });
    return r.ok;
  } catch (e) { return false; }
}

async function evaluar(env, yo, ev, c, id) {
  const email = yo ? yo.email : null;
  if (ev.tipo === "restringido") {
    const masiva = /extracci/i.test(ev.detalle || "");
    await alerta(env, { email, tipo: masiva ? "Posible extracción masiva de datos" : "Intento de acceso restringido",
      nivel: masiva || !email ? "alta" : "media",
      detalle: [ev.detalle, ev.ruta].filter(Boolean).join(" · ") }, c);
    return;
  }
  if (ev.tipo !== "inicio_sesion" || !email) return;

  // Ubicacion: se compara con los ingresos anteriores de la misma persona.
  const prev = (await env.DB.prepare(`SELECT DISTINCT pais, ciudad FROM eventos
    WHERE email = ? AND tipo = 'inicio_sesion' AND id < ?`).bind(email, id).all()).results || [];
  const lugar = [c.ciudad, c.pais].filter(Boolean).join(", ") || "ubicación desconocida";
  if (!prev.length) {
    await alerta(env, { email, tipo: "Primer ingreso del usuario", nivel: "baja", detalle: "Desde " + lugar }, c);
  } else if (c.pais && !prev.some(p => p.pais === c.pais)) {
    await alerta(env, { email, tipo: "Ingreso desde otro país", nivel: "alta", detalle: "Desde " + lugar }, c);
  } else if (c.ciudad && !prev.some(p => p.ciudad === c.ciudad)) {
    await alerta(env, { email, tipo: "Ingreso desde una ciudad nueva", nivel: "media", detalle: "Desde " + lugar }, c);
  }
  const h = horaBogota(new Date());
  if (h >= 23 || h < 5) {
    await alerta(env, { email, tipo: "Ingreso en horario inusual", nivel: "media",
      detalle: `A las ${String(h).padStart(2, "0")} h (hora de Bogotá)` }, c);
  }

  // Sesion unica: el ultimo dispositivo que entra queda como el vigente.
  const disp = String(ev.disp || "").slice(0, 64);
  if (!disp) return;
  const ant = await env.DB.prepare("SELECT disp FROM dispositivos WHERE email = ?").bind(email).first();
  if (ant && ant.disp !== disp) {
    await alerta(env, { email, tipo: "Mismo usuario en otro dispositivo", nivel: "media",
      detalle: "Se cerró la sesión del dispositivo anterior. Puede indicar contraseña compartida." }, c);
  }
  await env.DB.prepare(`INSERT INTO dispositivos (email, disp, ts, ip, ciudad, agente) VALUES (?,?,?,?,?,?)
    ON CONFLICT(email) DO UPDATE SET disp = excluded.disp, ts = excluded.ts, ip = excluded.ip,
    ciudad = excluded.ciudad, agente = excluded.agente`)
    .bind(email, disp, new Date().toISOString(), c.ip, c.ciudad, c.agente).run();
}

/* ---------------------------------------------------------- suspension */
let BLOQ = { t: 0, set: new Set() };
async function bloqueados(env) {
  if (!env.DB) return BLOQ.set;
  if (Date.now() - BLOQ.t < 30000) return BLOQ.set;
  try {
    await esquema(env);
    const r = await env.DB.prepare("SELECT email FROM bloqueados").all();
    BLOQ = { t: Date.now(), set: new Set((r.results || []).map(x => x.email)) };
  } catch (e) { /* si falla la consulta se conserva la lista anterior */ }
  return BLOQ.set;
}

/* ---------------------------------------------------------- limite de consultas
   Cuenta por usuario (o por IP si no hay identidad) dentro de cada copia del
   Worker. Es un freno contra quien intente bajarse los datos en bloque, no un
   contador exacto global. */
const CONTEO = new Map();
function excede(clave, limite) {
  const ahora = Date.now();
  let c = CONTEO.get(clave);
  if (!c || ahora - c.t > 60000) { c = { t: ahora, n: 0 }; CONTEO.set(clave, c); }
  c.n++;
  if (CONTEO.size > 5000) CONTEO.clear();
  return c.n > limite ? c.n : 0;
}

/* ---------------------------------------------------------- respuestas */
const json = (o, s = 200) => new Response(JSON.stringify(o), {
  status: s, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });

const prohibido = () => new Response(
  "<!doctype html><meta charset=utf-8><title>Acceso restringido</title>" +
  "<body style=\"font-family:system-ui;padding:40px;color:#150B3D\"><h2>Acceso restringido</h2>" +
  "<p>Su usuario no tiene permiso para ver esta informacion. El intento quedo registrado.</p>" +
  "<p><a href=\"/\">Volver al inicio</a></p>",
  { status: 403, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });

/* ---------------------------------------------------------- auditoria */
async function auditoria(env, url) {
  await esquema(env);
  const desde = url.searchParams.get("desde") || new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const hasta = url.searchParams.get("hasta") || new Date().toISOString().slice(0, 10);
  const email = (url.searchParams.get("email") || "").toLowerCase().trim();
  const filtro = "ts >= ? AND ts < date(?, '+1 day')" + (email ? " AND email = ?" : "");
  const args = email ? [desde, hasta, email] : [desde, hasta];

  const sesiones = await env.DB.prepare(`
    SELECT sesion, email, MIN(ts) inicio, MAX(ts) fin, SUM(segundos) segundos,
           MAX(ip) ip, MAX(pais) pais, MAX(ciudad) ciudad, MAX(agente) agente
    FROM eventos WHERE ${filtro} AND sesion <> ''
    GROUP BY sesion, email ORDER BY inicio DESC LIMIT 1000`).bind(...args).all();

  const modulos = await env.DB.prepare(`
    SELECT sesion, modulo, SUM(segundos) segundos, MIN(ts) primera
    FROM eventos WHERE ${filtro} AND sesion <> '' AND modulo <> ''
    GROUP BY sesion, modulo`).bind(...args).all();

  const restringidos = await env.DB.prepare(`
    SELECT ts, email, sesion, modulo, ruta, detalle, ip, pais
    FROM eventos WHERE ${filtro} AND tipo = 'restringido'
    ORDER BY ts DESC LIMIT 1000`).bind(...args).all();

  const usuarios = await env.DB.prepare(`
    SELECT email, COUNT(DISTINCT NULLIF(sesion, '')) sesiones, SUM(segundos) segundos,
           MIN(ts) primera, MAX(ts) ultima,
           SUM(CASE WHEN tipo='restringido' THEN 1 ELSE 0 END) restringidos
    FROM eventos WHERE ${filtro}
    GROUP BY email ORDER BY ultima DESC`).bind(...args).all();

  const porSesion = {};
  for (const m of modulos.results) (porSesion[m.sesion] ||= []).push(m);
  return {
    desde, hasta, email,
    usuarios: usuarios.results,
    sesiones: sesiones.results.map(s => ({ ...s, modulos: (porSesion[s.sesion] || [])
      .sort((a, b) => a.primera < b.primera ? -1 : 1) })),
    restringidos: restringidos.results
  };
}

async function csv(env, url) {
  await esquema(env);
  const desde = url.searchParams.get("desde") || "2000-01-01";
  const hasta = url.searchParams.get("hasta") || "2999-12-31";
  const r = await env.DB.prepare(`SELECT ts, email, sesion, tipo, modulo, segundos, ruta,
      ip, pais, ciudad, agente, detalle FROM eventos
      WHERE ts >= ? AND ts < date(?, '+1 day') ORDER BY ts LIMIT 100000`).bind(desde, hasta).all();
  const cols = ["ts", "email", "sesion", "tipo", "modulo", "segundos", "ruta", "ip", "pais", "ciudad", "agente", "detalle"];
  const q = v => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const body = "﻿" + cols.join(";") + "\n" + r.results.map(x => cols.map(c => q(x[c])).join(";")).join("\n");
  return new Response(body, { headers: {
    "Content-Type": "text/csv; charset=utf-8",
    "Content-Disposition": `attachment; filename="auditoria_${desde}_${hasta}.csv"`,
    "Cache-Control": "no-store" } });
}

/* ---------------------------------------------------------- demostracion
   Sin base D1 conectada, la auditoria muestra datos FICTICIOS para ver como
   funciona. Se generan siempre iguales (semilla fija) y fechados en los
   ultimos 14 dias. Al conectar D1 (binding DB) esto deja de usarse. */
function demoEventos() {
  let semilla = 20271027;
  const azar = () => (semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648;
  const elegir = l => l[Math.floor(azar() * l.length)];
  const USUARIOS = [
    { email: "candidato.demo@ejemplo.com", ip: "190.24.18.7", ciudad: "Soacha", dias: [0, 1, 2, 4, 6, 8, 11],
      agente: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36", curioso: true },
    { email: "gerente.campana@ejemplo.com", ip: "181.51.33.90", ciudad: "Bogotá", dias: [0, 1, 3, 5, 9, 12],
      agente: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1", curioso: false },
    { email: "asesor.juridico@ejemplo.com", ip: "186.155.4.21", ciudad: "Bogotá", dias: [2, 7, 10],
      agente: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/605.1.15", curioso: true },
    { email: "richbello@gmail.com", ip: "190.85.102.44", ciudad: "Soacha", dias: [0, 1, 2, 3, 4, 5, 6, 7],
      agente: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36", curioso: false }
  ];
  const MODULOS = ["Inicio", "01 Resultados históricos", "02 Pulso social", "03 Vigilancia fiscal",
    "04 Financiadores y contratos", "05 Territorio y obras", "06 Ficha del contendor"];
  const INTENTOS = [
    ["/modulos-3-integrados#cundinamarca", "Municipios de Cundinamarca (vista restringida)"],
    ["/data/cundinamarca/territorio/funza.json", "archivo o pagina restringida"],
    ["/municipios.html", "archivo o pagina restringida"],
    ["/api/auditoria", "consulta de auditoria"]
  ];
  const ev = [], hoy = new Date();
  for (const u of USUARIOS) {
    for (const d of u.dias) {
      const ini = new Date(hoy); ini.setUTCDate(ini.getUTCDate() - d);
      ini.setUTCHours(12 + Math.floor(azar() * 10), Math.floor(azar() * 60), 0, 0);   // 7 a. m. a 5 p. m. Bogota
      if (ini > hoy) ini.setUTCDate(ini.getUTCDate() - 1);
      const sesion = "demo-" + u.email.split("@")[0] + "-" + d;
      let t = ini.getTime();
      const base = { email: u.email, sesion, ip: u.ip, pais: "CO", ciudad: u.ciudad, agente: u.agente, detalle: "" };
      const push = (tipo, modulo, segundos, ruta, detalle) => t <= hoy.getTime() &&
        ev.push({ ...base, ts: new Date(t).toISOString(), tipo, modulo, segundos, ruta: ruta || "", detalle: detalle || "" });
      push("inicio_sesion", "Inicio", 0, "/");
      const recorrido = ["Inicio"].concat(Array.from({ length: 2 + Math.floor(azar() * 4) }, () => elegir(MODULOS.slice(1))));
      for (const m of recorrido) {
        push("modulo", m, 0, "/");
        const tramos = 1 + Math.floor(azar() * (m === "Inicio" ? 3 : 18));
        for (let i = 0; i < tramos; i++) { t += 30000; push("latido", m, 30, "/"); }
        if (u.curioso && m !== "Inicio" && azar() < 0.3) {
          const [ruta, det] = elegir(INTENTOS); t += 5000; push("restringido", m, 0, ruta, det);
        }
      }
      t += 10000; push("salida", recorrido[recorrido.length - 1], 8, "/");
    }
  }
  return ev.sort((a, b) => a.ts < b.ts ? -1 : 1);
}

function agregarDemo(url) {
  const desde = url.searchParams.get("desde") || new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const hasta = url.searchParams.get("hasta") || new Date().toISOString().slice(0, 10);
  const email = (url.searchParams.get("email") || "").toLowerCase().trim();
  const fin = new Date(hasta + "T00:00:00Z"); fin.setUTCDate(fin.getUTCDate() + 1);
  const ev = demoEventos().filter(e => e.ts >= desde && e.ts < fin.toISOString() && (!email || e.email === email));
  const ses = {}, usu = {};
  for (const e of ev) {
    const s = ses[e.sesion] ||= { sesion: e.sesion, email: e.email, inicio: e.ts, fin: e.ts, segundos: 0,
      ip: e.ip, pais: e.pais, ciudad: e.ciudad, agente: e.agente, mods: {} };
    s.fin = e.ts; s.segundos += e.segundos;
    if (e.modulo) { const m = s.mods[e.modulo] ||= { sesion: e.sesion, modulo: e.modulo, segundos: 0, primera: e.ts }; m.segundos += e.segundos; }
    const u = usu[e.email] ||= { email: e.email, ses: new Set(), segundos: 0, primera: e.ts, ultima: e.ts, restringidos: 0 };
    u.ses.add(e.sesion); u.segundos += e.segundos; u.ultima = e.ts;
    if (e.tipo === "restringido") u.restringidos++;
  }
  return {
    demo: true, desde, hasta, email,
    usuarios: Object.values(usu).map(u => ({ email: u.email, sesiones: u.ses.size, segundos: u.segundos,
      primera: u.primera, ultima: u.ultima, restringidos: u.restringidos })).sort((a, b) => a.ultima < b.ultima ? 1 : -1),
    sesiones: Object.values(ses).map(s => ({ sesion: s.sesion, email: s.email, inicio: s.inicio, fin: s.fin,
      segundos: s.segundos, ip: s.ip, pais: s.pais, ciudad: s.ciudad, agente: s.agente,
      modulos: Object.values(s.mods).sort((a, b) => a.primera < b.primera ? -1 : 1) }))
      .sort((a, b) => a.inicio < b.inicio ? 1 : -1),
    restringidos: ev.filter(e => e.tipo === "restringido").reverse()
      .map(({ ts, email, sesion, modulo, ruta, detalle, ip, pais }) => ({ ts, email, sesion, modulo, ruta, detalle, ip, pais }))
  };
}

function csvDemo(url) {
  const desde = url.searchParams.get("desde") || "2000-01-01";
  const hasta = url.searchParams.get("hasta") || "2999-12-31";
  const fin = new Date(hasta + "T00:00:00Z"); fin.setUTCDate(fin.getUTCDate() + 1);
  const filas = demoEventos().filter(e => e.ts >= desde && e.ts < fin.toISOString());
  const cols = ["ts", "email", "sesion", "tipo", "modulo", "segundos", "ruta", "ip", "pais", "ciudad", "agente", "detalle"];
  const q = v => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  return new Response("﻿# DATOS DE DEMOSTRACION - FICTICIOS\n" + cols.join(";") + "\n" +
    filas.map(x => cols.map(c => q(x[c])).join(";")).join("\n"), { headers: {
    "Content-Type": "text/csv; charset=utf-8",
    "Content-Disposition": `attachment; filename="auditoria_DEMO_${desde}_${hasta}.csv"`,
    "Cache-Control": "no-store" } });
}

/* ==========================================================================
   MODULO 11 · CIBERSEGURIDAD
   ========================================================================== */
const politica = env => ({
  inactividad_min: Number(env.INACTIVIDAD_MIN) || 30,
  retencion_dias: Number(env.RETENCION_DIAS) || 365,
  limite_min: Number(env.LIMITE_MIN) || 120,
  aviso_version: AVISO_VERSION,
  base: !!env.DB,
  telegram: !!(env.TELEGRAM_TOKEN && env.TELEGRAM_CHAT_ID)
});

const EMAIL_RX = /^[^\s@]{1,64}@[^\s@]{1,190}\.[a-z]{2,24}$/i;
const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
const rango = url => ({
  desde: url.searchParams.get("desde") || new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10),
  hasta: url.searchParams.get("hasta") || new Date().toISOString().slice(0, 10)
});
async function cuerpo(req) {
  try { return JSON.parse((await req.text()).slice(0, 8000)); } catch (e) { return null; }
}

/* ---------- DNS (Cloudflare DNS sobre HTTPS) */
const DOMINIO_RX = /^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$/;
function limpiarDominio(s) {
  s = String(s || "").trim().toLowerCase().replace(/^[a-z]+:\/\//, "").replace(/^www\./, "").split(/[\/?#:@\s]/)[0];
  return DOMINIO_RX.test(s) ? s : null;
}
async function doh(nombre, tipo) {
  const r = await fetch(`https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(nombre)}&type=${tipo}&do=1`,
    { headers: { accept: "application/dns-json" }, signal: AbortSignal.timeout(8000) });
  if (!r.ok) throw new Error("DNS " + r.status);
  return r.json();
}
const txtDe = (d, n = 16) => (d.Answer || []).filter(a => a.type === n)
  .map(a => String(a.data || "").replace(/"\s+"/g, "").replace(/^"|"$/g, ""));

async function revisarDominio(url) {
  const dom = limpiarDominio(url.searchParams.get("dominio"));
  if (!dom) return json({ error: "Escriba un dominio válido, por ejemplo candidato.com" }, 400);
  const [a, t, d, mx, caa] = await Promise.all([doh(dom, "A"), doh(dom, "TXT"),
    doh("_dmarc." + dom, "TXT"), doh(dom, "MX"), doh(dom, "CAA")]);
  if (a.Status === 3) return json({ dominio: dom, existe: false });

  const mxs = txtDe(mx, 15).map(x => x.split(/\s+/).pop().replace(/\.$/, "")).filter(Boolean);
  const spf = txtDe(t).find(x => /^v=spf1\b/i.test(x)) || null;
  const dmarc = txtDe(d).find(x => /^v=DMARC1\b/i.test(x)) || null;
  const p = dmarc ? ((dmarc.match(/\bp\s*=\s*(\w+)/i) || [])[1] || "").toLowerCase() : "";
  const caas = txtDe(caa, 257);
  const chequeos = [
    { clave: "spf", nombre: "SPF (quién puede enviar correo con el dominio)", valor: spf,
      estado: !spf ? "falta" : /[-]all\b/i.test(spf) ? "ok" : /~all\b/i.test(spf) ? "parcial" : "debil" },
    { clave: "dmarc", nombre: "DMARC (qué hacer con correos falsificados)", valor: dmarc,
      estado: !dmarc ? "falta" : p === "reject" ? "ok" : p === "quarantine" ? "parcial" : "debil" },
    { clave: "mx", nombre: "Servidor de correo (MX)", valor: mxs.join(", ") || null,
      estado: mxs.length ? "ok" : "info" },
    { clave: "dnssec", nombre: "DNSSEC (firma del dominio)", valor: a.AD ? "Activo" : null,
      estado: a.AD ? "ok" : "parcial" },
    { clave: "caa", nombre: "CAA (qué entidades pueden emitir certificados)", valor: caas.join(" · ") || null,
      estado: caas.length ? "ok" : "parcial" }
  ];
  return json({ dominio: dom, existe: true, chequeos, revisado: new Date().toISOString() });
}

/* ---------- Suplantacion: certificados publicos (crt.sh) + dominios parecidos */
function variantes(base, oficial, afijo) {
  const out = new Set();
  for (const t of ["com", "co", "com.co", "net", "org", "info", "online", "site", "net.co", "org.co"]) out.add(base + "." + t);
  const afijos = ["oficial", "-oficial", "2027", "-2027", "concejo", "prensa"];
  if (afijo) afijos.push(afijo, "-" + afijo);
  for (const a of afijos) { out.add(base + a + ".com"); out.add(base + a + ".co"); }
  const typos = [];
  for (let i = 0; i < base.length; i++) typos.push(base.slice(0, i) + base.slice(i + 1));                         // falta una letra
  for (let i = 0; i < base.length - 1; i++) typos.push(base.slice(0, i) + base[i + 1] + base[i] + base.slice(i + 2)); // letras cambiadas
  for (const [x, y] of [["o", "0"], ["l", "1"], ["i", "1"], ["e", "3"], ["a", "4"]]) if (base.includes(x)) typos.push(base.replace(x, y));
  for (const t of typos) if (t.length >= 3 && t !== base && !/^-|-$/.test(t)) out.add(t + ".com");
  if (oficial) out.delete(oficial);
  // El plan gratuito de Workers permite 50 consultas externas por solicitud.
  return [...out].slice(0, 40);
}

async function suplantacion(url) {
  const termino = String(url.searchParams.get("termino") || "").toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 40);
  const oficial = limpiarDominio(url.searchParams.get("oficial"));
  const afijo = String(url.searchParams.get("afijo") || "").toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 20);
  if (termino.length < 4) return json({ error: "Escriba al menos 4 letras, por ejemplo el nombre del candidato sin espacios." }, 400);

  const ct = (async () => {
    const r = await fetch(`https://crt.sh/?q=${encodeURIComponent("%" + termino + "%")}&output=json&exclude=expired&deduplicate=Y`,
      { headers: { "User-Agent": "XirinPanel/1.0" }, signal: AbortSignal.timeout(25000) });
    if (!r.ok) throw new Error("crt.sh respondió " + r.status);
    const lista = await r.json(), vistos = new Map();
    for (const x of lista) for (const n of String(x.name_value || "").toLowerCase().split(/\s+/)) {
      const nom = n.replace(/^\*\./, "");
      if (!nom.includes(termino)) continue;
      const prev = vistos.get(nom);
      if (!prev || String(x.not_before) > prev.desde) vistos.set(nom, { dominio: nom,
        emisor: (String(x.issuer_name || "").match(/O=("?)([^,"]+)\1/) || [])[2] || String(x.issuer_name || ""),
        desde: x.not_before, hasta: x.not_after });
    }
    return [...vistos.values()].map(c => ({ ...c,
      oficial: !!oficial && (c.dominio === oficial || c.dominio.endsWith("." + oficial)) }))
      .sort((a, b) => a.desde < b.desde ? 1 : -1).slice(0, 300);
  })();

  const base = oficial ? oficial.split(".")[0] : termino;
  const vs = Promise.all(variantes(base, oficial, afijo).map(async dominio => {
    try { const d = await doh(dominio, "NS"); return { dominio, registrado: d.Status === 0 ? true : d.Status === 3 ? false : null }; }
    catch (e) { return { dominio, registrado: null }; }
  }));

  const [c, v] = await Promise.allSettled([ct, vs]);
  return json({
    termino, oficial, revisado: new Date().toISOString(),
    certificados: c.status === "fulfilled" ? c.value : [],
    certificados_error: c.status === "rejected" ? String(c.reason && c.reason.message || c.reason) : null,
    variantes: v.status === "fulfilled" ? v.value : []
  });
}

/* ---------- Administracion: alertas, usuarios, suspension */
async function listarAlertas(env, url) {
  if (!env.DB) return alertasDemo(url);
  await esquema(env);
  const { desde, hasta } = rango(url);
  const nivel = url.searchParams.get("nivel") || "";
  const r = await env.DB.prepare(`SELECT id, ts, email, tipo, nivel, detalle, ip, pais, ciudad, notificada
    FROM alertas WHERE ts >= ? AND ts < date(?, '+1 day') ${nivel ? "AND nivel = ?" : ""}
    ORDER BY ts DESC LIMIT 1000`).bind(...(nivel ? [desde, hasta, nivel] : [desde, hasta])).all();
  return { desde, hasta, alertas: r.results || [] };
}

async function listarUsuarios(env) {
  if (!env.DB) return usuariosDemo(env);
  await esquema(env);
  const [ev, bl, di, av] = await Promise.all([
    env.DB.prepare(`SELECT email, MIN(ts) primera, MAX(ts) ultima, COUNT(DISTINCT NULLIF(sesion, '')) sesiones,
      SUM(segundos) segundos, SUM(CASE WHEN tipo='restringido' THEN 1 ELSE 0 END) restringidos
      FROM eventos WHERE email <> '(sin identificar)' GROUP BY email ORDER BY ultima DESC LIMIT 500`).all(),
    env.DB.prepare("SELECT email, ts, por, motivo FROM bloqueados").all(),
    env.DB.prepare("SELECT email, ts, ip, ciudad, agente FROM dispositivos").all(),
    env.DB.prepare("SELECT email, MAX(ts) ts FROM eventos WHERE tipo = 'aviso_aceptado' GROUP BY email").all()
  ]);
  const idx = (r, k = "email") => Object.fromEntries((r.results || []).map(x => [x[k], x]));
  const B = idx(bl), D = idx(di), A = idx(av);
  const admins = String(env.ADMINS || "").toLowerCase().split(",").map(x => x.trim());
  const filas = (ev.results || []).map(u => ({ ...u, admin: admins.includes(u.email),
    bloqueado: B[u.email] || null, dispositivo: D[u.email] || null, aviso: A[u.email] ? A[u.email].ts : null }));
  for (const e in B) if (!filas.some(f => f.email === e)) filas.push({ email: e, admin: false, bloqueado: B[e], sesiones: 0, segundos: 0 });
  return { usuarios: filas };
}

async function bloquear(env, req, yo, si) {
  const b = await cuerpo(req);
  const email = String(b && b.email || "").toLowerCase().trim();
  if (!EMAIL_RX.test(email)) return json({ error: "Correo no válido" }, 400);
  if (!env.DB) return json({ error: "La suspensión de usuarios necesita la base de datos D1 conectada." }, 409);
  const admins = String(env.ADMINS || "").toLowerCase().split(",").map(x => x.trim());
  if (si && admins.includes(email)) return json({ error: "No se puede suspender a un administrador." }, 400);
  await esquema(env);
  const c = contexto(req);
  if (si) {
    await env.DB.prepare(`INSERT INTO bloqueados (email, ts, por, motivo) VALUES (?,?,?,?)
      ON CONFLICT(email) DO UPDATE SET ts = excluded.ts, por = excluded.por, motivo = excluded.motivo`)
      .bind(email, new Date().toISOString(), yo.email, String(b.motivo || "").slice(0, 200)).run();
    await env.DB.prepare("DELETE FROM dispositivos WHERE email = ?").bind(email).run();
    BLOQ.set.add(email);
  } else {
    await env.DB.prepare("DELETE FROM bloqueados WHERE email = ?").bind(email).run();
    BLOQ.set.delete(email);
  }
  await env.DB.prepare(`INSERT INTO alertas (ts, email, tipo, nivel, detalle, ip, pais, ciudad, notificada)
    VALUES (?,?,?,?,?,?,?,?,0)`).bind(new Date().toISOString(), email, si ? "Usuario suspendido" : "Usuario reactivado",
    "baja", `Por ${yo.email}${b.motivo ? " · " + String(b.motivo).slice(0, 200) : ""}`, c.ip, c.pais, c.ciudad).run();
  return json({ ok: true });
}

async function estado(env, url, yo, admin) {
  if (!yo || admin || !env.DB) return json({ bloqueado: false, desplazado: false });
  await esquema(env);
  const disp = url.searchParams.get("disp") || "";
  const [b, d] = await Promise.all([
    env.DB.prepare("SELECT 1 FROM bloqueados WHERE email = ?").bind(yo.email).first(),
    env.DB.prepare("SELECT disp FROM dispositivos WHERE email = ?").bind(yo.email).first()]);
  return json({ bloqueado: !!b, desplazado: !!(d && disp && d.disp !== disp) });
}

/* ---------- Evidencia con huella SHA-256 */
const COLS = ["ts", "email", "sesion", "tipo", "modulo", "segundos", "ruta", "ip", "pais", "ciudad", "agente", "detalle"];
async function evidencia(env, url, yo) {
  const { desde, hasta } = rango(url);
  let filas, demo = false;
  if (env.DB) {
    await esquema(env);
    filas = (await env.DB.prepare(`SELECT ${COLS.join(", ")} FROM eventos
      WHERE ts >= ? AND ts < date(?, '+1 day') ORDER BY id LIMIT 100000`).bind(desde, hasta).all()).results || [];
  } else {
    demo = true;
    const fin = new Date(hasta + "T00:00:00Z"); fin.setUTCDate(fin.getUTCDate() + 1);
    filas = demoEventos().filter(e => e.ts >= desde && e.ts < fin.toISOString());
  }
  const q = v => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const csvTxt = "﻿" + (demo ? "# DATOS DE DEMOSTRACION - FICTICIOS\n" : "") + COLS.join(";") + "\n" +
    filas.map(x => COLS.map(c => q(x[c])).join(";")).join("\n");
  const sha256 = hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(csvTxt)));
  const generado = new Date().toISOString();
  if (!demo) await env.DB.prepare(`INSERT INTO evidencias (ts, por, desde, hasta, registros, sha256)
    VALUES (?,?,?,?,?,?)`).bind(generado, yo.email, desde, hasta, filas.length, sha256).run();
  return json({ demo, desde, hasta, registros: filas.length, sha256, generado, por: yo.email,
    archivo: `evidencia_${demo ? "DEMO_" : ""}${desde}_${hasta}.csv`, csv: csvTxt });
}

async function evidencias(env, url) {
  if (!env.DB) return json({ demo: true, evidencias: [] });
  await esquema(env);
  const sha = String(url.searchParams.get("sha") || "").toLowerCase().replace(/[^0-9a-f]/g, "");
  const r = sha
    ? await env.DB.prepare("SELECT * FROM evidencias WHERE sha256 = ?").bind(sha).all()
    : await env.DB.prepare("SELECT * FROM evidencias ORDER BY id DESC LIMIT 100").all();
  return json({ evidencias: r.results || [], buscado: sha || null });
}

/* ---------- Privacidad y lista de chequeo */
async function privacidad(env) {
  if (!env.DB) {
    const ev = demoEventos(), vistos = {};
    for (const e of ev) if (e.tipo === "inicio_sesion" && e.email !== "richbello@gmail.com" && !vistos[e.email]) vistos[e.email] = e.ts;
    return json({ demo: true, politica: politica(env),
      aceptaciones: Object.entries(vistos).map(([email, ts]) => ({ email, primera: ts, ultima: ts, veces: 1 })) });
  }
  await esquema(env);
  const r = await env.DB.prepare(`SELECT email, MIN(ts) primera, MAX(ts) ultima, COUNT(*) veces
    FROM eventos WHERE tipo = 'aviso_aceptado' GROUP BY email ORDER BY ultima DESC`).all();
  return json({ politica: politica(env), aceptaciones: r.results || [] });
}

async function checklist(env, req, yo) {
  if (!env.DB) return json({ sinBase: true, items: {} });
  await esquema(env);
  const clave = "checklist:" + (yo ? yo.email : "anonimo");
  if (req.method === "POST") {
    const b = await cuerpo(req);
    const items = {};
    if (b && b.items && typeof b.items === "object") for (const [k, v] of Object.entries(b.items).slice(0, 60))
      items[String(k).slice(0, 40)] = !!v;
    await env.DB.prepare(`INSERT INTO ajustes (clave, valor, ts) VALUES (?,?,?)
      ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, ts = excluded.ts`)
      .bind(clave, JSON.stringify(items), new Date().toISOString()).run();
    return json({ ok: true });
  }
  const r = await env.DB.prepare("SELECT valor, ts FROM ajustes WHERE clave = ?").bind(clave).first();
  return json({ items: r ? JSON.parse(r.valor) : {}, ts: r ? r.ts : null });
}

/* ---------- Demostracion del modulo (sin D1) */
function alertasDemo(url) {
  const { desde, hasta } = rango(url);
  const nivel = url.searchParams.get("nivel") || "";
  const fin = new Date(hasta + "T00:00:00Z"); fin.setUTCDate(fin.getUTCDate() + 1);
  const ev = demoEventos().filter(e => e.email !== "richbello@gmail.com");
  const out = [], primero = {}, n = {};
  for (const e of ev) {
    const base = { ts: e.ts, email: e.email, ip: e.ip, pais: e.pais, ciudad: e.ciudad, notificada: 0 };
    if (e.tipo === "inicio_sesion") {
      n[e.email] = (n[e.email] || 0) + 1;
      if (!primero[e.email]) { primero[e.email] = 1; out.push({ ...base, tipo: "Primer ingreso del usuario", nivel: "baja", detalle: "Desde " + e.ciudad + ", CO" }); }
      else if (e.email.startsWith("asesor") && n[e.email] === 2)
        out.push({ ...base, ciudad: "Medellín", ip: "181.143.70.12", tipo: "Ingreso desde una ciudad nueva", nivel: "media", detalle: "Desde Medellín, CO" });
      else if (e.email.startsWith("candidato") && n[e.email] === 3)
        out.push({ ...base, tipo: "Mismo usuario en otro dispositivo", nivel: "media", detalle: "Se cerró la sesión del dispositivo anterior. Puede indicar contraseña compartida." });
      else if (e.email.startsWith("asesor") && n[e.email] === 3)
        out.push({ ...base, tipo: "Posible extracción masiva de datos", nivel: "alta", detalle: "Exceso de consultas por minuto (posible extracción masiva) · /data/cundinamarca/analisis/" });
    } else if (e.tipo === "restringido") {
      out.push({ ...base, tipo: "Intento de acceso restringido", nivel: "media", detalle: [e.detalle, e.ruta].filter(Boolean).join(" · ") });
    }
  }
  return { demo: true, desde, hasta, alertas: out.filter(a => a.ts >= desde && a.ts < fin.toISOString() && (!nivel || a.nivel === nivel))
    .reverse().map((a, i) => ({ id: i + 1, ...a })) };
}

function usuariosDemo(env) {
  const d = agregarDemo(new URL("https://x/?desde=2000-01-01"));
  const admins = String(env.ADMINS || "").toLowerCase().split(",").map(x => x.trim());
  return { demo: true, usuarios: d.usuarios.map(u => {
    const s = d.sesiones.find(x => x.email === u.email);
    return { ...u, admin: admins.includes(u.email), bloqueado: null, aviso: admins.includes(u.email) ? null : u.primera,
      dispositivo: s ? { ts: s.inicio, ip: s.ip, ciudad: s.ciudad, agente: s.agente } : null };
  }) };
}

async function ciber(nombre, req, env, url, yo, admin) {
  if (CIBER_ADMIN.has(nombre) && !admin) return null;
  switch (nombre) {
    case "alertas": return json(await listarAlertas(env, url));
    case "usuarios": return json(await listarUsuarios(env));
    case "bloquear": return req.method === "POST" ? bloquear(env, req, yo, true) : json({ error: "POST" }, 405);
    case "desbloquear": return req.method === "POST" ? bloquear(env, req, yo, false) : json({ error: "POST" }, 405);
    case "evidencia": return evidencia(env, url, yo);
    case "evidencias": return evidencias(env, url);
    case "privacidad": return privacidad(env);
    case "dns": return revisarDominio(url);
    case "suplantacion": return suplantacion(url);
    case "checklist": return checklist(env, req, yo);
    default: return json({ error: "no existe" }, 404);
  }
}

const suspendido = () => new Response(
  "<!doctype html><meta charset=utf-8><title>Usuario suspendido</title>" +
  "<body style=\"font-family:system-ui;padding:40px;color:#150B3D\"><h2>Usuario suspendido</h2>" +
  "<p>El acceso de este usuario al panel está suspendido. Comuníquese con X-irin Technologies S.A.S.</p>" +
  "<p><a href=\"/cdn-cgi/access/logout\">Cerrar sesión</a></p>",
  { status: 403, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });

/* ---------------------------------------------------------- entrada */
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const ruta = url.pathname;
    const yo = await identidad(req, env);
    const admin = esAdmin(yo, env);

    // Usuario suspendido: no ve nada mas.
    if (yo && !admin && (await bloqueados(env)).has(yo.email)) {
      if (ruta.startsWith("/api/")) return json({ error: "suspendido" }, 403);
      if (!/\.[a-z0-9]+$/i.test(ruta) || /\.html$/i.test(ruta))
        ctx.waitUntil(registrar(env, req, yo, { tipo: "restringido", ruta, detalle: "usuario suspendido intentó entrar" }));
      return suspendido();
    }

    // Limite de consultas por minuto a datos y APIs (freno a la extraccion masiva).
    if (!admin && CUENTA_LIMITE.test(ruta)) {
      const limite = Number(env.LIMITE_MIN) || 120;
      const n = excede(yo ? yo.email : "ip:" + (req.headers.get("CF-Connecting-IP") || ""), limite);
      if (n) {
        if (n === limite + 1) ctx.waitUntil(registrar(env, req, yo, { tipo: "restringido", ruta,
          detalle: "Exceso de consultas por minuto (posible extracción masiva)" }));
        return new Response(JSON.stringify({ error: "Demasiadas consultas. Espere un minuto." }), { status: 429,
          headers: { "Content-Type": "application/json; charset=utf-8", "Retry-After": "60", "Cache-Control": "no-store" } });
      }
    }

    if (ruta === "/api/yo") return json({ email: yo ? yo.email : null, admin, politica: politica(env) });

    if (ruta === "/api/evento" && req.method === "POST") {
      const txt = (await req.text()).slice(0, 2000);
      let ev; try { ev = JSON.parse(txt); } catch (e) { return json({ ok: false }, 400); }
      if (!ev || !TIPOS.has(ev.tipo)) return json({ ok: false }, 400);
      ctx.waitUntil(registrar(env, req, yo, ev, admin));
      return json({ ok: true });
    }

    if (ruta === "/api/estado") return estado(env, url, yo, admin);

    const mc = ruta.match(/^\/api\/ciber\/([a-z]+)$/);
    if (mc) {
      if (!yo) return json({ error: "sin identificar" }, 401);
      try {
        const r = await ciber(mc[1], req, env, url, yo, admin);
        if (r) return r;
      } catch (e) {
        return json({ error: "No se pudo completar la consulta: " + (e && e.message || e) }, 502);
      }
      ctx.waitUntil(registrar(env, req, yo, { tipo: "restringido", ruta, detalle: "consulta de ciberseguridad (solo administradores)" }));
      return json({ error: "restringido" }, 403);
    }

    if (ruta === "/api/auditoria" || ruta === "/api/auditoria.csv") {
      if (!admin) {
        ctx.waitUntil(registrar(env, req, yo, { tipo: "restringido", ruta, detalle: "consulta de auditoria" }));
        return json({ error: "restringido" }, 403);
      }
      if (!env.DB) return ruta.endsWith(".csv") ? csvDemo(url) : json(agregarDemo(url));
      return ruta.endsWith(".csv") ? csv(env, url) : json(await auditoria(env, url));
    }

    if (!admin && RESTRINGIDO.some(rx => rx.test(ruta))) {
      ctx.waitUntil(registrar(env, req, yo, { tipo: "restringido", ruta, detalle: "archivo o pagina restringida" }));
      return prohibido();
    }

    return env.ASSETS.fetch(req);
  },

  // Retencion: borra registros mas antiguos que RETENCION_DIAS (por defecto 365).
  // Las constancias de evidencia (solo la huella) se conservan.
  async scheduled(evento, env, ctx) {
    if (!env.DB) return;
    await esquema(env);
    const dias = Number(env.RETENCION_DIAS) || 365;
    const corte = new Date(Date.now() - dias * 864e5).toISOString();
    await env.DB.batch([
      env.DB.prepare("DELETE FROM eventos WHERE ts < ?").bind(corte),
      env.DB.prepare("DELETE FROM alertas WHERE ts < ?").bind(corte)
    ]);
  }
};
