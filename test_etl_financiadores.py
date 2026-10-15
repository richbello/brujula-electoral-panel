#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica la logica de etl_financiadores.py contra fixtures, sin tocar la red.

Ejecutar:  python test_etl_financiadores.py
Sale con codigo 1 si algo falla, para poder usarlo en CI.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import etl_financiadores as etl

fallos = []
def check(nombre, ok, detalle=""):
    print(f"  {'OK  ' if ok else 'FALLA'}  {nombre}{'  ' + detalle if detalle else ''}")
    if not ok:
        fallos.append(nombre)

TOPE = 200_000_000          # umbral del 2% = 4.000.000

# ---------------------------------------------------- excepcion legal
print("\n[1] Excepcion del art. 2: prestacion de servicios profesionales")
casos = [
    ({"tipo_de_contrato": "Prestación de servicios", "objeto_del_contrato": "Servicios profesionales de apoyo juridico"}, True),
    ({"tipo_de_contrato": "Prestación de servicios profesionales", "objeto_del_contrato": "Asesoria"}, True),
    ({"tipo_de_contrato": "Prestacion de servicios", "objeto_del_contrato": "Apoyo a la gestion administrativa"}, True),
    ({"tipo_de_contrato": "Obra", "objeto_del_contrato": "Mantenimiento de la malla vial"}, False),
    ({"tipo_de_contrato": "Suministro", "objeto_del_contrato": "Suministro de papeleria"}, False),
    ({"tipo_de_contrato": "Consultoría", "objeto_del_contrato": "Interventoria tecnica"}, False),
]
for c, esperado in casos:
    obt = etl.es_servicios_profesionales(c)
    check(f"{c['tipo_de_contrato'][:28]:30} -> {'exceptuado' if esperado else 'cuenta'}", obt == esperado)

# ---------------------------------------------------- agrupacion de aportes
print("\n[2] Agrupacion de aportes")
ingresos = [
    # aporta dos veces al mismo candidato
    {"ing_identificacion": "860034594", "nombre_persona": "CONSTRUCTORA ANDINA S A S",
     "tpe_nombre": "Persona Juridica", "tid_nombre": "NIT", "ing_valor": "3000000",
     "nombre_candidato": "PEDRO ALCALDE", "can_identificacion": "79111222",
     "cnd_nombre": "Alcaldía", "cla_nombre": "Municipal", "org_nombre": "PARTIDO X",
     "mun_nombre": "SOACHA", "dep_nombre": "CUNDINAMARCA", "tdo_nombre": "Aporte",
     "ing_fecha_comprobante": "2019-08-01T00:00:00.000", "ing_concepto": "aporte"},
    {"ing_identificacion": "8600345941", "nombre_persona": "CONSTRUCTORA ANDINA S.A.S.",
     "tpe_nombre": "Persona Juridica", "tid_nombre": "NIT", "ing_valor": "2500000",
     "nombre_candidato": "PEDRO ALCALDE", "can_identificacion": "79111222",
     "cnd_nombre": "Alcaldía", "cla_nombre": "Municipal", "org_nombre": "PARTIDO X",
     "mun_nombre": "SOACHA", "dep_nombre": "CUNDINAMARCA", "tdo_nombre": "Aporte",
     "ing_fecha_comprobante": "2019-09-15T00:00:00.000", "ing_concepto": "aporte"},
    # aportante pequeno
    {"ing_identificacion": "52998877", "nombre_persona": "ANA TORRES",
     "tpe_nombre": "Persona Natural", "tid_nombre": "Cédula de Ciudadanía", "ing_valor": "1000000",
     "nombre_candidato": "PEDRO ALCALDE", "can_identificacion": "79111222",
     "cnd_nombre": "Alcaldía", "cla_nombre": "Municipal", "org_nombre": "PARTIDO X",
     "mun_nombre": "SOACHA", "dep_nombre": "CUNDINAMARCA", "tdo_nombre": "Aporte",
     "ing_fecha_comprobante": "2019-08-20T00:00:00.000", "ing_concepto": "aporte"},
    # aportante que nunca contrata
    {"ing_identificacion": "79000111", "nombre_persona": "JUAN SIN CONTRATOS",
     "tpe_nombre": "Persona Natural", "tid_nombre": "Cédula de Ciudadanía", "ing_valor": "9000000",
     "nombre_candidato": "PEDRO ALCALDE", "can_identificacion": "79111222",
     "cnd_nombre": "Alcaldía", "cla_nombre": "Municipal", "org_nombre": "PARTIDO X",
     "mun_nombre": "SOACHA", "dep_nombre": "CUNDINAMARCA", "tdo_nombre": "Aporte",
     "ing_fecha_comprobante": "2019-07-01T00:00:00.000", "ing_concepto": "aporte"},
]
fin = etl.agrupar_aportes(ingresos)
check("4 aportes -> 3 financiadores distintos", len(fin) == 3, f"obtuvo {len(fin)}")
andina = fin.get("860034594")
check("une los dos aportes del mismo NIT pese al digito de verificacion",
      andina is not None and andina["aportado"] == 5500000.0,
      str(andina["aportado"]) if andina else "no encontrado")
