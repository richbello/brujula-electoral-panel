#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
26_facebook_canal_sentimiento.py
Pulso de Facebook por PAGINA: trae las publicaciones recientes de una pagina
publica, baja los comentarios de las que tienen conversacion, clasifica
sentimiento + agenda con Claude y lo MEZCLA en data/sentimiento_soacha.json
como un candidato mas (bloque de Facebook), conservando YouTube y los demas.

Mismo formato de salida que 24_youtube_canal_sentimiento.py, asi el panel
soacha-2027.html compara a los candidatos lado a lado automaticamente.

Dos pases:
  1) AGENDA  -> de que habla el candidato. Sale de TODAS sus publicaciones
     desde la fecha indicada (sin sesgo), tengan o no comentarios.
  2) RECEPCION -> sentimiento. Solo baja comentarios de las publicaciones que
     SI tienen conversacion (ahorra creditos de Apify).

HABEAS DATA (Ley 1581/2012): del autor del comentario solo se guarda un hash
corto. Nunca se almacena el nombre ni el perfil.

Requiere:
    pip install apify-client anthropic
    APIFY_TOKEN        (Apify Console > Integrations)
    ANTHROPIC_API_KEY

Actores de Apify (agregalos una vez desde el Apify Store):
    apify/facebook-posts-scraper            pagina  -> publicaciones
    powerai/facebook-post-comments-scraper  post    -> comentarios   (ya lo tienes)

Uso:
    python 26_facebook_canal_sentimiento.py \
        --pagina https://www.facebook.com/JulianPericoJr \
        --candidato "JULIAN SANCHEZ PERICO" \
        --desde 2026-01-01

En seco (sin gastar API de Claude, solo trae posts y comentarios):
    python 26_facebook_canal_sentimiento.py --pagina ... --candidato ... --sin-clasificar
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from apify_client import ApifyClient

ACTOR_POSTS = "apify/facebook-posts-scraper"
ACTOR_COMENTARIOS = "powerai/facebook-post-comments-scraper"

SCORE_MAP = {"POSITIVO": 0.8, "NEUTRAL": 0.0, "NEGATIVO": -0.8}
TEMAS_VALIDOS = [
    "Gestion", "Seguridad", "Infraestructura", "Corrupcion",
    "Movilidad", "Servicios publicos", "Propuestas", "Otro",
]
ENCUADRES = [
    "Denuncia", "Propuesta", "Logro", "Ataque a rival",
    "Convocatoria", "Personal", "Informativo",
]
LOTE = 25          # comentarios por llamada a Claude
LOTE_AGENDA = 12   # posts por llamada
MODELO = "claude-haiku-4-5-20251001"


# --------------------------------------------------------------------------
# Helpers de normalizacion (campos de FB varian segun el actor)
# --------------------------------------------------------------------------

def primer_valor(item, claves, default=""):
    for k in claves:
        v = item.get(k)
        if v not in (None, "", []):
            return v
    return default


def run_dataset_id(run):
    """defaultDatasetId del run, sea dict (apify-client viejo) u objeto (nuevo)."""
    if isinstance(run, dict):
        return (run.get("defaultDatasetId") if isinstance(run, dict) else getattr(run, "default_dataset_id", None))
    return getattr(run, "default_dataset_id", None) or getattr(run, "defaultDatasetId", None)


def hash_autor(*partes):
    """SHA-256 corto. Permite contar/deduplicar sin guardar dato personal."""
    base = "|".join(str(p) for p in partes if p).strip().lower()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:12] if base else "anon"


