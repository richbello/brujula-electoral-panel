"""
Módulo 09 · Seguridad y convivencia
X-irin Technologies S.A.S.

Fuente: Policía Nacional, "Información de delitos a nivel de registro"
(SIEDCO), un archivo por año en https://www.policia.gov.co/estadistica-delictiva.
Así lo indicó la Policía Metropolitana de Soacha en la respuesta GS-2026-054022-MESOA
al derecho de petición: descargar el archivo del año y filtrar departamento y municipio.

El script:
  1. Busca en la página de la Policía los archivos de registro de cada año
     (los nombres cambian cuando la Policía los actualiza) y los descarga.
     Si la página no responde, usa la lista conocida de nombres.
  2. Lee cada hoja de cada libro, encuentra la fila de encabezados y reconoce
     las columnas por nombre (departamento, municipio, fecha, cantidad, género,
     edad, armas o medios, zona, barrio, etc.).
  3. Publica SOLO cifras agregadas, nunca registros individuales:
       data/seguridad/soacha.json         series por delito, año y mes, y perfiles
       data/seguridad/cundinamarca.json   totales por municipio, delito y año

Uso:
    python etl_seguridad.py                     descarga y procesa 2020 en adelante
    python etl_seguridad.py --carpeta descargas usa archivos ya descargados (.xlsx o .zip)
    python etl_seguridad.py --inspeccionar      solo muestra hojas y encabezados detectados
    python etl_seguridad.py --municipio Soacha --desde 2020

Requiere: requests, openpyxl
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("Falta la dependencia 'openpyxl'.  Instale con:  pip install openpyxl requests")

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "data" / "seguridad"
PAGINA = "https://www.policia.gov.co/estadistica-delictiva"
BASE = "https://www.policia.gov.co/sites/default/files/"
# Nombres publicados a octubre de 2026; se usan si la página no se puede leer.
CONOCIDOS = {
    2026: "INFORMACI%C3%93N_DELITOS_A_NIVEL_DE_REGISTRO_A%C3%91O_2026_3.xlsx",
    2025: "INFORMACI%C3%93N_DE_DELITOS_A_NIVEL_DE_REGISTRO_A%C3%91O_2025_3.xlsx",
    2024: "INFORMACI%C3%93N_DE_DELITOS_A_NIVEL_DE_REGISTRO_A%C3%91O_2024_3.xlsx",
    2023: "INFORMACI%C3%93N_DE_DELITOS_A_NIVEL_DE_REGISTRO_A%C3%91O_2023.zip",
    2022: "INFORMACI%C3%93N_DE_DELITOS_A_NIVEL_DE_REGISTRO_A%C3%91O_2022.zip",
    2021: "INFORMACI%C3%93N_DE_DELITOS_A_NIVEL_DE_REGISTRO_A%C3%91O_2021_3.xlsx",
    2020: "INFORMACI%C3%93N_DE_DELITOS_A_NIVEL_DE_REGISTRO_A%C3%91O_2020_3.xlsx",
}

# Categorías del módulo. Se asigna la primera cuyo patrón aparezca en el nombre
# de la hoja, en la columna de delito o en la de modalidad. El orden importa:
# "homicidio en accidente de tránsito" debe caer antes que "homicidio".
CATEGORIAS = [
    ("Homicidio en accidente de tránsito", r"HOMICIDIO.*(TRANSITO|ACCIDENTE)|TRANSITO.*HOMICIDIO|HOMICIDIO CULPOSO"),
    ("Lesiones en accidente de tránsito", r"LESION.*(TRANSITO|ACCIDENTE)|TRANSITO.*LESION|LESIONES CULPOSAS"),
    ("Homicidio", r"HOMICIDIO"),
    ("Lesiones personales", r"LESION"),
    ("Violencia intrafamiliar", r"VIOLENCIA INTRAFAMILIAR|INTRAFAMILIAR"),
    ("Delitos sexuales", r"SEXUAL|ACCESO CARNAL|ACTO SEXUAL|ACOSO SEXUAL|PORNOGRAF|PROXENET|ESTIMULO A LA PROSTITUCION"),
    ("Hurto a residencias", r"HURTO.*RESIDENCIA|RESIDENCIA"),
    ("Hurto a comercio", r"HURTO.*COMERCIO|COMERCIO"),
    ("Hurto de motocicletas", r"HURTO.*MOTO|MOTOCICLETA"),
    ("Hurto de automotores", r"HURTO.*AUTOMOTOR|AUTOMOTOR|HURTO.*VEHICULO"),
    ("Hurto a entidades financieras", r"FINANCIERA|BANCO"),
    ("Abigeato", r"ABIGEATO|CABEZAS DE GANADO|SEMOVIENTE"),
    ("Piratería terrestre", r"PIRATERIA"),
    ("Hurto a personas", r"HURTO.*PERSONA|PERSONAS|HURTO"),
    ("Extorsión", r"EXTORSION"),
    ("Secuestro", r"SECUESTRO|RETENCION ILEGAL"),
    ("Amenazas", r"AMENAZA"),
    ("Terrorismo", r"TERRORISMO"),
]

COLUMNAS = {
    "departamento": [r"^DEPARTAMENTO$", r"DEPARTAMENTO"],
    "municipio": [r"^MUNICIPIO$", r"MUNICIPIO"],
    "dane": [r"CODIGO DANE", r"COD.*DANE", r"DIVIPOLA"],
    "fecha": [r"FECHA HECHO", r"FECHA DEL HECHO", r"^FECHA$", r"FECHA"],
    "cantidad": [r"^CANTIDAD$", r"CANTIDAD", r"^TOTAL$"],
    "delito": [r"^DELITO$", r"DESCRIPCION CONDUCTA", r"CONDUCTA", r"DELITO"],
    "modalidad": [r"MODALIDAD", r"TIPO DE HURTO", r"CLASE"],
    "genero": [r"GENERO", r"^SEXO$", r"SEXO"],
    "edad": [r"AGRUPA EDAD", r"GRUPO ETARIO", r"EDAD"],
    "arma": [r"ARMAS? ?MEDIOS?", r"ARMA", r"MEDIO"],
    "zona": [r"^ZONA$", r"ZONA"],
    "barrio": [r"BARRIO"],
    "sitio": [r"CLASE ?(DE )?SITIO", r"SITIO", r"LUGAR"],
    "dia": [r"^DIA$", r"DIA SEMANA", r"DIA DE LA SEMANA"],
    "hora": [r"^HORA$", r"HORA"],
    "movil_agresor": [r"MOVIL AGRESOR"],
    "movil_victima": [r"MOVIL VICTIMA"],
}
PERFILES = ["genero", "edad", "arma", "zona", "sitio", "dia", "movil_agresor", "movil_victima", "modalidad"]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s if s is not None else ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[_\-./()]+", " ", s)).upper().strip()


def categoria(*textos) -> str | None:
    for t in textos:
        n = norm(t)
        if not n:
            continue
        for nombre, patron in CATEGORIAS:
            if re.search(patron, n):
                return nombre
    return None


def detectar_columnas(encabezados: list) -> dict:
    nombres = [norm(h) for h in encabezados]
    usadas, salida = set(), {}
    for clave, patrones in COLUMNAS.items():
        for p in patrones:
            idx = next((i for i, n in enumerate(nombres) if n and i not in usadas and re.search(p, n)), None)
            if idx is not None:
                salida[clave] = idx
                usadas.add(idx)
                break
    return salida


def a_fecha(v):
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:      # número de serie de Excel
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(v))).date()
    s = str(v).strip().split(" ")[0].split("T")[0]
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def a_cantidad(v) -> int:
    if v is None or v == "":
        return 1
    try:
        return max(0, int(round(float(str(v).replace(",", ".")))))
    except ValueError:
        return 1


def limpiar(v) -> str:
    s = re.sub(r"\s+", " ", str(v if v is not None else "")).strip()
    s = re.sub(r"\s*\(CT\)\s*$", "", s, flags=re.I)              # "Soacha (CT)" = cabecera
    if not s or norm(s) in ("NO REPORTADO", "NO REPORTA", "SIN DATO", "NAN", "NONE", "-", "NO APLICA"):
        return "No reportado"
    return s[:1].upper() + s[1:].lower() if s.isupper() else s


# ------------------------------------------------------------------ descarga
def descubrir_enlaces(sesion, desde: int) -> dict:
    enlaces = {}
    try:
        html = sesion.get(PAGINA, timeout=60).text
        for href in re.findall(r'href="([^"]+)"', html):
            h = href.replace("&amp;", "&")
            n = norm(requests_unquote(h))
            if "NIVEL DE REGISTRO" in n and re.search(r"\.(XLSX|ZIP|XLS)$", n):
                m = re.search(r"(20\d\d)", n)
                if m and int(m.group(1)) >= desde:
                    url = h if h.startswith("http") else "https://www.policia.gov.co" + h
                    enlaces.setdefault(int(m.group(1)), url)
        print(f"  página de la Policía: {len(enlaces)} archivos de registro encontrados")
    except Exception as e:  # noqa: BLE001
        print("  aviso: no se pudo leer la página de la Policía:", e)
    for anio, nombre in CONOCIDOS.items():
        if anio >= desde:
            enlaces.setdefault(anio, BASE + nombre)
    return dict(sorted(enlaces.items()))


def requests_unquote(s: str) -> str:
    from urllib.parse import unquote
    return unquote(s)


def descargar(desde: int, destino: Path) -> list[Path]:
    import requests
    destino.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X-irin Technologies; estadistica publica)"
    archivos = []
    for anio, url in descubrir_enlaces(s, desde).items():
        nombre = requests_unquote(url.rsplit("/", 1)[-1])
        ruta = destino / nombre
        if ruta.exists() and ruta.stat().st_size > 10000:
            print(f"  {anio}: ya descargado ({ruta.stat().st_size/1e6:.1f} MB)")
            archivos.append(ruta)
            continue
        for intento in range(1, 4):
            try:
                print(f"  {anio}: descargando {nombre} …", flush=True)
                r = s.get(url, timeout=600)
                r.raise_for_status()
                ruta.write_bytes(r.content)
                print(f"  {anio}: {len(r.content)/1e6:.1f} MB")
                archivos.append(ruta)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  {anio}: intento {intento} falló: {e}")
    return archivos


def libros(ruta: Path):
    """Entrega (nombre, bytes) de cada libro Excel, abriendo ZIP si hace falta."""
    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as z:
            for n in z.namelist():
                if n.lower().endswith((".xlsx", ".xlsm")) and not n.startswith("__MACOSX"):
                    yield f"{ruta.name}/{n}", z.read(n)
    elif ruta.suffix.lower() in (".xlsx", ".xlsm"):
        yield ruta.name, ruta.read_bytes()


def hojas(datos: bytes):
    """Entrega (hoja, columnas, filas) con la fila de encabezados ya encontrada."""
    wb = openpyxl.load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    for ws in wb.worksheets:
        filas = ws.iter_rows(values_only=True)
        previas = []
        cab = None
        for i, fila in enumerate(filas):
            if i > 40:
                break
            celdas = [norm(c) for c in fila]
            if any(c in ("MUNICIPIO",) or c.startswith("MUNICIPIO") for c in celdas) and \
               any(c.startswith("DEPARTAMENTO") for c in celdas):
                cab = list(fila)
                break
            previas.append(fila)
        if cab is None:
            continue
        titulo = " ".join(str(c) for f in previas for c in f if c)  # el título suele nombrar el delito
        yield ws.title, titulo, cab, filas
    wb.close()


# ------------------------------------------------------------------ proceso
def procesar(archivos: list[Path], municipio: str, desde: int, inspeccionar: bool = False):
    obj = norm(municipio)
    serie = defaultdict(Counter)                    # delito -> año -> n
    mensual = defaultdict(Counter)                  # delito -> AAAA-MM -> n
    perfil = defaultdict(lambda: defaultdict(Counter))   # delito -> campo -> valor -> n
    barrios = defaultdict(Counter)                  # delito -> barrio -> n
    horas = defaultdict(Counter)                    # delito -> franja -> n
    cund = defaultdict(lambda: defaultdict(Counter))     # delito -> año -> municipio -> n
    col_vistas, sin_categoria, fechas = {}, Counter(), []
    textos = Counter()                              # (texto del delito, categoría) en el municipio

    for ruta in archivos:
        for nombre, datos in libros(ruta):
            try:
                generador = list(hojas(datos)) if inspeccionar else hojas(datos)
            except Exception as e:  # noqa: BLE001
                print(f"  aviso: no se pudo abrir {nombre}: {e}")
                continue
            for hoja, titulo, cab, filas in generador:
                C = detectar_columnas(cab)
                col_vistas[f"{nombre} › {hoja}"] = {k: str(cab[v]) for k, v in C.items()}
                if inspeccionar:
                    print(f"\n  {nombre} › {hoja}\n    título: {titulo[:120]}\n    columnas: {[str(c) for c in cab]}\n    reconocidas: {list(C)}")
                    continue
                if "municipio" not in C or "departamento" not in C:
                    continue
                n_hoja = 0
                for fila in filas:
                    if not fila:
                        continue
                    get = lambda k: fila[C[k]] if k in C and C[k] < len(fila) else None  # noqa: E731
                    depto = norm(get("departamento"))
                    if "CUNDINAMARCA" not in depto:
                        continue
                    f = a_fecha(get("fecha"))
                    anio = f.year if f else None
                    if anio is None or anio < desde:
                        m = re.search(r"(20\d\d)", nombre)
                        anio = anio or (int(m.group(1)) if m else None)
                        if anio is None or anio < desde:
                            continue
                    cat = categoria(get("delito"), hoja, titulo, get("modalidad"))
                    if not cat:
                        sin_categoria[norm(get("delito")) or norm(hoja)] += 1
                        continue
                    n = a_cantidad(get("cantidad"))
                    mun = limpiar(get("municipio"))
                    cund[cat][anio][mun] += n
                    n_hoja += 1
                    if obj not in norm(get("municipio")):
                        continue
                    serie[cat][anio] += n
                    textos[(limpiar(get("delito")) if "delito" in C else hoja, cat)] += n
                    if f:
                        mensual[cat][f"{f.year}-{f.month:02d}"] += n
                        fechas.append(f)
                        if "dia" not in C:
                            perfil[cat]["dia"][DIAS[f.weekday()]] += n
                    for campo in PERFILES:
                        if campo in C:
                            perfil[cat][campo][limpiar(get(campo))] += n
                    if "barrio" in C:
                        barrios[cat][limpiar(get("barrio"))] += n
                    if "hora" in C:
                        h = get("hora")
                        try:
                            hh = h.hour if isinstance(h, (dt.time, dt.datetime)) else int(str(h).split(":")[0])
                            franja = ["00-06 madrugada", "06-12 mañana", "12-18 tarde", "18-24 noche"][min(3, hh // 6)]
                            horas[cat][franja] += n
                        except (ValueError, TypeError):
                            pass
                print(f"  {nombre} › {hoja}: {n_hoja:,} registros de Cundinamarca")
    return serie, mensual, perfil, barrios, horas, cund, col_vistas, sin_categoria, fechas, textos


def top(counter: Counter, n: int = 12) -> list:
    return [[k, v] for k, v in counter.most_common(n)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--municipio", default="Soacha")
    ap.add_argument("--desde", type=int, default=2020)
    ap.add_argument("--carpeta", help="Carpeta con los .xlsx/.zip ya descargados")
    ap.add_argument("--descargas", default=str(RAIZ / ".cache_policia"), help="Dónde guardar lo descargado")
    ap.add_argument("--inspeccionar", action="store_true", help="Solo mostrar hojas y columnas")
    a = ap.parse_args()

    print("Módulo 09 · Seguridad y convivencia — Policía Nacional (SIEDCO)")
    if a.carpeta:
        archivos = sorted(p for p in Path(a.carpeta).iterdir() if p.suffix.lower() in (".xlsx", ".xlsm", ".zip"))
    else:
        archivos = descargar(a.desde, Path(a.descargas))
    if not archivos:
        sys.exit("No hay archivos para procesar.")

    serie, mensual, perfil, barrios, horas, cund, cols, sin_cat, fechas, textos = procesar(
        archivos, a.municipio, a.desde, a.inspeccionar)
    if a.inspeccionar:
        return
    if not serie:
        print("\nNo se encontraron registros del municipio. Columnas detectadas por hoja:")
        for k, v in cols.items():
            print("  ", k, v)
        sys.exit(1)

    hoy = dt.date.today().isoformat()
    corte = max(fechas).isoformat() if fechas else None
    anios = sorted({y for s in serie.values() for y in s})
    delitos = {}
    for cat, _ in CATEGORIAS:
        if cat not in serie:
            continue
        p = perfil[cat]
        delitos[cat] = {
            "anual": {str(y): serie[cat].get(y, 0) for y in anios},
            "mensual": dict(sorted(mensual[cat].items())),
            "perfil": {campo: top(p[campo]) for campo in PERFILES if p.get(campo)},
            "barrios": top(barrios[cat], 25) if barrios.get(cat) else [],
            "franjas": dict(sorted(horas[cat].items())) if horas.get(cat) else {},
        }
    SALIDA.mkdir(parents=True, exist_ok=True)
    meta = {
        "generado": hoy, "corte": corte, "municipio": a.municipio, "anios": anios,
        "fuente": {"titulo": "Policía Nacional · Información de delitos a nivel de registro (SIEDCO)", "url": PAGINA},
        "nota": "Cifras sujetas a variación, en proceso de unificación con otros organismos del Estado. "
                "Solo se publican cifras agregadas; los registros individuales no salen del procesamiento.",
        "archivos": [p.name for p in archivos],
        "columnas_detectadas": cols,
        "clasificacion": [[t, c, n] for (t, c), n in textos.most_common()],
    }
    (SALIDA / "soacha.json").write_text(json.dumps({**meta, "delitos": delitos}, ensure_ascii=False, indent=1), "utf-8")

    c_out = {}
    for cat, por_anio in cund.items():
        c_out[cat] = {str(y): dict(sorted(m.items(), key=lambda kv: -kv[1])) for y, m in sorted(por_anio.items())}
    (SALIDA / "cundinamarca.json").write_text(json.dumps(
        {"generado": hoy, "corte": corte, "fuente": meta["fuente"], "delitos": c_out}, ensure_ascii=False), "utf-8")

    print(f"\n  escrito data/seguridad/soacha.json ({len(delitos)} delitos, años {anios[0]}–{anios[-1]}, corte {corte})")
    print(f"  escrito data/seguridad/cundinamarca.json ({len(c_out)} delitos)")
    if sin_cat:
        print("  sin categoría (no se publican):", sin_cat.most_common(8))
    for cat, d in delitos.items():
        print(f"    {cat:36s} " + "  ".join(f"{y}:{v:>6,}" for y, v in d["anual"].items()))


if __name__ == "__main__":
    main()
