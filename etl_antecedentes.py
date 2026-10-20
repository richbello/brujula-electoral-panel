#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Indices de antecedentes para la pestana "Vigilancia fiscal"
===========================================================

Convierte los CSV de SIRI (Procuraduria) y del Boletin de Responsables
Fiscales (Contraloria) en dos JSON compactos que GitHub Pages sirve como
archivos estaticos. La pagina modulos-3-integrados.html los descarga y cruza
en el navegador contra SECOP II, sin depender de ningun servidor.

Uso
---
    python etl_antecedentes.py --siri siri_antecedentes.csv \
                               --boletin boletin_responsables_fiscales.csv

Produce:
    data/vigilancia/siri.json
    data/vigilancia/boletin.json

Formato (por documento normalizado, solo digitos):
    siri.json    {"meta": {...}, "docs": {"<doc>": [[nombre, tipo_inhabilidad,
                  sanciones, fecha_efectos, anos, meses, dias, autoridad,
                  entidad_sancionado], ...]}}
    boletin.json {"meta": {...}, "docs": {"<doc>": [i, ...]},
                  "filas": [[nombre, ente_que_reporta, entidad_afectada,
                  departamento, municipio], ...]}

El Boletin trae los NIT con el digito de verificacion pegado
("NIT 8020062581") y SECOP II suele traerlos sin el ("802006258"). Cuando el
ultimo digito es un DV valido segun la DIAN, el registro se indexa con y sin DV.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path

SALIDA = Path(__file__).resolve().parent / "data" / "vigilancia"


def norm(v) -> str:
    s = "" if v is None else str(v)
    if "-" in s:
        s = s.split("-")[0]
    return re.sub(r"[^0-9]", "", s)


def dv_nit(base: str) -> int:
    pesos = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]
    s = sum(int(d) * p for d, p in zip(reversed(base), reversed(pesos)))
    r = s % 11
    return r if r < 2 else 11 - r


def claves_boletin(valor) -> list[str]:
    doc = norm(valor)
    claves = [doc] if doc else []
    if str(valor).strip().upper().startswith("NIT") and len(doc) == 10 \
            and dv_nit(doc[:9]) == int(doc[9]):
        claves.append(doc[:9])
    return claves


def limpio(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def construir_siri(ruta: Path) -> dict:
    docs: dict[str, list] = {}
    n = 0
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            doc = norm(row.get("numero_identificacion"))
            if not doc:
                continue
            nombre = " ".join(filter(None, (limpio(row.get(k)) for k in (
                "primer_nombre", "segundo_nombre", "primer_apellido", "segundo_apellido"))))
            docs.setdefault(doc, []).append([
                nombre,
                limpio(row.get("tipo_inhabilidad")),
                limpio(row.get("sanciones")),
                limpio(row.get("fecha_efectos_juridicos")),
                limpio(row.get("duracion_anos")),
                limpio(row.get("duracion_mes")),
                limpio(row.get("duracion_dias")),
                limpio(row.get("autoridad")),
                limpio(row.get("entidad_sancionado")),
            ])
            n += 1
    return {"meta": {"fuente": "SIRI - Procuraduria General de la Nacion",
                     "registros": n, "documentos": len(docs),
                     "generado": dt.date.today().isoformat()},
            "docs": docs}


def construir_boletin(ruta: Path) -> dict:
    filas: list[list] = []
    docs: dict[str, list] = {}
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            claves = claves_boletin(row.get("documento"))
            if not claves:
                continue
            i = len(filas)
            filas.append([
                limpio(row.get("nombre")),
                limpio(row.get("Ente que Reporta")),
                limpio(row.get("Entidad Afectada")),
                limpio(row.get("Departamento")),
                limpio(row.get("Municipio")),
            ])
            for c in claves:
                docs.setdefault(c, []).append(i)
    return {"meta": {"fuente": "Boletin de Responsables Fiscales - Contraloria General",
                     "registros": len(filas),
                     "generado": dt.date.today().isoformat()},
            "docs": docs, "filas": filas}


def escribir(nombre: str, datos: dict) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    p = SALIDA / nombre
    p.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{p}  {p.stat().st_size/1e6:.1f} MB  {datos['meta']['registros']} registros")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--siri", type=Path)
    ap.add_argument("--boletin", type=Path)
    a = ap.parse_args()
    if not (a.siri or a.boletin):
        ap.error("indique --siri y/o --boletin")
    if a.siri:
        escribir("siri.json", construir_siri(a.siri))
    if a.boletin:
        escribir("boletin.json", construir_boletin(a.boletin))
