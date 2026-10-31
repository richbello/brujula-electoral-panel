"""
Modulo 10 - Contratistas de Soacha frente al RUES.

Lee los contratos SECOP II de Soacha (data/cundinamarca/contratos/soacha.json)
y deja en data/soacha/rues/:

  base.json      contratistas con NIT (valor, contratos, entidades, modalidad)
                 e indice de personas naturales con contratos en Soacha
                 (para cruzar las cedulas de los representantes legales).
  snapshot.json  filas del RUES ya consultadas, para que la pagina muestre
                 algo aunque datos.gov.co no responda. La pagina consulta el
                 RUES en vivo para todos los NIT al abrirse.

Uso:  python etl_rues_soacha.py [snapshot.txt]
      snapshot.txt es opcional: filas separadas por | con las columnas de RUES_COLS.
"""
import json, re, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SRC = Path("data/cundinamarca/contratos/soacha.json")
OUT = Path("data/soacha/rues")
RUES_COLS = ["nit", "razon_social", "camara_comercio", "matricula", "tipo_sociedad",
             "organizacion_juridica", "categoria_matricula", "estado_matricula",
             "fecha_matricula", "fecha_renovacion", "ultimo_ano_renovado",
             "cod_ciiu_act_econ_pri", "cod_ciiu_act_econ_sec", "representante_legal",
             "num_identificacion_representante_legal"]

ASOC = re.compile(r"CONSORCIO|UNION TEMPORAL|UNIÓN TEMPORAL|\bU\.?T\.?\b")
PUB = re.compile(r"MUNICIPIO|DEPARTAMENTO|GOBERNACI|ALCALD|SECRETAR|\bE\.?S\.?E\b|EMPRESA SOCIAL DEL ESTADO|"
                 r"INSTITUTO MUNICIPAL|INSTITUTO DE |EPUXUA|FONDO DE DESARROLLO|E\.?I\.?C\.?E|AGENCIA NACIONAL|"
                 r"MINISTERIO|POLICIA|EJERCITO|UNIVERSIDAD NACIONAL|UNIVERSIDAD DE CUNDINAMARCA|\bSENA\b|"
                 r"AGUAS DE BOGOTA|EMPRESA DE ACUEDUCTO|REGISTRADUR|CONTRALOR|PERSONER|CONCEJO|NOTARIA|RTVC|"
                 r"SERVICIOS POSTALES|IMPRENTA NACIONAL|ENTERRITORIO|FINDETER|CAJA DE COMPENSACION|COMPENSAR|"
                 r"COLSUBSIDIO|CAFAM")
NIT_RX = re.compile(r"^[89]\d{8}\d?$")


def clase(nombre):
    u = nombre.upper()
    if ASOC.search(u): return "asociacion"
    if PUB.search(u): return "publica"
    return "privado"


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    cat, campos = d["catalogos"], d["campos"]
    ix = {c: i for i, c in enumerate(campos)}
    ent_cat = cat["entidad"]; tipo_cat = cat["tipo"]; mod_cat = cat["modalidad"]

    nits = {}
    personas = {}
    for row in d["contratos"]:
        doc = re.sub(r"\D", "", str(row[ix["doc_prov"]] or ""))
        if not doc: continue
        valor = row[ix["valor"]] or 0
        fecha = row[ix["fecha_firma"]] or ""
        url = row[ix["url"]] or ""
        m = re.search(r"noticeUID=([^&]+)", url)
        uid = m.group(1) if m else ""
        if NIT_RX.match(doc):
            nit = doc[:9]
            n = nits.setdefault(nit, {"nit": nit, "nombres": defaultdict(int), "n": 0, "valor": 0, "pagado": 0,
                                      "entidades": defaultdict(int), "directa": 0, "primera": fecha, "ultima": fecha,
                                      "objeto": "", "vobj": -1, "contratos": []})
            n["nombres"][row[ix["proveedor"]] or ""] += 1
            n["n"] += 1; n["valor"] += valor; n["pagado"] += row[ix["pagado"]] or 0
            n["entidades"][row[ix["entidad"]]] += 1
            if "irecta" in mod_cat[row[ix["modalidad"]]]: n["directa"] += 1
            if fecha and (not n["primera"] or fecha < n["primera"]): n["primera"] = fecha
            if fecha and fecha > n["ultima"]: n["ultima"] = fecha
            if valor > n["vobj"]: n["vobj"] = valor; n["objeto"] = (row[ix["objeto"]] or "")[:220]
            n["contratos"].append([row[ix["numero"]], row[ix["entidad"]], row[ix["modalidad"]], row[ix["tipo"]],
                                   valor, fecha, uid])
        else:
            p = personas.setdefault(doc, [(row[ix["proveedor"]] or "")[:60], []])
            p[1].append([row[ix["entidad"]], row[ix["tipo"]], round(valor), fecha, uid])

    lista = []
    for n in nits.values():
        nombre = max(n["nombres"].items(), key=lambda kv: kv[1])[0]
        n["contratos"].sort(key=lambda c: -c[4])
        lista.append({"nit": n["nit"], "nombre": nombre, "clase": clase(nombre), "n": n["n"],
                      "valor": round(n["valor"]), "pagado": round(n["pagado"]), "directa": n["directa"],
                      "entidades": sorted(n["entidades"], key=lambda e: -n["entidades"][e]),
                      "primera": n["primera"], "ultima": n["ultima"], "objeto": n["objeto"],
                      "contratos": n["contratos"][:15]})
    lista.sort(key=lambda x: -x["valor"])

    OUT.mkdir(parents=True, exist_ok=True)
    base = {"municipio": "Soacha", "periodo_desde": d.get("periodo_desde"), "fuente_contratos": "SECOP II",
            "generado": datetime.now().isoformat(timespec="seconds"),
            "catalogos": {"entidad": ent_cat, "tipo": tipo_cat, "modalidad": mod_cat},
            "contratistas": lista, "personas": personas}
    (OUT / "base.json").write_text(json.dumps(base, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    if len(sys.argv) > 1:
        filas = []
        for linea in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
            p = linea.split("|")
            if len(p) == len(RUES_COLS): filas.append(dict(zip(RUES_COLS, p)))
        snap = {"consultado": datetime.now().date().isoformat(), "fuente": "datos.gov.co c82u-588k", "filas": filas}
        (OUT / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"{len(lista)} NIT ({sum(x['clase']=='privado' for x in lista)} privados), {len(personas)} personas")


if __name__ == "__main__":
    main()
