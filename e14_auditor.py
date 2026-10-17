#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Defensa del Voto -- Auditoria de formularios E-14
=================================================

Tres pasos, cada uno es un subcomando:

  1. extraer  Lee imagenes o PDF de formularios E-14 (los que publica la
              Registraduria la noche de elecciones, o las fotos que toman los
              testigos) y, con Claude vision, los convierte en un registro
              estructurado por mesa. Salida: un archivo .jsonl, una linea por
              acta. Es reanudable: si se corta, vuelve a correrlo y salta las
              actas ya leidas.

  2. auditar  Corre las reglas sobre las actas extraidas y, si se le pasan,
              las compara contra el preconteo y contra el escrutinio (E-24).
              Salida: data/modulos/e14_auditoria.json, que es lo que lee la
              pagina defensa-voto.html.

  3. demo     Genera actas sinteticas con errores sembrados y las audita.
              Sirve para ver el modulo funcionando antes de tener E-14 reales.
              Todo lo que sale de aqui va marcado como DEMO.

QUE DETECTA
-----------
Severidad ALTA (errores verificables en el propio formulario):
  * suma_lista      votos por la lista + votos por candidatos != total de la lista
  * suma_mesa       totales de listas + blanco + nulos + no marcados != total
  * urna_vs_e11     votos en la urna mayores que los sufragantes del E-11
  * total_vs_urna   total de votos del acta distinto de los votos en la urna
  * enmendadura     tachones, borrones o numeros sobrescritos que vio el lector
  * firmas          acta con menos firmas de jurados que el minimo configurado

Severidad MEDIA (diferencias entre documentos):
  * dif_escrutinio  el E-14 dice una cosa y el escrutinio (E-24) otra
  * dif_preconteo   el E-14 dice una cosa y el preconteo publicado otra
  * ilegible        el lector no pudo leer el acta con confianza suficiente

Severidad BAJA (patrones estadisticos, no prueban nada por si solos):
  * concentracion   una lista saca casi todos los votos de la mesa siendo
                    minoritaria en el municipio
  * nulos_atipicos  nulos + no marcados muy por encima de lo normal
  * mesa_gemela     dos mesas del mismo puesto con resultados identicos

LIMITES
-------
Un hallazgo es un indicio para revisar, no una prueba de fraude. Los E-14 que
publica la Registraduria son la copia de "delegados"; el que tiene valor
juridico en el escrutinio es el de claveros. Las reclamaciones que genera la
pagina son borradores: un abogado debe revisarlas antes de radicarlas ante la
comision escrutadora.

Uso
---
    # 1. extraer (requiere ANTHROPIC_API_KEY en el entorno o en .env)
    python e14_auditor.py extraer --entrada e14_soacha_2023/ --salida data/_e14_actas.jsonl

    # 2. auditar
    python e14_auditor.py auditar --actas data/_e14_actas.jsonl \\
        --escrutinio e24_soacha.csv --preconteo preconteo_soacha.csv \\
        --foco 005 --municipio Soacha --eleccion "Concejo 2023"

    # 3. demo
    python e14_auditor.py demo

Formato de los CSV de preconteo y escrutinio (formato largo, una fila por cifra):
    mesa_id,lista,candidato,votos
    01-005-012,005,LOGO,14        <- votos solo por el logo de la lista 005
    01-005-012,005,103,22         <- votos por el candidato 103 de la lista 005
    01-005-012,005,TOTAL,61       <- total de la lista 005
    01-005-012,BLANCO,,9
    01-005-012,NULOS,,3
    01-005-012,NO_MARCADOS,,2

mesa_id es zona-puesto-mesa con ceros a la izquierda (01-005-012).

Requiere: anthropic (solo para "extraer")
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

RAIZ = Path(__file__).resolve().parent
SALIDA_DEFECTO = RAIZ / "data" / "modulos" / "e14_auditoria.json"
SALIDA_DEMO = RAIZ / "data" / "modulos" / "e14_auditoria_demo.json"

SEVERIDAD = {
    "suma_lista": "alta", "suma_mesa": "alta", "urna_vs_e11": "alta",
    "total_vs_urna": "alta", "enmendadura": "alta", "firmas": "alta",
    "dif_escrutinio": "media", "dif_preconteo": "media", "ilegible": "media",
    "concentracion": "baja", "nulos_atipicos": "baja", "mesa_gemela": "baja",
}
ORDEN_SEV = {"alta": 0, "media": 1, "baja": 2}

