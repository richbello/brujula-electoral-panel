import os, re
repo = r"C:\RICHARD\RB\2026\brujula-panel-web"
os.chdir(repo)
files = []
for root,dirs,fs in os.walk(repo):
    dirs[:] = [d for d in dirs if d != ".git" and not d.startswith("_backup")]
    for n in fs:
        if n.endswith((".html",".js")): files.append(os.path.join(root,n))
print("Archivos encontrados:", len(files))
c = 0
for p in files:
    t = open(p,"r",encoding="utf-8").read()
    o = t
    t = re.sub(r"Brújula Electoral", "Estrategia Electoral 2027", t, flags=re.IGNORECASE)
    t = re.sub(r"brujula electoral", "estrategia electoral 2027", t, flags=re.IGNORECASE)
    t = re.sub(r"Panel de fuerza por puesto de votación", "Panel de Estrategia Electoral 2027", t)
    if t != o:
        open(p,"w",encoding="utf-8").write(t)
        c += 1
        print("  actualizado:", os.path.basename(p))
print("Archivos modificados:", c)
os.system("git add -A")
os.system("git commit -m \"Cambiar titulo: Brujula Electoral -> Estrategia Electoral 2027\"")
os.system("git push")
print("Push hecho. Refresca en 1-2 min con Ctrl+Shift+R")
