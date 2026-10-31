#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Financiadores y contratos para los 116 municipios de Cundinamarca
=================================================================

Misma logica que etl_financiadores.py (el corte de Soacha), aplicada a cada
municipio del departamento:

  1. Baja UNA sola vez los aportes de Cuentas Claras 2019 de todo
     Cundinamarca (dataset jgra-rz2t) y los reparte por municipio.
  2. Para cada municipio con aportes, consulta SECOP II (jbjy-vk9h) con
     nombre exacto y departamento = Cundinamarca, para no mezclar homonimos
     de otros departamentos (Granada, La Vega, Nariño, Madrid...).
  3. Cruza con etl_financiadores.armar(), asi el archivo tiene exactamente
     el formato que la pagina ya sabe leer.

Cuentas Claras escribe "FACATATIVA" y SECOP "Facatativá": los nombres se
comparan sin tildes y con los alias conocidos (Villa de San Diego de Ubaté /
Ubaté, San Juan de Rioseco / Río Seco...).

Si un municipio falla, o SECOP no devuelve ningun contrato (casi siempre un
nombre que no coincide), se conserva su archivo anterior y se sigue con el
siguiente. Al final se informa cuales fallaron.

TOPES DE CAMPANA
----------------
El 2% de la inhabilidad se calcula sobre el tope que fijo el CNE para cada
municipio. No hay fuente abierta con esos topes, asi que se pueden pasar en
un CSV opcional con columnas  municipio,tope  (--topes). Los municipios sin
tope se cruzan igual, pero sus coincidencias quedan como 'revisar'.

Salida
------
    data/cundinamarca/financiadores/<municipio>.json
    data/cundinamarca/financiadores/indice.json

Soacha conserva su corte propio en data/modulos/financiadores.json (es el
que ven los clientes); este lote no lo toca salvo que se pida con --solo.

Uso
---
    python 32_financiadores_cundinamarca.py
    python 32_financiadores_cundinamarca.py --solo "Facatativá" "Chía"
    python 32_financiadores_cundinamarca.py --topes topes_2019.csv

Requiere: requests
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import etl_financiadores as etl  # noqa: E402
from etl_financiadores import norm_lugar  # noqa: E402

RAIZ = Path(__file__).resolve().parent
DESTINO = RAIZ / "data" / "cundinamarca" / "financiadores"
INDICE = DESTINO / "indice.json"
INDICE_TERRITORIO = RAIZ / "data" / "cundinamarca" / "territorio" / "indice.json"
DEPARTAMENTO = "Cundinamarca"

# Los 116 municipios de Cundinamarca (DANE). El segundo elemento son alias con
# que pueden aparecer en Cuentas Claras o en SECOP.
MUNICIPIOS: list[tuple[str, tuple[str, ...]]] = [
    ("Agua de Dios", ()), ("Albán", ()), ("Anapoima", ()), ("Anolaima", ()),
    ("Apulo", ("Rafael Reyes",)), ("Arbeláez", ()), ("Beltrán", ()), ("Bituima", ()),
    ("Bojacá", ()), ("Cabrera", ()), ("Cachipay", ()), ("Cajicá", ()),
    ("Caparrapí", ()), ("Cáqueza", ()), ("Carmen de Carupa", ()), ("Chaguaní", ()),
    ("Chía", ()), ("Chipaque", ()), ("Choachí", ()), ("Chocontá", ()),
    ("Cogua", ()), ("Cota", ()), ("Cucunubá", ()), ("El Colegio", ("Mesitas del Colegio",)),
    ("El Peñón", ()), ("El Rosal", ()), ("Facatativá", ()), ("Fómeque", ()),
    ("Fosca", ()), ("Funza", ()), ("Fúquene", ()), ("Fusagasugá", ()),
    ("Gachalá", ()), ("Gachancipá", ()), ("Gachetá", ()), ("Gama", ()),
    ("Girardot", ()), ("Granada", ()), ("Guachetá", ()), ("Guaduas", ()),
    ("Guasca", ()), ("Guataquí", ()), ("Guatavita", ()), ("Guayabal de Síquima", ()),
    ("Guayabetal", ()), ("Gutiérrez", ()), ("Jerusalén", ()), ("Junín", ()),
    ("La Calera", ()), ("La Mesa", ()), ("La Palma", ()), ("La Peña", ()),
    ("La Vega", ()), ("Lenguazaque", ()), ("Machetá", ()), ("Madrid", ()),
    ("Manta", ()), ("Medina", ()), ("Mosquera", ()), ("Nariño", ()),
    ("Nemocón", ()), ("Nilo", ()), ("Nimaima", ()), ("Nocaima", ()),
    ("Pacho", ()), ("Paime", ()), ("Pandi", ()), ("Paratebueno", ("Paratebueno (La Naguaya)",)),
    ("Pasca", ()), ("Puerto Salgar", ()), ("Pulí", ()), ("Quebradanegra", ("Quebrada Negra",)),
    ("Quetame", ()), ("Quipile", ()), ("Ricaurte", ()), ("San Antonio del Tequendama", ()),
    ("San Bernardo", ()), ("San Cayetano", ()), ("San Francisco", ()),
    ("San Juan de Rioseco", ("San Juan de Río Seco", "San Juan de Rio Seco")),
    ("Sasaima", ()), ("Sesquilé", ()), ("Sibaté", ()), ("Silvania", ()),
    ("Simijaca", ()), ("Soacha", ()), ("Sopó", ()), ("Subachoque", ()),
    ("Suesca", ()), ("Supatá", ()), ("Susa", ()), ("Sutatausa", ()),
    ("Tabio", ()), ("Tausa", ()), ("Tena", ()), ("Tenjo", ()),
    ("Tibacuy", ()), ("Tibirita", ()), ("Tocaima", ()), ("Tocancipá", ()),
    ("Topaipí", ()), ("Ubalá", ()), ("Ubaque", ()),
    ("Villa de San Diego de Ubaté", ("Ubaté", "Ubate", "Villa de San Diego de Ubate")),
    ("Une", ()), ("Útica", ()), ("Venecia", ("Ospina Pérez",)), ("Vergara", ()),
    ("Vianí", ()), ("Villagómez", ()), ("Villapinzón", ()), ("Villeta", ()),
    ("Viotá", ()), ("Yacopí", ()), ("Zipacón", ()), ("Zipaquirá", ()),
]


