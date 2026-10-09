#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL de Vigilancia Fiscal
========================

Construye el insumo real de la pestaña "Vigilancia fiscal" del panel
Estrategia Electoral 2027, cruzando dos fuentes abiertas:

  1. SECOP II - Contratos Electronicos   datos.gov.co  dataset jbjy-vk9h
  2. Responsabilidad Fiscal (SIREF/BRF)  datos.gov.co  dataset jr8e-e8tu

Produce data/modulos/vigilancia_fiscal.json, que la pagina lee en el
navegador. El JSON lleva fecha de corte y metadatos de cada fuente, de modo
que el panel siempre pueda decir de cuando son las cifras que muestra.

IMPORTANTE SOBRE EL CRUCE
-------------------------
Coincidir por numero de documento NO prueba que un contratista este
inhabilitado. Hay homonimos, NIT mal digitados en SECOP, y registros del
boletin que ya fueron pagados y levantados. Por eso cada alerta sale marcada
como "requiere verificacion" y con el enlace al certificado oficial de la
Contraloria. Verifique antes de afirmar nada en publico.

Uso
---
    python etl_vigilancia_fiscal.py --municipio Soacha --desde 2020-01-01

    # con token de Socrata (recomendado, evita el throttling anonimo)
    export SOCRATA_APP_TOKEN=xxxxxxxx
    python etl_vigilancia_fiscal.py --municipio Soacha

Requiere: requests
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Falta la dependencia 'requests'.  Instale con:  pip install requests")

# --------------------------------------------------------------------------
# Configuracion de fuentes
# --------------------------------------------------------------------------

DOMINIO = "https://www.datos.gov.co"

FUENTES = {
    "secop": {
        "dataset": "jbjy-vk9h",
        "nombre": "SECOP II - Contratos Electronicos",
        "entidad": "Colombia Compra Eficiente",
        "pagina": f"{DOMINIO}/Gastos-Gubernamentales/SECOP-II-Contratos-Electronicos/jbjy-vk9h",
    },
    "brf": {
        "dataset": "jr8e-e8tu",
        "nombre": "Responsabilidad Fiscal (SIREF - Boletin de Responsables Fiscales)",
        "entidad": "Contraloria General de la Republica",
        "pagina": f"{DOMINIO}/Organismos-de-Control/Responsabilidad-Fiscal/jr8e-e8tu",
    },
}

CERTIFICADO_CGR = "https://www.contraloria.gov.co/control-fiscal/responsabilidad-fiscal/certificado-de-antecedentes-fiscales"

PAGINA = 1000          # registros por request a Socrata
MAX_REINTENTOS = 4
PAUSA_BASE = 2.0       # segundos, con backoff exponencial


# --------------------------------------------------------------------------
# Normalizacion de documentos
# --------------------------------------------------------------------------

def digito_verificacion(nit9: str) -> int:
    """Digito de verificacion de un NIT colombiano (algoritmo DIAN).

    Se aplican los pesos a los 9 digitos base alineados a la derecha.
    """
    pesos = [41, 37, 29, 23, 19, 17, 13, 7, 3]
    base = nit9.rjust(9, "0")
    suma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = suma % 11
    return resto if resto < 2 else 11 - resto


