#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica la logica de etl_vigilancia_fiscal.py contra fixtures, sin tocar la red.

Ejecutar:  python test_etl_vigilancia.py
Sale con codigo 1 si algo falla, para poder usarlo en CI.
"""
import sys, json, datetime as dt
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import etl_vigilancia_fiscal as etl

fallos = []
def check(nombre, ok, detalle=""):
    print(f"  {'OK  ' if ok else 'FALLA'}  {nombre}{'  ' + detalle if detalle else ''}")
    if not ok:
        fallos.append(nombre)

# ---------------------------------------------------------------- DV DIAN
print("\n[1] Digito de verificacion (NIT reales conocidos)")
vectores = [
    ("899999115", 8, "ETB"),
    ("899999068", 1, "Ecopetrol"),
    ("890903938", 8, "Bancolombia"),
    ("860034594", 1, "Colpatria (visto en el boletin)"),
    ("860525148", 5, "Fiduciaria La Previsora (visto en el boletin)"),
]
for base, esperado, quien in vectores:
    obtenido = etl.digito_verificacion(base)
    check(f"{base}-{esperado}  {quien}", obtenido == esperado, f"calculado={obtenido}")

# ------------------------------------------------- claves de documento
print("\n[2] Normalizacion de documentos")
check("NIT con DV genera la base de 9",
      "860034594" in etl.claves_documento("8600345941"))
check("NIT con puntos y guion se normaliza",
      etl.claves_documento("860.034.594-1") == etl.claves_documento("8600345941"))
check("NIT de 9 digitos genera su variante con DV",
      "8600345941" in etl.claves_documento("860034594"))
# una cedula de 10 digitos cuyo prefijo NO valida como NIT no debe truncarse
ced = "1022367775"
base_ced = ced[:9]
es_nit_valido = etl.digito_verificacion(base_ced) == int(ced[9])
check("cedula de 10 digitos no se trunca por error",
      (base_ced in etl.claves_documento(ced)) == es_nit_valido,
      f"(prefijo valida como NIT: {es_nit_valido})")
check("documento vacio no genera claves", etl.claves_documento("") == set())
check("documento basura no genera claves", etl.claves_documento("N/A") == set())

# ------------------------------------------------------------- numeros
print("\n[3] Parseo de valores")
check("formato del boletin  '$ 6,012,499,968.00'",
      etl.a_numero("$ 6,012,499,968.00") == 6012499968.0,
      str(etl.a_numero("$ 6,012,499,968.00")))
check("formato de SECOP  '11986667'", etl.a_numero("11986667") == 11986667.0)
check("separador de miles con punto  '1.234.567'",
      etl.a_numero("1.234.567") == 1234567.0, str(etl.a_numero("1.234.567")))
check("vacio -> 0", etl.a_numero(None) == 0.0)

# --------------------------------------------------------- cruce BRF
print("\n[4] Cruce contra el boletin")
brf = [
    {  # NIT con DV, como viene en el boletin
        "n_mero_de_identificaci_n": "8600345941",
        "raz_n_social_de_la_entidad": "CONSTRUCTORA ANDINA S.A.",
        "tipo_de_sanci_n_multa": "Fallo con Responsabilidad Fiscal",
        "tema_clasificaci_n_o_motivo": "Responsabilidad Fiscal",
        "monto_de_la_multa_o_sanci": "$ 418,832,816.00",
        "fecha_de_firmeza_de_la_decisi": "2021-05-14",
        "fuente": "SIREF",
    },
    {
        "n_mero_de_identificaci_n": "79123456",
        "raz_n_social_de_la_entidad": "PEDRO PEREZ GOMEZ",
        "tipo_de_sanci_n_multa": "Fallo con Responsabilidad Fiscal",
        "monto_de_la_multa_o_sanci": "$ 50,000,000.00",
        "fecha_de_firmeza_de_la_decisi": "2019-02-01",
        "fuente": "SIREF",
    },
]
contratos = [
    {  # mismo NIT pero SIN el DV -> debe cruzar igual
        "documento_proveedor": "860034594", "tipodocproveedor": "NIT",
        "proveedor_adjudicado": "CONSTRUCTORA ANDINA S A",
        "nombre_entidad": "ALCALDIA DE SOACHA", "nit_entidad": "800000001",
        "referencia_del_contrato": "100-2025", "estado_contrato": "En ejecucion",
        "modalidad_de_contratacion": "Licitacion publica",
        "objeto_del_contrato": "Mantenimiento vial",
        "valor_del_contrato": "2500000000", "fecha_de_firma": "2025-03-01T00:00:00.000",
        "urlproceso": {"url": "https://community.secop.gov.co/x"},
    },
    {  # contratista limpio
        "documento_proveedor": "901222333", "tipodocproveedor": "NIT",
        "proveedor_adjudicado": "EMPRESA LIMPIA SAS",
        "nombre_entidad": "ALCALDIA DE SOACHA", "nit_entidad": "800000001",
        "referencia_del_contrato": "101-2025", "estado_contrato": "En ejecucion",
        "modalidad_de_contratacion": "Minima cuantia",
        "objeto_del_contrato": "Papeleria", "valor_del_contrato": "9000000",
        "fecha_de_firma": "2025-04-01T00:00:00.000",
    },
    {  # homonimo: mismo documento, nombre totalmente distinto
        "documento_proveedor": "79123456", "tipodocproveedor": "Cedula de Ciudadania",
        "proveedor_adjudicado": "MARIA RODRIGUEZ LOPEZ",
        "nombre_entidad": "IMRD SOACHA", "nit_entidad": "832000906",
        "referencia_del_contrato": "55-2024", "estado_contrato": "Terminado",
        "modalidad_de_contratacion": "Contratacion directa",
        "objeto_del_contrato": "Servicios profesionales", "valor_del_contrato": "30000000",
        "fecha_de_firma": "2024-02-01T00:00:00.000",
    },
]
indice = etl.indexar_brf(brf)
alertas = etl.cruzar(contratos, indice)
check("detecta 2 contratistas en el boletin", len(alertas) == 2, f"obtuvo {len(alertas)}")
porcrit = {a["nivel"] for a in alertas}
andina = next((a for a in alertas if "ANDINA" in a["nombre_secop"]), None)
check("cruza pese a la diferencia de digito de verificacion", andina is not None)
if andina:
    check("clasifica como critico (contrato en ejecucion)", andina["nivel"] == "critico")
    check("no lo marca como homonimo (nombres compatibles)",
          andina["posible_homonimo"] is False)
    check("trae el monto de la sancion",
          andina["sanciones"][0]["monto"] == 418832816.0)
maria = next((a for a in alertas if "MARIA" in a["nombre_secop"]), None)
if maria:
    check("marca posible homonimo cuando los nombres no coinciden",
          maria["posible_homonimo"] is True)
    check("sin contrato activo -> alto, no critico", maria["nivel"] == "alto")
check("el contratista limpio no genera alerta",
      not any("LIMPIA" in a["nombre_secop"] for a in alertas))

# ------------------------------------------- indicios de fraccionamiento
print("\n[5] Indicios de fraccionamiento")
seguidos = [
    {"documento_proveedor": "901999888", "proveedor_adjudicado": "PROVEEDOR X SAS",
     "nombre_entidad": "ALCALDIA DE SOACHA", "nit_entidad": "800000001",
     "modalidad_de_contratacion": "Contratacion directa",
     "referencia_del_contrato": f"F-{i}", "valor_del_contrato": "19000000",
     "fecha_de_firma": f"2025-01-{10+i*5:02d}T00:00:00.000"}
    for i in range(4)
]
lejanos = [
    {"documento_proveedor": "901777666", "proveedor_adjudicado": "PROVEEDOR Y SAS",
     "nombre_entidad": "ALCALDIA DE SOACHA", "nit_entidad": "800000001",
     "modalidad_de_contratacion": "Contratacion directa",
     "referencia_del_contrato": f"L-{i}", "valor_del_contrato": "19000000",
     "fecha_de_firma": f"202{5+i}-01-10T00:00:00.000"}
    for i in range(3)
]
competitivos = [
    {"documento_proveedor": "901555444", "proveedor_adjudicado": "PROVEEDOR Z SAS",
     "nombre_entidad": "ALCALDIA DE SOACHA", "nit_entidad": "800000001",
     "modalidad_de_contratacion": "Licitacion publica",
     "referencia_del_contrato": f"C-{i}", "valor_del_contrato": "19000000",
     "fecha_de_firma": f"2025-02-{10+i*3:02d}T00:00:00.000"}
    for i in range(4)
]
h = etl.indicios_fraccionamiento(seguidos + lejanos + competitivos,
                                 ventana_dias=90, minimo_contratos=3)
check("detecta 4 contratos directos en 15 dias", len(h) == 1, f"obtuvo {len(h)}")
if h:
    check("suma el valor del bloque", h[0]["valor_total"] == 76000000.0,
          str(h[0]["valor_total"]))
    check("reporta el contratista correcto", h[0]["documento"] == "901999888")
check("reporta 4 contratos, no solo los 3 del minimo",
      bool(h) and h[0]["contratos"] == 4, f"contratos={h[0]['contratos'] if h else 0}")
check("ignora contratos separados por anios",
      not any(x["documento"] == "901777666" for x in h))
check("ignora modalidades competitivas",
      not any(x["documento"] == "901555444" for x in h))

# ------------------------------------------------------- concentracion
print("\n[6] Concentracion y multi-entidad")
top, top3 = etl.concentracion(contratos)
check("top3 es porcentaje valido", 0 <= top3 <= 100, f"{top3}%")
check("el mayor contrato encabeza", top[0]["documento"] == "860034594")
suma_part = round(sum(t["participacion"] for t in top), 1)
check("las participaciones suman ~100%", abs(suma_part - 100.0) < 0.5, f"{suma_part}%")

multi = etl.multi_entidad(contratos * 1, minimo=2)
check("sin contratistas en 2+ entidades en este fixture", multi == [])
cruzado = contratos + [{**contratos[0], "nombre_entidad": "OTRA ENTIDAD",
                        "referencia_del_contrato": "200-2025"}]
multi2 = etl.multi_entidad(cruzado, minimo=2)
check("detecta contratista en 2 entidades", len(multi2) == 1 and multi2[0]["entidades"] == 2)

# ------------------------------------------------- construccion del JSON
print("\n[7] Estructura del JSON de salida")
etl.consultar = lambda dataset, **kw: (contratos if dataset == "jbjy-vk9h" else brf)
datos = etl.construir("Soacha", "2020-01-01", "2026-10-09", token=None,
                      ventana_dias=90, minimo_contratos=3, limite=None)
for clave in ["meta", "kpis", "alertas_boletin", "indicios_fraccionamiento",
              "concentracion", "multi_entidad"]:
    check(f"contiene '{clave}'", clave in datos)
check("meta trae fecha de generacion", bool(datos["meta"]["generado_en"]))
check("meta declara las 2 fuentes con dataset y conteo",
      len(datos["meta"]["fuentes"]) == 2
      and all(f.get("dataset") and "registros" in f for f in datos["meta"]["fuentes"]))
check("meta incluye la advertencia de verificacion",
      "no prueba inhabilidad" in datos["meta"]["advertencia"])
check("es serializable a JSON", bool(json.dumps(datos, ensure_ascii=False)))

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("   -", f)
    sys.exit(1)
print("Todas las verificaciones pasaron.")