def normalizar_fecha(raw):
    """A ISO corto YYYY-MM-DD."""
    if not raw:
        return ""
    raw = str(raw).strip()
    if "T" in raw and len(raw) >= 10:
        return raw[:10]
    if raw.isdigit() and len(raw) >= 10:
        try:
            return datetime.fromtimestamp(int(raw[:10]), tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return ""


def num(item, claves):
    v = primer_valor(item, claves, 0)
    try:
        return int(float(v))
    except Exception:
        return 0


def post_id_de_url(url):
    """Extrae el id numerico de una URL de post/reel/video de Facebook."""
    m = re.search(r"/(?:reel|videos|posts|photos)/(\d+)", url or "")
    if m:
        return m.group(1)
    m = re.search(r"(\d{6,})", url or "")
    return m.group(1) if m else ""


# --------------------------------------------------------------------------
# Apify
# --------------------------------------------------------------------------

def traer_posts(client, pagina, desde, limite):
    """Publicaciones recientes de una pagina publica (del mas nuevo al mas viejo)."""
    run_input = {"startUrls": [{"url": pagina}], "resultsLimit": limite}
    if desde:
        run_input["onlyPostsNewerThan"] = desde

    run = client.actor(ACTOR_POSTS).call(run_input=run_input)
    ds = run_dataset_id(run)

    posts = []
    for it in client.dataset(ds).iterate_items():
        url = primer_valor(it, ["url", "postUrl", "topLevelUrl", "link", "permalink"])
        texto = primer_valor(it, ["text", "message", "postText", "caption", "content"])
        pid = primer_valor(it, ["postId", "id", "post_id"]) or post_id_de_url(url)
        if not (url or pid):
            continue
        posts.append({
            "id": str(pid),
            "url": url or f"https://www.facebook.com/{pid}",
            "titulo": (texto or "(publicacion sin texto)").replace("\n", " ").strip()[:120],
            "descripcion": (texto or "").replace("\n", " ").strip()[:600],
            "fecha": normalizar_fecha(primer_valor(
                it, ["time", "date", "timestamp", "publishedTime", "created_time"])),
            "vistas": num(it, ["viewsCount", "videoViewCount", "playCount",
                               "reactionsCount", "likesCount", "likes"]),
            "likes": num(it, ["reactionsCount", "likesCount", "likes", "reactions"]),
            "n_comentarios_canal": num(it, ["commentsCount", "commentCount", "comments"]),
            "shares": num(it, ["sharesCount", "shareCount", "shares"]),
        })

    # Orden cronologico descendente y corte por fecha de seguridad.
    posts = [p for p in posts if (not desde or not p["fecha"] or p["fecha"] >= desde)]
    posts.sort(key=lambda p: p["fecha"], reverse=True)
    return posts[:limite]


def traer_comentarios(client, post, limite):
    """Comentarios de UNA publicacion. Un run por post (el actor es por post)."""
    run_input = {
        "startUrls": [{"url": post["url"]}],
        "post_id": post["id"],
        "maxResults": limite,
        "resultsLimit": limite,
    }
    try:
        run = client.actor(ACTOR_COMENTARIOS).call(run_input=run_input)
    except Exception as e:
        print(f"    [!] comentarios fallaron ({str(e)[:70]})")
        return []

    ds = run_dataset_id(run)
    out = []
    for it in client.dataset(ds).iterate_items():
        texto = primer_valor(it, ["text", "commentText", "message", "comment"])
        if not texto:
            continue
        out.append({
            "texto": texto.replace("\n", " ").strip(),
            "autor_hash": hash_autor(
                primer_valor(it, ["profileName", "name", "authorName", "user_name"]),
                primer_valor(it, ["profileUrl", "user_url", "commentator_profile"]),
            ),
            "fecha": normalizar_fecha(primer_valor(
                it, ["date", "commentDate", "created_time", "time"])),
            "likes": num(it, ["likesCount", "likes", "reactionsCount", "reactions"]),
            "respuestas": num(it, ["replyCount", "replies", "reply_count"]),
            "video_id": post["id"],
        })
        if len(out) >= limite:
            break
    return out


# --------------------------------------------------------------------------
# Clasificacion con Claude, en lotes
# --------------------------------------------------------------------------

def clasificar_lote(client, comentarios, candidato):
    numerados = "\n".join(f"{i+1}. {c['texto'][:400]}" for i, c in enumerate(comentarios))
    prompt = f"""Analiza estos comentarios de Facebook sobre el politico colombiano {candidato} (Soacha, Cundinamarca).

Para CADA comentario numerado, clasifica el sentimiento HACIA EL POLITICO y el tema dominante.

Comentarios:
{numerados}

Responde SOLO un arreglo JSON, sin markdown, un objeto por comentario y en el mismo orden:
[{{"n": 1, "sentimiento": "POSITIVO|NEUTRAL|NEGATIVO", "tema": "{('|'.join(TEMAS_VALIDOS))}"}}, ...]

Criterios:
- POSITIVO: apoyo, agradecimiento o respaldo genuino al politico.
- NEGATIVO: critica, burla, sarcasmo, acusacion o rechazo.
- NEUTRAL: pregunta, dato, comentario ajeno al politico o ambiguo.
Un comentario que critica a OTRO politico y no a {candidato} es NEUTRAL."""
    try:
        msg = client.messages.create(model=MODELO, max_tokens=4000,
                                     messages=[{"role": "user", "content": prompt}])
        txt = msg.content[0].text.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```[a-z]*\n?|```$", "", txt).strip()
        datos = json.loads(txt)
    except Exception as e:
        print(f"    [!] lote fallido ({str(e)[:70]}), queda NEUTRAL")
        return [("NEUTRAL", 0.0, "Otro")] * len(comentarios)

    por_n = {int(d.get("n", i + 1)): d for i, d in enumerate(datos)}
    salida = []
    for i in range(len(comentarios)):
        d = por_n.get(i + 1, {})
        sent = str(d.get("sentimiento", "NEUTRAL")).upper()
        if sent not in SCORE_MAP:
            sent = "NEUTRAL"
        tema = d.get("tema", "Otro")
        if tema not in TEMAS_VALIDOS:
            tema = "Otro"
        salida.append((sent, SCORE_MAP[sent], tema))
    return salida


def clasificar_todos(client, comentarios, candidato):
    for i in range(0, len(comentarios), LOTE):
        trozo = comentarios[i:i + LOTE]
        print(f"  clasificando {i+1}-{i+len(trozo)} de {len(comentarios)}...")
        for c, (sent, score, tema) in zip(trozo, clasificar_lote(client, trozo, candidato)):
            c["sentimiento"], c["score"], c["tema"] = sent, score, tema
        time.sleep(0.3)


def clasificar_agenda_lote(client, posts, candidato):
    bloques = []
    for i, v in enumerate(posts, 1):
        desc = v.get("descripcion", "").replace("\n", " ")[:300]
        bloques.append(f'{i}. PUBLICACION: {desc or v["titulo"]}')
    listado = "\n".join(bloques)

    prompt = f"""Estas son publicaciones de {candidato}, politico de Soacha (Cundinamarca), en SU PROPIA pagina de Facebook.

No midas si la publicacion es buena o mala. Clasifica DE QUE HABLA y QUE ESTA HACIENDO el candidato en cada una.

{listado}

Responde SOLO un arreglo JSON, sin markdown, un objeto por publicacion y en el mismo orden:
[{{"n": 1, "tema": "{('|'.join(TEMAS_VALIDOS))}", "encuadre": "{('|'.join(ENCUADRES))}", "titular": "resumen de maximo 9 palabras"}}, ...]

Encuadres:
- Denuncia: senala un problema, irregularidad o incumplimiento ajeno.
- Propuesta: plantea algo que hara o deberia hacerse.
- Logro: se atribuye un resultado conseguido.
- Ataque a rival: apunta a una persona o administracion concreta.
- Convocatoria: cita a un evento, marcha, reunion o votacion.
- Personal: vida personal, familia, agradecimientos.
- Informativo: dato o noticia sin postura propia."""
    try:
        msg = client.messages.create(model=MODELO, max_tokens=3000,
                                     messages=[{"role": "user", "content": prompt}])
        txt = msg.content[0].text.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```[a-z]*\n?|```$", "", txt).strip()
        datos = json.loads(txt)
    except Exception as e:
        print(f"    [!] lote de agenda fallido ({str(e)[:70]})")
        return [("Otro", "Informativo", v["titulo"][:60]) for v in posts]

    por_n = {int(d.get("n", i + 1)): d for i, d in enumerate(datos)}
    salida = []
    for i, v in enumerate(posts):
        d = por_n.get(i + 1, {})
        tema = d.get("tema", "Otro")
        if tema not in TEMAS_VALIDOS:
            tema = "Otro"
        enc = d.get("encuadre", "Informativo")
        if enc not in ENCUADRES:
            enc = "Informativo"
        salida.append((tema, enc, d.get("titular", v["titulo"][:60])))
    return salida


def clasificar_agenda(client, posts, candidato):
    for i in range(0, len(posts), LOTE_AGENDA):
        trozo = posts[i:i + LOTE_AGENDA]
        print(f"  agenda {i+1}-{i+len(trozo)} de {len(posts)}...")
        for v, (tema, enc, titular) in zip(trozo, clasificar_agenda_lote(client, trozo, candidato)):
            v["tema_agenda"], v["encuadre"], v["titular"] = tema, enc, titular
        time.sleep(0.3)


# --------------------------------------------------------------------------
# Agregacion (igual estructura que el pulso de YouTube)
# --------------------------------------------------------------------------

def promedio(xs):
    return round(sum(xs) / len(xs), 2) if xs else 0.0


def construir_agenda(posts):
    if not posts:
        return {}
    temas = defaultdict(lambda: {"n": 0, "vistas": 0})
    encuadres = defaultdict(int)
    for v in posts:
        t = v.get("tema_agenda", "Otro")
        temas[t]["n"] += 1
        temas[t]["vistas"] += v.get("vistas", 0)
        encuadres[v.get("encuadre", "Informativo")] += 1

    total = len(posts)
    con_coms = [v for v in posts if v.get("comentarios_analizados", 0) > 0]

    por_tema = []
    for t, d in sorted(temas.items(), key=lambda kv: -kv[1]["n"]):
        vs = [v for v in posts if v.get("tema_agenda") == t]
        con = [v for v in vs if v.get("comentarios_analizados", 0) > 0]
        por_tema.append({
            "tema": t,
            "videos": d["n"],
            "pct": round(d["n"] / total * 100),
            "vistas": d["vistas"],
            "vistas_prom": int(d["vistas"] / d["n"]) if d["n"] else 0,
            "score": promedio([v["score"] for v in con]) if con else None,
            "comentarios": sum(v.get("comentarios_analizados", 0) for v in vs),
        })

    return {
        "total_videos": total,
        "desde": min(v["fecha"] for v in posts if v["fecha"]) if any(v["fecha"] for v in posts) else "",
        "hasta": max(v["fecha"] for v in posts if v["fecha"]) if any(v["fecha"] for v in posts) else "",
        "videos_con_conversacion": len(con_coms),
        "pct_sin_conversacion": round((total - len(con_coms)) / total * 100),
        "vistas_totales": sum(v.get("vistas", 0) for v in posts),
        "temas": por_tema,
        "encuadres": [
            {"encuadre": e, "videos": n, "pct": round(n / total * 100)}
            for e, n in sorted(encuadres.items(), key=lambda kv: -kv[1])
        ],
    }


def construir_bloque(posts, comentarios):
    por_video = defaultdict(list)
    for c in comentarios:
        por_video[c["video_id"]].append(c)

    for v in posts:
        cs = por_video.get(v["id"], [])
        v["comentarios_analizados"] = len(cs)
        v["score"] = promedio([c["score"] for c in cs])
        temas = defaultdict(int)
        for c in cs:
            temas[c["tema"]] += 1
        v["tema"] = max(temas, key=temas.get) if temas else "Otro"
        neg = [c for c in cs if c["score"] < 0]
        pos = [c for c in cs if c["score"] > 0]
        v["comentario_neg"] = max(neg, key=lambda c: c["likes"])["texto"][:220] if neg else ""
        v["comentario_pos"] = max(pos, key=lambda c: c["likes"])["texto"][:220] if pos else ""

    scores = [c["score"] for c in comentarios]
    negativos = sum(1 for c in comentarios if c["score"] < 0)

    temas_agg = defaultdict(lambda: {"n": 0, "s": []})
    for c in comentarios:
        temas_agg[c["tema"]]["n"] += 1
        temas_agg[c["tema"]]["s"].append(c["score"])
    temas = sorted(
        ({"tema": t, "score": promedio(d["s"]), "menciones": d["n"]}
         for t, d in temas_agg.items()),
        key=lambda t: t["menciones"], reverse=True,
    )[:4]

    serie = [
        {"f": datetime.strptime(v["fecha"], "%Y-%m-%d").strftime("%d %b"), "s": v["score"]}
        for v in sorted([p for p in posts if p["fecha"]], key=lambda v: v["fecha"])
        if v["comentarios_analizados"] > 0
    ]

    destacados = sorted(
        [v for v in posts if v["comentarios_analizados"] > 0],
        key=lambda v: v["comentarios_analizados"], reverse=True,
    )[:4]

    return {
        "score": promedio(scores),
        "posts": len([v for v in posts if v["comentarios_analizados"] > 0]),
        "comentarios": len(comentarios),
        "toxicidad_pct": int(negativos / len(comentarios) * 100) if comentarios else 0,
        "temas": temas,
        "serie": serie,
        "videos": posts,
        "posts_destacados": [
            {
                "plataforma": "facebook",
                "fecha": v["fecha"],
                "score": v["score"],
                "resumen": v["titulo"],
                "tema": v["tema"],
                "url": v["url"],
                "comentarios": v["comentarios_analizados"],
                "comentario_pos": v["comentario_pos"],
                "comentario_neg": v["comentario_neg"],
            }
            for v in destacados
        ],
    }


def mezclar(ruta, candidato, bloque, pagina, agenda):
    """Reemplaza solo el Facebook del candidato; conserva todo lo demas."""
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            doc = json.load(f)
    else:
        doc = {"meta": {}, "candidatos": {}}

    cands = doc.setdefault("candidatos", {})
    c = cands.setdefault(candidato, {
        "es_cliente": False, "partido": "Candidato",
        "por_plataforma": {}, "temas": [], "serie": [], "posts_destacados": [],
    })

    plats = c.setdefault("por_plataforma", {})
    plats["facebook"] = {
        "score": bloque["score"],
        "posts": bloque["posts"],
        "comentarios": bloque["comentarios"],
    }

    tot_posts = sum(p.get("posts", 0) for p in plats.values())
    tot_coms = sum(p.get("comentarios", 0) for p in plats.values())
    ponderado = [
        p.get("score", 0) * p.get("comentarios", 0)
        for p in plats.values() if p.get("comentarios", 0)
    ]

    c["total_posts"] = tot_posts
    c["total_comentarios"] = tot_coms
    c["sentimiento_promedio"] = round(sum(ponderado) / tot_coms, 2) if tot_coms else 0.0
    c["toxicidad_pct"] = bloque["toxicidad_pct"]
    c["alerta_toxicidad"] = bloque["toxicidad_pct"] >= 70
    c["temas"] = bloque["temas"]
    c["serie"] = bloque["serie"] or c.get("serie", [])
    for v in bloque["videos"]:
        v.pop("descripcion", None)
    c["videos"] = bloque["videos"]
    c["agenda"] = agenda

    s = c["sentimiento_promedio"]
    c["tendencia"] = "sube" if s >= 0.2 else ("baja" if s <= -0.2 else "estable")

    otros = [p for p in c.get("posts_destacados", []) if p.get("plataforma") != "facebook"]
    c["posts_destacados"] = bloque["posts_destacados"] + otros[:2]

    # Totales globales del documento (sobre todos los candidatos).
    doc["meta"] = doc.get("meta", {})
    doc["meta"]["total_comentarios"] = sum(
        d.get("total_comentarios", 0) for d in cands.values()
    )

    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return doc


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Pulso de Facebook por pagina")
    ap.add_argument("--pagina", required=True, help="URL de la pagina publica de Facebook")
    ap.add_argument("--candidato", required=True, help="Nombre como aparece en el JSON")
    ap.add_argument("--desde", default="2026-01-01",
                    help="Trae publicaciones desde esta fecha (AAAA-MM-DD). "
                         "Use --desde '' para no filtrar por fecha")
    ap.add_argument("--max-posts", type=int, default=100,
                    help="Tope de publicaciones a traer")
    ap.add_argument("--comentarios", type=int, default=40, help="Maximo de comentarios por post")
    ap.add_argument("--top-comentados", type=int, default=15,
                    help="Solo baja comentarios de los N posts con mas comentarios (control de costo)")
    ap.add_argument("--salida", default="data/sentimiento_soacha.json")
    ap.add_argument("--sin-clasificar", action="store_true",
                    help="Trae posts y comentarios sin llamar a Claude")
    ap.add_argument("--sin-agenda", action="store_true", help="Omite el pase de agenda")
    args = ap.parse_args()

    token = os.getenv("APIFY_TOKEN")
    if not token:
        sys.exit("Falta APIFY_TOKEN")

    client = ApifyClient(token)

    an = None
    if not args.sin_clasificar:
        import anthropic
        an_key = os.getenv("ANTHROPIC_API_KEY")
        if not an_key:
            sys.exit("Falta ANTHROPIC_API_KEY")
        an = anthropic.Anthropic(api_key=an_key)

    print("=" * 68)
    print(f"Pulso Facebook - {args.candidato}")
    print("=" * 68)

    desde = args.desde or None
    print(f"Pagina: {args.pagina}")
    print(f"[>] Trayendo publicaciones (Apify: {ACTOR_POSTS})...")
    posts = traer_posts(client, args.pagina, desde, args.max_posts)
    print(f"Publicaciones recuperadas: {len(posts)}" + (f" (desde {desde})" if desde else ""))
    if not posts:
        sys.exit("La pagina no devolvio publicaciones. Revisa la URL (debe ser publica).")
    print(f"Mas reciente : {posts[0]['fecha']} - {posts[0]['titulo'][:55]}")
    print(f"Mas antigua  : {posts[-1]['fecha']}")

    # --- Pase 1: comentarios solo donde hay conversacion ---
    con_coms = sorted(
        [p for p in posts if p["n_comentarios_canal"] > 0],
        key=lambda p: p["n_comentarios_canal"], reverse=True,
    )[:args.top_comentados]
    print(f"\n[>] Bajando comentarios de {len(con_coms)} publicaciones con conversacion "
          f"(de {len(posts)})...")

    todos = []
    for i, p in enumerate(con_coms, 1):
        cs = traer_comentarios(client, p, args.comentarios)
        print(f"  [{i:3d}/{len(con_coms)}] {p['fecha']} {len(cs):3d} com. | {p['titulo'][:40]}")
        todos.extend(cs)

    print(f"\nComentarios recuperados: {len(todos)}")

    if todos:
        if args.sin_clasificar:
            for c in todos:
                c["sentimiento"], c["score"], c["tema"] = "NEUTRAL", 0.0, "Otro"
            print("(modo en seco: comentarios sin clasificar)")
        else:
            clasificar_todos(an, todos, args.candidato)
    else:
        print("Ninguna publicacion con comentarios: no habra bloque de sentimiento.")

    bloque = construir_bloque(posts, todos)

    # --- Pase 2: agenda (sobre TODAS las publicaciones) ---
    agenda = {}
    if not args.sin_agenda:
        if args.sin_clasificar:
            for v in posts:
                v["tema_agenda"], v["encuadre"] = "Otro", "Informativo"
                v["titular"] = v["titulo"][:60]
            print("(modo en seco: agenda sin clasificar)")
        else:
            print("\n[>] Clasificando agenda...")
            clasificar_agenda(an, posts, args.candidato)
        agenda = construir_agenda(posts)

    mezclar(args.salida, args.candidato.upper(), bloque, args.pagina, agenda)

    print("\n" + "-" * 68)
    print(f"Score Facebook: {bloque['score']:+.2f} "
          f"({bloque['comentarios']} comentarios en {bloque['posts']} publicaciones)")
    print(f"Toxicidad     : {bloque['toxicidad_pct']}%")
    if agenda:
        print(f"Agenda        : {agenda['total_videos']} publicaciones, "
              f"{agenda['desde']} a {agenda['hasta']}, "
              f"{agenda['pct_sin_conversacion']}% sin conversacion")
        for t in agenda["temas"][:6]:
            s = f"{t['score']:+.2f}" if t["score"] is not None else " s/d"
            print(f"  {t['tema']:20s} {t['videos']:3d} posts ({t['pct']:2d}%) | score {s}")
        print("  Encuadres: " + ", ".join(
            f"{e['encuadre']} {e['pct']}%" for e in agenda["encuadres"][:4]))
    print(f"JSON          : {args.salida}")


if __name__ == "__main__":
    main()

