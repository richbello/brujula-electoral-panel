#!/usr/bin/env python3
"""
Pipeline Electoral 2027 - Soacha
Pulso de YouTube por canal: ultimos N videos (shorts incluidos) + sentimiento.

A diferencia de 23_youtube_tiktok_sentimiento_unificado.py, este script NO
depende de un CSV armado a mano con un scraper: va directo a la API oficial
de YouTube, resuelve el canal por su @handle, toma los ultimos N videos de la
lista de subidas (los shorts estan ahi) y baja los comentarios de cada uno.

El sentimiento se clasifica con Claude en lotes (hasta 25 comentarios por
llamada), no uno por uno, para que 900 comentarios cuesten centavos y no
media hora.

El resultado se MEZCLA con data/sentimiento_soacha.json: se reemplaza solo el
bloque de YouTube del candidato analizado y se conservan TikTok, Facebook y
los demas candidatos tal como estaban.

Requiere:
  - YOUTUBE_API_KEY   (Google Cloud -> YouTube Data API v3 -> clave de API)
  - ANTHROPIC_API_KEY

Uso tipico:
    python 24_youtube_canal_sentimiento.py \
        --canal @DannyCaicedoOficial \
        --candidato "DANNY CAICEDO" \
        --videos 15

Uso en seco (sin gastar API de Claude, solo trae videos y comentarios):
    python 24_youtube_canal_sentimiento.py --canal @DannyCaicedoOficial \
        --candidato "DANNY CAICEDO" --sin-clasificar
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import requests

API = "https://www.googleapis.com/youtube/v3"

SCORE_MAP = {"POSITIVO": 0.8, "NEUTRAL": 0.0, "NEGATIVO": -0.8}
TEMAS_VALIDOS = [
    "Gestion", "Seguridad", "Infraestructura", "Corrupcion",
    "Movilidad", "Servicios publicos", "Propuestas", "Otro",
]
# Que esta haciendo el candidato con el video. Mide agenda, no recepcion.
ENCUADRES = [
    "Denuncia", "Propuesta", "Logro", "Ataque a rival",
    "Convocatoria", "Personal", "Informativo",
]
LOTE = 25          # comentarios por llamada a Claude
LOTE_AGENDA = 12   # videos por llamada (titulo + descripcion son largos)
MODELO = "claude-haiku-4-5-20251001"


# --------------------------------------------------------------------------
# YouTube Data API v3
# --------------------------------------------------------------------------

def yt(endpoint, key, **params):
    """Llamada a la API de YouTube con manejo de error legible."""
    params["key"] = key
    r = requests.get(f"{API}/{endpoint}", params=params, timeout=30)
    if r.status_code != 200:
        detalle = ""
        try:
            detalle = r.json().get("error", {}).get("message", "")
        except Exception:
            detalle = r.text[:200]
        raise RuntimeError(f"YouTube {endpoint} HTTP {r.status_code}: {detalle}")
    return r.json()


def resolver_canal(handle, key):
    """
    @DannyCaicedoOficial -> (channel_id, uploads_playlist_id, titulo).

    La lista de subidas (UU...) incluye los shorts, asi que no hace falta
    raspar la pestana /shorts.
    """
    handle = handle.strip()
    if not handle.startswith("@") and not handle.startswith("UC"):
        handle = "@" + handle

    if handle.startswith("UC"):
        data = yt("channels", key, part="contentDetails,snippet", id=handle)
    else:
        data = yt("channels", key, part="contentDetails,snippet", forHandle=handle)

    items = data.get("items") or []
    if not items:
        raise RuntimeError(f"No se encontro el canal {handle}")

    c = items[0]
    return (
        c["id"],
        c["contentDetails"]["relatedPlaylists"]["uploads"],
        c["snippet"]["title"],
    )


def listar_videos(uploads_id, key, limite, desde=None):
    """
    Videos de la lista de subidas, del mas nuevo al mas viejo.

    Con `desde` (AAAA-MM-DD) trae TODOS los publicados en esa fecha o despues
    y deja de paginar al cruzar el corte: la playlist viene ordenada por
    fecha, asi que no hace falta recorrerla entera. `limite` queda como tope
    de seguridad para canales con miles de videos.
    """
    ids, token, corte_alcanzado = [], None, False

    while len(ids) < limite and not corte_alcanzado:
        data = yt(
            "playlistItems", key,
            part="contentDetails",
            playlistId=uploads_id,
            maxResults=min(50, limite - len(ids)),
            pageToken=token,
        )
        for it in data.get("items", []):
            cd = it["contentDetails"]
            publicado = (cd.get("videoPublishedAt") or "")[:10]
            if desde and publicado and publicado < desde:
                corte_alcanzado = True
                break
            ids.append(cd["videoId"])

        token = data.get("nextPageToken")
        if not token:
            break

    ids = ids[:limite]
    if not ids:
        return []

    # El endpoint videos acepta 50 ids por llamada.
    por_id = {}
    for i in range(0, len(ids), 50):
        detalle = yt("videos", key, part="snippet,statistics",
                     id=",".join(ids[i:i + 50]))
        for v in detalle.get("items", []):
            por_id[v["id"]] = v

    videos = []
    for vid in ids:                       # conserva el orden cronologico
        v = por_id.get(vid)
        if not v:
            continue
        st, sn = v.get("statistics", {}), v["snippet"]
        videos.append({
            "id": vid,
            "titulo": sn["title"],
            "descripcion": (sn.get("description") or "")[:600],
            "fecha": sn["publishedAt"][:10],
            "url": f"https://www.youtube.com/watch?v={vid}",
            "vistas": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "n_comentarios_canal": int(st.get("commentCount", 0)),
        })
    return videos


def comentarios_de(video_id, key, limite, orden):
    """Comentarios de un video. Devuelve [] si estan desactivados."""
    out, token = [], None
    while len(out) < limite:
        try:
            data = yt(
                "commentThreads", key,
                part="snippet",
                videoId=video_id,
                order=orden,
                textFormat="plainText",
                maxResults=min(100, limite - len(out)),
                pageToken=token,
            )
        except RuntimeError as e:
            if "disabled" in str(e).lower() or "403" in str(e):
                print(f"    comentarios desactivados o sin acceso ({video_id})")
                return out
            raise

        for it in data.get("items", []):
            s = it["snippet"]["topLevelComment"]["snippet"]
            texto = (s.get("textDisplay") or "").strip()
            if not texto:
                continue
            out.append({
                "texto": texto,
                "fecha": s.get("publishedAt", "")[:10],
                "likes": int(s.get("likeCount", 0)),
                "respuestas": int(it["snippet"].get("totalReplyCount", 0)),
                "video_id": video_id,
            })

        token = data.get("nextPageToken")
        if not token:
            break
    return out


# --------------------------------------------------------------------------
# Clasificacion con Claude, en lotes
# --------------------------------------------------------------------------

def clasificar_lote(client, comentarios, candidato):
    """
    Clasifica hasta LOTE comentarios en una sola llamada.
    Devuelve lista de (sentimiento, score, tema) alineada con la entrada.
    """
    numerados = "\n".join(
        f"{i+1}. {c['texto'][:400]}" for i, c in enumerate(comentarios)
    )
    prompt = f"""Analiza estos comentarios de YouTube sobre el politico colombiano {candidato} (Soacha, Cundinamarca).

