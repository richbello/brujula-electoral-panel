import os, re, shutil
from datetime import datetime
repo = r"C:\RICHARD\RB\2026\brujula-panel-web"
os.chdir(repo)
m = {"#2C3E2E":"#0F1C2E","#1f2b22":"#0F1C2E","#1F2E20":"#0A1626","#26352a":"#13273D","#34463a":"#1E3A57","#3A5A3F":"#1E3A57","#233145":"#1C2A3F","#eef1f5":"#F4F6F9","#f5f3ec":"#F4F6F9","#F9F8F4":"#F4F6F9","#eef0ea":"#F4F6F9","#dde3ec":"#E2E8F0","#e3dfd3":"#E2E8F0","#E8E4DB":"#E2E8F0","#c4cedb":"#CBD5E1","#6a7688":"#6B7A90","#667067":"#6B7A90","#7A8A7B":"#6B7A90","#93a0b2":"#94A3B8","#C9A961":"#C8A560","#c8a25a":"#C8A560","#A88A4F":"#A98841","#9c7a38":"#A98841","#f5f3ed":"#F4EDDA","#f3ead6":"#F4EDDA","#2f7d5b":"#2E9E7B","#e7f1ea":"#E4F3EC","#a4503c":"#C0485A","#f3e4df":"#F6E3E6","#b5852a":"#BE8A2C","#f7efd9":"#F7EFDA","#6B8E23":"#5E8ABF"}
files=[]
for root,dirs,fs in os.walk(repo):
    dirs[:]=[d for d in dirs if d!=".git" and not d.startswith("_backup")]
    for n in fs:
        if n.endswith((".html",".css",".js")): files.append(os.path.join(root,n))
print("Archivos encontrados:",len(files))
b=os.path.join(repo,"_backup_colores_"+datetime.now().strftime("%Y%m%d_%H%M%S"))
for p in files:
    dest=os.path.join(b,os.path.relpath(p,repo))
    os.makedirs(os.path.dirname(dest),exist_ok=True)
    shutil.copy2(p,dest)
print("Backup:",b)
c=0
for p in files:
    t=open(p,"r",encoding="utf-8").read()
    o=t
    for old,new in m.items(): t=re.sub(re.escape(old),new,t,flags=re.IGNORECASE)
    if t!=o:
        open(p,"w",encoding="utf-8").write(t)
        c+=1
        print("  recoloreado:",os.path.basename(p))
print("Archivos modificados:",c)
os.system("git add -A")
os.system('git commit -m "Tema Medianoche: recoloreo navy champan"')
os.system("git push")
print("Push hecho. Refresca con Ctrl+Shift+R en 1-2 min")