check("agrupa por candidato financiado",
      andina and len(andina["candidatos"]) == 1 and andina["candidatos"]["PEDRO ALCALDE"]["valor"] == 5500000.0)

# ---------------------------------------------------- cruce con contratos
print("\n[3] Cruce contra SECOP y clasificacion")
contratos = [
    # obra en el mismo municipio -> cuenta
    {"documento_proveedor": "8600345941", "proveedor_adjudicado": "CONSTRUCTORA ANDINA S A S",
     "nombre_entidad": "MUNICIPIO DE SOACHA.", "ciudad": "SOACHA", "tipo_de_contrato": "Obra",
     "objeto_del_contrato": "Mantenimiento de la malla vial", "valor_del_contrato": "1200000000",
     "fecha_de_firma": "2021-03-10T00:00:00.000", "estado_contrato": "Terminado",
     "referencia_del_contrato": "100-2021", "id_contrato": "CO1.A"},
    # servicios profesionales -> exceptuado por el art. 2
    {"documento_proveedor": "860034594", "proveedor_adjudicado": "CONSTRUCTORA ANDINA S A S",
     "nombre_entidad": "MUNICIPIO DE SOACHA.", "ciudad": "SOACHA",
     "tipo_de_contrato": "Prestación de servicios",
     "objeto_del_contrato": "Servicios profesionales de asesoria", "valor_del_contrato": "80000000",
     "fecha_de_firma": "2021-05-01T00:00:00.000", "estado_contrato": "Terminado",
     "referencia_del_contrato": "101-2021", "id_contrato": "CO1.B"},
    # aportante pequeno con contrato -> no supera el umbral
    {"documento_proveedor": "52998877", "proveedor_adjudicado": "ANA TORRES",
     "nombre_entidad": "MUNICIPIO DE SOACHA.", "ciudad": "SOACHA", "tipo_de_contrato": "Suministro",
     "objeto_del_contrato": "Suministro de papeleria", "valor_del_contrato": "40000000",
     "fecha_de_firma": "2022-02-02T00:00:00.000", "estado_contrato": "Terminado",
     "referencia_del_contrato": "102-2022", "id_contrato": "CO1.C"},
    # el mismo contrato repetido: no debe contarse dos veces
    {"documento_proveedor": "860034594", "proveedor_adjudicado": "CONSTRUCTORA ANDINA S A S",
     "nombre_entidad": "MUNICIPIO DE SOACHA.", "ciudad": "SOACHA", "tipo_de_contrato": "Obra",
     "objeto_del_contrato": "Mantenimiento de la malla vial", "valor_del_contrato": "1200000000",
     "fecha_de_firma": "2021-03-10T00:00:00.000", "estado_contrato": "Terminado",
     "referencia_del_contrato": "100-2021", "id_contrato": "CO1.A"},
]
idx = etl.indexar_contratos(contratos)
h = etl.cruzar(fin, idx, TOPE)
check("solo los financiadores con contrato aparecen", len(h) == 2, f"obtuvo {len(h)}")
check("el aportante sin contratos no aparece",
      not any(x["documento"] == "79000111" for x in h))