Para CADA comentario numerado, clasifica el sentimiento HACIA EL POLITICO y el tema dominante.

Comentarios:
{numerados}

Responde SOLO un arreglo JSON, sin markdown, con un objeto por comentario y en el mismo orden:
[{{"n": 1, "sentimiento": "POSITIVO|NEUTRAL|NEGATIVO", "tema": "{('|'.join(TEMAS_VALIDOS))}"}}, ...]

Criterios:
- POSITIVO: apoyo, agradecimiento o respaldo genuino al politico.
- NEGATIVO: critica, burla, sarcasmo, acusacion o rechazo.
- NEUTRAL: pregunta, dato, comentario ajeno al politico o ambiguo.
Un comentario que critica a OTRO politico y no a {candidato} es NEUTRAL."""

    try:
        msg = client.messages.create(
            model=MODELO,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
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


# --------------------------------------------------------------------------
# Agenda: de que habla el candidato (no depende de comentarios)
# --------------------------------------------------------------------------

def clasificar_agenda_lote(client, videos, candidato):
    """Tema y encuadre de cada video a partir del titulo y la descripcion."""
    bloques = []
    for i, v in enumerate(videos, 1):
        desc = v.get("descripcion", "").replace("\n", " ")[:300]
        bloques.append(f'{i}. TITULO: {v["titulo"]}\n   DESCRIPCION: {desc}')
    listado = "\n".join(bloques)

    prompt = f"""Estos son videos publicados por {candidato}, politico de Soacha (Cundinamarca), en SU PROPIO canal de YouTube.

