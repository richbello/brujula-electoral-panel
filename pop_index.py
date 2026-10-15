#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acentos vividos en la portada: header degradado, titulo con degradado,
barra de color por tarjeta y sombras de color en hover."""
import io, os, re

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
t = io.open(p, encoding="utf-8").read()

# 1) tokens extra de acento
t = t.replace(
    "--ok:#00C97B;--warn:#EA6A0A}",
    "--ok:#00C97B;--warn:#EA6A0A;"
    "--g1:#7C4DFF;--g2:#B026FF;--g3:#FF2D6F;--g4:#00B2FF;--g5:#00E676}"
)

# 2) header con degradado + filo de color
t = t.replace(
    "header{background:var(--navy);color:#fff}",
    "header{background:linear-gradient(120deg,#150B3D 0%,#2E1A7A 45%,#5B21B6 100%);"
    "color:#fff;border-bottom:3px solid var(--gold);"
    "box-shadow:0 6px 28px rgba(124,77,255,.35)}"
)

# 3) marca del logo con brillo
t = t.replace(
    ".mark{width:38px;height:38px;border:2px solid var(--gold);border-radius:50%;"
    "display:grid;place-items:center}",
    ".mark{width:38px;height:38px;border:2px solid var(--gold);border-radius:50%;"
    "display:grid;place-items:center;background:radial-gradient(circle,"
    "rgba(255,176,32,.28),transparent 70%);box-shadow:0 0 16px rgba(255,176,32,.55)}"
)

# 4) H1 con degradado de texto
t = t.replace(
    "h1{font-size:34px;font-weight:700;margin:10px 0;letter-spacing:-.02em}",
    "h1{font-size:34px;font-weight:700;margin:10px 0;letter-spacing:-.02em;"
    "background:linear-gradient(95deg,#150B3D 0%,#7C4DFF 55%,#FF2D6F 100%);"
    "-webkit-background-clip:text;background-clip:text;color:transparent;"
    "display:inline-block}"
)

# 5) eyebrow y titulos de seccion mas encendidos
t = t.replace(
    "color:var(--gold)}\nh1{", "color:#B026FF}\nh1{"
)
t = t.replace(
    ".sec h3{font-size:12px;font-weight:600;letter-spacing:.08em;"
    "text-transform:uppercase;color:var(--muted);",
    ".sec h3{font-size:12px;font-weight:700;letter-spacing:.08em;"
    "text-transform:uppercase;color:#7C4DFF;"
)

# 6) tarjetas: barra superior de color + hover con sombra de color
t = t.replace(
    ".card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:26px;",
    ".card{position:relative;overflow:hidden;background:#fff;border:1px solid var(--line);"
    "border-radius:12px;padding:26px;"
)
t = t.replace(
    ".card:hover{border-color:var(--gold);box-shadow:0 10px 30px rgba(15,28,46,.08);"
    "transform:translateY(-2px)}",
    ".card::before{content:'';position:absolute;inset:0 0 auto 0;height:5px;"
    "background:var(--accent,var(--g1))}\n"
    ".card:hover{border-color:var(--accent,var(--g1));"
    "box-shadow:0 16px 38px -8px var(--accent,var(--g1));transform:translateY(-4px)}\n"
    ".card:nth-child(1){--accent:var(--g1)}.card:nth-child(2){--accent:var(--g4)}\n"
    ".card:nth-child(3){--accent:var(--g3)}.card:nth-child(4){--accent:var(--g2)}\n"
    ".card:nth-child(5){--accent:var(--g5)}"
)
t = t.replace(
    ".num{font-size:13px;font-weight:700;color:var(--gold)}",
    ".num{font-size:13px;font-weight:800;color:var(--accent,var(--g1));"
    "font-size:15px;letter-spacing:.04em}"
)
t = t.replace(
    ".card:hover .go{color:var(--gold)}",
    ".card:hover .go{color:var(--accent,var(--g1))}"
)

# 7) chips con mas contraste
t = t.replace(
    ".real{background:#D6FBEC;color:var(--ok)}.demo{background:#FFF0CC;color:var(--warn)}",
    ".real{background:linear-gradient(135deg,#00E676,#00C97B);color:#06301F}"
    ".demo{background:linear-gradient(135deg,#FFC53D,#FF8A00);color:#3A1A00}"
)

io.open(p, "w", encoding="utf-8").write(t)
print("portada: acentos vividos aplicados")
