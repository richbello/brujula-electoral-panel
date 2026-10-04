import os, re
repo = r"C:\RICHARD\RB\2026\brujula-panel-web"
os.chdir(repo)
# Archivos principales (NO backups)
files = [
    "index.html",
    "analisis-electoral-2027-embed.html",
    "analisis-electoral-2027.html",
    "soacha-2027.html",
    "soacha-2027-temp.html",
    "js/analisis-soacha.js"
]
c = 0
for p in files:
    if not os.path.exists(p): continue
    t = open(p,"r",encoding="utf-8").read()
    o = t
    # Reemplazos
    t = t.replace("Brújula <b>Electoral</b>", "Estrategia <b>Electoral 2027</b>")
    t = t.replace("Brújula Electoral", "Estrategia Electoral 2027")
    t = t.replace("Panel de fuerza por puesto de votación", "Panel de Estrategia Electoral 2027")
    if t != o:
        open(p,"w",encoding="utf-8").write(t)
        c += 1
        print("  actualizado:", p)
print("Archivos modificados:", c)
os.system("git add -A")
os.system("git commit -m \"Cambiar titulo: Brujula Electoral -> Estrategia Electoral 2027\"")
os.system("git push")
print("Push hecho. Refresca en 1-2 min")
