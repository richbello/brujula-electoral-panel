#!/usr/bin/env python3
"""
Territorio y obras de los municipios de Cundinamarca, desde 2020 y separado
por gobierno (2020-2023 y 2024-2027).

A diferencia de 28_territorio_cundinamarca.py, que reutiliza los contratos
ya descargados (solo desde 2024, un unico gobierno), este script consulta
SECOP II para cada municipio con la misma logica de etl_territorio.py que
usa Soacha. Asi todos los municipios quedan comparables con Soacha.

El municipio se busca por nombre exacto y departamento = Cundinamarca, para
no mezclar homonimos de otros departamentos (La Vega, Granada, Nariño...).

Si la consulta de un municipio falla, se conserva su archivo anterior y se
sigue con el siguiente; al final se informa cuales fallaron.

Salida:
    data/cundinamarca/territorio/<municipio>.json
    data/cundinamarca/territorio/indice.json

Uso:
    python 31_territorio_cundinamarca_gobiernos.py
    python 31_territorio_cundinamarca_gobiernos.py --solo "La Vega" "Facatativá"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import etl_territorio as etl  # noqa: E402

RAIZ = Path(__file__).resolve().parent
DESTINO = RAIZ / "data" / "cundinamarca" / "territorio"
INDICE = DESTINO / "indice.json"
DEPARTAMENTO = "Cundinamarca"
MINIMO = 20_000_000


def municipios_del_indice() -> list[dict]:
    d = json.loads(INDICE.read_text(encoding="utf-8"))
    # Soacha tiene su propio corte (etl_territorio.py) y "No Definido" no es un
    # municipio: es el valor que SECOP pone cuando la entidad no registro ciudad.
    return [m for m in d.get("municipios", [])
            if m.get("archivo") != "soacha.json" and m.get("municipio") != "No Definido"]


def resumen(m: dict, datos: dict) -> dict:
    k = datos["kpis"]
    return {"municipio": m["municipio"], "archivo": m["archivo"],
            "contratos": k["contratos"], "obras_vencidas": k["obras_vencidas"],
            "desde": datos["meta"]["ventana"]["desde"]}


def main() -> int:
    hoy = dt.date.today()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desde", default="2020-01-01")
    p.add_argument("--solo", nargs="*", default=None,
                   help="nombres de municipios a procesar (por defecto, todos los del indice)")
    p.add_argument("--app-token", default=os.environ.get("SOCRATA_APP_TOKEN"))
    a = p.parse_args()

    lista = municipios_del_indice()
    if a.solo:
        pedidos = {s.lower() for s in a.solo}
        lista = [m for m in lista if m["municipio"].lower() in pedidos]
    previo = {m["archivo"]: m for m in json.loads(INDICE.read_text(encoding="utf-8"))["municipios"]}

    fallos, nuevos = [], {}
    for i, m in enumerate(lista, 1):
        print(f"\n[{i}/{len(lista)}] {m['municipio']}")
        try:
            datos = etl.construir(m["municipio"], a.desde, hoy.isoformat(), token=a.app_token,
                                  minimo=MINIMO, limite=None, departamento=DEPARTAMENTO)
        except Exception as exc:  # noqa: BLE001
            print(f"   ERROR: {exc}  -> se conserva el archivo anterior")
            fallos.append(m["municipio"])
            time.sleep(5)
            continue
        if not datos["kpis"]["contratos"]:
            # Cero contratos casi siempre es un nombre que no coincide con SECOP:
            # mejor conservar el corte anterior que publicar un municipio vacio.
            print("   0 contratos: el nombre no coincide con SECOP -> se conserva el anterior")
            fallos.append(m["municipio"])
            continue
        # El indice de contratistas solo lo usa la Ficha (Soacha); fuera pesa sin uso.
        datos.pop("contratistas", None)
        datos["kpis"].pop("contratistas", None)
        (DESTINO / m["archivo"]).write_text(
            json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        nuevos[m["archivo"]] = resumen(m, datos)
        g = {x["clave"]: x["obras_vencidas"] for x in datos.get("por_gobierno", [])}
        print(f"   {datos['kpis']['contratos']:,} contratos · {datos['kpis']['obras_vencidas']:,} vencidas "
              f"(2020-2023: {g.get('2020-2023', 0)}, 2024-2027: {g.get('2024-2027', 0)})")

    indice = [nuevos.get(k, v) for k, v in previo.items()]
    indice.sort(key=lambda x: x["municipio"])
    INDICE.write_text(json.dumps({"municipios": indice}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{len(nuevos)} municipios actualizados desde {a.desde}.")
    if fallos:
        print(f"{len(fallos)} conservaron su corte anterior: {', '.join(fallos)}")
    return 0 if nuevos or not lista else 1


if __name__ == "__main__":
    raise SystemExit(main())
