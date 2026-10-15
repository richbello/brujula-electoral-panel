#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL de Financiadores y Contratos
================================

Cruza quien financio una campana contra los contratos que esa misma persona
o empresa obtuvo despues con el Estado, en el nivel administrativo del
candidato que ayudo a elegir.

  1. Base ingresos cuentas claras   datos.gov.co  dataset jgra-rz2t
     (ingresos reportados al CNE, elecciones territoriales 2019)
  2. SECOP II - Contratos Electronicos   datos.gov.co  dataset jbjy-vk9h

BASE LEGAL
----------
Ley 1474 de 2011, articulo 2 - Inhabilidad para contratar de quienes
financien campanas politicas:

  Quien aporte mas del 2,0% de las sumas maximas a invertir por los
  candidatos en cada circunscripcion NO puede celebrar contratos con las
  entidades publicas, incluso descentralizadas, del nivel administrativo
  para el cual fue elegido el candidato financiado. La inhabilidad dura
  todo el periodo para el que fue elegido, y alcanza a parientes hasta el
  segundo grado de consanguinidad, segundo de afinidad y primero civil, y
  a las sociedades donde el financiador sea representante legal, miembro
  de junta o socio controlante.

  EXCEPCION: no aplica a los contratos de prestacion de servicios
  profesionales. Este ETL los separa para no reportarlos como infraccion.

LO QUE ESTE ETL **NO** PUEDE VER
--------------------------------
- Parientes del financiador: no hay fuente publica que los relacione.
- Sociedades donde el financiador sea socio controlante: SECOP no publica
  la composicion accionaria.
Por eso un resultado vacio no prueba que no haya inhabilidad, y una
coincidencia no prueba que si la haya. Es un punto de partida para
verificar, no un fallo.

EL TOPE DE CAMPANA
------------------
El 2% se calcula sobre el tope que fija el CNE por resolucion para cada
eleccion y cada circunscripcion, y depende del censo electoral. Como no
existe una fuente abierta con el tope por municipio, se pasa por parametro
(--tope). Sin tope, el ETL reporta igual las coincidencias pero no afirma
que superen el umbral.

Uso
---
    python etl_financiadores.py --municipio SOACHA --tope 180000000

Requiere: requests
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Falta la dependencia 'requests'.  Instale con:  pip install requests")

# Se reutiliza la normalizacion de documento ya probada en vigilancia fiscal:
# SECOP y las demas fuentes escriben el NIT con y sin digito de verificacion.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from etl_vigilancia_fiscal import (  # noqa: E402
    DOMINIO,
    a_numero,
    claves_documento,
    consultar,
)

FUENTES = {
    "ingresos": {
        "dataset": "jgra-rz2t",
        "nombre": "Base ingresos cuentas claras 2019",
        "entidad": "Consejo Nacional Electoral",
        "pagina": f"{DOMINIO}/d/jgra-rz2t",
        "eleccion": "Territoriales 2019",
        "posesion": "2020-01-01",
        "fin_periodo": "2023-12-31",
    },
    "secop": {
        "dataset": "jbjy-vk9h",
        "nombre": "SECOP II - Contratos Electronicos",
        "entidad": "Colombia Compra Eficiente",
        "pagina": f"{DOMINIO}/d/jbjy-vk9h",
    },
}

LEY = ("Ley 1474 de 2011, articulo 2 - Inhabilidad para contratar de quienes "
       "financien campanas politicas")
UMBRAL = 0.02  # 2,0% del tope de campana

# El articulo 2 enumera los cargos que cubre: Presidencia, gobernaciones,
# alcaldias y Congreso. NO cubre concejos, asambleas ni JAL. Un aporte a un
# candidato al concejo no genera esta inhabilidad, por grande que sea.
CARGOS_CUBIERTOS = ("alcald", "gobernac", "presidenc", "senado", "camara", "cámara")


def cargo_cubierto(cargo: str) -> bool:
    c = str(cargo or "").lower()
    return any(t in c for t in CARGOS_CUBIERTOS)

# La excepcion legal: estos contratos no generan la inhabilidad.
def es_servicios_profesionales(contrato: dict) -> bool:
    texto = " ".join([
        str(contrato.get("tipo_de_contrato") or ""),
        str(contrato.get("objeto_del_contrato") or ""),
    ]).lower()
    return ("prestaci" in texto and "servicio" in texto
            and ("profesional" in texto or "apoyo a la gesti" in texto))


# --------------------------------------------------------------------------
# Descarga
# --------------------------------------------------------------------------

def traer_financiadores(municipio: str | None, departamento: str | None,
                        token: str | None) -> list[dict]:
    cond = []
    if municipio:
        cond.append(f"upper(mun_nombre) like upper('%{municipio}%')")
    if departamento:
        cond.append(f"upper(dep_nombre) like upper('%{departamento}%')")
    where = " OR ".join(cond) if cond else None
    return consultar(FUENTES["ingresos"]["dataset"], where=where, token=token)