No midas si el video es bueno o malo. Clasifica DE QUE HABLA y QUE ESTA HACIENDO el candidato en cada uno.

{listado}

Responde SOLO un arreglo JSON, sin markdown, un objeto por video y en el mismo orden:
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
        msg = client.messages.create(
            model=MODELO,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        txt = msg.content[0].text.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```[a-z]*\n?|```$", "", txt).strip()
        datos = json.loads(txt)
    except Exception as e:
        print(f"    [!] lote de agenda fallido ({str(e)[:70]})")
        return [("Otro", "Informativo", v["titulo"][:60]) for v in videos]

    por_n = {int(d.get("n", i + 1)): d for i, d in enumerate(datos)}
    salida = []
    for i, v in enumerate(videos):
        d = por_n.get(i + 1, {})
        tema = d.get("tema", "Otro")
        if tema not in TEMAS_VALIDOS:
            tema = "Otro"
        enc = d.get("encuadre", "Informativo")
        if enc not in ENCUADRES:
            enc = "Informativo"
        salida.append((tema, enc, d.get("titular", v["titulo"][:60])))
    return salida


def clasificar_agenda(client, videos, candidato):
    for i in range(0, len(videos), LOTE_AGENDA):
        trozo = videos[i:i + LOTE_AGENDA]
        print(f"  agenda {i+1}-{i+len(trozo)} de {len(videos)}...")
        for v, (tema, enc, titular) in zip(
                trozo, clasificar_agenda_lote(client, trozo, candidato)):
            v["tema_agenda"], v["encuadre"], v["titular"] = tema, enc, titular
        time.sleep(0.3)


def construir_agenda(videos):
    """
    Distribucion de temas y encuadres sobre TODOS los videos del corte,
    tengan o no comentarios. Mide de que habla el candidato.
    """
    if not videos:
        return {}

    temas, encuadres = defaultdict(lambda: {"n": 0, "vistas": 0}), defaultdict(int)
    for v in videos:
        t = v.get("tema_agenda", "Otro")
        temas[t]["n"] += 1
        temas[t]["vistas"] += v.get("vistas", 0)
        encuadres[v.get("encuadre", "Informativo")] += 1

    total = len(videos)
    con_coms = [v for v in videos if v.get("comentarios_analizados", 0) > 0]

    # Donde hay conversacion y donde no: el tema puede concentrar publicaciones
    # y aun asi no generar una sola respuesta.
    por_tema = []
    for t, d in sorted(temas.items(), key=lambda kv: -kv[1]["n"]):
        vs = [v for v in videos if v.get("tema_agenda") == t]
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
        "desde": min(v["fecha"] for v in videos),
        "hasta": max(v["fecha"] for v in videos),
        "videos_con_conversacion": len(con_coms),
        "pct_sin_conversacion": round((total - len(con_coms)) / total * 100),
        "vistas_totales": sum(v.get("vistas", 0) for v in videos),
        "temas": por_tema,
        "encuadres": [
            {"encuadre": e, "videos": n, "pct": round(n / total * 100)}
            for e, n in sorted(encuadres.items(), key=lambda kv: -kv[1])
        ],
    }


# --------------------------------------------------------------------------
# Agregacion
# --------------------------------------------------------------------------

def promedio(xs):
    return round(sum(xs) / len(xs), 2) if xs else 0.0


