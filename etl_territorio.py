#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL de Territorio y Obras Inconclusas
=====================================

Dos analisis sobre SECOP II - Contratos Electronicos (jbjy-vk9h):

  1. OBRAS VENCIDAS. Contratos cuya fecha de fin ya paso y que siguen
     figurando en ejecucion. No depende de geografia: cubre el 100% de los
     contratos del municipio y es el dato mas solido del modulo.

  2. SECTORES NOMBRADOS. Donde el objeto del contrato nombra un lugar
     (comuna, vereda, barrio, colegio, parque, via), se extrae y se agrupa
     el valor por lugar.

POR QUE ESTO NO ES UN MAPA DE LA INVERSION
------------------------------------------
SECOP trae un campo "direccion de ejecucion del contrato", pero en la
practica contiene la direccion de la entidad contratante, no la del sitio de
la obra: decenas de contratos repiten la direccion de la alcaldia. Por eso
NO se usa.

El lugar real solo aparece en el texto del objeto, y solo en una parte de los
contratos. El resto dice "del municipio de X" o no menciona lugar. En una
muestra de los contratos grandes de Soacha, uno de cada cuatro nombraba un
sitio concreto.

Eso significa que un sector que no aparece puede no haber recibido nada, o
puede haber recibido mucho sin que el objeto lo nombre. El ETL calcula y
publica la COBERTURA -- que porcentaje del valor quedo sin ubicar -- y la
pagina la muestra. Sin ese numero a la vista, afirmar "a mi barrio no le
llego nada" seria una conclusion falsa.

Cuando un objeto nombra varios lugares, el valor se reparte en partes
iguales entre ellos, para que la suma por sector no supere el total.

Uso
---
    python etl_territorio.py --municipio Soacha --desde 2020-01-01

Requiere: requests
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import requests  # noqa: F401
except ImportError:  # pragma: no cover
    sys.exit("Falta la dependencia 'requests'.  Instale con:  pip install requests")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etl_vigilancia_fiscal import DOMINIO, a_numero, a_fecha, consultar  # noqa: E402

DATASET = "jbjy-vk9h"
FUENTE = {
    "dataset": DATASET,
    "nombre": "SECOP II - Contratos Electronicos",
    "entidad": "Colombia Compra Eficiente",
    "pagina": f"{DOMINIO}/d/{DATASET}",
}

# Estados que indican que el contrato sigue abierto.
ABIERTOS = ("ejecu", "activo", "celebrado", "firmado")
# Estados que indican que ya cerro, aunque la fecha haya pasado.
CERRADOS = ("terminad", "liquidad", "cedido", "suspendid", "cerrado", "anulad")


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn")


# --------------------------------------------------------------------------
# Extraccion de lugares del objeto contractual
# --------------------------------------------------------------------------

ROMANOS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
           "VII": 7, "VIII": 8, "IX": 9, "X": 10}

# Articulos y preposiciones que pueden ABRIR un nombre ("de los Locos") y se
# descartan al principio, pero no cortan la captura.
ARRANQUE = {"DEL", "DE", "LA", "EL", "LOS", "LAS"}

# Palabras que indican que el nombre ya termino: lo que sigue es otra cosa.
# Sin esto, "PARQUE DE LOS LOCOS DEL MUNICIPIO DE SOACHA" se guardaba entero.
FRENO = {"EN", "PARA", "CON", "QUE", "POR", "DESDE", "HASTA", "ENTRE", "SEGUN",
         "MEDIANTE", "UBICAD", "LOCALIZAD", "PERTENECIENTE", "CORRESPONDIENTE",
         "MUNICIPIO", "SOACHA", "CUNDINAMARCA", "COLOMBIA", "CIUDAD", "DEPARTAMENTO",
         "Y", "E", "O", "U", "ASI", "COMO", "DEMAS", "OTROS", "VARIOS"}