def traer_contratos(municipio: str | None, departamento: str | None,
                    desde: str, hasta: str, token: str | None,
                    limite: int | None) -> list[dict]:
    cond = []
    if municipio:
        cond.append(f"upper(ciudad) like upper('%{municipio}%')")
    if departamento:
        cond.append(f"upper(departamento) like upper('%{departamento}%')")
    territorio = f"({' OR '.join(cond)})" if cond else "1=1"
    where = (f"{territorio} AND fecha_de_firma >= '{desde}T00:00:00' "
             f"AND fecha_de_firma <= '{hasta}T23:59:59'")
    return consultar(FUENTES["secop"]["dataset"], where=where,
                     order="fecha_de_firma DESC", limite_total=limite, token=token)


# --------------------------------------------------------------------------
# Cruce
# --------------------------------------------------------------------------

def indexar_contratos(contratos: list[dict]) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = defaultdict(list)
    for c in contratos:
        for clave in claves_documento(c.get("documento_proveedor")):
            idx[clave].append(c)
    return idx


def agrupar_aportes(filas: list[dict]) -> dict[str, dict]:
    """Un financiador puede aportar varias veces y a varios candidatos."""
    por_doc: dict[str, dict] = {}
    for f in filas:
        claves = claves_documento(f.get("ing_identificacion"))
        if not claves:
            continue
        llave = min(claves, key=len)
        ficha = por_doc.setdefault(llave, {
            "documento": re.sub(r"\D", "", str(f.get("ing_identificacion") or "")),
            "nombre": f.get("nombre_persona") or "",
            "tipo_persona": f.get("tpe_nombre") or "",
            "tipo_documento": f.get("tid_nombre") or "",
            "aportado": 0.0,
            "aportes": [],
            "candidatos": {},
            "_claves": set(),
        })
        ficha["_claves"] |= claves
        valor = a_numero(f.get("ing_valor"))
        ficha["aportado"] += valor
        ficha["aportes"].append({
            "candidato": f.get("nombre_candidato") or "",
            "documento_candidato": re.sub(r"\D", "", str(f.get("can_identificacion") or "")),
            "cargo": f.get("cnd_nombre") or "",
            "nivel": f.get("cla_nombre") or "",
            "partido": f.get("org_nombre") or "",
            "municipio": f.get("mun_nombre") or "",
            "departamento": f.get("dep_nombre") or "",
            "valor": valor,
            "concepto": (f.get("ing_concepto") or "")[:200],
            "tipo": f.get("tdo_nombre") or "",
            "fecha": str(f.get("ing_fecha_comprobante") or "")[:10],
        })
        cand = f.get("nombre_candidato") or ""
        if cand:
            c = ficha["candidatos"].setdefault(cand, {
                "candidato": cand,
                "cargo": f.get("cnd_nombre") or "",
                "partido": f.get("org_nombre") or "",
                "municipio": f.get("mun_nombre") or "",
                "valor": 0.0,
            })
            c["valor"] += valor
    return por_doc