def slug(nombre: str) -> str:
    """'Guayabal de Síquima' -> 'guayabal_de_siquima' (igual que Territorio)."""
    return re.sub(r"[^a-z0-9]+", "_", norm_lugar(nombre).lower()).strip("_")


def claves_municipio(nombre: str, alias: tuple[str, ...]) -> set[str]:
    return {norm_lugar(n) for n in (nombre, *alias)}


def nombres_secop(nombre: str, alias: tuple[str, ...],
                  vistos_en_secop: dict[str, set[str]]) -> list[str]:
    """Todas las grafias con que el municipio puede estar en la columna ciudad.

    Se usan las que Territorio ya encontro en SECOP, mas el nombre oficial y
    los alias, con y sin tilde. La consulta compara en mayusculas.
    """
    claves = claves_municipio(nombre, alias)
    nombres = {nombre, *alias}
    for c in claves:
        nombres |= vistos_en_secop.get(c, set())
        nombres.add(c)  # sin tilde
    return sorted({n.upper() for n in nombres})


def _soql(t: str) -> str:
    return str(t).replace("'", "''")


# --------------------------------------------------------------------------
# Descarga
# --------------------------------------------------------------------------

def traer_aportes_departamento(token: str | None) -> list[dict]:
    return etl.consultar(etl.FUENTES["ingresos"]["dataset"],
                         where="upper(dep_nombre) like '%CUNDINAMARCA%'", token=token)


def traer_contratos_municipio(nombres: list[str], desde: str, hasta: str,
                              token: str | None) -> list[dict]:
    lista = ", ".join(f"'{_soql(n)}'" for n in nombres)
    where = (f"upper(ciudad) in ({lista}) AND upper(departamento) = 'CUNDINAMARCA' "
             f"AND fecha_de_firma >= '{desde}T00:00:00' "
             f"AND fecha_de_firma <= '{hasta}T23:59:59'")
    return etl.consultar(etl.FUENTES["secop"]["dataset"], where=where,
                         order="fecha_de_firma DESC", token=token)


# --------------------------------------------------------------------------
# Reparto de aportes por municipio
# --------------------------------------------------------------------------

