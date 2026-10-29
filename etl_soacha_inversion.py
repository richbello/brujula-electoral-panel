"""
Módulo 08 · Soacha: inversión departamental y nacional
X-irin Technologies S.A.S.

Genera los datos de las pestañas 3 (Regalías) y 4 (Finanzas del municipio)
en data/soacha/inversion/. Las pestañas 1 (Megaproyectos) y 2 (Contratos
departamentales) no dependen de este script: la 1 lee megaproyectos.json,
que se actualiza a mano, y la 2 consulta SECOP II en vivo desde el navegador.

Uso (desde la carpeta del repositorio):

    python etl_soacha_inversion.py
    python etl_soacha_inversion.py --regalias export_mapainversiones.csv
    python etl_soacha_inversion.py --chip ejecucion_soacha.csv

  --regalias  CSV exportado de Mapa Inversiones / MapaRegalías (DNP) con los
              proyectos de Soacha. El script reconoce las columnas por nombre
              aunque cambien de mayúsculas o tildes; si el archivo trae
              proyectos de otros municipios, deja solo los que mencionan Soacha.
  --chip      CSV con la ejecución presupuestal del municipio sacada de CHIP
              (FUT ingresos y gastos), en el formato de
              data/soacha/inversion/plantilla_chip.csv.

Sin argumentos, regenera finanzas.json con el resumen de la contratación
municipal (SECOP II) y deja regalias.json como esté (o vacío si no existe).
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "data" / "soacha" / "inversion"
FISCAL_SOACHA = RAIZ / "data" / "cundinamarca" / "analisis" / "soacha.json"


def sin_tildes(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").upper().strip()


def numero(v):
    """Convierte '1.234.567,89', '1,234,567.89', '$ 1234567' o 1234567 en float."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not s:
        return 0.0
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) <= 2:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
        if s.count(".") > 1:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def leer_csv(ruta):
    datos = Path(ruta).read_bytes()
    for cod in ("utf-8-sig", "latin-1"):
        try:
            texto = datos.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    muestra = texto[:5000]
    sep = ";" if muestra.count(";") > muestra.count(",") else ","
    return list(csv.DictReader(texto.splitlines(), delimiter=sep))


def columna(cabeceras, *candidatos):
    """Primera cabecera que contenga alguno de los textos candidatos."""
    norm = {c: sin_tildes(c) for c in cabeceras}
    for cand in candidatos:
        cand = sin_tildes(cand)
        for original, n in norm.items():
            if cand in n:
                return original
    return None


def guardar(nombre, obj):
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / nombre
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  escrito", ruta.relative_to(RAIZ))


# ------------------------------------------------------------- regalías
def regalias(ruta_csv):
    filas = leer_csv(ruta_csv)
    if not filas:
        sys.exit("El CSV de regalías está vacío.")
    cab = list(filas[0].keys())
    c = {
        "bpin": columna(cab, "BPIN", "CODIGO"),
        "nombre": columna(cab, "NOMBRE DEL PROYECTO", "NOMBRE PROYECTO", "PROYECTO", "NOMBRE"),
        "sector": columna(cab, "SECTOR"),
        "ejecutor": columna(cab, "EJECUTOR", "ENTIDAD"),
        "estado": columna(cab, "ESTADO"),
        "valor": columna(cab, "VALOR TOTAL", "VALOR PROYECTO", "VALOR APROBADO", "VALOR"),
        "sgr": columna(cab, "VALOR SGR", "RECURSOS SGR", "REGALIAS"),
        "fisico": columna(cab, "AVANCE FISICO", "FISICO"),
        "financiero": columna(cab, "AVANCE FINANCIERO", "FINANCIERO"),
        "ubicacion": columna(cab, "MUNICIPIO", "UBICACION", "LOCALIZACION"),
        "alerta": columna(cab, "ALERTA", "RIESGO"),
        "fecha": columna(cab, "FECHA APROBACION", "FECHA"),
    }
    if not c["nombre"] or not c["valor"]:
        sys.exit("No encontré las columnas de nombre y valor del proyecto. Cabeceras: " + ", ".join(cab))

    def pct(v):
        x = numero(v)
        return round(x * 100, 2) if 0 < x <= 1 else round(x, 2)

    proyectos = []
    for f in filas:
        texto = " ".join(str(f.get(k) or "") for k in (c["ubicacion"], c["ejecutor"], c["nombre"]) if k)
        if c["ubicacion"] or c["ejecutor"]:
            if "SOACHA" not in sin_tildes(texto):
                continue
        proyectos.append({
            "bpin": (f.get(c["bpin"]) or "").strip() if c["bpin"] else "",
            "nombre": (f.get(c["nombre"]) or "").strip(),
            "sector": (f.get(c["sector"]) or "").strip() if c["sector"] else "",
            "ejecutor": (f.get(c["ejecutor"]) or "").strip() if c["ejecutor"] else "",
            "estado": (f.get(c["estado"]) or "").strip() if c["estado"] else "",
            "valor": numero(f.get(c["valor"])),
            "valor_sgr": numero(f.get(c["sgr"])) if c["sgr"] else None,
            "avance_fisico": pct(f.get(c["fisico"])) if c["fisico"] else None,
            "avance_financiero": pct(f.get(c["financiero"])) if c["financiero"] else None,
            "alerta": (f.get(c["alerta"]) or "").strip() if c["alerta"] else "",
            "fecha": (f.get(c["fecha"]) or "").strip()[:10] if c["fecha"] else "",
        })
    proyectos.sort(key=lambda p: -p["valor"])
    guardar("regalias.json", {
        "generado": date.today().isoformat(),
        "fuente": {"titulo": "Mapa Inversiones / MapaRegalías · DNP", "archivo": Path(ruta_csv).name},
        "columnas_detectadas": {k: v for k, v in c.items() if v},
        "proyectos": proyectos,
    })
    print(f"  {len(proyectos)} proyectos de regalías en Soacha")