def cruzar(financiadores: dict[str, dict], idx: dict[str, list[dict]],
           tope: float | None) -> list[dict]:
    hallazgos = []
    minimo = tope * UMBRAL if tope else None

    for ficha in financiadores.values():
        vistos: set[str] = set()
        contratos: list[dict] = []
        for clave in ficha["_claves"]:
            for c in idx.get(clave, []):
                cid = str(c.get("id_contrato") or c.get("referencia_del_contrato") or id(c))
                if cid in vistos:
                    continue
                vistos.add(cid)
                contratos.append(c)
        if not contratos:
            continue

        # el territorio del aporte, para saber si el contrato es del mismo nivel
        municipios_aporte = {str(a["municipio"]).upper() for a in ficha["aportes"]}

        detalle, exceptuados = [], []
        valor_contratos = 0.0
        for c in contratos:
            fila = {
                "referencia": c.get("referencia_del_contrato") or c.get("id_contrato") or "",
                "entidad": c.get("nombre_entidad") or "",
                "ciudad": c.get("ciudad") or "",
                "tipo": c.get("tipo_de_contrato") or "",
                "modalidad": c.get("modalidad_de_contratacion") or "",
                "objeto": (c.get("objeto_del_contrato") or "")[:240],
                "valor": a_numero(c.get("valor_del_contrato")),
                "firma": str(c.get("fecha_de_firma") or "")[:10],
                "estado": c.get("estado_contrato") or "",
                "mismo_territorio": str(c.get("ciudad") or "").upper() in municipios_aporte,
                "url": (c.get("urlproceso") or {}).get("url", "") if isinstance(c.get("urlproceso"), dict) else "",
            }
            if es_servicios_profesionales(c):
                exceptuados.append(fila)
            else:
                detalle.append(fila)
                valor_contratos += fila["valor"]

        detalle.sort(key=lambda x: -x["valor"])
        exceptuados.sort(key=lambda x: -x["valor"])

        supera = (minimo is not None and ficha["aportado"] > minimo)
        en_territorio = any(f["mismo_territorio"] for f in detalle)

        # Autofinanciacion: el aportante ES el candidato. Poner plata en la
        # campana propia no es el supuesto del articulo 2, que persigue que un
        # tercero financie y despues contrate. Se separa, no se oculta.
        docs_candidatos = {a["documento_candidato"] for a in ficha["aportes"] if a["documento_candidato"]}
        auto = ficha["documento"] in docs_candidatos

        # Solo los aportes a cargos que el articulo enumera pueden generar la
        # inhabilidad. Un aporte a un concejal no la genera.
        aportes_cubiertos = [a for a in ficha["aportes"] if cargo_cubierto(a["cargo"])]
        cubierto = bool(aportes_cubiertos)
        aportado_cubierto = sum(a["valor"] for a in aportes_cubiertos)
        supera_cubierto = (minimo is not None and aportado_cubierto > minimo)

        if auto:
            nivel = "autofinanciacion"
        elif not detalle:
            nivel = "solo_exceptuados"
        elif not cubierto:
            nivel = "cargo_no_cubierto"
        elif supera_cubierto and en_territorio:
            nivel = "posible_inhabilidad"
        else:
            nivel = "revisar"

        hallazgos.append({
            "documento": ficha["documento"],
            "nombre": ficha["nombre"],
            "tipo_persona": ficha["tipo_persona"],
            "tipo_documento": ficha["tipo_documento"],
            "aportado": ficha["aportado"],
            "aportado_cargo_cubierto": aportado_cubierto,
            "autofinanciacion": auto,
            "cargo_cubierto": cubierto,
            "porcentaje_tope": round(aportado_cubierto / tope * 100, 2) if tope else None,
            "supera_umbral": supera_cubierto if tope else None,
            "candidatos": sorted(ficha["candidatos"].values(), key=lambda x: -x["valor"]),
            "aportes": sorted(ficha["aportes"], key=lambda x: -x["valor"]),
            "contratos": detalle,
            "valor_contratos": valor_contratos,
            "contratos_exceptuados": exceptuados,
            "valor_exceptuado": sum(f["valor"] for f in exceptuados),
            "retorno": round(valor_contratos / ficha["aportado"], 1) if ficha["aportado"] else None,
            "en_territorio": en_territorio,
            "nivel": nivel,
        })

    orden = {"posible_inhabilidad": 0, "revisar": 1, "cargo_no_cubierto": 2,
             "solo_exceptuados": 3, "autofinanciacion": 4}
    hallazgos.sort(key=lambda h: (orden[h["nivel"]], -h["valor_contratos"]))
    return hallazgos


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