# Resultados que no son un lugar aunque el patron los capture.
BASURA = {"", "OFICIAL", "OFICIALES", "PUBLICA", "PUBLICO", "MUNICIPAL", "DISTRITAL",
          "ACTUALIZACION", "ADECUACION", "MANTENIMIENTO", "CONSTRUCCION", "DOTACION",
          "MEJORAMIENTO", "SUMINISTRO", "PRESTACION", "SERVICIOS", "SERVICIO",
          "CIUDAD", "MUNICIPIO", "SOACHA", "CUNDINAMARCA", "COLOMBIA", "SECTOR",
          "SECTORES", "BARRIO", "BARRIOS", "COMUNA", "COMUNAS", "VEREDA", "URBANA",
          "URBANAS", "RURAL", "RURALES", "NUEVA", "NUEVO", "VIAS", "VIA", "TODOS",
          "VARIOS", "DIFERENTES", "LAS", "LOS", "DEL", "UNA", "UNO",
          "SUSCRITO", "SUSCRITA", "VIGENTE", "VIGENTES", "RESPECTIVO", "RESPECTIVA"}

# Un participio suelto describe una seleccion, no nombra un lugar:
# "instituciones educativas FOCALIZADAS", "barrios ELEGIDOS".
# La raiz debe tener al menos 4 letras, para no confundir nombres cortos:
# "Vida" termina en -ida y "Prado" en -ado, pero no son participios.
PARTICIPIO = re.compile(r"^[A-Za-zÁÉÍÓÚÑáéíóúñ]{4,}(AD[OA]S?|ID[OA]S?)$")


def _limpiar_nombre(txt: str) -> str:
    """Recorta el nombre del lugar: arranca tras los articulos y se detiene en
    la primera palabra que indica que el nombre ya termino."""
    t = re.sub(r"[^\wÁÉÍÓÚÑáéíóúñ ]+", " ", str(txt or ""))
    t = re.sub(r"\s+", " ", t).strip()
    palabras: list[str] = []
    for p in t.split():
        u = sin_tildes(p).upper()
        if not palabras and u in ARRANQUE:
            continue                       # "de los Locos" -> arranca en Locos
        if palabras and any(u.startswith(f) for f in FRENO):
            break                          # "Locos DEL MUNICIPIO" -> corta
        if u in FRENO and not palabras:
            return ""                      # arranca en una palabra de freno
        palabras.append(p)
        if len(palabras) >= 4:
            break
    # un conector que quedo colgando al final no es parte del nombre:
    # "Locos del" -> "Locos"
    while palabras and sin_tildes(palabras[-1]).upper() in ARRANQUE:
        palabras.pop()
    nombre = " ".join(palabras).title().strip()
    # un nombre que solo tiene palabras genericas no identifica ningun lugar
    utiles = [w for w in nombre.split()
              if sin_tildes(w).upper() not in BASURA and len(w) > 2]
    if not utiles or len(nombre) < 3:
        return ""
    if len(utiles) == 1 and PARTICIPIO.match(sin_tildes(utiles[0]).upper()):
        return ""
    return nombre


