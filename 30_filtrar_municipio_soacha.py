"""Genera brujula_datos_soacha.json y brujula_analisis_soacha.json
a partir de los archivos de los exportadores 07 y 08, dejando solo Soacha.
No inventa cifras: solo filtra y recalcula totales de Soacha."""
import json, sys

src_datos, src_anal, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
MUN = "SOACHA"

D = json.load(open(src_datos, encoding="utf-8"))
A = json.load(open(src_anal, encoding="utf-8"))
TD = D["territorios"]["CUNDINAMARCA"]
TA = A["territorios"]["CUNDINAMARCA"]
S = TD["unidades"].index(MUN)
assert TA["unidades"][S] == MUN

# ---------- Datos por puesto (exportador 07) ----------
viejo_a_nuevo = {}
puestos = []
for i, p in enumerate(TD["puestos"]):
    if p["l"] == S:
        viejo_a_nuevo[i] = len(puestos)
        puestos.append(p)

corp_d = {}
for corp, v in TD["corp"].items():
    cands = []
    for c in v["candidatos"]:
        p = [[viejo_a_nuevo[i], n] for i, n in c.get("p", []) if i in viejo_a_nuevo]
        if not p:
            continue
        c2 = dict(c)
        c2["p"] = sorted(p, key=lambda x: -x[1])
        c2["v"] = sum(n for _, n in p)
        if corp == "ASAMBLEA":
            c2["v19"] = None  # el dato 2019 del archivo es departamental, no de Soacha
        cands.append(c2)
    cands.sort(key=lambda c: -c["v"])
    nv = {k: val for k, val in v.items() if k != "candidatos"}
    nv["candidatos"] = cands
    corp_d[corp] = nv

# ---------- Alcaldía (sin votos por puesto en las fuentes: resultado municipal) ----------
# Nombres de las personas detrás de cada grupo significativo de ciudadanos / coalición.
# Si un grupo no está aquí se muestra con el nombre del grupo, tal como lo reporta la Registraduría.
NOMBRES = {
    "PERICO": "VÍCTOR JULIÁN SÁNCHEZ (PERICO)",
    "PARA AVANZAR MAS": "DANY RENÉ CAICEDO",
    "COALICION PACTO HISTORICO ALIANZA VERDE": "HEINER DE JESÚS GAITÁN PARRA",
    "RESCATEMOS A SOACHA": "GLORIA BETTY ZORRO",
    "SOACHA CIUDAD PODEROSA": "JUAN CARLOS SALDARRIAGA GAVIRIA",
    "ALIANZA POR SOACHA": "JORGE GIOVANNY RAMÍREZ MOYA",
}
AL = TA["corp"].get("ALCALDE")
if AL:
    uni = next(u for u in AL["unidades"] if u["i"] == S)
    def carrera(col, validos):
        out = []
        for p in AL["partidos"]:
            r = next((u for u in p.get("u", []) if u[0] == S), None)
            if r and (r[col] or 0) > 0:
                v = r[3] if col == 2 else round(r[1] * validos)
                out.append({"n": NOMBRES.get(p["n"], p["n"]), "pt": p["n"], "v": v, "s": r[col]})
        return sorted(out, key=lambda x: -x["v"])
    c23 = carrera(2, uni["m23"]["validos"])
    c19 = carrera(1, uni["m19"]["validos"])
    corp_d["ALCALDE"] = {
        "ambito": "territorio",
        "candidatos": [{**x, "v19": None, "p": [], "l": S} for x in c23],
        "carrera": {"anio": D["meta"]["anio"], "previo": D["meta"]["anio_previo"],
                    "m23": uni["m23"], "m19": uni["m19"], "c23": c23, "c19": c19},
    }

datos = {
    "version": D["version"],
    "meta": {**D["meta"], "filtro": MUN},
    "territorios": {"SOACHA": {
        "nombre": "Soacha", "unidad": "municipio", "municipio": True, "unidades": TD["unidades"],
        "puestos": puestos, "corp": corp_d}},
}

# ---------- Análisis por partido (exportador 08) ----------
an, ap = str(A["meta"]["anio"]), str(A["meta"]["anio_previo"])
corp_a = {}
for corp, v in TA["corp"].items():
    uni = next((u for u in v["unidades"] if u["i"] == S), None)
    if uni is None:
        continue
    partidos = []
    for p in v["partidos"]:
        r = next((u for u in p.get("u", []) if u[0] == S), None)
        if not r or not ((r[1] or 0) > 0 or (r[2] or 0) > 0):
            continue
        s19, s23 = r[1] or 0, r[2] or 0
        v19 = 0 if p["v"][0] == 0 else round(s19 * uni["m19"]["validos"])
        partidos.append({"n": p["n"], "v": [v19, r[3]], "s": [s19, s23], "u": [r]})
    partidos.sort(key=lambda p: -p["s"][1])
    corp_a[corp] = {"ambito": v["ambito"],
                    "total": {ap: uni["m19"], an: uni["m23"]},
                    "partidos": partidos, "unidades": [uni]}

anal = {
    "tipo": "analisis", "version": A["version"],
    "meta": {**A["meta"], "filtro": MUN},
    "territorios": {"SOACHA": {"nombre": "Soacha", "unidad": "municipio", "municipio": True,
                               "unidades": TA["unidades"], "corp": corp_a}},
}

for nombre, obj in [("brujula_datos_soacha.json", datos), ("brujula_analisis_soacha.json", anal)]:
    with open(f"{out_dir}/{nombre}", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

# ---------- Resumen para revisión ----------
print("Puestos de votación en Soacha:", len(puestos))
for corp, v in corp_d.items():
    tot = sum(c["v"] for c in v["candidatos"])
    print(f"{corp}: {len(v['candidatos'])} candidatos/listas, {tot:,} votos en Soacha")
for corp, v in corp_a.items():
    m = v["total"][an]
    print(f"\nANÁLISIS {corp} {an}: válidos {m['validos']:,}, blanco {m['blanco']:.1%}")
    for p in v["partidos"][:5]:
        print(f"   {p['n'][:50]:50s} {p['v'][1]:>7,}  {p['s'][1]:.2%}")
