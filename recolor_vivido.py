#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tema VIVIDO — recoloreo de la paleta navy/oro mate a indigo-violeta + ambar
electrico, esmeralda y magenta. Mismo patron que recolor.py: backup, sustitucion
de hex en .html/.css/.js, y reporte.

Marcas intactas: #1877F2 (Facebook), #FF0000 (YouTube), #000000, #FFFFFF.
"""
import os, re, shutil, sys
from datetime import datetime

repo = os.path.dirname(os.path.abspath(__file__))
os.chdir(repo)

m = {
    # ---------- estructura: navy apagado -> indigo/violeta profundo ----------
    "#0F1C2E": "#150B3D",   # --navy / --ink  (base de header y titulos)
    "#0A1626": "#0D0628",   # --ink-2
    "#0E1A2B": "#140A38",
    "#0C1523": "#0C0526",
    "#132033": "#1A0F45",
    "#13273D": "#241465",
    "#1A2A42": "#1F1150",
    "#1B2B40": "#20124F",
    "#1C2A3F": "#241552",   # --text
    "#1E3A57": "#2E1A7A",
    "#20344C": "#26155C",
    "#223349": "#281663",
    "#2A3D55": "#30197A",
    "#33445C": "#3A1F8C",
    "#274D80": "#3B23A6",
    "#3D4A40": "#3B3560",

    # ---------- acento principal: oro mate -> ambar electrico ----------
    "#C8A560": "#FFB020",   # --gold / --brass
    "#A98841": "#E08A00",   # --brass-deep
    "#CF9A41": "#F59E0B",
    "#E0B45F": "#FFC53D",
    "#8A5A12": "#B45309",
    "#6B5418": "#92400E",
    "#231802": "#2B1400",
    # tintes calidos
    "#F4EDDA": "#FFF3D6",   # --brass-soft
    "#FBF1E0": "#FFF0CC",
    "#F0E2C2": "#FFE8B0",
    "#F0DDB8": "#FFE3A3",
    "#ECDFC4": "#FFEBC2",
    "#EAD9A8": "#FFDE94",
    "#E7D4A8": "#FFD98C",
    "#E3D3AB": "#FFDFA0",
    "#FBF7EE": "#FFF8E8",
    "#FAF9F5": "#FFFBF0",
    "#FFF3CD": "#FFF0BF",
    "#FFC107": "#FFC400",
    "#FF9800": "#FF8A00",
    "#E68900": "#F57C00",

    # ---------- positivo: verde apagado -> esmeralda vivo ----------
    "#2E9E7B": "#00C97B",   # --ok
    "#27AE60": "#09BF5C",
    "#2F7A45": "#0E9F52",
    "#245C43": "#0B7A47",
    "#6A9F4F": "#4CBF4A",
    "#E6F4EF": "#D6FBEC",
    "#E4F3EC": "#D2FAE8",
    "#CFE4D8": "#B4F5D9",
    "#DFE8DF": "#DCF7E6",
    "#C9D1C8": "#C2E8D4",
    "#C6D2C6": "#BFE7D2",

    # ---------- negativo: ladrillo -> magenta/rojo encendido ----------
    "#C0485A": "#FF2D6F",   # --bad / --down
    "#E74C3C": "#FF3B30",
    "#A2402F": "#D62246",
    "#7A3A2C": "#A3153A",
    "#C6763F": "#F2682A",
    "#8B0000": "#C8003C",   # --crit
    "#F6E3E6": "#FFE0EA",
    "#F9E5E8": "#FFDCE7",
    "#FFE6E6": "#FFDEE8",
    "#E9D2CB": "#FFD5DF",
    "#FEF2F2": "#FFF0F4",
    "#FECACA": "#FFC2D4",

    # ---------- advertencia: ocre -> naranja intenso ----------
    "#BE8A2C": "#F97316",   # --warn
    "#B7791F": "#EA6A0A",
    "#F7EFDA": "#FFEBD6",

    # ---------- azules de apoyo -> azur/cian electrico ----------
    "#5E8ABF": "#3B82F6",
    "#7C9CC9": "#60A5FA",
    "#4A72A8": "#2563EB",
    "#B9CBE4": "#A5C8FF",
    "#2563EB": "#1D4ED8",

    # ---------- gradientes existentes: subir saturacion ----------
    "#667EEA": "#7C4DFF",
    "#764BA2": "#B026FF",
    "#F093FB": "#FF6EC7",
    "#F5576C": "#FF2D6F",
    "#4FACFE": "#00B2FF",
    "#00F2FE": "#00E5FF",
    "#43E97B": "#00E676",
    "#38F9D7": "#00F5D4",

    # ---------- fondos y lineas: tinte violeta ----------
    "#F4F6F9": "#F3F1FF",   # --bg / --paper
    "#F7F9FC": "#F6F4FF",
    "#F8FAFC": "#F7F5FF",
    "#F2F5F9": "#F2EFFF",
    "#F1F5F9": "#F1EEFF",
    "#EEF1F5": "#EFEBFF",
    "#FAFBFC": "#FAF8FF",
    "#F9F9F9": "#F8F6FF",
    "#F5F5F5": "#F5F2FF",
    "#E2E8F0": "#E0D9F7",   # --line
    "#E2E7EE": "#E0D9F7",
    "#E8EDF4": "#E7DFFB",
    "#E8EEF6": "#E7DFFB",
    "#CDD7E4": "#CBBCEE",
    "#CBD5E1": "#C9BAED",   # --line-strong
    "#B7C4D6": "#B3A0E6",

    # ---------- textos secundarios: gris azul -> gris violeta ----------
    "#6B7A90": "#6B5E90",   # --muted
    "#5B6B80": "#5C4F82",
    "#6B7D95": "#6A5D93",
    "#94A3B8": "#9A8CC0",   # --muted-2
    "#8FA0B7": "#9184BC",
    "#93A4BB": "#9487BE",
    "#9FB0C6": "#A294C9",
    "#7D8EA6": "#7D6FA8",
    "#AEB9C8": "#B4A6DB",
    "#334155": "#3A2D66",
}

SKIP = {"#1877F2", "#FF0000", "#000000", "#FFFFFF", "#1A1A1A"}
for k in SKIP:
    m.pop(k, None)

files = []
for root, dirs, fs in os.walk(repo):
    dirs[:] = [d for d in dirs if d != ".git" and not d.startswith("_backup")]
    for n in fs:
        if n.endswith((".html", ".css", ".js")):
            files.append(os.path.join(root, n))
print("Archivos encontrados:", len(files))

b = os.path.join(repo, "_backup_colores_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
for p in files:
    dest = os.path.join(b, os.path.relpath(p, repo))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(p, dest)
print("Backup:", b)

c = 0
total = 0
for p in files:
    t = open(p, "r", encoding="utf-8").read()
    o = t
    n_file = 0
    for old, new in m.items():
        t, k = re.subn(re.escape(old), new, t, flags=re.IGNORECASE)
        n_file += k
    if t != o:
        open(p, "w", encoding="utf-8").write(t)
        c += 1
        total += n_file
        print("  recoloreado: %-42s %3d cambios" % (os.path.basename(p), n_file))
print("Archivos modificados: %d  |  sustituciones: %d" % (c, total))