def extraer_lugares(objeto: str) -> list[dict]:
    """Devuelve los lugares nombrados en el objeto, sin repetir."""
    o = str(objeto or "")
    up = sin_tildes(o).upper()
    hallados: list[dict] = []
    vistos: set[tuple] = set()

    def add(tipo: str, nombre: str):
        nombre = nombre.strip()
        if not nombre or len(nombre) < 2:
            return
        clave = (tipo, sin_tildes(nombre).upper())
        if clave in vistos:
            return
        vistos.add(clave)
        hallados.append({"tipo": tipo, "nombre": nombre})

    # COMUNA 3 / COMUNA III
    for m in re.finditer(r"\bCOMUNAS?\s+((?:\d{1,2}|[IVX]{1,4})(?:\s*[,YE]+\s*(?:\d{1,2}|[IVX]{1,4}))*)", up):
        for tok in re.split(r"[,YE\s]+", m.group(1)):
            tok = tok.strip()
            if not tok:
                continue
            n = int(tok) if tok.isdigit() else ROMANOS.get(tok)
            if n:
                add("Comuna", f"Comuna {n}")

    # VEREDA X / CORREGIMIENTO X
    for etiqueta, tipo in (("VEREDAS?", "Vereda"), ("CORREGIMIENTOS?", "Corregimiento")):
        for m in re.finditer(etiqueta + r"\s+([A-ZÁÉÍÓÚÑ0-9 ]{3,40})", up):
            pos = m.start(1)
            add(tipo, _limpiar_nombre(o[pos:pos + len(m.group(1))]))

    # BARRIO X / SECTOR X / SECTORES A; B; C / URBANIZACION X
    for etiqueta, tipo in (("BARRIOS?", "Barrio"), ("SECTORES?", "Sector"),
                           ("URBANIZACIONE?S?", "Urbanización")):
        for m in re.finditer(etiqueta + r"\s+([A-ZÁÉÍÓÚÑ0-9;,\- ]{3,120})", up):
            bruto = o[m.start(1):m.start(1) + len(m.group(1))]
            # varios sectores suelen venir separados por ; o ,
            for parte in re.split(r"[;]", bruto):
                nom = _limpiar_nombre(parte)
                if nom:
                    add(tipo, nom)

    # Colegios e instituciones educativas
    for m in re.finditer(r"(?:INSTITUCION(?:ES)? EDUCATIV[AO]S?(?: OFICIAL(?:ES)?)?|"
                         r"\bI\.?E\.?D\.?|\bIED\b|COLEGIOS?|"
                         r"ESTABLECIMIENTOS? EDUCATIVOS?)\s+([A-ZÁÉÍÓÚÑ0-9 ]{4,50})", up):
        add("Institución educativa", _limpiar_nombre(o[m.start(1):m.start(1) + len(m.group(1))]))

    # Parques, plazoletas, escenarios con nombre propio
    for etiqueta, tipo in (("PARQUES?", "Parque"), ("PLAZOLETAS?", "Plazoleta"),
                           ("POLIDEPORTIVOS?", "Polideportivo"), ("SALON(?:ES)? COMUNAL(?:ES)?", "Salón comunal")):
        for m in re.finditer(etiqueta + r"\s+((?:DE\s+)?(?:LOS|LAS|EL|LA)?\s*[A-ZÁÉÍÓÚÑ0-9 ]{3,40})", up):
            nom = _limpiar_nombre(o[m.start(1):m.start(1) + len(m.group(1))])
            if nom and sin_tildes(nom).upper() not in ("MUNICIPIO", "SOACHA"):
                add(tipo, nom)

    # Vias con nombre propio (no "calle 13" generica del domicilio)
    for m in re.finditer(r"\bAVENIDAS?\s+([A-ZÁÉÍÓÚÑ0-9 ]{3,40})", up):
        add("Vía", "Avenida " + _limpiar_nombre(o[m.start(1):m.start(1) + len(m.group(1))]))
    for m in re.finditer(r"\bV[IÍ]A\s+([A-ZÁÉÍÓÚÑ]{3,20}\s*[-–]\s*[A-ZÁÉÍÓÚÑ]{3,20})", up):
        add("Vía", _limpiar_nombre(o[m.start(1):m.start(1) + len(m.group(1))]))

    return hallados


# --------------------------------------------------------------------------
# Analisis
# --------------------------------------------------------------------------

