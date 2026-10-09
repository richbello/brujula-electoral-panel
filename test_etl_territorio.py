#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica la logica de etl_territorio.py contra fixtures, sin tocar la red.

Los objetos contractuales de las pruebas son textos reales de SECOP para
Soacha, para que la extraccion se mida contra lo que de verdad llega.

Ejecutar:  python test_etl_territorio.py
"""
import sys, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import etl_territorio as etl

fallos = []
def check(nombre, ok, detalle=""):
    print(f"  {'OK  ' if ok else 'FALLA'}  {nombre}{'  ' + detalle if detalle else ''}")
    if not ok:
        fallos.append(nombre)

def nombres(objeto):
    return {(l["tipo"], l["nombre"]) for l in etl.extraer_lugares(objeto)}

# ------------------------------------------------ extraccion de lugares
print("\n[1] Comunas (objetos reales de Soacha)")
c1 = nombres("CONSTRUCCION DE VIAS PRINCIPALES DE CONEXIÓN EN LA COMUNA 1")
check("'COMUNA 1' -> Comuna 1", ("Comuna", "Comuna 1") in c1, str(c1))
c2 = nombres("MEJORAMIENTO DE LAS VIAS CALLE 22 DE LA COMUNA 6 Y CALLE 30 DE LA COMUNA 5")
check("dos comunas en un mismo objeto",
      ("Comuna", "Comuna 6") in c2 and ("Comuna", "Comuna 5") in c2, str(c2))
c3 = nombres("DEL COMANDO ESTACIÓN DE POLICÍA DE LA COMUNA 2 Y LA SALA INTEGRADA")
check("comuna dentro de un objeto largo", ("Comuna", "Comuna 2") in c3)
c4 = nombres("DOTACION PARA LAS COMUNAS 1, 2 Y 3 DEL MUNICIPIO")
check("lista 'COMUNAS 1, 2 Y 3'",
      all(("Comuna", f"Comuna {n}") in c4 for n in (1, 2, 3)), str(c4))

print("\n[2] Sectores, colegios, parques y vias")
s1 = nombres("GERENCIA INTEGRAL PARA EL MEJORAMIENTO Y PAVIMENTACIÓN DE VÍAS URBANAS "
             "EN LOS SECTORES DANUBIO; VILLALUZ; PRADO VEGAS")
check("separa sectores por punto y coma", len([x for x in s1 if x[0] == "Sector"]) >= 2, str(s1))
e1 = nombres("DOTACION DE LA Institución Educativa Oficial Vida Nueva")
check("institucion educativa", any(t == "Institución educativa" for t, _ in e1), str(e1))
p1 = nombres("CONSTRUCCIÓN DE PARQUE DE LOS LOCOS")
check("parque con nombre propio", any(t == "Parque" for t, _ in p1), str(p1))
v1 = nombres("CONSTRUCCIÓN DE LA AVENIDA LAS TORRES ENTRE LA CALLE 46B Y LA GLORIETA TERREROS")
check("avenida con nombre propio", any(t == "Vía" for t, _ in v1), str(v1))

print("\n[3] Objetos que NO nombran lugar")
for obj in ["PRESTACIÓN DE SERVICIOS PROFESIONALES COMO ASESOR EN CONTRATACIÓN PÚBLICA",
            "MANTENIMIENTOS Y ADECUACIÓN DE PARQUES DEL MUNICIPIO DE SOACHA CUNDINAMARCA",
            "SELECCIONAR UN SOCIO ESTRATÉGICO PARA LA CONSTITUCIÓN DE UNA SOCIEDAD",
            "GERENCIA INTEGRAL DE FONDOS PARA EL FORTALECIMIENTO SOCIAL"]:
    lg = etl.extraer_lugares(obj)
    check(f"'{obj[:46]}…'", len(lg) == 0, f"extrajo {[l['nombre'] for l in lg]}")

# ------------------------------------------------ obras vencidas
print("\n[4] Obras vencidas")
HOY = dt.date(2026, 10, 9)
base = {"nombre_entidad": "MUNICIPIO DE SOACHA.", "proveedor_adjudicado": "CONSTRUCTORA X",
        "documento_proveedor": "860034594", "tipo_de_contrato": "Obra",
        "objeto_del_contrato": "CONSTRUCCION DE VIAS EN LA COMUNA 4",
        "fecha_de_inicio_del_contrato": "2022-01-10T00:00:00.000"}
contratos = [
    # vencida hace mas de un ano y sigue en ejecucion -> entra
    dict(base, referencia_del_contrato="A", valor_del_contrato="900000000",
         valor_pagado="400000000", fecha_de_fin_del_contrato="2024-06-30T00:00:00.000",
         estado_contrato="En ejecucion", fecha_de_firma="2022-01-05T00:00:00.000"),
    # vencida pero ya terminada -> no entra
    dict(base, referencia_del_contrato="B", valor_del_contrato="500000000",
         valor_pagado="500000000", fecha_de_fin_del_contrato="2024-01-15T00:00:00.000",
         estado_contrato="Terminado", fecha_de_firma="2022-02-05T00:00:00.000"),
    # en ejecucion pero aun no vence -> no entra
    dict(base, referencia_del_contrato="C", valor_del_contrato="700000000",
         valor_pagado="100000000", fecha_de_fin_del_contrato="2027-12-31T00:00:00.000",
         estado_contrato="En ejecucion", fecha_de_firma="2025-02-05T00:00:00.000"),
    # vencida y abierta pero pequena -> no entra por el minimo
    dict(base, referencia_del_contrato="D", valor_del_contrato="5000000",
         valor_pagado="0", fecha_de_fin_del_contrato="2023-03-01T00:00:00.000",
         estado_contrato="En ejecucion", fecha_de_firma="2022-03-05T00:00:00.000"),
    # vencida y liquidada -> no entra
    dict(base, referencia_del_contrato="E", valor_del_contrato="800000000",
         valor_pagado="800000000", fecha_de_fin_del_contrato="2023-08-01T00:00:00.000",
         estado_contrato="Liquidado", fecha_de_firma="2022-04-05T00:00:00.000"),
]
v = etl.obras_vencidas(contratos, HOY, minimo=20_000_000)
check("solo entra la vencida que sigue abierta y supera el minimo",
      len(v) == 1 and v[0]["referencia"] == "A", f"entraron {[x['referencia'] for x in v]}")
if v:
    check("calcula los dias de atraso", v[0]["dias_vencido"] == (HOY - dt.date(2024, 6, 30)).days,
          str(v[0]["dias_vencido"]))
    check("calcula el saldo pendiente", v[0]["pendiente"] == 500000000.0, str(v[0]["pendiente"]))
    check("trae el lugar del objeto",
          any(l["nombre"] == "Comuna 4" for l in v[0]["lugares"]))

# ------------------------------------------------ reparto y cobertura
print("\n[5] Reparto del valor y cobertura")
reparto = [
    {"objeto_del_contrato": "OBRAS EN LA COMUNA 1 Y LA COMUNA 2",
     "valor_del_contrato": "100000000", "referencia_del_contrato": "R1",
     "nombre_entidad": "MUNICIPIO DE SOACHA.", "fecha_de_firma": "2023-01-01T00:00:00.000"},
    {"objeto_del_contrato": "PRESTACION DE SERVICIOS DE APOYO",
     "valor_del_contrato": "300000000", "referencia_del_contrato": "R2",
     "nombre_entidad": "MUNICIPIO DE SOACHA.", "fecha_de_firma": "2023-02-01T00:00:00.000"},
]
sec, cob = etl.por_sector(reparto)
total_sec = sum(s["valor"] for s in sec)
check("reparte el valor entre los dos lugares, sin duplicar",
      abs(total_sec - 100000000.0) < 1, f"suma por sector = {total_sec:,.0f}")
check("cada comuna recibe la mitad",
      all(abs(s["valor"] - 50000000.0) < 1 for s in sec), str([s['valor'] for s in sec]))
check("cuenta 1 contrato con lugar y 1 sin lugar",
      cob["contratos_con_lugar"] == 1 and cob["contratos_sin_lugar"] == 1)
check("la cobertura en valor es 25%", cob["pct_valor"] == 25.0, f"{cob['pct_valor']}%")
check("la cobertura en contratos es 50%", cob["pct_contratos"] == 50.0, f"{cob['pct_contratos']}%")
check("la suma por sector nunca supera el total contratado",
      total_sec <= sum(etl.a_numero(c["valor_del_contrato"]) for c in reparto))

# ------------------------------------------------ JSON
print("\n[6] Estructura del JSON")
etl.consultar = lambda *a, **k: contratos + reparto
d = etl.construir("Soacha", "2020-01-01", "2026-10-09", token=None,
                  minimo=20_000_000, limite=None, hoy=HOY)
for clave in ["meta", "kpis", "obras_vencidas", "sectores"]:
    check(f"contiene '{clave}'", clave in d)
check("advierte que NO es un mapa de inversion",
      "NO es un mapa" in d["meta"]["advertencia_mapa"])
check("publica la cobertura en meta y en kpis",
      "cobertura" in d["meta"] and "cobertura_valor" in d["kpis"])
check("la advertencia de cobertura trae el porcentaje",
      str(d["meta"]["cobertura"]["pct_valor"]) in d["meta"]["advertencia_cobertura"])
check("explica el reparto entre lugares", "partes iguales" in d["meta"]["reparto"])
check("es serializable", bool(json.dumps(d, ensure_ascii=False)))


# ------------------------------------------ calidad de los nombres
print("\n[7] El nombre se corta donde debe (casos vistos en el corte real)")
casos = [
 ("CONSTRUCCIÓN DE PARQUE DE LOS LOCOS DEL MUNICIPIO DE SOACHA", "Parque", "Locos"),
 ("ADECUACION DE LA PLAZOLETA DE LOS SUEÑOS EN LA CIUDAD DE SOACHA", "Plazoleta", "Sueños"),
 ("CONSTRUCCIÓN DE LA AVENIDA LAS TORRES ENTRE LA CALLE 46B", "Vía", "Avenida Torres"),
]
for objeto, tipo, esperado in casos:
    got = {l["nombre"] for l in etl.extraer_lugares(objeto) if l["tipo"] == tipo}
    check(f"{tipo} -> '{esperado}'", esperado in got, str(got))

print("\n[8] Se descarta lo que no es un lugar")
for objeto, razon in [
  ("ACTUALIZACIÓN Y DOTACIÓN DE COLEGIO OFICIAL", "'Colegio Oficial' no nombra ningun colegio"),
  ("MANTENIMIENTO DE INSTITUCIONES EDUCATIVAS DE LA CIUDAD DE SOACHA", "'Ciudad de Soacha' no es un colegio"),
  ("MEJORAMIENTO DE VIAS URBANAS DEL MUNICIPIO", "'del municipio' no es un sector"),
  ("ADECUACION DE PARQUES DEL MUNICIPIO DE SOACHA", "parques sin nombre propio"),
]:
    lg = etl.extraer_lugares(objeto)
    check(razon, len(lg) == 0, f"extrajo {[l['nombre'] for l in lg]}")

print("\n[9] Lo valido sigue pasando tras el filtro")
for objeto, esperado in [
  ("DOTACION DE LA Institución Educativa Oficial Vida Nueva", "Vida Nueva"),
  ("OBRAS EN EL BARRIO LEON XIII", "Leon Xiii"),
  ("PAVIMENTACION EN LOS SECTORES DANUBIO; VILLALUZ", "Danubio"),
]:
    got = {l["nombre"] for l in etl.extraer_lugares(objeto)}
    check(f"'{esperado}' se conserva", esperado in got, str(got))

print("\n[10] Adjetivos de seleccion no son lugares")
for objeto, malo in [
  ("DOTACION DE INSTITUCIONES EDUCATIVAS FOCALIZADAS", "Focalizadas"),
  ("OBRAS EN LOS BARRIOS ELEGIDOS POR LA COMUNIDAD", "Elegidos"),
  ("MANTENIMIENTO EN EL SECTOR SUSCRITO", "Suscrito"),
  ("INTERVENCION EN LOS SECTORES PRIORIZADOS", "Priorizados"),
]:
    got = {l["nombre"] for l in etl.extraer_lugares(objeto)}
    check(f"descarta '{malo}'", malo not in got, str(got))
check("pero 'Danubio' y 'Prado Vegas' sobreviven",
      {"Danubio","Prado Vegas"} <= {l["nombre"] for l in
        etl.extraer_lugares("PAVIMENTACION EN LOS SECTORES DANUBIO; PRADO VEGAS")})

print("\n[11] Indice de contratistas para la ficha")
idx = etl.indice_contratistas(contratos, HOY)
check("agrupa los 5 contratos del fixture en 1 contratista", len(idx) == 1, str(len(idx)))
if idx:
    f = idx[0]
    check("suma todos los contratos, no solo los vencidos", f["contratos"] == 5, str(f["contratos"]))
    check("suma el valor total", f["valor"] == 2905000000.0, str(f["valor"]))
    # El indice cuenta 2 vencidos y la lista visible muestra 1: el contrato
    # pequeno queda fuera de la lista por el umbral de presentacion, pero
    # sigue estando vencido. El indice no debe heredar ese umbral.
    check("cuenta los vencidos sin aplicar el umbral de presentacion",
          f["vencidos"] == 2, str(f["vencidos"]))
    check("acumula el saldo vencido sin pagar", f["pendiente_vencido"] == 505000000.0,
          str(f["pendiente_vencido"]))
    check("la lista visible si aplica el umbral y muestra solo 1",
          len(etl.obras_vencidas(contratos, HOY, minimo=20_000_000)) == 1)
    check("registra primera y ultima firma", f["primero"] == "2022-01-05" and f["ultimo"] == "2025-02-05",
          f'{f["primero"]} .. {f["ultimo"]}')
    check("guarda los contratos mayores", len(f["mayores"]) == 5 and f["mayores"][0]["valor"] == 900000000.0)
    check("cuenta las entidades", f["entidades"] == 1, str(f["entidades"]))
check("un contrato sin documento no entra",
      etl.indice_contratistas([{"documento_proveedor": "", "valor_del_contrato": "1"}], HOY) == [])
check("el JSON publica el indice", "contratistas" in d and isinstance(d["contratistas"], list))

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("   -", f)
    sys.exit(1)
print("Todas las verificaciones pasaron.")