def construir_bloque_youtube(videos, comentarios):
    por_video = defaultdict(list)
    for c in comentarios:
        por_video[c["video_id"]].append(c)

    for v in videos:
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

    # Serie cronologica real: un punto por video, del mas viejo al mas nuevo.
    serie = [
        {"f": datetime.strptime(v["fecha"], "%Y-%m-%d").strftime("%d %b"), "s": v["score"]}
        for v in sorted(videos, key=lambda v: v["fecha"])
        if v["comentarios_analizados"] > 0
    ]

    destacados = sorted(
        [v for v in videos if v["comentarios_analizados"] > 0],
        key=lambda v: v["comentarios_analizados"], reverse=True,
    )[:4]

    return {
        "score": promedio(scores),
        "posts": len([v for v in videos if v["comentarios_analizados"] > 0]),
        "comentarios": len(comentarios),
        "toxicidad_pct": int(negativos / len(comentarios) * 100) if comentarios else 0,
        "temas": temas,
        "serie": serie,
        "videos": videos,
        "posts_destacados": [
            {
                "plataforma": "youtube",
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


def mezclar(ruta, candidato, bloque, canal, agenda):
    """Reemplaza solo el YouTube del candidato; conserva todo lo demas."""
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            doc = json.load(f)
    else:
        doc = {"meta": {}, "candidatos": {}}

    cands = doc.setdefault("candidatos", {})
    c = cands.setdefault(candidato, {
        "es_cliente": True, "partido": "Candidato",
        "por_plataforma": {}, "temas": [], "serie": [], "posts_destacados": [],
    })

    plats = c.setdefault("por_plataforma", {})
    plats["youtube"] = {
        "score": bloque["score"],
        "posts": bloque["posts"],
        "comentarios": bloque["comentarios"],
    }

    # Totales recalculados sobre todas las plataformas presentes.
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
    # La descripcion solo sirve para clasificar la agenda; no se publica,
    # para no inflar el JSON que sirve GitHub Pages.
    for v in bloque["videos"]:
        v.pop("descripcion", None)
    c["videos"] = bloque["videos"]
    c["agenda"] = agenda

    s = c["sentimiento_promedio"]
    c["tendencia"] = "sube" if s >= 0.2 else ("baja" if s <= -0.2 else "estable")

    # Los destacados de YouTube van primero; se conservan los de otras redes.
    otros = [p for p in c.get("posts_destacados", []) if p.get("plataforma") != "youtube"]
    c["posts_destacados"] = bloque["posts_destacados"] + otros[:2]

    ahora = datetime.now(timezone.utc) - timedelta(hours=5)   # hora de Bogota
    # Campos que el hero de soacha-2027.html lee en la raiz del documento.
    doc["corporacion"] = doc.get("corporacion") or "Concejo de Soacha 2027"
    doc["ventana_texto"] = (
        f"{agenda['total_videos']} videos del canal, "
        f"{agenda['desde']} a {agenda['hasta']}"
        if agenda else f"{len(bloque['videos'])} videos del canal"
    )
    doc["actualizado"] = ahora.strftime("%d %b %Y, %I:%M %p")
    doc["fuente"] = "youtube_api"
    doc["meta"] = {
        "generado": ahora.isoformat(),
        "fuente": f"YouTube Data API v3 - {canal}",
        "ventana": f"ultimos {len(bloque['videos'])} videos del canal",
        "total_comentarios": sum(
            d.get("total_comentarios", 0) for d in cands.values()
        ),
        "modelo": MODELO,
    }

    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return doc


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Pulso de YouTube por canal")
    ap.add_argument("--canal", required=True, help="@handle o ID UC... del canal")
    ap.add_argument("--candidato", required=True, help="Nombre como aparece en el JSON")
    ap.add_argument("--desde", default="2026-01-01",
                    help="Trae todos los videos desde esta fecha (AAAA-MM-DD). "
                         "Use --desde '' para ignorar la fecha y usar solo --videos")
    ap.add_argument("--videos", type=int, default=200,
                    help="Tope de videos a traer (seguridad contra canales enormes)")
    ap.add_argument("--comentarios", type=int, default=60, help="Maximo por video")
    ap.add_argument("--orden", default="relevance", choices=["relevance", "time"])
    ap.add_argument("--salida", default="data/sentimiento_soacha.json")
    ap.add_argument("--sin-clasificar", action="store_true",
                    help="Trae videos y comentarios sin llamar a Claude")
    ap.add_argument("--sin-agenda", action="store_true",
                    help="Omite el pase de agenda (solo sentimiento)")
    args = ap.parse_args()

    yt_key = os.getenv("YOUTUBE_API_KEY")
    if not yt_key:
        sys.exit("Falta YOUTUBE_API_KEY")

    client = None
    if not args.sin_clasificar:
        import anthropic
        an_key = os.getenv("ANTHROPIC_API_KEY")
        if not an_key:
            sys.exit("Falta ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=an_key)

    print("=" * 68)
    print(f"Pulso YouTube - {args.candidato}")
    print("=" * 68)

    cid, uploads, titulo = resolver_canal(args.canal, yt_key)
    print(f"Canal: {titulo}  ({cid})")

    desde = args.desde or None
    videos = listar_videos(uploads, yt_key, args.videos, desde)
    print(f"Videos recuperados: {len(videos)}"
          + (f" (desde {desde})" if desde else ""))
    if not videos:
        sys.exit("El canal no devolvio videos en ese rango.")
    print(f"Mas reciente : {videos[0]['fecha']} - {videos[0]['titulo'][:55]}")
    print(f"Mas antiguo  : {videos[-1]['fecha']}")

    # --- Pase 1: comentarios (recepcion) ---
    todos = []
    sin_coms = 0
    for i, v in enumerate(videos, 1):
        cs = comentarios_de(v["id"], yt_key, args.comentarios, args.orden)
        if not cs:
            sin_coms += 1
        print(f"  [{i:3d}/{len(videos)}] {v['fecha']} {len(cs):3d} com. | {v['titulo'][:46]}")
        todos.extend(cs)

    print(f"\nComentarios recuperados: {len(todos)}")
    print(f"Videos sin un solo comentario: {sin_coms} de {len(videos)}")

    if todos:
        if args.sin_clasificar:
            for c in todos:
                c["sentimiento"], c["score"], c["tema"] = "NEUTRAL", 0.0, "Otro"
            print("(modo en seco: comentarios sin clasificar)")
        else:
            clasificar_todos(client, todos, args.candidato)
    else:
        print("Ningun video tiene comentarios: no habra bloque de sentimiento.")

    bloque = construir_bloque_youtube(videos, todos)

    # --- Pase 2: agenda (de que habla, exista o no conversacion) ---
    agenda = {}
    if not args.sin_agenda:
        if args.sin_clasificar:
            for v in videos:
                v["tema_agenda"], v["encuadre"] = "Otro", "Informativo"
                v["titular"] = v["titulo"][:60]
            print("(modo en seco: agenda sin clasificar)")
        else:
            print("\n[>] Clasificando agenda...")
            clasificar_agenda(client, videos, args.candidato)
        agenda = construir_agenda(videos)

    mezclar(args.salida, args.candidato.upper(), bloque, titulo, agenda)

    print("\n" + "-" * 68)
    print(f"Score YouTube : {bloque['score']:+.2f} "
          f"({bloque['comentarios']} comentarios en {bloque['posts']} videos)")
    print(f"Toxicidad     : {bloque['toxicidad_pct']}%")
    if agenda:
        print(f"Agenda        : {agenda['total_videos']} videos, "
              f"{agenda['desde']} a {agenda['hasta']}, "
              f"{agenda['pct_sin_conversacion']}% sin conversacion")
        for t in agenda["temas"][:5]:
            s = f"{t['score']:+.2f}" if t["score"] is not None else " s/d"
            print(f"  {t['tema']:20s} {t['videos']:3d} videos ({t['pct']:2d}%) "
                  f"| {t['vistas_prom']:7,d} vistas prom | score {s}")
        print("  Encuadres: " + ", ".join(
            f"{e['encuadre']} {e['pct']}%" for e in agenda["encuadres"][:4]))
    print(f"JSON          : {args.salida}")


if __name__ == "__main__":
    main()