ha = next((x for x in h if x["documento"] == "860034594"), None)
check("cruza pese al digito de verificacion", ha is not None)
if ha:
    check("no cuenta dos veces el mismo contrato", len(ha["contratos"]) == 1,
          f"contratos={len(ha['contratos'])}")
    check("separa el de servicios profesionales", len(ha["contratos_exceptuados"]) == 1)
    check("el exceptuado no suma al total contratado", ha["valor_contratos"] == 1200000000.0,
          str(ha["valor_contratos"]))
    check("aporto 2,75% del tope (supera el 2%)", ha["porcentaje_tope"] == 2.75,
          str(ha["porcentaje_tope"]))
    check("marca posible inhabilidad", ha["nivel"] == "posible_inhabilidad", ha["nivel"])
    check("calcula el retorno aporte -> contratos", ha["retorno"] == 218.2, str(ha["retorno"]))

hb = next((x for x in h if x["documento"] == "52998877"), None)
if hb:
    check("aporte de 0,5% del tope no supera el umbral", hb["supera_umbral"] is False,
          f"{hb['porcentaje_tope']}%")
    check("sin superar el umbral queda en 'revisar'", hb["nivel"] == "revisar", hb["nivel"])

# ---------------------------------------------------- sin tope
print("\n[4] Sin tope de campana no se afirma el umbral")
h2 = etl.cruzar(fin, idx, None)
check("nadie queda marcado como posible inhabilidad",
      not any(x["nivel"] == "posible_inhabilidad" for x in h2))
check("supera_umbral queda indefinido", all(x["supera_umbral"] is None for x in h2))
check("porcentaje_tope queda indefinido", all(x["porcentaje_tope"] is None for x in h2))

# ---------------------------------------------------- territorio
print("\n[5] Nivel administrativo")
otro = [dict(contratos[0], ciudad="MEDELLIN", nombre_entidad="MUNICIPIO DE MEDELLIN",
             id_contrato="CO1.Z", referencia_del_contrato="900-2021")]
h3 = etl.cruzar(etl.agrupar_aportes(ingresos[:2]), etl.indexar_contratos(otro), TOPE)
check("contrato en otro municipio no marca inhabilidad",
      h3 and h3[0]["nivel"] == "revisar", h3[0]["nivel"] if h3 else "sin hallazgos")
check("y queda senalado como fuera del territorio",
      h3 and h3[0]["en_territorio"] is False)

# ---------------------------------------------------- estructura del JSON
print("\n[6] Estructura del JSON")
etl.traer_financiadores = lambda *a, **k: ingresos
etl.traer_contratos = lambda *a, **k: contratos
d = etl.construir("SOACHA", None, desde="2020-01-01", hasta="2023-12-31",
                  tope=TOPE, token=None, limite=None)
for clave in ["meta", "kpis", "hallazgos"]:
    check(f"contiene '{clave}'", clave in d)
check("cita la base legal", "1474" in d["meta"]["base_legal"])
check("declara la excepcion de servicios profesionales",
      "servicios profesionales" in d["meta"]["excepcion"])
check("declara que no ve parientes ni sociedades",
      any("pariente" in l for l in d["meta"]["limitaciones"])
      and any("socio controlante" in l for l in d["meta"]["limitaciones"]))
check("guarda el tope y el umbral usados",
      d["meta"]["tope_campana"] == TOPE and d["meta"]["umbral_valor"] == 4000000.0)
check("cuenta 1 posible inhabilidad", d["kpis"]["posible_inhabilidad"] == 1,
      str(d["kpis"]["posible_inhabilidad"]))
check("es serializable", bool(json.dumps(d, ensure_ascii=False)))

d2 = etl.construir("SOACHA", None, desde="2020-01-01", hasta="2023-12-31",
                   tope=None, token=None, limite=None)
check("sin tope lo advierte en las limitaciones",
      any("no se evalua el umbral" in l for l in d2["meta"]["limitaciones"]))