def obras_vencidas(contratos: list[dict], hoy: dt.date, *, minimo: float) -> list[dict]:
    """Contratos cuya fecha de fin ya paso y que siguen figurando abiertos."""
    salida = []
    for c in contratos:
        fin = a_fecha(c.get("fecha_de_fin_del_contrato"))
        if not fin or fin >= hoy:
            continue
        estado = sin_tildes(c.get("estado_contrato")).lower()
        if any(t in estado for t in CERRADOS):
            continue
        if not any(t in estado for t in ABIERTOS):
            continue
        valor = a_numero(c.get("valor_del_contrato"))
        if valor < minimo:
            continue
        pagado = a_numero(c.get("valor_pagado"))
        # SECOP deja valor_pagado en blanco en la gran mayoria de los
        # contratos. Restarlo del valor no da un saldo: da el valor otra vez.
        # Por eso el pendiente solo existe si el pago fue reportado.
        reportado = pagado > 0
        salida.append({
            "referencia": c.get("referencia_del_contrato") or c.get("id_contrato") or "",
            "entidad": c.get("nombre_entidad") or "",
            "contratista": c.get("proveedor_adjudicado") or "",
            "documento": re.sub(r"\D", "", str(c.get("documento_proveedor") or "")),
            "objeto": (c.get("objeto_del_contrato") or "")[:300],
            "tipo": c.get("tipo_de_contrato") or "",
            "valor": valor,
            "pagado": pagado,
            "pago_reportado": reportado,
            "pendiente": max(valor - pagado, 0.0) if reportado else None,
            "inicio": str(c.get("fecha_de_inicio_del_contrato") or "")[:10],
            "fin": fin.isoformat(),
            "dias_vencido": (hoy - fin).days,
            "estado": c.get("estado_contrato") or "",
            "lugares": extraer_lugares(c.get("objeto_del_contrato")),
            "url": (c.get("urlproceso") or {}).get("url", "") if isinstance(c.get("urlproceso"), dict) else "",
        })
    salida.sort(key=lambda x: (-x["valor"], -x["dias_vencido"]))
    return salida


def indice_contratistas(contratos: list[dict], hoy: dt.date, *, tope: int = 1500) -> list[dict]:
    """Huella contractual de cada contratista del municipio.

    Alimenta la Ficha del contendor, que necesita responder "cuanto ha
    contratado esta persona aqui", no solo "aparece en el top de obras
    vencidas". Por eso recorre TODOS los contratos, no solo los vencidos.
    """
    reg: dict[str, dict] = {}
    for c in contratos:
        doc = re.sub(r"\D", "", str(c.get("documento_proveedor") or ""))
        if not doc:
            continue
        f = reg.setdefault(doc, {
            "documento": doc,
            "nombre": c.get("proveedor_adjudicado") or "",
            "tipo_documento": c.get("tipodocproveedor") or "",
            "contratos": 0,
            "valor": 0.0,
            "pagado": 0.0,
            "entidades": set(),
            "primero": None,
            "ultimo": None,
            "vencidos": 0,
            "vencidos_con_pago": 0,
            "valor_vencido": 0.0,
            "pendiente_vencido": 0.0,
            "contratos_con_pago": 0,
            "mayores": [],
        })
        valor = a_numero(c.get("valor_del_contrato"))
        f["contratos"] += 1
        f["valor"] += valor
        pagado_c = a_numero(c.get("valor_pagado"))
        f["pagado"] += pagado_c
        if pagado_c > 0:
            f["contratos_con_pago"] += 1
        if c.get("nombre_entidad"):
            f["entidades"].add(c["nombre_entidad"])

        firma = a_fecha(c.get("fecha_de_firma"))
        if firma:
            if not f["primero"] or firma < f["primero"]:
                f["primero"] = firma
            if not f["ultimo"] or firma > f["ultimo"]:
                f["ultimo"] = firma

        fin = a_fecha(c.get("fecha_de_fin_del_contrato"))
        estado = sin_tildes(c.get("estado_contrato")).lower()
        if (fin and fin < hoy and not any(t in estado for t in CERRADOS)
                and any(t in estado for t in ABIERTOS)):
            f["vencidos"] += 1
            f["valor_vencido"] += valor
            pag = a_numero(c.get("valor_pagado"))
            if pag > 0:
                f["pendiente_vencido"] += max(valor - pag, 0.0)
                f["vencidos_con_pago"] += 1

        f["mayores"].append({
            "referencia": c.get("referencia_del_contrato") or c.get("id_contrato") or "",
            "entidad": c.get("nombre_entidad") or "",
            "objeto": (c.get("objeto_del_contrato") or "")[:180],
            "valor": valor,
            "firma": firma.isoformat() if firma else "",
            "estado": c.get("estado_contrato") or "",
        })

    salida = []
    for f in reg.values():
        f["mayores"].sort(key=lambda x: -x["valor"])
        salida.append({
            **{k: v for k, v in f.items() if k not in ("entidades", "primero", "ultimo", "mayores")},
            "entidades": len(f["entidades"]),
            "nombres_entidades": sorted(f["entidades"])[:5],
            "primero": f["primero"].isoformat() if f["primero"] else "",
            "ultimo": f["ultimo"].isoformat() if f["ultimo"] else "",
            "mayores": f["mayores"][:5],
        })
    salida.sort(key=lambda x: -x["valor"])
    return salida[:tope]