def claves_documento(valor: Any) -> set[str]:
    """Devuelve el conjunto de claves con que puede aparecer un documento.

    SECOP y el boletin no escriben el NIT igual: uno trae el digito de
    verificacion y el otro no, y a veces vienen con puntos o guiones. Para
    cruzar sin falsos negativos se generan las variantes equivalentes.

    El DV solo se agrega o se quita cuando el algoritmo DIAN lo confirma, de
    modo que una cedula de 10 digitos nunca se trunca por error.
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos or len(digitos) < 5:
        return set()

    claves = {digitos}

    # 10 digitos que son un NIT valido con DV -> agregar la base de 9
    if len(digitos) == 10:
        base, dv = digitos[:9], int(digitos[9])
        if digito_verificacion(base) == dv:
            claves.add(base)

    # 9 digitos -> agregar la variante con su DV
    if len(digitos) == 9:
        claves.add(digitos + str(digito_verificacion(digitos)))

    return claves


def a_numero(valor: Any) -> float:
    """Convierte '$ 6,012,499,968.00' o '11986667' a float."""
    if valor is None:
        return 0.0
    txt = re.sub(r"[^\d.\-]", "", str(valor))
    if txt.count(".") > 1:  # separador de miles con punto
        txt = txt.replace(".", "")
    try:
        return float(txt) if txt not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0


def a_fecha(valor: Any) -> dt.date | None:
    if not valor:
        return None
    txt = str(valor)[:10]
    try:
        return dt.date.fromisoformat(txt)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Cliente Socrata
# --------------------------------------------------------------------------

def consultar(dataset: str, *, where: str | None = None, select: str | None = None,
              order: str | None = None, limite_total: int | None = None,
              token: str | None = None) -> list[dict]:
    """Descarga un dataset de Socrata paginando hasta agotarlo."""
    url = f"{DOMINIO}/resource/{dataset}.json"
    cabeceras = {"X-App-Token": token} if token else {}
    filas: list[dict] = []
    offset = 0

    while True:
        params: dict[str, Any] = {"$limit": PAGINA, "$offset": offset}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        if order:
            params["$order"] = order

        lote = _get_con_reintentos(url, params, cabeceras)
        filas.extend(lote)
        print(f"    {dataset}: {len(filas):,} registros", end="\r", flush=True)

        if len(lote) < PAGINA:
            break
        if limite_total and len(filas) >= limite_total:
            filas = filas[:limite_total]
            break
        offset += PAGINA

    print(f"    {dataset}: {len(filas):,} registros          ")
    return filas


def _get_con_reintentos(url: str, params: dict, cabeceras: dict) -> list[dict]:
    ultimo_error: Exception | None = None
    for intento in range(MAX_REINTENTOS):
        try:
            r = requests.get(url, params=params, headers=cabeceras, timeout=90)
            if r.status_code == 429:  # throttling
                espera = PAUSA_BASE * (2 ** intento)
                print(f"\n    throttling de Socrata, esperando {espera:.0f}s "
                      f"(use SOCRATA_APP_TOKEN para evitarlo)")
                time.sleep(espera)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            ultimo_error = exc
            if intento < MAX_REINTENTOS - 1:
                time.sleep(PAUSA_BASE * (2 ** intento))
    raise RuntimeError(f"Socrata no respondio tras {MAX_REINTENTOS} intentos: {ultimo_error}")


# --------------------------------------------------------------------------
# Analisis
# --------------------------------------------------------------------------

def indexar_brf(filas_brf: Iterable[dict]) -> dict[str, list[dict]]:
    """Indexa el boletin por cada clave de documento posible."""
    indice: dict[str, list[dict]] = defaultdict(list)
    for fila in filas_brf:
        for clave in claves_documento(fila.get("n_mero_de_identificaci_n")):
            indice[clave].append(fila)
    return indice


def cruzar(contratos: list[dict], indice_brf: dict[str, list[dict]]) -> list[dict]:
    """Contratistas de SECOP que aparecen en el boletin de responsables."""
    por_contratista: dict[str, dict] = {}

    for c in contratos:
        doc = c.get("documento_proveedor")
        claves = claves_documento(doc)
        if not claves:
            continue

        coincidencias: list[dict] = []
        vistos: set[int] = set()
        for clave in claves:
            for reg in indice_brf.get(clave, []):
                if id(reg) not in vistos:
                    vistos.add(id(reg))
                    coincidencias.append(reg)
        if not coincidencias:
            continue

        llave = min(claves, key=len)
        ficha = por_contratista.setdefault(llave, {
            "documento": re.sub(r"\D", "", str(doc)),
            "tipo_documento": c.get("tipodocproveedor") or "",
            "nombre_secop": c.get("proveedor_adjudicado") or "",
            "contratos": [],
            "valor_total": 0.0,
            "sanciones": [],
        })

        valor = a_numero(c.get("valor_del_contrato"))
        ficha["valor_total"] += valor
        ficha["contratos"].append({
            "referencia": c.get("referencia_del_contrato") or c.get("id_contrato") or "",
            "entidad": c.get("nombre_entidad") or "",
            "estado": c.get("estado_contrato") or "",
            "modalidad": c.get("modalidad_de_contratacion") or "",
            "objeto": (c.get("objeto_del_contrato") or "")[:240],
            "valor": valor,
            "firma": str(c.get("fecha_de_firma") or "")[:10],
            "url": (c.get("urlproceso") or {}).get("url", "") if isinstance(c.get("urlproceso"), dict) else "",
        })

        if not ficha["sanciones"]:
            for reg in coincidencias:
                ficha["sanciones"].append({
                    "razon_social_boletin": reg.get("raz_n_social_de_la_entidad") or "",
                    "tipo": reg.get("tipo_de_sanci_n_multa") or "",
                    "motivo": reg.get("tema_clasificaci_n_o_motivo") or "",
                    "monto": a_numero(reg.get("monto_de_la_multa_o_sanci")),
                    "fecha_firmeza": str(reg.get("fecha_de_firmeza_de_la_decisi") or "")[:10],
                    "resolucion": reg.get("n_mero_de_resoluci_n_que") or "",
                    "fuente": reg.get("fuente") or "",
                })

    # nivel de riesgo y coherencia de nombres
    alertas = []
    for ficha in por_contratista.values():
        activos = [k for k in ficha["contratos"]
                   if "ejecu" in (k["estado"] or "").lower()]
        ficha["contratos_activos"] = len(activos)
        ficha["valor_activo"] = sum(k["valor"] for k in activos)
        ficha["nivel"] = "critico" if activos else "alto"

        # si el nombre en SECOP y en el boletin no se parecen, puede ser homonimo
        nombre_brf = (ficha["sanciones"][0]["razon_social_boletin"] if ficha["sanciones"] else "")
        ficha["posible_homonimo"] = not _nombres_compatibles(ficha["nombre_secop"], nombre_brf)

        ficha["contratos"].sort(key=lambda k: k["valor"], reverse=True)
        alertas.append(ficha)

    alertas.sort(key=lambda f: (f["nivel"] != "critico", -f["valor_total"]))
    return alertas


def _nombres_compatibles(a: str, b: str) -> bool:
    """Heuristica suave: comparten al menos una palabra significativa."""
    def tokens(s: str) -> set[str]:
        s = re.sub(r"[^\wáéíóúñ ]", " ", (s or "").lower())
        vacias = {"de", "la", "el", "los", "las", "y", "del", "sa", "sas",
                  "ltda", "s", "a", "eu", "e", "u", "cia", "compania", "en",
                  "liquidacion", "consorcio", "union", "temporal"}
        return {t for t in s.split() if len(t) > 2 and t not in vacias}
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return True  # sin datos para dudar
    return bool(ta & tb)


def indicios_fraccionamiento(contratos: list[dict], *, ventana_dias: int,
                             minimo_contratos: int) -> list[dict]:
    """Patron: mismo contratista y misma entidad, varios contratos directos
    muy seguidos.

    Esto NO es una determinacion de fraccionamiento, que es una figura
    juridica. Es un patron que amerita revision.
    """
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for c in contratos:
        modalidad = (c.get("modalidad_de_contratacion") or "").lower()
        if "directa" not in modalidad and "minima" not in modalidad:
            continue
        doc = re.sub(r"\D", "", str(c.get("documento_proveedor") or ""))
        nit_ent = re.sub(r"\D", "", str(c.get("nit_entidad") or ""))
        fecha = a_fecha(c.get("fecha_de_firma"))
        if not doc or not nit_ent or not fecha:
            continue
        grupos[(nit_ent, doc)].append({**c, "_fecha": fecha})

    hallazgos = []
    for (nit_ent, doc), items in grupos.items():
        if len(items) < minimo_contratos:
            continue
        items.sort(key=lambda x: x["_fecha"])

        # Ventana deslizante: se recorren todas y se reporta la mas densa.
        # Cortar en la primera que alcanza el minimo subestimaria el patron,
        # porque la ventana sigue creciendo con los contratos siguientes.
        mejor: list[dict] | None = None
        mejor_total = 0.0
        i = 0
        for j in range(len(items)):
            while (items[j]["_fecha"] - items[i]["_fecha"]).days > ventana_dias:
                i += 1
            bloque = items[i:j + 1]
            if len(bloque) < minimo_contratos:
                continue
            total = sum(a_numero(b.get("valor_del_contrato")) for b in bloque)
            if mejor is None or (len(bloque), total) > (len(mejor), mejor_total):
                mejor, mejor_total = bloque, total

        if mejor:
            hallazgos.append({
                "entidad": mejor[0].get("nombre_entidad") or "",
                "nit_entidad": nit_ent,
                "contratista": mejor[0].get("proveedor_adjudicado") or "",
                "documento": doc,
                "contratos": len(mejor),
                "dias": (mejor[-1]["_fecha"] - mejor[0]["_fecha"]).days,
                "valor_total": mejor_total,
                "desde": mejor[0]["_fecha"].isoformat(),
                "hasta": mejor[-1]["_fecha"].isoformat(),
                "modalidades": sorted({(b.get("modalidad_de_contratacion") or "") for b in mejor}),
                "referencias": [b.get("referencia_del_contrato") or "" for b in mejor][:12],
            })

    hallazgos.sort(key=lambda h: -h["valor_total"])
    return hallazgos


def concentracion(contratos: list[dict], tope: int = 10) -> tuple[list[dict], float]:
    acumulado: dict[str, dict] = {}
    for c in contratos:
        doc = re.sub(r"\D", "", str(c.get("documento_proveedor") or "")) or "sin-documento"
        f = acumulado.setdefault(doc, {
            "documento": doc,
            "contratista": c.get("proveedor_adjudicado") or "",
            "contratos": 0,
            "valor_total": 0.0,
            "entidades": set(),
        })
        f["contratos"] += 1
        f["valor_total"] += a_numero(c.get("valor_del_contrato"))
        f["entidades"].add(c.get("nombre_entidad") or "")

    total = sum(f["valor_total"] for f in acumulado.values()) or 1.0
    ordenados = sorted(acumulado.values(), key=lambda f: -f["valor_total"])
    salida = []
    for f in ordenados[:tope]:
        salida.append({
            "documento": f["documento"],
            "contratista": f["contratista"],
            "contratos": f["contratos"],
            "entidades": len(f["entidades"]),
            "valor_total": f["valor_total"],
            "participacion": round(f["valor_total"] / total * 100, 2),
        })
    top3 = sum(f["valor_total"] for f in ordenados[:3]) / total * 100
    return salida, round(top3, 2)


def multi_entidad(contratos: list[dict], minimo: int = 2, tope: int = 15) -> list[dict]:
    reg: dict[str, dict] = {}
    for c in contratos:
        doc = re.sub(r"\D", "", str(c.get("documento_proveedor") or ""))
        if not doc:
            continue
        f = reg.setdefault(doc, {
            "documento": doc,
            "contratista": c.get("proveedor_adjudicado") or "",
            "entidades": set(),
            "contratos": 0,
            "valor_total": 0.0,
        })
        f["entidades"].add(c.get("nombre_entidad") or "")
        f["contratos"] += 1
        f["valor_total"] += a_numero(c.get("valor_del_contrato"))

    salida = [
        {**{k: v for k, v in f.items() if k != "entidades"},
         "entidades": len(f["entidades"]),
         "nombres_entidades": sorted(f["entidades"])[:6]}
        for f in reg.values() if len(f["entidades"]) >= minimo
    ]
    salida.sort(key=lambda f: (-f["entidades"], -f["valor_total"]))
    return salida[:tope]


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

def construir(municipio: str, desde: str, hasta: str, *, token: str | None,
              ventana_dias: int, minimo_contratos: int,
              limite: int | None) -> dict:
    ahora = dt.datetime.now().astimezone()

    print(f"[1/3] SECOP II  ->  contratos de {municipio} entre {desde} y {hasta}")
    where_secop = (
        f"ciudad like '%{municipio}%' "
        f"AND fecha_de_firma >= '{desde}T00:00:00' "
        f"AND fecha_de_firma <= '{hasta}T23:59:59'"
    )
    contratos = consultar(FUENTES["secop"]["dataset"], where=where_secop,
                          order="fecha_de_firma DESC", limite_total=limite, token=token)

    print("[2/3] Responsabilidad Fiscal  ->  boletin completo")
    brf = consultar(FUENTES["brf"]["dataset"], token=token)

    print("[3/3] Cruzando y calculando indicadores")
    indice = indexar_brf(brf)
    alertas = cruzar(contratos, indice)
    fracc = indicios_fraccionamiento(contratos, ventana_dias=ventana_dias,
                                     minimo_contratos=minimo_contratos)
    top, top3 = concentracion(contratos)
    multi = multi_entidad(contratos)

    valor_total = sum(a_numero(c.get("valor_del_contrato")) for c in contratos)
    contratistas = {re.sub(r"\D", "", str(c.get("documento_proveedor") or ""))
                    for c in contratos}
    contratistas.discard("")
    criticos = [a for a in alertas if a["nivel"] == "critico"]

    ultima_act = max(
        (str(c.get("ultima_actualizacion") or "")[:10] for c in contratos),
        default="",
    )

    return {
        "meta": {
            "generado_en": ahora.isoformat(timespec="seconds"),
            "municipio": municipio,
            "ventana": {"desde": desde, "hasta": hasta},
            "parametros": {
                "fraccionamiento_ventana_dias": ventana_dias,
                "fraccionamiento_minimo_contratos": minimo_contratos,
            },
            "fuentes": [
                {
                    "nombre": FUENTES["secop"]["nombre"],
                    "entidad": FUENTES["secop"]["entidad"],
                    "dataset": FUENTES["secop"]["dataset"],
                    "url": FUENTES["secop"]["pagina"],
                    "registros": len(contratos),
                    "ultima_actualizacion_registro": ultima_act,
                },
                {
                    "nombre": FUENTES["brf"]["nombre"],
                    "entidad": FUENTES["brf"]["entidad"],
                    "dataset": FUENTES["brf"]["dataset"],
                    "url": FUENTES["brf"]["pagina"],
                    "registros": len(brf),
                },
            ],
            "advertencia": (
                "La coincidencia por numero de documento no prueba inhabilidad. "
                "Puede haber homonimos, documentos mal digitados en SECOP o "
                "sanciones ya levantadas. Verifique cada caso en el certificado "
                "de antecedentes fiscales de la Contraloria antes de afirmarlo."
            ),
            "certificado_oficial": CERTIFICADO_CGR,
        },
        "kpis": {
            "contratos": len(contratos),
            "contratistas": len(contratistas),
            "valor_total": valor_total,
            "alertas_boletin": len(alertas),
            "riesgo_critico": len(criticos),
            "indicios_fraccionamiento": len(fracc),
            "concentracion_top3": top3,
        },
        "alertas_boletin": alertas[:50],
        "indicios_fraccionamiento": fracc[:30],
        "concentracion": top,
        "multi_entidad": multi,
    }


def main() -> int:
    hoy = dt.date.today().isoformat()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--municipio", default="Soacha")
    p.add_argument("--desde", default="2020-01-01")
    p.add_argument("--hasta", default=hoy)
    p.add_argument("--salida", default="data/modulos/vigilancia_fiscal.json")
    p.add_argument("--ventana-dias", type=int, default=90,
                   help="ventana para el patron de contratos seguidos")
    p.add_argument("--minimo-contratos", type=int, default=3,
                   help="contratos minimos dentro de la ventana")
    p.add_argument("--limite", type=int, default=None,
                   help="tope de contratos a descargar (para pruebas)")
    p.add_argument("--app-token", default=os.environ.get("SOCRATA_APP_TOKEN"))
    args = p.parse_args()

    try:
        datos = construir(
            args.municipio, args.desde, args.hasta,
            token=args.app_token,
            ventana_dias=args.ventana_dias,
            minimo_contratos=args.minimo_contratos,
            limite=args.limite,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("No se sobrescribio el archivo de salida.", file=sys.stderr)
        return 1

    destino = Path(args.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    k = datos["kpis"]
    print()
    print(f"  Escrito: {destino}")
    print(f"  Contratos            {k['contratos']:,}")
    print(f"  Contratistas         {k['contratistas']:,}")
    print(f"  Valor total          ${k['valor_total']:,.0f}")
    print(f"  Alertas del boletin  {k['alertas_boletin']:,}  (criticas: {k['riesgo_critico']})")
    print(f"  Indicios fraccion.   {k['indicios_fraccionamiento']:,}")
    print(f"  Concentracion top 3  {k['concentracion_top3']}%")
    print()
    print("  Recuerde: las alertas requieren verificacion antes de hacerlas publicas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
