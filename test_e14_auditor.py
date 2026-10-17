#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica las reglas de e14_auditor.py con actas armadas a mano, sin red ni API.

Ejecutar:  python test_e14_auditor.py
"""
import sys, json, copy, tempfile, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import e14_auditor as e14

fallos = []
def check(nombre, ok, detalle=""):
    print(f"  {'OK  ' if ok else 'FALLA'}  {nombre}{'  ' + detalle if detalle else ''}")
    if not ok:
        fallos.append(nombre)

def tipos(h):
    return [x["tipo"] for x in h]

# Acta limpia: 2 listas, todo cuadra.
#   lista 001: logo 10 + (20 + 5) = 35
#   lista 005: logo 8 + (30 + 12) = 50
#   35 + 50 + blanco 6 + nulos 3 + no marcados 1 = 95 = urna = E-11
LIMPIA = {
    "zona": "1", "puesto": "5", "mesa": "12", "puesto_nombre": "Colegio X",
    "sufragantes_e11": 95, "votos_urna": 95,
    "listas": [
        {"codigo": "001", "votos_lista": 10, "candidatos": {"101": 20, "102": 5}, "total": 35},
        {"codigo": "005", "votos_lista": 8, "candidatos": {"501": 30, "502": 12}, "total": 50},
    ],
    "blanco": 6, "nulos": 3, "no_marcados": 1, "total_votos": 95,
    "firmas_jurados": 3, "enmendaduras": [], "legible": True, "confianza": 0.95,
}

print("\n[1] Acta limpia")
check("mesa_id con ceros", e14.mesa_id(LIMPIA) == "01-005-012", e14.mesa_id(LIMPIA))
check("sin hallazgos internos", e14.reglas_internas(LIMPIA) == [], str(tipos(e14.reglas_internas(LIMPIA))))

print("\n[2] Errores aritmeticos")
a = copy.deepcopy(LIMPIA); a["listas"][1]["total"] = 60
h = e14.reglas_internas(a)
check("total de lista mal sumado -> suma_lista", "suma_lista" in tipos(h))
sl = next(x for x in h if x["tipo"] == "suma_lista")
check("  diferencia +10 en lista 005", sl["diferencia"] == 10 and sl["lista"] == "005", str(sl))
check("  arrastra suma de mesa (60 != 50)", "suma_mesa" in tipos(h))

a = copy.deepcopy(LIMPIA); a["total_votos"] = 99
h = e14.reglas_internas(a)
check("total de mesa mal -> suma_mesa", "suma_mesa" in tipos(h))
check("  y no coincide con urna", "total_vs_urna" in tipos(h))

print("\n[3] Urna vs E-11")
a = copy.deepcopy(LIMPIA); a["sufragantes_e11"] = 90
h = e14.reglas_internas(a)
u = [x for x in h if x["tipo"] == "urna_vs_e11"]
check("5 votos de mas", u and u[0]["diferencia"] == 5, str(u))
check("  severidad alta", u and u[0]["severidad"] == "alta")

print("\n[4] Valores no numericos del jurado")
check("'-' es None", e14._int("-") is None)
check("'--' es None", e14._int("--") is None)
check("' 12 ' es 12", e14._int(" 12 ") == 12)
check("'1.204' es 1204", e14._int("1.204") == 1204)
a = copy.deepcopy(LIMPIA); a["listas"][0]["candidatos"]["102"] = "-"; a["listas"][0]["total"] = 30
a["total_votos"] = 90; a["votos_urna"] = 90; a["sufragantes_e11"] = 90
check("guion cuenta como 0 en sumas", e14.reglas_internas(a) == [], str(tipos(e14.reglas_internas(a))))

print("\n[5] Enmendaduras, firmas, legibilidad")
a = copy.deepcopy(LIMPIA)
a["enmendaduras"] = [{"campo": "lista 005 total", "lista": "005", "detalle": "tachado"}]
a["firmas_jurados"] = 1; a["confianza"] = 0.5
t = tipos(e14.reglas_internas(a))
check("enmendadura", "enmendadura" in t)
check("firmas insuficientes", "firmas" in t)
check("ilegible por confianza baja", "ilegible" in t)
check("min_firmas configurable", "firmas" not in tipos(e14.reglas_internas(a, min_firmas=1)))

print("\n[6] Comparacion con escrutinio")
esc = {("005", "501"): 22, ("005", "TOTAL"): 42, ("001", "TOTAL"): 35, ("BLANCO", ""): 6}
h = e14.comparar(LIMPIA, esc, "dif_escrutinio", "escrutinio")
check("dos diferencias (candidato y total)", len(h) == 2, str([x["detalle"] for x in h]))
c = next(x for x in h if x.get("candidato") == "501")
check("  le quitaron 8 al candidato 501", c["diferencia"] == -8, str(c))
check("  impacto foco 005 = 8 (sin doble conteo)", e14.impacto_foco(h, "005") == 8)
check("  solo candidato tambien cuenta", e14.impacto_foco([c], "005") == 8)
check("  impacto otra lista = 0", e14.impacto_foco(h, "001") == 0)

print("\n[7] CSV largo")
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "e24.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["mesa_id", "lista", "candidato", "votos"])
        w.writerow(["01-005-012", "005", "501", "22"]); w.writerow(["01-005-012", "blanco", "", "6"])
        w.writerow(["01-005-012", "005", "total", "42"]); w.writerow(["01-005-012", "001", "102", "-"])
    x = e14.leer_csv_largo(p)
    check("lee candidato", x["01-005-012"][("005", "501")] == 22)
    check("normaliza BLANCO y TOTAL", ("BLANCO", "") in x["01-005-012"] and ("005", "TOTAL") in x["01-005-012"])
    check("ignora guiones", ("001", "102") not in x["01-005-012"])

print("\n[8] Reglas de conjunto")
base = []
for i in range(20):
    a = copy.deepcopy(LIMPIA); a["mesa"] = str(i + 1)
    a["listas"][0]["candidatos"]["101"] += i  # que no sean gemelas
    a["listas"][0]["total"] += i; a["total_votos"] += i; a["votos_urna"] += i; a["sufragantes_e11"] += i
    base.append(a)
# lista minoritaria 009 arrasa en una mesa
rara = copy.deepcopy(LIMPIA); rara["mesa"] = "50"
rara["listas"].append({"codigo": "009", "votos_lista": 10, "candidatos": {"901": 80}, "total": 90})
rara["listas"][0].update(votos_lista=1, candidatos={"101": 1, "102": 0}, total=2)
rara["listas"][1].update(votos_lista=1, candidatos={"501": 1, "502": 0}, total=2)
rara["total_votos"] = rara["votos_urna"] = rara["sufragantes_e11"] = 104
# nulos disparados
nul = copy.deepcopy(base[5]); nul["mesa"] = "60"; nul["nulos"] += 40; nul["total_votos"] += 40
nul["votos_urna"] += 40; nul["sufragantes_e11"] += 40
gem = copy.deepcopy(base[7]); gem["mesa"] = "70"
r = e14.reglas_conjunto(base + [rara, nul, gem])
check("concentracion en la mesa rara", any(x["tipo"] == "concentracion" for x in r.get("01-005-050", [])))
check("  ninguna mesa normal marcada por concentracion",
      not any(x["tipo"] == "concentracion" for k, v in r.items() if k != "01-005-050" for x in v))
check("nulos atipicos", any(x["tipo"] == "nulos_atipicos" for x in r.get("01-005-060", [])))
check("mesa gemela en ambas", all(any(x["tipo"] == "mesa_gemela" for x in r.get(k, []))
                                  for k in ("01-005-008", "01-005-070")))

print("\n[9] Auditoria completa y demo")
res = e14.auditar([LIMPIA, a], escrutinio={"01-005-012": esc}, foco="005")
check("resumen cuenta actas", res["resumen"]["actas"] == 2)
check("ordena por severidad", res["mesas"][0]["severidad"] in ("alta", "media"))
check("votos en juego del foco", res["resumen"]["votos_en_juego_foco"] == 8, str(res["resumen"]))
actas, pre, esc2 = e14.generar_demo()
dem = e14.auditar(actas, pre, esc2, foco="005", meta={"demo": True})
pt = dem["resumen"]["por_tipo"]
for t in ("suma_lista", "suma_mesa", "urna_vs_e11", "enmendadura", "firmas", "ilegible",
          "dif_escrutinio", "dif_preconteo", "concentracion", "nulos_atipicos", "mesa_gemela"):
    check(f"demo produce {t}", pt.get(t, 0) > 0, str(pt.get(t, 0)))
check("demo es serializable", len(json.dumps(dem)) > 1000)
neg = [m["mesa_id"] for m in dem["mesas"] if any(v < 0 for v in m["validos_por_lista"].values())]
check("demo sin votos negativos", not neg, str(neg[:3]))

print(f"\n{'TODO OK' if not fallos else str(len(fallos)) + ' FALLAS: ' + ', '.join(fallos)}")
sys.exit(1 if fallos else 0)