def por_sector(contratos: list[dict]) -> tuple[list[dict], dict]:
    """Agrupa el valor por lugar nombrado y calcula la cobertura.

    Si un objeto nombra varios lugares, el valor se reparte en partes iguales
    para que la suma por sector no supere el total contratado.
    """
    acumulado: dict[tuple, dict] = {}
    con_lugar = sin_lugar = 0
    valor_con = valor_sin = 0.0

    for c in contratos:
        valor = a_numero(c.get("valor_del_contrato"))
        lugares = extraer_lugares(c.get("objeto_del_contrato"))
        if not lugares:
            sin_lugar += 1
            valor_sin += valor
            continue
        con_lugar += 1
        valor_con += valor
        parte = valor / len(lugares)
        for lg in lugares:
            clave = (lg["tipo"], lg["nombre"])
            f = acumulado.setdefault(clave, {
                "tipo": lg["tipo"], "nombre": lg["nombre"],
                "valor": 0.0, "contratos": 0, "ejemplos": [],
            })
            f["valor"] += parte
            f["contratos"] += 1
            if len(f["ejemplos"]) < 4:
                f["ejemplos"].append({
                    "referencia": c.get("referencia_del_contrato") or "",
                    "objeto": (c.get("objeto_del_contrato") or "")[:180],
                    "valor": valor,
                    "entidad": c.get("nombre_entidad") or "",
                    "firma": str(c.get("fecha_de_firma") or "")[:10],
                })
            f["valor"] = round(f["valor"], 2)

    sectores = sorted(acumulado.values(), key=lambda x: -x["valor"])
    total = valor_con + valor_sin
    cobertura = {
        "contratos_con_lugar": con_lugar,
        "contratos_sin_lugar": sin_lugar,
        "valor_con_lugar": valor_con,
        "valor_sin_lugar": valor_sin,
        "pct_contratos": round(con_lugar / (con_lugar + sin_lugar) * 100, 1) if (con_lugar + sin_lugar) else 0.0,
        "pct_valor": round(valor_con / total * 100, 1) if total else 0.0,
    }
    return sectores, cobertura


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