def construir(municipio: str | None, departamento: str | None, *, desde: str,
              hasta: str, tope: float | None, token: str | None,
              limite: int | None) -> dict:
    ahora = dt.datetime.now().astimezone()
    objetivo = municipio or departamento or "todo el pais"

    print(f"[1/3] Cuentas Claras  ->  aportes en {objetivo}")
    ingresos = traer_financiadores(municipio, departamento, token)

    print(f"[2/3] SECOP II  ->  contratos entre {desde} y {hasta}")
    contratos = traer_contratos(municipio, departamento, desde, hasta, token, limite)

    print("[3/3] Cruzando financiadores con contratistas")
    financiadores = agrupar_aportes(ingresos)
    idx = indexar_contratos(contratos)
    hallazgos = cruzar(financiadores, idx, tope)

    con_inhab = [h for h in hallazgos if h["nivel"] == "posible_inhabilidad"]
    terceros = [h for h in hallazgos if not h["autofinanciacion"]]
    auto = [h for h in hallazgos if h["autofinanciacion"]]
    no_cubierto = [h for h in hallazgos if h["nivel"] == "cargo_no_cubierto"]
    total_aportado = sum(h["aportado"] for h in hallazgos)
    total_contratos = sum(h["valor_contratos"] for h in hallazgos)

    return {
        "meta": {
            "generado_en": ahora.isoformat(timespec="seconds"),
            "municipio": municipio or "",
            "departamento": departamento or "",
            "eleccion": FUENTES["ingresos"]["eleccion"],
            "ventana_contratos": {"desde": desde, "hasta": hasta},
            "tope_campana": tope,
            "umbral_pct": UMBRAL * 100,
            "umbral_valor": tope * UMBRAL if tope else None,
            "base_legal": LEY,
            "excepcion": ("La inhabilidad no aplica a contratos de prestacion de "
                          "servicios profesionales; esos contratos se listan aparte "
                          "y no cuentan para el total."),
            "cargos_cubiertos": ("El articulo 2 solo cubre Presidencia, gobernaciones, "
                                 "alcaldias y Congreso. Un aporte a un candidato al "
                                 "concejo, a la asamblea o a una JAL no genera esta "
                                 "inhabilidad, y se marca como 'cargo no cubierto'."),
            "autofinanciacion": ("Cuando el aportante es el propio candidato, no hay un "
                                 "tercero que financie a cambio de algo: se marca como "
                                 "'autofinanciacion' y se excluye de las alertas."),
            "limitaciones": [
                "No se detectan parientes del financiador: no hay fuente publica que los relacione.",
                "No se detectan sociedades donde el financiador sea socio controlante: SECOP no publica composicion accionaria.",
                "Coincidir por documento no prueba la inhabilidad; verifique cada caso antes de afirmarlo.",
                "La autofinanciacion y los cargos no cubiertos por el articulo se listan, pero no son alertas.",
            ] + ([] if tope else [
                "No se indico el tope de campana, asi que no se evalua el umbral del 2%: "
                "todas las coincidencias quedan como 'revisar'."
            ]),
            "fuentes": [
                {"nombre": FUENTES["ingresos"]["nombre"], "entidad": FUENTES["ingresos"]["entidad"],
                 "dataset": FUENTES["ingresos"]["dataset"], "url": FUENTES["ingresos"]["pagina"],
                 "registros": len(ingresos)},
                {"nombre": FUENTES["secop"]["nombre"], "entidad": FUENTES["secop"]["entidad"],
                 "dataset": FUENTES["secop"]["dataset"], "url": FUENTES["secop"]["pagina"],
                 "registros": len(contratos)},
            ],
        },
        "kpis": {
            "financiadores": len(financiadores),
            "contratos_analizados": len(contratos),
            "financiadores_con_contrato": len(hallazgos),
            "terceros_con_contrato": len(terceros),
            "autofinanciacion": len(auto),
            "cargo_no_cubierto": len(no_cubierto),
            "posible_inhabilidad": len(con_inhab),
            "total_aportado": total_aportado,
            "total_contratado": total_contratos,
            "retorno_global": round(total_contratos / total_aportado, 1) if total_aportado else None,
        },
        "hallazgos": hallazgos[:100],
    }


def main() -> int:
    f = FUENTES["ingresos"]
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--municipio", default="SOACHA")
    p.add_argument("--departamento", default=None,
                   help="alternativa o complemento al municipio (ej. CUNDINAMARCA)")
    p.add_argument("--desde", default=f["posesion"],
                   help=f"inicio de la ventana de contratos (posesion: {f['posesion']})")
    p.add_argument("--hasta", default=f["fin_periodo"],
                   help=f"fin del periodo del candidato ({f['fin_periodo']})")
    p.add_argument("--tope", type=float, default=None,
                   help="tope de campana en pesos, segun la resolucion del CNE "
                        "para esa eleccion y circunscripcion. El umbral es el 2%%.")
    p.add_argument("--salida", default="data/modulos/financiadores.json")
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--app-token", default=os.environ.get("SOCRATA_APP_TOKEN"))
    a = p.parse_args()

    try:
        datos = construir(a.municipio, a.departamento, desde=a.desde, hasta=a.hasta,
                          tope=a.tope, token=a.app_token, limite=a.limite)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("No se sobrescribio el archivo de salida.", file=sys.stderr)
        return 1

    destino = Path(a.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    k = datos["kpis"]
    print()
    print(f"  Escrito: {destino}")
    print(f"  Financiadores                {k['financiadores']:,}")
    print(f"  Contratos analizados         {k['contratos_analizados']:,}")
    print(f"  Financiadores con contrato   {k['financiadores_con_contrato']:,}")
    print(f"     de terceros               {k['terceros_con_contrato']:,}")
    print(f"     autofinanciacion          {k['autofinanciacion']:,}  (no aplica el art. 2)")
    print(f"     cargo no cubierto         {k['cargo_no_cubierto']:,}  (concejo, asamblea, JAL)")
    print(f"  Posible inhabilidad          {k['posible_inhabilidad']:,}")
    print(f"  Total aportado               ${k['total_aportado']:,.0f}")
    print(f"  Total contratado             ${k['total_contratado']:,.0f}")
    if k["retorno_global"]:
        print(f"  Retorno global               {k['retorno_global']}x")
    if not a.tope:
        print("\n  Sin --tope no se evalua el umbral del 2%: todo queda como 'revisar'.")
    print("\n  Aportar es legal. El hallazgo es el patron, y la inhabilidad del")
    print("  articulo 2 hay que verificarla caso por caso antes de afirmarla.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