# Solicitud que corresponde a cada tipo de hallazgo en el borrador de
# reclamacion. La pagina arma el texto; aqui solo queda la intencion.
SOLICITUD = {
    "suma_lista": "corrección aritmética y, de persistir la inconsistencia, recuento de votos",
    "suma_mesa": "corrección aritmética y, de persistir la inconsistencia, recuento de votos",
    "urna_vs_e11": "recuento de votos y verificación del registro de votantes (E-11)",
    "total_vs_urna": "recuento de votos",
    "enmendadura": "recuento de votos por enmendaduras en el acta",
    "firmas": "verificación de la firma del acta por los jurados de votación",
    "dif_escrutinio": "revisión de la diferencia entre el acta de mesa y el escrutinio",
    "dif_preconteo": "verificación de la cifra consolidada frente al acta de mesa",
    "ilegible": "cotejo con el ejemplar de claveros y, si es necesario, recuento",
}

ESPECIALES = ("BLANCO", "NULOS", "NO_MARCADOS")


# ====================================================================== util
def _int(v: Any) -> int | None:
    """Convierte a entero tolerando None, '', '-', '--' y espacios."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(".", "").replace(",", "")
    if s in ("", "-", "--", "---", "*"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def mesa_id(acta: dict) -> str:
    if acta.get("mesa_id"):
        return str(acta["mesa_id"])
    z = str(acta.get("zona", "")).zfill(2)
    p = str(acta.get("puesto", "")).zfill(3)
    m = str(acta.get("mesa", "")).zfill(3)
    return f"{z}-{p}-{m}"


def _hallazgo(tipo: str, detalle: str, lista: str | None = None,
              diferencia: int | None = None, **extra) -> dict:
    h = {"tipo": tipo, "severidad": SEVERIDAD[tipo], "detalle": detalle}
    if lista is not None:
        h["lista"] = lista
    if diferencia is not None:
        h["diferencia"] = diferencia
    if tipo in SOLICITUD:
        h["solicitud"] = SOLICITUD[tipo]
    h.update(extra)
    return h


def cifras_acta(acta: dict) -> dict[tuple[str, str], int]:
    """Aplana un acta a {(lista, candidato): votos} con la misma clave que los CSV."""
    out: dict[tuple[str, str], int] = {}
    for l in acta.get("listas", []):
        cod = str(l.get("codigo"))
        if _int(l.get("votos_lista")) is not None:
            out[(cod, "LOGO")] = _int(l["votos_lista"])
        for cand, v in (l.get("candidatos") or {}).items():
            if _int(v) is not None:
                out[(cod, str(cand))] = _int(v)
        if _int(l.get("total")) is not None:
            out[(cod, "TOTAL")] = _int(l["total"])
    for k, campo in (("BLANCO", "blanco"), ("NULOS", "nulos"), ("NO_MARCADOS", "no_marcados")):
        if _int(acta.get(campo)) is not None:
            out[(k, "")] = _int(acta[campo])
    return out


def validos_por_lista(acta: dict) -> dict[str, int]:
    out = {}
    for l in acta.get("listas", []):
        t = _int(l.get("total"))
        if t is None:
            t = (_int(l.get("votos_lista")) or 0) + sum(
                _int(v) or 0 for v in (l.get("candidatos") or {}).values())
        out[str(l.get("codigo"))] = t
    return out


# ============================================================ reglas por acta
def reglas_internas(acta: dict, min_firmas: int = 3, min_confianza: float = 0.7) -> list[dict]:
    """Reglas que solo necesitan el propio formulario."""
    h: list[dict] = []

    if acta.get("legible") is False or (
            acta.get("confianza") is not None and float(acta["confianza"]) < min_confianza):
        h.append(_hallazgo("ilegible",
                           f"Lectura con confianza {acta.get('confianza', 0):.0%}; revisar el acta a mano."))

    suma_listas = 0
    for l in acta.get("listas", []):
        cod = str(l.get("codigo"))
        logo = _int(l.get("votos_lista")) or 0
        cands = sum(_int(v) or 0 for v in (l.get("candidatos") or {}).values())
        total = _int(l.get("total"))
        if total is None:
            suma_listas += logo + cands
            continue
        suma_listas += total
        if logo + cands != total:
            h.append(_hallazgo(
                "suma_lista",
                f"Lista {cod}: logo {logo} + candidatos {cands} = {logo + cands}, "
                f"pero el acta registra total {total}.",
                lista=cod, diferencia=total - (logo + cands)))

    blanco = _int(acta.get("blanco")) or 0
    nulos = _int(acta.get("nulos")) or 0
    nm = _int(acta.get("no_marcados")) or 0
    calc = suma_listas + blanco + nulos + nm
    total_acta = _int(acta.get("total_votos"))
    urna = _int(acta.get("votos_urna"))
    e11 = _int(acta.get("sufragantes_e11"))

    if total_acta is not None and calc != total_acta:
        h.append(_hallazgo(
            "suma_mesa",
            f"Listas {suma_listas} + blanco {blanco} + nulos {nulos} + no marcados {nm} = {calc}, "
            f"pero el acta registra total {total_acta}.",
            diferencia=total_acta - calc))

    referencia = total_acta if total_acta is not None else calc
    if urna is not None and referencia != urna:
        h.append(_hallazgo(
            "total_vs_urna",
            f"El total de votos ({referencia}) no coincide con los votos en la urna ({urna}).",
            diferencia=referencia - urna))

    if urna is not None and e11 is not None and urna > e11:
        h.append(_hallazgo(
            "urna_vs_e11",
            f"Hay {urna} votos en la urna y solo {e11} sufragantes en el E-11 "
            f"({urna - e11} de más). Debieron incinerarse los sobrantes.",
            diferencia=urna - e11))

    for e in acta.get("enmendaduras") or []:
        campo = e.get("campo", "campo sin identificar")
        h.append(_hallazgo("enmendadura",
                           f"Enmendadura en {campo}: {e.get('detalle', 'número sobrescrito o tachado')}.",
                           lista=e.get("lista")))

    firmas = _int(acta.get("firmas_jurados"))
    if firmas is not None and firmas < min_firmas:
        h.append(_hallazgo("firmas", f"El acta tiene {firmas} firma(s) de jurados; se esperaban al menos {min_firmas}."))

    return h


def comparar(acta: dict, externo: dict[tuple[str, str], int], tipo: str, nombre: str) -> list[dict]:
    """Compara las cifras del acta contra otra fuente (preconteo o escrutinio)."""
    h = []
    propias = cifras_acta(acta)
    for clave in sorted(set(propias) & set(externo)):
        a, b = propias[clave], externo[clave]
        if a == b:
            continue
        lista, cand = clave
        if lista in ESPECIALES:
            etiqueta = lista.replace("_", " ").lower()
        elif cand == "LOGO":
            etiqueta = f"lista {lista} (voto por el logo)"
        elif cand == "TOTAL":
            etiqueta = f"lista {lista} (total)"
        else:
            etiqueta = f"candidato {cand} de la lista {lista}"
        h.append(_hallazgo(
            tipo, f"{etiqueta}: E-14 {a}, {nombre} {b} (diferencia {b - a:+d}).",
            lista=None if lista in ESPECIALES else lista, diferencia=b - a,
            candidato=None if cand in ("LOGO", "TOTAL", "") else cand,
            nivel={"TOTAL": "total", "LOGO": "logo", "": "total"}.get(cand, "candidato")))
    return h


# ===================================================== reglas sobre el conjunto
def _mad(xs: list[float]) -> tuple[float, float]:
    med = statistics.median(xs)
    mad = statistics.median([abs(x - med) for x in xs]) or 1e-9
    return med, mad


def reglas_conjunto(actas: list[dict], umbral_conc: float = 0.8,
                    max_cuota_mun: float = 0.3, min_validos: int = 40) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if not actas:
        return out

    # cuota municipal de cada lista
    tot_lista: dict[str, int] = defaultdict(int)
    for a in actas:
        for cod, v in validos_por_lista(a).items():
            tot_lista[cod] += v
    gran = sum(tot_lista.values()) or 1
    cuota_mun = {k: v / gran for k, v in tot_lista.items()}

    for a in actas:
        vl = validos_por_lista(a)
        validos = sum(vl.values())
        if validos < min_validos:
            continue
        for cod, v in vl.items():
            c = v / validos
            if c >= umbral_conc and cuota_mun.get(cod, 0) < max_cuota_mun:
                out[mesa_id(a)].append(_hallazgo(
                    "concentracion",
                    f"Lista {cod} obtiene {c:.0%} de los votos válidos de la mesa; "
                    f"en todo el municipio tiene {cuota_mun[cod]:.0%}.",
                    lista=cod))

    # nulos + no marcados atipicos (z robusto con mediana y MAD)
    ratios = []
    for a in actas:
        t = _int(a.get("total_votos")) or _int(a.get("votos_urna")) or 0
        if t >= min_validos:
            ratios.append(((_int(a.get("nulos")) or 0) + (_int(a.get("no_marcados")) or 0)) / t)
        else:
            ratios.append(None)
    validos_r = [r for r in ratios if r is not None]
    if len(validos_r) >= 10:
        med, mad = _mad(validos_r)
        for a, r in zip(actas, ratios):
            if r is None:
                continue
            z = 0.6745 * (r - med) / mad
            if z > 3.5 and r - med > 0.05:
                out[mesa_id(a)].append(_hallazgo(
                    "nulos_atipicos",
                    f"Nulos + no marcados suman {r:.0%} del total; la mediana del municipio es {med:.0%}."))

    # mesas gemelas: mismo puesto, mismo vector de resultados no trivial
    por_puesto: dict[tuple, dict[tuple, list[str]]] = defaultdict(lambda: defaultdict(list))
    for a in actas:
        vec = tuple(sorted(cifras_acta(a).items()))
        if sum(v for _, v in vec) < min_validos:
            continue
        por_puesto[(a.get("zona"), a.get("puesto"))][vec].append(mesa_id(a))
    for grupos in por_puesto.values():
        for ids in grupos.values():
            if len(ids) > 1:
                for i in ids:
                    otras = ", ".join(x for x in ids if x != i)
                    out[i].append(_hallazgo("mesa_gemela",
                                            f"Resultados idénticos, cifra por cifra, a la mesa {otras} del mismo puesto."))
    return out


# =============================================================== orquestacion
def leer_jsonl(path: Path) -> list[dict]:
    actas = []
    with open(path, encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                actas.append(json.loads(linea))
    return actas


def leer_csv_largo(path: Path | None) -> dict[str, dict[tuple[str, str], int]]:
    if not path:
        return {}
    out: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            v = _int(r.get("votos"))
            if v is None:
                continue
            lista = str(r.get("lista", "")).strip().upper() if str(r.get("lista", "")).strip().upper() in ESPECIALES \
                else str(r.get("lista", "")).strip()
            cand = str(r.get("candidato") or "").strip()
            cand = cand.upper() if cand.upper() in ("LOGO", "TOTAL") else cand
            out[str(r["mesa_id"]).strip()][(lista, cand)] = v
    return out


def impacto_foco(hallazgos: list[dict], foco: str | None) -> int:
    """Votos de la lista foco en juego en una mesa.

    Por cada fuente (acta, preconteo, escrutinio) se toma la diferencia del
    total de la lista si existe; si no, la suma de logo y candidatos. Asi una
    misma diferencia no se cuenta dos veces (candidato y total). Entre fuentes
    se toma la mayor, porque preconteo y escrutinio describen los mismos votos.
    """
    if not foco:
        return 0
    por_fuente: dict[str, list[dict]] = defaultdict(list)
    for h in hallazgos:
        if h.get("lista") == foco and h.get("diferencia"):
            por_fuente[h["tipo"]].append(h)
    mejor = 0
    for hs in por_fuente.values():
        tot = [abs(h["diferencia"]) for h in hs if h.get("nivel", "total") == "total"]
        mejor = max(mejor, sum(tot) if tot else sum(abs(h["diferencia"]) for h in hs))
    return mejor


def auditar(actas: list[dict], preconteo: dict | None = None, escrutinio: dict | None = None,
            foco: str | None = None, meta: dict | None = None, min_firmas: int = 3) -> dict:
    preconteo = preconteo or {}
    escrutinio = escrutinio or {}
    conjunto = reglas_conjunto(actas)

    mesas = []
    conteo = defaultdict(int)
    for a in actas:
        mid = mesa_id(a)
        h = reglas_internas(a, min_firmas=min_firmas)
        if mid in escrutinio:
            h += comparar(a, escrutinio[mid], "dif_escrutinio", "escrutinio")
        if mid in preconteo:
            h += comparar(a, preconteo[mid], "dif_preconteo", "preconteo")
        h += conjunto.get(mid, [])
        h.sort(key=lambda x: ORDEN_SEV[x["severidad"]])
        for x in h:
            conteo[x["tipo"]] += 1
        sev = h[0]["severidad"] if h else None
        mesas.append({
            "mesa_id": mid,
            "zona": str(a.get("zona", "")), "puesto": str(a.get("puesto", "")),
            "puesto_nombre": a.get("puesto_nombre", ""), "mesa": str(a.get("mesa", "")),
            "votos_urna": _int(a.get("votos_urna")), "sufragantes_e11": _int(a.get("sufragantes_e11")),
            "total_votos": _int(a.get("total_votos")),
            "validos_por_lista": validos_por_lista(a),
            "blanco": _int(a.get("blanco")), "nulos": _int(a.get("nulos")),
            "no_marcados": _int(a.get("no_marcados")),
            "archivo": a.get("archivo"), "url": a.get("url"),
            "severidad": sev, "impacto_foco": impacto_foco(h, foco),
            "hallazgos": h,
        })

    mesas.sort(key=lambda m: (ORDEN_SEV.get(m["severidad"], 9), -m["impacto_foco"], m["mesa_id"]))
    con_h = [m for m in mesas if m["hallazgos"]]
    por_puesto: dict[str, dict] = {}
    for m in mesas:
        p = por_puesto.setdefault(m["puesto"], {"puesto": m["puesto"], "nombre": m["puesto_nombre"],
                                                "zona": m["zona"], "mesas": 0, "alta": 0, "media": 0, "baja": 0})
        p["mesas"] += 1
        if m["severidad"]:
            p[m["severidad"]] += 1

    listas = sorted({k for m in mesas for k in m["validos_por_lista"]})
    return {
        "meta": {
            **(meta or {}),
            "generado": dt.datetime.now().isoformat(timespec="seconds"),
            "foco": foco,
            "fuentes": {"preconteo": bool(preconteo), "escrutinio": bool(escrutinio)},
            "aviso": ("Cada hallazgo es un indicio para revisar, no una prueba. Las reclamaciones "
                      "son borradores que debe revisar un abogado antes de radicarlas."),
        },
        "resumen": {
            "actas": len(mesas),
            "con_hallazgos": len(con_h),
            "alta": sum(1 for m in mesas if m["severidad"] == "alta"),
            "media": sum(1 for m in mesas if m["severidad"] == "media"),
            "baja": sum(1 for m in mesas if m["severidad"] == "baja"),
            "votos_en_juego_foco": sum(m["impacto_foco"] for m in mesas),
            "por_tipo": dict(sorted(conteo.items(), key=lambda kv: -kv[1])),
        },
        "listas": listas,
        "puestos": sorted(por_puesto.values(), key=lambda p: (-p["alta"], -p["media"], p["puesto"])),
        "mesas": mesas,
    }


# =================================================================== extraer
ESQUEMA_E14 = {
    "type": "object",
    "properties": {
        "corporacion": {"type": "string", "description": "CONCEJO, JAL, ASAMBLEA, ALCALDIA, etc."},
        "municipio": {"type": "string"},
        "zona": {"type": "string"}, "puesto": {"type": "string"},
        "puesto_nombre": {"type": "string"}, "mesa": {"type": "string"},
        "sufragantes_e11": {"type": ["integer", "null"], "description": "Total sufragantes formato E-11"},
        "votos_urna": {"type": ["integer", "null"], "description": "Total votos en la urna"},
        "votos_incinerados": {"type": ["integer", "null"]},
        "listas": {"type": "array", "items": {"type": "object", "properties": {
            "codigo": {"type": "string"}, "nombre": {"type": "string"},
            "votos_lista": {"type": ["integer", "null"], "description": "Votos solo por la agrupacion o logo"},
            "candidatos": {"type": "object", "additionalProperties": {"type": ["integer", "null"]},
                           "description": "Numero de candidato -> votos, tal como esta escrito"},
            "total": {"type": ["integer", "null"], "description": "Total votos de la lista escrito en el acta"}},
            "required": ["codigo", "votos_lista", "candidatos", "total"]}},
        "blanco": {"type": ["integer", "null"]}, "nulos": {"type": ["integer", "null"]},
        "no_marcados": {"type": ["integer", "null"]},
        "total_votos": {"type": ["integer", "null"], "description": "Total de votos de la mesa escrito en el acta"},
        "firmas_jurados": {"type": ["integer", "null"], "description": "Cuantas firmas de jurados hay"},
        "enmendaduras": {"type": "array", "items": {"type": "object", "properties": {
            "campo": {"type": "string"}, "lista": {"type": ["string", "null"]},
            "detalle": {"type": "string"}}, "required": ["campo", "detalle"]}},
        "legible": {"type": "boolean"},
        "confianza": {"type": "number", "description": "0 a 1, que tan seguro estas de la lectura completa"},
        "observaciones": {"type": "string"},
    },
    "required": ["zona", "puesto", "mesa", "listas", "blanco", "nulos", "no_marcados",
                 "total_votos", "votos_urna", "sufragantes_e11", "enmendaduras", "legible", "confianza"],
}

PROMPT_E14 = """Este es un formulario E-14 (acta de escrutinio de jurados de votacion) de Colombia.
Transcribe EXACTAMENTE lo que esta escrito a mano en cada casilla. No corrijas sumas ni completes
valores: si una suma no cuadra, transcribela tal cual, porque el objetivo es detectar esos errores.

