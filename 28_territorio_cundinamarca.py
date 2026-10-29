"""
Territorio y obras inconclusas para los municipios de Cundinamarca.

Lee los contratos ya descargados en data/cundinamarca/contratos/<municipio>.json
(los produce 27_exportar_contratos_detalle.py) y aplica exactamente la misma
logica de etl_territorio.py (obras vencidas y valor por sector nombrado).
No consulta SECOP: reutiliza lo que ya esta en el repositorio.

Salida:
    data/cundinamarca/territorio/<municipio>.json   mismo formato que data/modulos/territorio.json
    data/cundinamarca/territorio/indice.json        lista para el selector del modulo

Uso:
    python 28_territorio_cundinamarca.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etl_territorio import FUENTE, obras_vencidas, por_sector  # noqa: E402

RAIZ = Path(__file__).resolve().parent
ORIGEN = RAIZ / "data" / "cundinamarca" / "contratos"
DESTINO = RAIZ / "data" / "cundinamarca" / "territorio"
MINIMO = 20_000_000


def a_secop(campos: list[str], cat: dict, fila: list) -> dict:
    """Devuelve el contrato con los nombres de columna de SECOP II."""
    c = dict(zip(campos, fila))
    nombre = lambda k: cat[k][c[k]] if isinstance(c.get(k), int) and c[k] < len(cat[k]) else (c.get(k) or "")
    return {
        "referencia_del_contrato": c.get("numero") or "",
        "nombre_entidad": nombre("entidad"),
        "proveedor_adjudicado": c.get("proveedor") or "",
        "documento_proveedor": c.get("doc_prov") or "",
        "tipo_de_contrato": nombre("tipo"),
        "estado_contrato": nombre("estado"),
        "objeto_del_contrato": c.get("objeto") or "",
        "valor_del_contrato": c.get("valor") or 0,
        "valor_pagado": c.get("pagado") or 0,
        "fecha_de_firma": c.get("fecha_firma") or "",
        "fecha_de_inicio_del_contrato": c.get("fecha_inicio") or "",
        "fecha_de_fin_del_contrato": c.get("fecha_fin") or "",
        "urlproceso": {"url": c.get("url") or ""},
    }


def construir(d: dict, hoy: dt.date) -> dict:
    cat = d["catalogos"]
    contratos = [a_secop(d["campos"], cat, f) for f in d["contratos"]]
    vencidas = obras_vencidas(contratos, hoy, minimo=MINIMO)
    sectores, cobertura = por_sector(contratos)

    valor_total = sum(float(c["valor_del_contrato"] or 0) for c in contratos)
    con_pago = sum(1 for c in contratos if float(c["valor_pagado"] or 0) > 0)
    pct_pago = round(con_pago / len(contratos) * 100, 1) if contratos else 0.0
    hasta = str(d.get("generado") or hoy.isoformat())[:10]

    return {
        "meta": {
            "generado_en": d.get("generado") or dt.datetime.now().isoformat(timespec="seconds"),
            "municipio": d["municipio"],
            "ventana": {"desde": d.get("periodo_desde") or "", "hasta": hasta},
            "minimo_obra": MINIMO,
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
            "valor_vencido": sum(v["valor"] for v in vencidas),
            "vencidas_con_pago_reportado": sum(1 for v in vencidas if v["pago_reportado"]),
            "pct_contratos_con_pago": pct_pago,
            "sectores": len(sectores),
            "cobertura_valor": cobertura["pct_valor"],
        },
        "obras_vencidas": vencidas[:80],
        "sectores": sectores[:60],
    }


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    indice = []
    for ruta in sorted(ORIGEN.glob("*.json")):
        d = json.loads(ruta.read_text(encoding="utf-8"))
        hoy = dt.date.fromisoformat(str(d.get("generado") or dt.date.today())[:10])
        # Si 31_territorio_cundinamarca_gobiernos.py ya dejo un corte que arranca
        # antes (2020, con los dos gobiernos), no se reemplaza por uno mas corto.
        actual = DESTINO / ruta.name
        if actual.exists():
            previo = json.loads(actual.read_text(encoding="utf-8"))
            ini_previo = (previo.get("meta", {}).get("ventana") or {}).get("desde") or "9999"
            if ini_previo < (d.get("periodo_desde") or "0000"):
                k = previo["kpis"]
                indice.append({"municipio": d["municipio"], "archivo": ruta.name,
                               "contratos": k["contratos"], "obras_vencidas": k["obras_vencidas"],
                               "desde": ini_previo})
                print(f"{d['municipio']:<28} conserva su corte desde {ini_previo}")
                continue
        t = construir(d, hoy)
        (DESTINO / ruta.name).write_text(
            json.dumps(t, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        indice.append({"municipio": d["municipio"], "archivo": ruta.name,
                       "contratos": t["kpis"]["contratos"],
                       "obras_vencidas": t["kpis"]["obras_vencidas"]})
        print(f"{d['municipio']:<28} {t['kpis']['contratos']:>6} contratos  "
              f"{t['kpis']['obras_vencidas']:>4} obras vencidas")
    indice.sort(key=lambda x: x["municipio"])
    (DESTINO / "indice.json").write_text(
        json.dumps({"municipios": indice}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(indice)} municipios -> {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
