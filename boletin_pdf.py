#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lector del PDF trimestral del Boletin de Responsables Fiscales (CGR)
====================================================================

El dataset abierto de datos.gov.co trae una sola fila por responsable, asi
que pierde los fallos adicionales de quien tiene varios. El PDF oficial
trae una fila por caso (entidad afectada + tipo de responsabilidad), con
las columnas TR (I=Individual, S=Solidario) y R (cantidad de registros).

Las columnas se ubican por la posicion horizontal de cada palabra respecto
del encabezado de cada pagina, y un caso empieza en cada renglon que trae
tipo de documento (NIT/CC/CE...) o un valor en la columna TR. Asi tambien
se conservan los pocos casos que el boletin publica sin documento.

Ojo: Departamento y Municipio son la SEDE DEL ENTE QUE REPORTA, no el lugar
del dano. El lugar del dano se lee en "Entidad afectada".

Uso suelto (para revisar):  python boletin_pdf.py Boletin.pdf
"""

from __future__ import annotations

import collections
import re
import sys

TIPOS_DOC = re.compile(r"^(NIT|CC|CE|PA|TI|PEP|NUIP|RC|PPT)$")
ENCABEZADO = {"Tipo", "Entidad", "TR", "R", "Ente", "Departamento", "Municipio"}
COLUMNAS = ["nombre", "documento", "entidad", "tr", "r", "ente", "depto", "municipio"]


def _limites(palabras) -> list[float] | None:
    h = {w["text"]: w["x0"] for w in palabras if 125 < w["top"] < 148}
    if not ENCABEZADO <= h.keys():
        return None
    # El contenido arranca un poco a la izquierda de cada titulo de columna.
    return [h["Tipo"] - 6, h["Entidad"] - 26, h["TR"] - 4, h["R"] - 4,
            h["R"] + 11, h["Departamento"] - 16, h["Municipio"] - 20]


def leer(ruta) -> tuple[dict, list[dict]]:
    import pdfplumber  # pip install pdfplumber

    meta: dict = {}
    crudos: list[list[list[str]]] = []
    paginas_sin_encabezado: list[int] = []
    with pdfplumber.open(ruta) as pdf:
        for n, pag in enumerate(pdf.pages, 1):
            palabras = pag.extract_words()
            if not meta:
                t = " ".join(w["text"] for w in palabras if 100 < w["top"] < 122)
                m = re.search(r"N°\s*(\d+).*?corte a \w+ (\d{1,2} de \w+ de \d{4})", t)
                if m:
                    meta = {"numero": int(m.group(1)), "corte": m.group(2)}
            lim = _limites(palabras)
            if not lim:
                paginas_sin_encabezado.append(n)
                continue
            cuerpo = [w for w in palabras
                      if 145 < w["top"] < pag.height - 60 and w["text"] != "JMMC"]
            renglones: list[list] = []
            for w in sorted(cuerpo, key=lambda w: (w["top"], w["x0"])):
                if renglones and w["top"] - renglones[-1][0] <= 2:
                    renglones[-1][1].append(w)
                else:
                    renglones.append([w["top"], [w]])
            actual = None
            for _, ws in renglones:
                cols: list[list[str]] = [[] for _ in COLUMNAS]
                for w in sorted(ws, key=lambda w: w["x0"]):
                    cols[sum(w["x0"] >= x for x in lim)].append(w["text"])
                nuevo = (cols[1] and TIPOS_DOC.match(cols[1][0])) or cols[3] in (["I"], ["S"])
                if nuevo:
                    actual = [[] for _ in COLUMNAS]
                    crudos.append(actual)
                if actual is not None:
                    for i, c in enumerate(cols):
                        actual[i].extend(c)

    casos = []
    for c in crudos:
        v = {k: " ".join(x).strip() for k, x in zip(COLUMNAS, c)}
        tipo, _, num = v.pop("documento").partition(" ")
        v["tipo_doc"], v["documento"] = (tipo, num.replace(" ", "")) if TIPOS_DOC.match(tipo) else ("", "")
        casos.append(v)
    meta["paginas"] = n
    if paginas_sin_encabezado:
        meta["paginas_sin_encabezado"] = paginas_sin_encabezado
    return meta, casos


def validar(casos: list[dict]) -> list[str]:
    """Problemas de lectura evidentes (columnas corridas)."""
    errores = []
    for i, c in enumerate(casos):
        if c["tr"] not in ("I", "S"):
            errores.append(f"caso {i}: TR '{c['tr']}' ({c['nombre']})")
        if not c["r"].isdigit():
            errores.append(f"caso {i}: R '{c['r']}' ({c['nombre']})")
        if not c["entidad"] or not c["ente"]:
            errores.append(f"caso {i}: sin entidad o ente ({c['nombre']})")
    return errores


if __name__ == "__main__":
    meta, casos = leer(sys.argv[1])
    print(meta, len(casos), "casos,", len({c["documento"] for c in casos if c["documento"]}), "responsables")
    for e in validar(casos)[:20]:
        print("  !", e)