Reglas:
- Casillas con guiones, asteriscos o vacias: null. Un cero escrito: 0.
- Registra en "enmendaduras" cada casilla con tachones, borrones, numeros sobrescritos o
  correcciones, indicando el campo (p. ej. "lista 005 candidato 103") y que se ve.
- Si un numero es ambiguo (un 1 que puede ser 7), elige la lectura mas probable, bajala a la
  confianza y mencionalo en observaciones.
- Cuenta las firmas de jurados visibles al pie.
- Si el documento tiene varias paginas, consolida todas en un solo registro.
Usa la herramienta registrar_e14."""

EXT_IMAGEN = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp", ".gif": "image/gif"}


def _bloque_archivo(path: Path) -> dict:
    datos = base64.standard_b64encode(path.read_bytes()).decode()
    ext = path.suffix.lower()
    if ext == ".pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": datos}}
    return {"type": "image", "source": {"type": "base64", "media_type": EXT_IMAGEN[ext], "data": datos}}


def _cargar_env():
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def extraer(entrada: Path, salida: Path, modelo: str, limite: int | None = None) -> int:
    try:
        import anthropic
    except ImportError:
        sys.exit("Falta el paquete anthropic: pip install anthropic")
    _cargar_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Falta ANTHROPIC_API_KEY (variable de entorno o archivo .env).")

    archivos = sorted(p for p in (entrada.rglob("*") if entrada.is_dir() else [entrada])
                      if p.suffix.lower() in (".pdf", *EXT_IMAGEN))
    hechos = set()
    if salida.exists():
        hechos = {json.loads(l).get("archivo") for l in salida.read_text(encoding="utf-8").splitlines() if l.strip()}
    pendientes = [p for p in archivos if str(p) not in hechos][: limite or None]
    print(f"{len(archivos)} archivos, {len(hechos)} ya leidos, {len(pendientes)} por leer.")

    cliente = anthropic.Anthropic()
    salida.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(salida, "a", encoding="utf-8") as out:
        for i, p in enumerate(pendientes, 1):
            try:
                r = cliente.messages.create(
                    model=modelo, max_tokens=4096,
                    tools=[{"name": "registrar_e14", "description": "Registra los datos transcritos del E-14.",
                            "input_schema": ESQUEMA_E14}],
                    messages=[{"role": "user", "content": [_bloque_archivo(p), {"type": "text", "text": PROMPT_E14}]}],
                )
                acta = next(b.input for b in r.content if b.type == "tool_use")
            except Exception as e:  # una acta mala no detiene el lote
                print(f"  [{i}/{len(pendientes)}] ERROR {p.name}: {e}")
                continue
            acta["archivo"] = str(p)
            acta["mesa_id"] = mesa_id(acta)
            out.write(json.dumps(acta, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            print(f"  [{i}/{len(pendientes)}] {p.name} -> mesa {acta['mesa_id']} (confianza {acta.get('confianza', 0):.0%})")
    return n


# ====================================================================== demo
def generar_demo(n_puestos: int = 14, semilla: int = 2023) -> tuple[list[dict], dict, dict]:
    """Actas sinteticas con errores sembrados. Nombres y cifras inventados."""
    rnd = random.Random(semilla)
    listas = {f"{i:03d}": [f"{i}{j:02d}" for j in range(1, 8)] for i in (1, 2, 3, 4, 5, 6, 7, 9)}
    peso = {"001": 0.21, "002": 0.17, "003": 0.15, "004": 0.13, "005": 0.12, "006": 0.09, "007": 0.08, "009": 0.05}
    actas, pre, esc = [], defaultdict(dict), defaultdict(dict)
    for p in range(1, n_puestos + 1):
        zona = f"{(p - 1) // 5 + 1:02d}"
        puesto = f"{p:03d}"
        for m in range(1, rnd.randint(6, 16) + 1):
            e11 = rnd.randint(130, 290)
            urna = e11
            blanco, nulos, nm = rnd.randint(4, 18), rnd.randint(1, 8), rnd.randint(1, 9)
            restante = urna - blanco - nulos - nm
            ls = []
            cods = list(listas)
            reparto = [rnd.gammavariate(peso[c] * 30, 1) for c in cods]
            s = sum(reparto)
            asign = [int(restante * r / s) for r in reparto]
            asign[0] += restante - sum(asign)
            for cod, tot in zip(cods, asign):
                logo = int(tot * rnd.uniform(0.15, 0.35))
                resto = tot - logo
                pesos = [rnd.random() ** 2 for _ in listas[cod]]
                sp = sum(pesos)
                c = {k: int(resto * w / sp) for k, w in zip(listas[cod], pesos)}
                c[listas[cod][0]] += resto - sum(c.values())
                ls.append({"codigo": cod, "votos_lista": logo, "candidatos": c, "total": tot})
            acta = {"corporacion": "CONCEJO", "municipio": "DEMO", "zona": zona, "puesto": puesto,
                    "puesto_nombre": f"Puesto demo {puesto}", "mesa": f"{m:03d}",
                    "sufragantes_e11": e11, "votos_urna": urna, "votos_incinerados": 0,
                    "listas": ls, "blanco": blanco, "nulos": nulos, "no_marcados": nm,
                    "total_votos": urna, "firmas_jurados": 3, "enmendaduras": [],
                    "legible": True, "confianza": round(rnd.uniform(0.86, 0.99), 2)}
            acta["mesa_id"] = mesa_id(acta)
            actas.append(acta)

    # sembrar errores conocidos sobre una muestra fija
    muestra = rnd.sample(actas, 40)
    for k, a in enumerate(muestra):
        tipo = k % 10
        l = rnd.choice(a["listas"])
        if tipo == 0:   # total de lista mal sumado
            l["total"] += rnd.choice([-10, -5, 4, 10])
        elif tipo == 1:  # total de mesa mal sumado
            a["total_votos"] += rnd.choice([-12, 7, 20])
        elif tipo == 2:  # mas votos en urna que sufragantes
            extra = rnd.randint(3, 15)
            a["votos_urna"] += extra
            a["total_votos"] += extra
            a["blanco"] += extra
        elif tipo == 3:  # enmendadura en el foco
            a["enmendaduras"].append({"campo": "lista 005 total", "lista": "005",
                                      "detalle": "el total aparece tachado y sobrescrito"})
        elif tipo == 4:
            a["firmas_jurados"] = rnd.choice([0, 1, 2])
        elif tipo == 5:
            a["confianza"] = 0.55
        elif tipo == 6:  # concentracion atipica en la lista minoritaria
            valid = sum(x["total"] for x in a["listas"])
            for x in a["listas"]:
                x["votos_lista"], x["candidatos"] = 0, {kk: 0 for kk in x["candidatos"]}
                x["total"] = 0
            fav = next(x for x in a["listas"] if x["codigo"] == "009")
            fav["candidatos"][listas["009"][0]] = int(valid * 0.88)
            fav["votos_lista"] = valid - int(valid * 0.88) - 6
            fav["total"] = valid - 6
            a["listas"][0]["candidatos"][listas["001"][0]] = 6
            a["listas"][0]["total"] = 6
        elif tipo == 7:  # nulos disparados
            mover = int(a["total_votos"] * 0.22)
            movido = 0
            for x in sorted(a["listas"], key=lambda x: -x["votos_lista"]):
                q = min(x["votos_lista"], mover - movido)
                x["votos_lista"] -= q
                x["total"] -= q
                movido += q
            a["nulos"] += movido

    # preconteo y escrutinio coherentes con el E-14, con diferencias sembradas
    for a in actas:
        for clave, v in cifras_acta(a).items():
            pre[a["mesa_id"]][clave] = v
            esc[a["mesa_id"]][clave] = v
    for a in rnd.sample(actas, 12):  # el escrutinio le baja votos al foco
        l = next(x for x in a["listas"] if x["codigo"] == "005")
        cand = rnd.choice(list(l["candidatos"]))
        d = rnd.randint(5, 30)
        esc[a["mesa_id"]][("005", cand)] = max(0, l["candidatos"][cand] - d)
        esc[a["mesa_id"]][("005", "TOTAL")] = max(0, l["total"] - d)
    for a in rnd.sample(actas, 10):  # errores de digitacion del preconteo
        l = rnd.choice(a["listas"])
        pre[a["mesa_id"]][(l["codigo"], "TOTAL")] = l["total"] + rnd.choice([-10, 10, 1, -1])
    # una mesa gemela
    a, b = actas[3], actas[4]
    b["listas"] = json.loads(json.dumps(a["listas"]))
    for k in ("blanco", "nulos", "no_marcados", "total_votos", "votos_urna", "sufragantes_e11"):
        b[k] = a[k]
    for clave, v in cifras_acta(b).items():
        pre[b["mesa_id"]][clave] = v
        esc[b["mesa_id"]][clave] = v
    return actas, dict(pre), dict(esc)


# ======================================================================= cli
def _escribir(res: dict, salida: Path):
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    r = res["resumen"]
    print(f"{r['actas']} actas, {r['con_hallazgos']} con hallazgos "
          f"(alta {r['alta']}, media {r['media']}, baja {r['baja']}). -> {salida}")


def main(argv: Iterable[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extraer", help="leer E-14 con Claude vision")
    e.add_argument("--entrada", required=True, type=Path, help="carpeta o archivo con PDF/imagenes")
    e.add_argument("--salida", default=RAIZ / "data" / "_e14_actas.jsonl", type=Path)
    e.add_argument("--modelo", default=os.environ.get("E14_MODELO", "claude-sonnet-5-5"))
    e.add_argument("--limite", type=int, help="leer solo N actas (para probar)")

    a = sub.add_parser("auditar", help="aplicar reglas y comparar fuentes")
    a.add_argument("--actas", required=True, type=Path)
    a.add_argument("--preconteo", type=Path)
    a.add_argument("--escrutinio", type=Path)
    a.add_argument("--foco", help="codigo de la lista a defender, p. ej. 005")
    a.add_argument("--municipio", default="")
    a.add_argument("--eleccion", default="")
    a.add_argument("--min-firmas", type=int, default=3)
    a.add_argument("--salida", default=SALIDA_DEFECTO, type=Path)

    d = sub.add_parser("demo", help="generar y auditar actas sinteticas")
    d.add_argument("--salida", default=SALIDA_DEMO, type=Path)

    args = ap.parse_args(argv)
    if args.cmd == "extraer":
        extraer(args.entrada, args.salida, args.modelo, args.limite)
    elif args.cmd == "auditar":
        res = auditar(leer_jsonl(args.actas), leer_csv_largo(args.preconteo), leer_csv_largo(args.escrutinio),
                      foco=args.foco, min_firmas=args.min_firmas,
                      meta={"municipio": args.municipio, "eleccion": args.eleccion, "demo": False})
        _escribir(res, args.salida)
    else:
        actas, pre, esc = generar_demo()
        res = auditar(actas, pre, esc, foco="005",
                      meta={"municipio": "Municipio demo", "eleccion": "Concejo (datos sintéticos)", "demo": True})
        _escribir(res, args.salida)


if __name__ == "__main__":
    main()
