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
                               --boletin-pdf Boletin_Trimestre_Julio_Agosto_Septiembre_2026.pdf

    --boletin-pdf (recomendado) lee el PDF trimestral oficial de la CGR: trae
    TODOS los casos, uno por fallo. --boletin lee el CSV de datos.gov.co, que
    solo trae una fila por responsable y pierde los fallos adicionales.

Produce:
    data/vigilancia/siri.json
    data/vigilancia/boletin.json

Formato (por documento normalizado, solo digitos):
    siri.json    {"meta": {...}, "docs": {"<doc>": [[nombre, tipo_inhabilidad,
                  sanciones, fecha_efectos, anos, meses, dias, autoridad,
                  entidad_sancionado], ...]}}
    boletin.json {"meta": {...}, "docs": {"<doc>": [i, ...]},
                  "filas": [[nombre, ente_que_reporta, entidad_afectada,
                  departamento, municipio, tr, r, tipo_y_documento,
                  desde_boletin_n], ...]}
                 Con --boletin-pdf hay una fila por caso; tr = I (individual)
                 o S (solidario) y r = registros de ese caso. Departamento y
                 municipio son la sede del ente que reporta, no el lugar del dano.

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


def _clave_caso(f: list) -> str:
    """Un caso = documento (o nombre) + entidad afectada + TR + ente que reporta."""
    return "|".join([f[7] or f[0], f[2], f[5], f[1]])


def construir_boletin_pdf(ruta: Path, anterior: Path | None = None) -> dict:
    """Con --anterior (el boletin.json del trimestre previo) cada caso hereda
    el numero de boletin en que aparecio por primera vez. El boletin no
    publica la fecha del fallo; esto da al menos el trimestre de entrada."""
    from boletin_pdf import leer, validar

    meta, casos = leer(ruta)
    errores = validar(casos)
    if errores:
        raise SystemExit("El PDF no se leyo bien:\n  " + "\n  ".join(errores[:20]))
    filas: list[list] = []
    docs: dict[str, list] = {}
    for c in casos:
        i = len(filas)
        documento = (c["tipo_doc"] + " " + c["documento"]).strip()
        filas.append([limpio(c["nombre"]), limpio(c["ente"]), limpio(c["entidad"]),
                      limpio(c["depto"]), limpio(c["municipio"]), c["tr"], int(c["r"]),
                      documento])
        for k in claves_boletin(documento) if c["documento"].isdigit() else []:
            docs.setdefault(k, []).append(i)

    numero = meta.get("numero")
    cortes = {str(numero): meta.get("corte")} if numero else {}
    previo: dict[str, int] = {}
    salieron = 0
    if anterior:
        ant = json.loads(Path(anterior).read_text(encoding="utf-8"))
        n_ant = ant["meta"].get("numero")
        cortes = {**ant["meta"].get("cortes", {}), **({str(n_ant): ant["meta"].get("corte")} if n_ant else {}), **cortes}
        for f in ant["filas"]:
            if len(f) >= 8:
                previo.setdefault(_clave_caso(f), f[8] if len(f) > 8 and f[8] else n_ant)
        actuales = {_clave_caso(f) for f in filas}
        salieron = sum(1 for k in previo if k not in actuales)
    for f in filas:
        # Sin trimestre anterior no se sabe desde cuando figura: queda None.
        f.append(previo.get(_clave_caso(f), numero if anterior else None))
    nuevos = sum(1 for f in filas if anterior and f[8] == numero)

    return {"meta": {"fuente": "Boletin de Responsables Fiscales - Contraloria General",
                     "origen": "PDF trimestral oficial (SIBOR)",
                     "numero": meta.get("numero"), "corte": meta.get("corte"),
                     "registros": len(filas),
                     "responsables": len({f[7] for f in filas if f[7]}),
                     "sin_documento": sum(1 for f in filas if not f[7]),
                     "cortes": cortes,
                     "comparado_con": (ant["meta"].get("numero") if anterior else None),
                     "casos_nuevos": nuevos if anterior else None,
                     "casos_que_salieron": salieron if anterior else None,
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
    ap.add_argument("--boletin", type=Path, help="CSV de datos.gov.co (resumido)")
    ap.add_argument("--boletin-pdf", type=Path, help="PDF trimestral oficial (completo)")
    ap.add_argument("--anterior", type=Path, default=None,
                    help="boletin.json del trimestre previo, para saber desde cuando figura cada caso "
                         "(por defecto, el data/vigilancia/boletin.json actual)")
    a = ap.parse_args()
    if not (a.siri or a.boletin or a.boletin_pdf):
        ap.error("indique --siri, --boletin o --boletin-pdf")
    if a.siri:
        escribir("siri.json", construir_siri(a.siri))
    if a.boletin_pdf:
        actual = SALIDA / "boletin.json"
        anterior = a.anterior or (actual if actual.exists() else None)
        if anterior and json.loads(anterior.read_text(encoding="utf-8"))["meta"].get("origen") is None:
            anterior = None   # el corte viejo de datos.gov.co no sirve para comparar casos
        escribir("boletin.json", construir_boletin_pdf(a.boletin_pdf, anterior))
    elif a.boletin:
        escribir("boletin.json", construir_boletin(a.boletin))