def construir(municipio: str, desde: str, hasta: str, *, token: str | None,
              minimo: float, limite: int | None, hoy: dt.date | None = None) -> dict:
    ahora = dt.datetime.now().astimezone()
    hoy = hoy or ahora.date()

    print(f"[1/2] SECOP II  ->  contratos de {municipio} entre {desde} y {hasta}")
    where = (f"upper(ciudad) like upper('%{municipio}%') "
             f"AND fecha_de_firma >= '{desde}T00:00:00' "
             f"AND fecha_de_firma <= '{hasta}T23:59:59'")
    contratos = consultar(DATASET, where=where, order="fecha_de_firma DESC",
                          limite_total=limite, token=token)

    print("[2/2] Calculando obras vencidas y sectores")
    vencidas = obras_vencidas(contratos, hoy, minimo=minimo)
    sectores, cobertura = por_sector(contratos)
    contratistas = indice_contratistas(contratos, hoy)

    valor_total = sum(a_numero(c.get("valor_del_contrato")) for c in contratos)
    valor_vencido = sum(v["valor"] for v in vencidas)
    con_pago = sum(1 for c in contratos if a_numero(c.get("valor_pagado")) > 0)
    pct_pago = round(con_pago / len(contratos) * 100, 1) if contratos else 0.0

    return {
        "meta": {
            "generado_en": ahora.isoformat(timespec="seconds"),
            "municipio": municipio,
            "ventana": {"desde": desde, "hasta": hasta},
            "minimo_obra": minimo,
            "cobertura": cobertura,
            "advertencia_mapa": (
                "Esto NO es un mapa de la inversion. SECOP trae un campo de "
                "direccion de ejecucion, pero contiene la direccion de la entidad "
                "contratante, no la del sitio de la obra, asi que no se usa. El "
                "lugar solo aparece en el texto del objeto y solo en una parte de "
                "los contratos."
            ),
            "advertencia_cobertura": (
                f"El {cobertura['pct_valor']}% del valor contratado nombra un lugar. "
                f"El {round(100 - cobertura['pct_valor'], 1)}% restante corresponde a "
                "contratos de alcance municipal o sin lugar en el objeto. Un sector "
                "que no aparece puede no haber recibido nada, o haber recibido sin "
                "que el objeto lo nombre: con estos datos no se puede distinguir."
            ),
            "advertencia_pagos": (
                f"SECOP reporta valor pagado en apenas el {pct_pago}% de los contratos de este "
                "corte. Donde no lo reporta, no se puede calcular cuanto falta por pagar: el "
                "modulo muestra 'no reportado' en vez de restar y presentar el valor del "
                "contrato como si fuera un saldo pendiente."
            ),
            "reparto": ("Cuando un objeto nombra varios lugares, el valor se reparte en "
                        "partes iguales entre ellos, para que la suma por sector no "
                        "supere el total contratado."),
            "fuentes": [dict(FUENTE, registros=len(contratos))],
        },
        "kpis": {
            "contratos": len(contratos),
            "valor_total": valor_total,
            "obras_vencidas": len(vencidas),
            "valor_vencido": valor_vencido,
            "vencidas_con_pago_reportado": sum(1 for v in vencidas if v["pago_reportado"]),
            "pct_contratos_con_pago": pct_pago,
            "sectores": len(sectores),
            "cobertura_valor": cobertura["pct_valor"],
            "contratistas": len(contratistas),
        },
        "obras_vencidas": vencidas[:80],
        "sectores": sectores[:60],
        "contratistas": contratistas,
    }


def main() -> int:
    hoy = dt.date.today().isoformat()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--municipio", default="Soacha")
    p.add_argument("--desde", default="2020-01-01")
    p.add_argument("--hasta", default=hoy)
    p.add_argument("--minimo", type=float, default=20_000_000,
                   help="valor minimo para listar una obra vencida (por defecto 20 millones)")
    p.add_argument("--salida", default="data/modulos/territorio.json")
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--app-token", default=os.environ.get("SOCRATA_APP_TOKEN"))
    a = p.parse_args()

    try:
        datos = construir(a.municipio, a.desde, a.hasta, token=a.app_token,
                          minimo=a.minimo, limite=a.limite)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("No se sobrescribio el archivo de salida.", file=sys.stderr)
        return 1

    destino = Path(a.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    k, c = datos["kpis"], datos["meta"]["cobertura"]
    print()
    print(f"  Escrito: {destino}")
    print(f"  Contratos            {k['contratos']:,}")
    print(f"  Valor total          ${k['valor_total']:,.0f}")
    print(f"  Obras vencidas       {k['obras_vencidas']:,}  (${k['valor_vencido']:,.0f})")
    print(f"  Con pago reportado   {k['vencidas_con_pago_reportado']:,} de esas  "
          f"(SECOP reporta pagos en el {k['pct_contratos_con_pago']}% de los contratos)")
    print(f"  Sectores nombrados   {k['sectores']:,}")
    print(f"  Contratistas         {k['contratistas']:,}  (indice para la ficha)")
    print(f"  Cobertura            {c['pct_valor']}% del valor nombra un lugar "
          f"({c['contratos_con_lugar']:,} de {c['contratos_con_lugar'] + c['contratos_sin_lugar']:,} contratos)")
    print()
    print("  Las obras vencidas cubren el 100% de los contratos y son el dato firme.")
    print("  Los sectores son parciales: lea la cobertura antes de concluir nada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