# ------------------------------------- cargos que cubre el articulo
print("\n[7] El articulo 2 solo cubre ciertos cargos")
for cargo, esperado in [("Alcaldía",True),("Gobernación",True),("Presidencia",True),
                        ("Senado",True),("Cámara",True),
                        ("Concejo",False),("Asamblea",False),("Junta Administradora Local",False),
                        ("Edil",False)]:
    check(f"{cargo:28} -> {'cubierto' if esperado else 'NO cubierto'}",
          etl.cargo_cubierto(cargo) == esperado)

print("\n[8] Aporte a un concejal no genera la inhabilidad")
conc = [dict(ingresos[0], cnd_nombre="Concejo", ing_identificacion="901555444",
             nombre_persona="DONANTE DE CONCEJAL", ing_valor="50000000",
             nombre_candidato="UN CONCEJAL", can_identificacion="79999888")]
cc = [dict(contratos[0], documento_proveedor="901555444",
           proveedor_adjudicado="DONANTE DE CONCEJAL", id_contrato="CO1.X",
           referencia_del_contrato="500-2021")]
hc = etl.cruzar(etl.agrupar_aportes(conc), etl.indexar_contratos(cc), TOPE)
check("aporto 25% del tope pero al concejo", bool(hc))
if hc:
    check("queda como 'cargo no cubierto', no como inhabilidad",
          hc[0]["nivel"] == "cargo_no_cubierto", hc[0]["nivel"])
    check("no cuenta como aporte a cargo cubierto",
          hc[0]["aportado_cargo_cubierto"] == 0.0, str(hc[0]["aportado_cargo_cubierto"]))

print("\n[9] Autofinanciacion: el aportante es el candidato")
auto = [dict(ingresos[0], ing_identificacion="79777666", nombre_persona="CANDIDATO QUE SE FINANCIA",
             can_identificacion="79777666", nombre_candidato="CANDIDATO QUE SE FINANCIA",
             ing_valor="90000000", cnd_nombre="Alcaldía")]
ca = [dict(contratos[0], documento_proveedor="79777666",
           proveedor_adjudicado="CANDIDATO QUE SE FINANCIA", id_contrato="CO1.Y",
           referencia_del_contrato="600-2022")]
ha = etl.cruzar(etl.agrupar_aportes(auto), etl.indexar_contratos(ca), TOPE)
check("lo detecta", bool(ha) and ha[0]["autofinanciacion"] is True)
if ha:
    check("no lo marca como posible inhabilidad",
          ha[0]["nivel"] == "autofinanciacion", ha[0]["nivel"])
check("un tercero con los mismos montos si quedaria marcado",
      (lambda r: bool(r) and r[0]["nivel"] == "posible_inhabilidad")(
        etl.cruzar(etl.agrupar_aportes([dict(auto[0], ing_identificacion="79000999",
                     nombre_persona="UN TERCERO")]),
                   etl.indexar_contratos([dict(ca[0], documento_proveedor="79000999",
                     proveedor_adjudicado="UN TERCERO")]), TOPE)))

print("\n[10] Conteos del resumen")
mixto = conc + auto + ingresos[:2]
cmix  = cc + ca + contratos[:1]
dm = etl.construir("SOACHA", None, desde="2020-01-01", hasta="2023-12-31",
                   tope=TOPE, token=None, limite=None) if False else None
etl.traer_financiadores = lambda *a, **k: mixto
etl.traer_contratos = lambda *a, **k: cmix
dm = etl.construir("SOACHA", None, desde="2020-01-01", hasta="2023-12-31",
                   tope=TOPE, token=None, limite=None)
km = dm["kpis"]
check("cuenta la autofinanciacion aparte", km["autofinanciacion"] == 1, str(km["autofinanciacion"]))
check("cuenta los cargos no cubiertos aparte", km["cargo_no_cubierto"] == 1, str(km["cargo_no_cubierto"]))
check("los terceros excluyen la autofinanciacion",
      km["terceros_con_contrato"] == km["financiadores_con_contrato"] - km["autofinanciacion"])
check("el corte explica ambos filtros",
      "concejo" in dm["meta"]["cargos_cubiertos"].lower()
      and "tercero" in dm["meta"]["autofinanciacion"].lower())

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("   -", f)
    sys.exit(1)
print("Todas las verificaciones pasaron.")
