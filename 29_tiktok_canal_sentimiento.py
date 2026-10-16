#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline Electoral 2027 - Soacha
Pulso de TikTok por perfil: videos desde una fecha + comentarios + sentimiento.

Hermano de 24_youtube_canal_sentimiento.py: usa la MISMA clasificacion con
Claude (sentimiento por comentario y agenda por video) importandola de ese
script, y deja los videos en el mismo formato. Asi la pagina soacha-2027.html
muestra para TikTok las mismas secciones (agenda y rendimiento de contenido).

Datos via Apify (APIFY_TOKEN):
  - clockworks/tiktok-scraper           -> videos del perfil con reproducciones,
                                           likes, comentarios, compartidos
  - clockworks/tiktok-comments-scraper  -> texto de los comentarios

Se guarda en data/sentimiento_soacha.json, en el candidato indicado:
  por_plataforma.tiktok, videos_tiktok, agenda_tiktok.
No toca el bloque de YouTube ni los demas candidatos.

Uso:
    python 29_tiktok_canal_sentimiento.py --perfil julianperico \
        --candidato "JULIAN SANCHEZ PERICO" --desde 2026-04-01

Prueba barata (solo videos y metricas, sin comentarios ni Claude):
    python 29_tiktok_canal_sentimiento.py --perfil julianperico \
        --candidato "JULIAN SANCHEZ PERICO" --solo-metricas
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

from apify_client import ApifyClient

AQUI = os.path.dirname(os.path.abspath(__file__))
ACTOR_VIDEOS = "clockworks/tiktok-scraper"
ACTOR_COMENTARIOS = "clockworks/tiktok-comments-scraper"


