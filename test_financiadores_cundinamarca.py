#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica 32_financiadores_cundinamarca.py sin tocar la red.

Ejecutar:  python test_financiadores_cundinamarca.py
Sale con codigo 1 si algo falla, para poder usarlo en CI.
"""
import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
spec = importlib.util.spec_from_file_location("lote", RAIZ / "32_financiadores_cundinamarca.py")
lote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lote)
import etl_financiadores as etl  # noqa: E402

fallos = []
def check(nombre, ok, detalle=""):
    print(f"  {'OK  ' if ok else 'FALLA'}  {nombre}{'  ' + detalle if detalle else ''}")
    if not ok:
        fallos.append(nombre)

print("\n[1] Lista de municipios")
nombres = [n for n, _ in lote.MUNICIPIOS]
check("son 116", len(nombres) == 116, str(len(nombres)))
check("sin repetidos", len(set(map(lote.slug, nombres))) == len(nombres))
terr = json.loads((RAIZ / "data/cundinamarca/territorio/indice.json").read_text(encoding="utf-8"))
nuestros = {f"{lote.slug(n)}.json" for n in nombres}
ajenos = [m["archivo"] for m in terr["municipios"]
          if m["archivo"] not in nuestros and m["municipio"] != "No Definido"]
check("los archivos coinciden con los de Territorio", not ajenos, ", ".join(ajenos))

print("\n[2] Nombres sin tilde")
check("FACATATIVA == Facatativá", etl.norm_lugar("FACATATIVA") == etl.norm_lugar("Facatativá"))
check("EL PEÑON == El Peñón", etl.norm_lugar("EL PEÑON") == etl.norm_lugar("El Peñón"))
check("slug de Guayabal de Síquima", lote.slug("Guayabal de Síquima") == "guayabal_de_siquima")
check("slug de Nariño", lote.slug("Nariño") == "narino")

print("\n[3] Reparto de aportes por municipio")
fila = lambda mun, doc="79000111": {"mun_nombre": mun, "ing_identificacion": doc, "ing_valor": "1000"}
grupos, sueltos = lote.repartir([
    fila("FACATATIVA"), fila("Facatativá"), fila("VILLA DE SAN DIEGO DE UBATE"),
    fila("UBATE"), fila("UNE"), fila("FUQUENE"), fila(""), fila("BOGOTA D.C."),
])
check("Facatativá junta las dos grafias", len(grupos.get("facatativa", [])) == 2)
check("Ubaté reconoce su nombre largo", len(grupos.get("villa_de_san_diego_de_ubate", [])) == 2)
check("UNE no se confunde con FUQUENE",
      len(grupos.get("une", [])) == 1 and len(grupos.get("fuquene", [])) == 1)
check("los aportes sin municipio se reportan", sueltos.get("(sin municipio)") == 1)
check("los nombres ajenos se reportan", sueltos.get("BOGOTA D.C.") == 1)

print("\n[4] Grafias para SECOP")
n = lote.nombres_secop("Facatativá", (), {"FACATATIVA": {"Facatativá"}})
check("con y sin tilde", "FACATATIVÁ" in n and "FACATATIVA" in n, str(n))
check("comillas escapadas", lote._soql("D'Ely") == "D''Ely")

print("\n[5] El cruce marca 'mismo territorio' aunque cambien las tildes")
ingresos = [{
    "ing_identificacion": "860034594", "nombre_persona": "CONSTRUCTORA X SAS",
    "tpe_nombre": "Persona Juridica", "tid_nombre": "NIT", "ing_valor": "9000000",
    "nombre_candidato": "ALCALDE Y", "can_identificacion": "79111222",
    "cnd_nombre": "Alcaldía", "cla_nombre": "Municipal", "org_nombre": "P",
    "mun_nombre": "FACATATIVA", "dep_nombre": "CUNDINAMARCA", "tdo_nombre": "Aporte",
    "ing_fecha_comprobante": "2019-08-01T00:00:00.000", "ing_concepto": "aporte"}]
contratos = [{
    "documento_proveedor": "8600345941", "id_contrato": "C1", "nombre_entidad": "MUNICIPIO DE FACATATIVA",
    "ciudad": "Facatativá", "tipo_de_contrato": "Obra", "objeto_del_contrato": "Pavimentacion",
    "valor_del_contrato": "500000000", "fecha_de_firma": "2021-03-01T00:00:00.000"}]
d = etl.armar(ingresos, contratos, municipio="Facatativá", departamento="Cundinamarca",
              desde="2020-01-01", hasta="2023-12-31", tope=200_000_000)
h = d["hallazgos"][0]
check("contrato en el mismo territorio", h["contratos"][0]["mismo_territorio"] is True)
check("con tope, queda como posible inhabilidad", h["nivel"] == "posible_inhabilidad", h["nivel"])
check("el corte nombra el municipio", d["meta"]["municipio"] == "Facatativá")
check("resumen del indice", lote.resumen("Facatativá", "facatativa.json", d)["posible_inhabilidad"] == 1)

print("\n" + "=" * 60)
if fallos:
    print(f"{len(fallos)} verificaciones fallaron.")
    sys.exit(1)
print("Todas las verificaciones pasaron.")