def repartir(ingresos: list[dict]) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Devuelve {slug: filas} y {nombre_sin_reconocer: filas}.

    Los aportes sin municipio (gobernacion, asamblea) o con un nombre que no
    corresponde a ningun municipio quedan en el segundo diccionario, para
    reportarlos en vez de perderlos en silencio.
    """
    por_clave = {}
    for nombre, alias in MUNICIPIOS:
        for c in claves_municipio(nombre, alias):
            por_clave[c] = slug(nombre)

    grupos: dict[str, list[dict]] = defaultdict(list)
    sueltos: dict[str, int] = defaultdict(int)
    for f in ingresos:
        clave = norm_lugar(f.get("mun_nombre"))
        s = por_clave.get(clave)
        if s:
            grupos[s].append(f)
        else:
            sueltos[clave or "(sin municipio)"] += 1
    return dict(grupos), dict(sueltos)


def leer_topes(ruta: str | None) -> dict[str, float]:
    if not ruta:
        return {}
    topes = {}
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        for fila in csv.DictReader(fh):
            nombre = fila.get("municipio") or ""
            valor = re.sub(r"[^\d.]", "", str(fila.get("tope") or ""))
            if nombre and valor:
                topes[slug(nombre)] = float(valor)
    return topes


def grafias_territorio() -> dict[str, set[str]]:
    """Nombres tal como SECOP los escribe, tomados del indice de Territorio."""
    vistos: dict[str, set[str]] = defaultdict(set)
    try:
        d = json.loads(INDICE_TERRITORIO.read_text(encoding="utf-8"))
        for m in d.get("municipios", []):
            vistos[norm_lugar(m["municipio"])].add(m["municipio"])
    except (OSError, ValueError, KeyError):
        pass
    return vistos


def resumen(nombre: str, archivo: str, datos: dict) -> dict:
    k = datos["kpis"]
    return {
        "municipio": nombre, "archivo": archivo,
        "financiadores": k["financiadores"],
        "con_contrato": k["financiadores_con_contrato"],
        "terceros": k["terceros_con_contrato"],
        "posible_inhabilidad": k["posible_inhabilidad"],
        "contratos": k["contratos_analizados"],
        "tope": datos["meta"]["tope_campana"],
        "generado": datos["meta"]["generado_en"][:10],
    }


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

def main() -> int:
    f = etl.FUENTES["ingresos"]
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desde", default=f["posesion"])
    p.add_argument("--hasta", default=f["fin_periodo"])
    p.add_argument("--solo", nargs="*", default=None,
                   help="municipios a procesar (por defecto, todos menos Soacha)")
    p.add_argument("--topes", default=None, help="CSV opcional con columnas municipio,tope")
    p.add_argument("--app-token", default=os.environ.get("SOCRATA_APP_TOKEN"))
    a = p.parse_args()

    if a.solo:
        pedidos = {slug(s) for s in a.solo}
        lista = [(n, al) for n, al in MUNICIPIOS if slug(n) in pedidos]
        desconocidos = pedidos - {slug(n) for n, _ in lista}
        if desconocidos:
            print(f"No son municipios de Cundinamarca: {', '.join(sorted(desconocidos))}")
    else:
        lista = [(n, al) for n, al in MUNICIPIOS if n != "Soacha"]

    topes = leer_topes(a.topes)
    vistos = grafias_territorio()
    DESTINO.mkdir(parents=True, exist_ok=True)
    previo = {}
    if INDICE.exists():
        previo = {m["archivo"]: m for m in json.loads(INDICE.read_text(encoding="utf-8"))["municipios"]}

    print(f"[1/2] Cuentas Claras 2019  ->  aportes de todo {DEPARTAMENTO}")
    try:
        ingresos = traer_aportes_departamento(a.app_token)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR al bajar Cuentas Claras: {exc}\nNo se toco ningun archivo.", file=sys.stderr)
        return 1
    grupos, sueltos = repartir(ingresos)
    print(f"    {len(grupos)} municipios con aportes; "
          f"{sum(sueltos.values()):,} filas sin municipio reconocido")

    print(f"\n[2/2] SECOP II por municipio  ->  contratos entre {a.desde} y {a.hasta}")
    fallos, nuevos = [], {}
    for i, (nombre, alias) in enumerate(lista, 1):
        s = slug(nombre)
        archivo = f"{s}.json"
        print(f"\n[{i}/{len(lista)}] {nombre}")
        filas = grupos.get(s, [])
        if not filas:
            print("   sin aportes en Cuentas Claras -> se conserva el anterior")
            fallos.append(nombre)
            continue
        try:
            contratos = traer_contratos_municipio(nombres_secop(nombre, alias, vistos),
                                                  a.desde, a.hasta, a.app_token)
        except Exception as exc:  # noqa: BLE001
            print(f"   ERROR: {exc}  -> se conserva el archivo anterior")
            fallos.append(nombre)
            time.sleep(5)
            continue
        if not contratos:
            print("   0 contratos: el nombre no coincide con SECOP -> se conserva el anterior")
            fallos.append(nombre)
            continue

        datos = etl.armar(filas, contratos, municipio=nombre, departamento=DEPARTAMENTO,
                          desde=a.desde, hasta=a.hasta, tope=topes.get(s))
        (DESTINO / archivo).write_text(
            json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        nuevos[archivo] = resumen(nombre, archivo, datos)
        k = datos["kpis"]
        print(f"   {k['financiadores']:,} financiadores · {k['contratos_analizados']:,} contratos · "
              f"{k['financiadores_con_contrato']:,} con contrato · "
              f"{k['posible_inhabilidad']:,} posible inhabilidad")

    previo.update(nuevos)
    indice = sorted(previo.values(), key=lambda x: norm_lugar(x["municipio"]))
    INDICE.write_text(json.dumps({
        "departamento": DEPARTAMENTO,
        "eleccion": f["eleccion"],
        "ventana_contratos": {"desde": a.desde, "hasta": a.hasta},
        "actualizado": dt.date.today().isoformat(),
        "aportes_sin_municipio": dict(sorted(sueltos.items(), key=lambda x: -x[1])[:30]),
        "municipios": indice,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{len(nuevos)} municipios actualizados; el indice tiene {len(indice)}.")
    if fallos:
        print(f"{len(fallos)} conservaron su corte anterior: {', '.join(fallos)}")
    return 0 if nuevos or not lista else 1


if __name__ == "__main__":
    raise SystemExit(main())
