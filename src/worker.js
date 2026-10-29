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
 * 4. Todo lo demas lo sirve tal cual desde los archivos estaticos.
 */

const RESTRINGIDO = [/^\/data\/cundinamarca\//, /^\/auditoria(\.html)?$/, /^\/municipios(\.html)?$/];
const TIPOS = new Set(["inicio_sesion", "modulo", "latido", "salida", "restringido"]);
const MAX_SEG = 120;   // un latido nunca suma mas de 2 minutos

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
    env.DB.prepare("CREATE INDEX IF NOT EXISTS ev_tipo_ts ON eventos(tipo, ts)")
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

async function registrar(env, req, yo, ev) {
  if (!env.DB) return;
  try {
    await esquema(env);
    const c = contexto(req);
    await env.DB.prepare(`INSERT INTO eventos
      (ts, email, sesion, tipo, modulo, segundos, ruta, ip, pais, ciudad, agente, detalle)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
      new Date().toISOString(), yo ? yo.email : "(sin identificar)",
      (ev.sesion || "").slice(0, 64), ev.tipo, (ev.modulo || "").slice(0, 80),
      Math.max(0, Math.min(MAX_SEG, Math.round(Number(ev.segundos) || 0))),
      (ev.ruta || "").slice(0, 300), c.ip, c.pais, c.ciudad, c.agente,
      (ev.detalle || "").slice(0, 300)
    ).run();
  } catch (e) {
    console.log("registro fallido", e && e.message);
  }
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

/* ---------------------------------------------------------- entrada */
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const ruta = url.pathname;
    const yo = await identidad(req, env);
    const admin = esAdmin(yo, env);

    if (ruta === "/api/yo") return json({ email: yo ? yo.email : null, admin });

    if (ruta === "/api/evento" && req.method === "POST") {
      const txt = (await req.text()).slice(0, 2000);
      let ev; try { ev = JSON.parse(txt); } catch (e) { return json({ ok: false }, 400); }
      if (!TIPOS.has(ev.tipo)) return json({ ok: false }, 400);
      ctx.waitUntil(registrar(env, req, yo, ev));
      return json({ ok: true });
    }

    if (ruta === "/api/auditoria" || ruta === "/api/auditoria.csv") {
      if (!admin) {
        ctx.waitUntil(registrar(env, req, yo, { tipo: "restringido", ruta, detalle: "consulta de auditoria" }));
        return json({ error: "restringido" }, 403);
      }
      if (!env.DB) return json({ error: "Falta conectar la base de datos D1 (binding DB)." }, 500);
      return ruta.endsWith(".csv") ? csv(env, url) : json(await auditoria(env, url));
    }

    if (!admin && RESTRINGIDO.some(rx => rx.test(ruta))) {
      ctx.waitUntil(registrar(env, req, yo, { tipo: "restringido", ruta, detalle: "archivo o pagina restringida" }));
      return prohibido();
    }

    return env.ASSETS.fetch(req);
  }
};