# ------------------------------------------------------------- finanzas
def chip(ruta_csv):
    filas = leer_csv(ruta_csv)
    salida = []
    for f in filas:
        tipo = sin_tildes(f.get("tipo")).lower()
        if tipo not in ("ingreso", "gasto"):
            continue
        salida.append({
            "vigencia": int(numero(f.get("vigencia"))),
            "tipo": tipo,
            "concepto": (f.get("concepto") or "").strip(),
            "definitivo": numero(f.get("presupuesto_definitivo")),
            "ejecutado": numero(f.get("ejecutado")),
        })
    if not salida:
        sys.exit("El CSV de CHIP no trae filas válidas. Use plantilla_chip.csv como guía.")
    return salida


def finanzas(ruta_chip):
    previo = {}
    if (SALIDA / "finanzas.json").exists():
        previo = json.loads((SALIDA / "finanzas.json").read_text(encoding="utf-8"))

    contratacion = None
    if FISCAL_SOACHA.exists():
        f = json.loads(FISCAL_SOACHA.read_text(encoding="utf-8"))
        m4, m5 = f.get("modulo_04_contratos", {}), f.get("modulo_05_obras", {})
        contratacion = {
            "periodo_desde": f.get("periodo_desde"),
            "generado": f.get("generado"),
            "resumen": f.get("resumen"),
            "indice_alertas": f.get("indice_alertas"),
            "nivel": f.get("nivel"),
            "posicion": f.get("posicion"),
            "total_rankeados": f.get("total_rankeados"),
            "indicadores": {k: m4.get(k) for k in (
                "pct_contratos_directa", "pct_directa_valor", "hhi", "top1_proveedor_pct",
                "top5_proveedores_pct", "pct_con_adicion")},
            "top_proveedores": (m4.get("top_proveedores") or [])[:10],
            "obras": {k: v for k, v in m5.items() if not isinstance(v, list)},
        }
    else:
        print("  aviso: no encontré", FISCAL_SOACHA.relative_to(RAIZ), "· la contratación municipal queda vacía")

    ejecucion = chip(ruta_chip) if ruta_chip else previo.get("ejecucion", [])
    guardar("finanzas.json", {
        "generado": date.today().isoformat(),
        "municipio": "Soacha",
        "contratacion_municipal": contratacion,
        "ejecucion": ejecucion,
        "fuente_ejecucion": ("CHIP · FUT (" + Path(ruta_chip).name + ")") if ruta_chip
                            else previo.get("fuente_ejecucion", ""),
    })


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regalias", help="CSV exportado de Mapa Inversiones / MapaRegalías")
    ap.add_argument("--chip", help="CSV de ejecución presupuestal (formato plantilla_chip.csv)")
    a = ap.parse_args()

    print("Módulo 08 · Soacha: inversión departamental y nacional")
    if a.regalias:
        regalias(a.regalias)
    elif not (SALIDA / "regalias.json").exists():
        guardar("regalias.json", {"generado": date.today().isoformat(), "fuente": None, "proyectos": []})
    finanzas(a.chip)


if __name__ == "__main__":
    main()