def cargar_modulo_24():
    """Reutiliza clasificacion y agregacion del pipeline de YouTube."""
    ruta = os.path.join(AQUI, "24_youtube_canal_sentimiento.py")
    if not os.path.exists(ruta):
        sys.exit("Falta 24_youtube_canal_sentimiento.py en esta carpeta.")
    spec = importlib.util.spec_from_file_location("yt24", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dataset_items(client, run):
    """Compatible con apify-client 1.x (dict) y 3.x (objeto Run)."""
    ds = getattr(run, "default_dataset_id", None)
    if ds is None and isinstance(run, dict):
        ds = run.get("defaultDatasetId")
    if not ds:
        raise RuntimeError("Apify no devolvio dataset (revisa el run en la consola)")
    return list(client.dataset(ds).iterate_items())


def g(d, *ruta, default=None):
    for k in ruta:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return default if d is None else d


# --------------------------------------------------------------------------
# Apify
# --------------------------------------------------------------------------

def traer_videos(client, perfil, desde, limite):
    entrada = {
        "profiles": [perfil.lstrip("@")],
        "profileScrapeSections": ["videos"],
        "resultsPerPage": limite,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
    }
    if desde:
        entrada["oldestPostDateUnified"] = desde
    print(f"[apify] videos de @{perfil.lstrip('@')} ...")
    run = client.actor(ACTOR_VIDEOS).call(run_input=entrada)
    items = dataset_items(client, run)

    videos = []
    for it in items:
        vid = str(it.get("id") or "")
        if not vid or it.get("error"):
            continue
        fecha = (it.get("createTimeISO") or "")[:10]
        if not fecha and it.get("createTime"):
            fecha = datetime.fromtimestamp(int(it["createTime"]), tz=timezone.utc).strftime("%Y-%m-%d")
        if desde and fecha and fecha < desde:
            continue
        texto = (it.get("text") or "").strip()
        primera = texto.split("\n")[0].strip() or "(sin texto)"
        videos.append({
            "id": vid,
            "titulo": primera[:140],
            "descripcion": texto[:600],
            "fecha": fecha,
            "url": it.get("webVideoUrl") or f"https://www.tiktok.com/@{perfil.lstrip('@')}/video/{vid}",
            "vistas": int(it.get("playCount") or 0),
            "likes": int(it.get("diggCount") or 0),
            "n_comentarios_canal": int(it.get("commentCount") or 0),
            "compartidos": int(it.get("shareCount") or 0),
            "guardados": int(it.get("collectCount") or 0),
            "duracion": int(g(it, "videoMeta", "duration", default=0) or 0),
        })
    # sin duplicados, del mas nuevo al mas viejo
    vistos, unicos = set(), []
    for v in sorted(videos, key=lambda v: v["fecha"], reverse=True):
        if v["id"] not in vistos:
            vistos.add(v["id"])
            unicos.append(v)
    return unicos[:limite]


def traer_comentarios(client, videos, por_video, tope_total):
    """Solo pide comentarios de los videos que tienen; prioriza los mas comentados."""
    con = sorted([v for v in videos if v["n_comentarios_canal"] > 0],
                 key=lambda v: v["n_comentarios_canal"], reverse=True)
    elegidos, presupuesto = [], tope_total
    for v in con:
        if presupuesto <= 0:
            break
        elegidos.append(v)
        presupuesto -= min(por_video, v["n_comentarios_canal"])
    if not elegidos:
        return []

    print(f"[apify] comentarios de {len(elegidos)} videos (max {por_video} c/u, tope {tope_total}) ...")
    run = client.actor(ACTOR_COMENTARIOS).call(run_input={
        "postURLs": [v["url"] for v in elegidos],
        "commentsPerPost": por_video,
        "maxRepliesPerComment": 0,
    })
    items = dataset_items(client, run)

    ids = {v["id"] for v in videos}
    out = []
    for it in items:
        texto = (it.get("text") or "").strip()
        if not texto:
            continue
        m = re.search(r"/video/(\d+)", it.get("videoWebUrl") or it.get("submittedVideoUrl") or "")
        vid = m.group(1) if m else str(it.get("awemeId") or it.get("aweme_id") or "")
        if vid not in ids:
            continue
        out.append({
            "comment_id": str(it.get("cid") or it.get("id") or ""),
            "texto": texto,
            "fecha": (it.get("createTimeISO") or "")[:10],
            "likes": int(it.get("diggCount") or 0),
            "respuestas": int(it.get("replyCommentTotal") or 0),
            "video_id": vid,
        })
    return out


# --------------------------------------------------------------------------
# Mezcla en el JSON
# --------------------------------------------------------------------------

def mezclar_tiktok(ruta, candidato, bloque, agenda, perfil, crear, modelo):
    if not os.path.exists(ruta):
        sys.exit(f"No existe {ruta}. Corre primero el pipeline de YouTube o crea el JSON.")
    with open(ruta, encoding="utf-8") as f:
        doc = json.load(f)

    cands = doc.setdefault("candidatos", {})
    if candidato not in cands:
        if not crear:
            print(f"\n[!] '{candidato}' no existe en el JSON. Candidatos actuales:")
            for k in cands:
                print(f"    - {k}")
            sys.exit("Usa el nombre exacto, o agrega --crear si de verdad es nuevo.")
        cands[candidato] = {
            "es_cliente": False, "partido": "Candidato",
            "por_plataforma": {}, "temas": [], "serie": [], "posts_destacados": [],
        }
    c = cands[candidato]
    plats = c.setdefault("por_plataforma", {})
    plats["tiktok"] = {
        "score": bloque["score"],
        "posts": bloque["posts"],
        "comentarios": bloque["comentarios"],
    }

    # Totales ponderados por comentarios, sobre todas las redes presentes.
    tot_coms = sum(p.get("comentarios", 0) for p in plats.values())
    c["total_posts"] = sum(p.get("posts", 0) for p in plats.values())
    c["total_comentarios"] = tot_coms
    pond = sum(p.get("score", 0) * p.get("comentarios", 0) for p in plats.values())
    c["sentimiento_promedio"] = round(pond / tot_coms, 2) if tot_coms else 0.0
    s = c["sentimiento_promedio"]
    c["tendencia"] = "sube" if s >= 0.2 else ("baja" if s <= -0.2 else "estable")

    # Si TikTok es su red principal (sin YouTube), sus temas, serie y toxicidad
    # pasan a ser los del candidato.
    if not g(plats, "youtube", "comentarios", default=0):
        c["temas"] = bloque["temas"]
        c["serie"] = bloque["serie"] or c.get("serie", [])
        c["toxicidad_pct"] = bloque["toxicidad_pct"]
        c["alerta_toxicidad"] = bloque["toxicidad_pct"] >= 70

    for v in bloque["videos"]:
        v.pop("descripcion", None)
    c["videos_tiktok"] = bloque["videos"]
    c["agenda_tiktok"] = agenda
    c["perfil_tiktok"] = "@" + perfil.lstrip("@")

    for p in bloque["posts_destacados"]:
        p["plataforma"] = "tiktok"
    otros = [p for p in c.get("posts_destacados", []) if p.get("plataforma") != "tiktok"]
    c["posts_destacados"] = otros[:4] + bloque["posts_destacados"][:3]

    ahora = datetime.now(timezone.utc) - timedelta(hours=5)
    doc["actualizado"] = ahora.strftime("%d %b %Y, %I:%M %p")
    meta = doc.setdefault("meta", {})
    meta["generado"] = ahora.isoformat()
    meta["modelo"] = modelo
    meta["total_comentarios"] = sum(d.get("total_comentarios", 0) for d in cands.values())

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Pulso de TikTok por perfil")
    ap.add_argument("--perfil", required=True, help="usuario de TikTok, con o sin @")
    ap.add_argument("--candidato", required=True, help="Nombre EXACTO como esta en el JSON")
    ap.add_argument("--desde", default="2026-04-01", help="AAAA-MM-DD")
    ap.add_argument("--videos", type=int, default=80, help="Tope de videos")
    ap.add_argument("--comentarios", type=int, default=25, help="Max comentarios por video")
    ap.add_argument("--tope-comentarios", type=int, default=600,
                    help="Max comentarios en total (controla el costo de Apify)")
    ap.add_argument("--salida", default="data/sentimiento_soacha.json")
    ap.add_argument("--solo-metricas", action="store_true",
                    help="Solo videos y metricas: sin comentarios ni Claude (barato)")
    ap.add_argument("--crear", action="store_true",
                    help="Permite crear el candidato si no existe en el JSON")
    args = ap.parse_args()

    token = os.getenv("APIFY_TOKEN")
    if not token:
        sys.exit("Falta APIFY_TOKEN")
    yt24 = cargar_modulo_24()

    client_ai = None
    if not args.solo_metricas:
        import anthropic
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("Falta ANTHROPIC_API_KEY")
        client_ai = anthropic.Anthropic(api_key=key)

    candidato = args.candidato.upper().strip()
    # Validar el nombre ANTES de gastar en Apify.
    if os.path.exists(args.salida) and not args.crear:
        with open(args.salida, encoding="utf-8") as f:
            existentes = json.load(f).get("candidatos", {})
        if candidato not in existentes:
            print(f"[!] '{candidato}' no existe en {args.salida}. Candidatos actuales:")
            for k in existentes:
                print(f"    - {k}")
            sys.exit("Usa el nombre exacto, o agrega --crear si de verdad es nuevo.")

    apify = ApifyClient(token)
    print("=" * 68)
    print(f"Pulso TikTok - {candidato}  (@{args.perfil.lstrip('@')})")
    print("=" * 68)

    videos = traer_videos(apify, args.perfil, args.desde, args.videos)
    if not videos:
        sys.exit("TikTok no devolvio videos en ese rango (perfil privado o mal escrito?).")
    print(f"Videos: {len(videos)}  ({videos[-1]['fecha']} a {videos[0]['fecha']})")
    print(f"Reproducciones totales: {sum(v['vistas'] for v in videos):,}")
    sin = sum(1 for v in videos if v["n_comentarios_canal"] == 0)
    print(f"Videos sin comentarios: {sin} de {len(videos)}")

    comentarios = []
    if not args.solo_metricas:
        comentarios = traer_comentarios(apify, videos, args.comentarios, args.tope_comentarios)
        print(f"Comentarios recuperados: {len(comentarios)}")
        if comentarios:
            yt24.clasificar_todos(client_ai, comentarios, candidato)

    bloque = yt24.construir_bloque_youtube(videos, comentarios)

    if args.solo_metricas:
        for v in videos:
            v["tema_agenda"], v["encuadre"], v["titular"] = "Otro", "Informativo", v["titulo"][:60]
    else:
        print("\n[>] Clasificando agenda...")
        yt24.clasificar_agenda(client_ai, videos, candidato)
    agenda = yt24.construir_agenda(videos)

    mezclar_tiktok(args.salida, candidato, bloque, agenda, args.perfil,
                   args.crear, yt24.MODELO)

    print("\n" + "-" * 68)
    print(f"Score TikTok : {bloque['score']:+.2f} "
          f"({bloque['comentarios']} comentarios en {bloque['posts']} videos)")
    print(f"Toxicidad    : {bloque['toxicidad_pct']}%")
    print(f"Agenda       : {agenda['total_videos']} videos, {agenda['desde']} a {agenda['hasta']}")
    for t in agenda["temas"][:5]:
        s = f"{t['score']:+.2f}" if t["score"] is not None else " s/d"
        print(f"  {t['tema']:20s} {t['videos']:3d} videos ({t['pct']:2d}%) "
              f"| {t['vistas_prom']:9,d} repr. prom | score {s}")
    print("  Encuadres: " + ", ".join(
        f"{e['encuadre']} {e['pct']}%" for e in agenda["encuadres"][:4]))
    print(f"JSON         : {args.salida}")


if __name__ == "__main__":
    main()
