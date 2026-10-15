"""
Diagnóstico detallado de contratación pública para cualquier municipio de Cundinamarca.

Solo incluye las entidades bajo la órbita del alcalde (Alcaldía y entidades
municipales descentralizadas). Excluye SENA, INPEC, Concejo, Personería,
hospitales ESE y demás entidades con sede en el municipio que no dependen
de la administración municipal.

Uso:
    python diagnostico_municipio.py villeta --alcalde "Bernardo Olaya Triana"
    python diagnostico_municipio.py nilo --alcalde "Nombre" --alcaldesa
Sale: diagnosticos_pdf/<municipio>_diagnostico_detallado.pdf
"""
from __future__ import annotations

import argparse
import csv
import html
import datetime as dt
import json
import re
import statistics as st
from collections import Counter
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

RAIZ = Path(__file__).resolve().parent
CONTRATOS = RAIZ / "data/cundinamarca/contratos"
RANKING = RAIZ / "data/cundinamarca/analisis/ranking_municipios.csv"
SALIDAS = RAIZ / "diagnosticos_pdf"

# Firma profesional: se usa en portada, pie de página y cierre de todos los diagnósticos.
AUTOR = "Richard Bello Roncancio"
TITULOS = ["Economista",
           "Tecnólogo en Análisis y Desarrollo de Software",
           "Candidato a Magíster en Seguridad Informática",
           "Especialista en Presupuesto, Finanzas y Contratación Pública"]
TELEFONO = "+57 320 830 3847"
CORREO = "richbello@gmail.com"

NO_PROPIAS = ("CONCEJO", "PERSONER", "CONTRALOR", "SENA", "PENITENCI", "CARCEL", "INPEC",
              "HOSPITAL", "E.S.E", "ESE ", "ICBF", "REGISTRADUR", "FISCAL", "POLICIA", "EJERCITO",
              "GOBERNACI", "DEPARTAMENT", "UNIVERSIDAD", "CORPORACION AUTONOMA", "CAR ")

CERRADOS = ("terminad", "liquidad", "cedido", "suspendid", "cerrado", "anulad")
AZUL, ROJO, GRIS, CLARO = HexColor("#1F3A5F"), HexColor("#B23A30"), HexColor("#5B6470"), HexColor("#F2F4F7")
AMBAR = HexColor("#FFF6E5")


# ---------------------------------------------------------------- datos
def propia(entidad: str) -> bool:
    e = sin_tildes(entidad.upper())
    municipal = ("ALCALD" in e or "MUNICIP" in e or "EMPRESAS PUBLICAS" in e
                 or "SERVICIOS PUBLICOS" in e)
    return municipal and not any(x in e for x in NO_PROPIAS)


def sin_tildes(t: str) -> str:
    return t.translate(str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN"))


def cargar(slug):
    d = json.loads((CONTRATOS / f"{slug}.json").read_text(encoding="utf-8"))
    cat, campos = d["catalogos"], d["campos"]
    filas = []
    for f in d["contratos"]:
        r = dict(zip(campos, f))
        for k in ("entidad", "modalidad", "tipo", "estado"):
            if isinstance(r[k], int):
                r[k] = cat[k][r[k]]
        r["objeto"] = html.escape((r["objeto"] or "").replace("\n", " ").replace("; ", ", ").strip())
        r["proveedor"] = html.escape(r["proveedor"] or "")
        r["valor"] = float(r["valor"] or 0)
        r["pagado"] = float(r["pagado"] or 0)
        filas.append(r)
    corte = dt.date.fromisoformat(d["generado"][:10])
    return [r for r in filas if propia(r["entidad"])], filas, corte, d["municipio"]


def vencido(r, hoy):
    f = r["fecha_fin"]
    return bool(f) and dt.date.fromisoformat(f[:10]) < hoy and not any(
        t in (r["estado"] or "").lower() for t in CERRADOS)


def dias(r, hoy):
    return (hoy - dt.date.fromisoformat(r["fecha_fin"][:10])).days


def benchmark(municipio):
    filas = list(csv.DictReader(open(RANKING, encoding="utf-8-sig"), delimiter=";"))
    num = lambda x: float(x.replace(",", ".")) if x else None
    rk = [r for r in filas if r["posicion"]]
    v = next((r for r in filas if r["municipio"] == municipio and r["posicion"]), None)
    if v is None:
        return None
    out = {"n": len(rk), "pos": int(num(v["posicion"]))}
    for k in ("pct_directa_valor", "pct_obras_vencidas_abiertas", "pct_con_adicion", "indice_alertas"):
        vals = sorted((num(r[k]) for r in rk if r[k]), reverse=True)
        out[k] = (num(v[k]), st.median(vals), vals.index(num(v[k])) + 1) if v[k] else None
    return out


# ---------------------------------------------------------------- formato
def pesos(x):
    return "$" + f"{x:,.0f}".replace(",", ".")


def empresa(p):
    t = p.title().replace("G&Amp;C", "G&amp;C")
    return re.sub(r"\b(Sas|S\.A\.S|Ltda|Esp|Jac)\b\.?", lambda m: m.group(0).upper(), t)


CORTOS = (("SENA", "el SENA"), ("PENITENCI", "el INPEC"), ("CARCEL", "el INPEC"), ("CONCEJO", "el Concejo"),
          ("PERSONER", "la Personería"), ("HOSPITAL", "el hospital"), ("E.S.E", "el hospital"),
          ("CONTRALOR", "la Contraloría"), ("ICBF", "el ICBF"), ("GOBERNACI", "la Gobernación"),
          ("REGISTRADUR", "la Registraduría"), ("POLICIA", "la Policía"), ("UNIVERSIDAD", "la universidad"))


def entidad_corta(e):
    u = sin_tildes(e.upper())
    return next((c for k, c in CORTOS if k in u), nombre_entidad(e))


def nombre_entidad(e):
    t = " " + e.rstrip("*").title() + " "
    for w in ("De", "Del", "La", "Las", "Los", "El", "Y", "Para", "En"):
        t = t.replace(f" {w} ", f" {w.lower()} ")
    return t.strip()


def n(x):
    return f"{x:,}".replace(",", ".")


def millones(x):
    return "$" + f"{x / 1e6:,.0f}".replace(",", ".") + " millones"


def fecha(s):
    return dt.date.fromisoformat(s[:10]).strftime("%d/%m/%Y") if s else "—"


S = {
    "t": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=AZUL),
    "st": ParagraphStyle("st", fontName="Helvetica", fontSize=10.5, leading=14, textColor=GRIS),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=AZUL,
                        spaceBefore=10, spaceAfter=5),
    "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13.2, alignment=TA_LEFT),
    "pc": ParagraphStyle("pc", fontName="Helvetica", fontSize=8, leading=10),
    "pcb": ParagraphStyle("pcb", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=white),
    "nota": ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=8, leading=10.5, textColor=GRIS),
    "kpi": ParagraphStyle("kpi", fontName="Helvetica-Bold", fontSize=18, leading=21, textColor=ROJO),
    "kpil": ParagraphStyle("kpil", fontName="Helvetica", fontSize=8.3, leading=10.5, textColor=GRIS),
}


def link(url, texto="Ver en SECOP"):
    return Paragraph(f'<link href="{url}" color="#1F5FBF"><u>{texto}</u></link>', S["pc"])


def tabla(datos, anchos, cabecera=AZUL, zebra=True):
    t = Table(datos, colWidths=anchos, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), cabecera),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#D5DAE1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if zebra:
        estilo.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CLARO]))
    t.setStyle(TableStyle(estilo))
    return t


def caja(contenido, fondo=AMBAR, borde=HexColor("#E3B341")):
    t = Table([[contenido]], colWidths=[18.6 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fondo),
                           ("BOX", (0, 0), (-1, -1), 0.8, borde),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GRIS)
    canvas.drawString(1.5 * cm, 1.0 * cm,
                      f"Fuente: SECOP II (datos.gov.co) · Análisis: {AUTOR}, {TITULOS[0]} · {TELEFONO}")
    canvas.drawRightString(20.1 * cm, 1.0 * cm, f"Página {doc.page}")
    canvas.restoreState()


# ---------------------------------------------------------------- hallazgos
TIPO_TXT = {"Obra": "obra", "Suministros": "suministro", "Consultoría": "consultoría",
            "Interventoría": "interventoría", "Compraventa": "compraventa"}


def valores_repetidos(M, hoy):
    """Grupo más relevante de >=3 contratos (no prestación de servicios) con el mismo valor
    (redondeado a miles), mismo tipo y misma entidad, firmados en un lapso <= 90 días."""
    grupos = {}
    for r in M:
        if (r["tipo"] not in ("Obra", "Suministros", "Consultoría", "Interventoría", "Compraventa")
                or r["valor"] < 20e6 or not r["fecha_firma"]):
            continue
        grupos.setdefault((r["entidad"], r["tipo"], round(r["valor"], -3)), []).append(r)
    candidatos = []
    for (_, tipo, valor), rs in grupos.items():
        rs.sort(key=lambda r: r["fecha_firma"])
        for a in range(len(rs)):
            ventana = [r for r in rs[a:] if (dt.date.fromisoformat(r["fecha_firma"][:10])
                       - dt.date.fromisoformat(rs[a]["fecha_firma"][:10])).days <= 90]
            if len(ventana) >= 3:
                candidatos.append((tipo == "Obra", len(ventana) * valor, ventana))
                break
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: (c[0], c[1]))[2]


# ---------------------------------------------------------------- documento
def construir(slug, alcalde=None, femenino=False):
    M, todas, hoy, municipio = cargar(slug)
    B = benchmark(municipio)
    P = lambda t, s="p": Paragraph(t, S[s])
    h = []
    cargo = "Alcaldesa" if femenino else "Alcalde"
    tratamiento = f"{'la señora' if femenino else 'el señor'} {cargo}"

    valor_m = sum(r["valor"] for r in M)
    V = [r for r in M if vencido(r, hoy)]
    v_sin_pago = sum(1 for r in V if r["pagado"] == 0)
    ps = [r for r in V if r["tipo"] == "Prestación de servicios"]
    otros6 = sorted([r for r in V if r["tipo"] != "Prestación de servicios" and dias(r, hoy) > 180],
                    key=lambda r: -r["valor"])
    directa = [r for r in M if "irecta" in r["modalidad"]]
    obras = [r for r in M if r["tipo"] == "Obra"]
    obras_v = [r for r in obras if vencido(r, hoy)]
    repetidos = valores_repetidos(M, hoy)
    ids = {id(r) for r in M}
    excluidas = Counter(r["entidad"] for r in todas if id(r) not in ids)
    incluidas = Counter(r["entidad"] for r in M)

    # ---------- Página 1: portada y resumen
    destinatario = (f"Preparado para {tratamiento} <b>{alcalde}</b>" if alcalde
                    else f"Preparado para la Alcaldía Municipal de {municipio}")
    h += [P("Diagnóstico de contratación pública", "t"),
          P(f"Municipio de {municipio}, Cundinamarca", "t"), Spacer(1, 4),
          P(f"{destinatario} · Corte de datos: {fecha(str(hoy))} · Periodo: 01/01/2024 a la fecha "
            "de corte", "st"),
          Spacer(1, 3),
          P(f"Elaborado por <b>{AUTOR}</b> — {' · '.join(TITULOS)}", "st"),
          Spacer(1, 10)]

    nombres = sorted(incluidas, key=lambda e: -incluidas[e])
    lista = ", ".join(nombre_entidad(e) for e in nombres)
    fuera = (f" Se dejaron por fuera {n(sum(excluidas.values()))} contratos de entidades que tienen "
             "sede en el municipio pero no dependen de la administración (" +
             ", ".join(dict.fromkeys(entidad_corta(e) for e in excluidas)) + ")." if excluidas else "")
    h.append(P(
        f"Este documento revisa los <b>{n(len(M))}</b> contratos registrados en SECOP II por "
        f"{lista}, por un valor de <b>{millones(valor_m)}</b>.{fuera} Todo lo que aparece aquí es "
        "información pública: cada contrato citado trae su enlace directo a SECOP II para verificarlo.",
        "p"))
    h.append(Spacer(1, 10))

    kpis = [
        (n(len(V)), f"contratos con fecha de terminación vencida que SECOP II sigue mostrando como "
         f"abiertos ({len(V) / len(M) * 100:.0f}% del total)"),
        (f"{len(obras_v)} de {len(obras)}", "contratos de obra aparecen abiertos después de su fecha "
         f"de fin ({sum(1 for r in obras_v if r['pagado'] == 0)} sin pagos reportados)"),
        (f"{len(directa) / len(M) * 100:.0f}%", f"de los contratos se adjudicaron por contratación "
         f"directa ({sum(r['valor'] for r in directa) / valor_m * 100:.0f}% del valor)"),
    ]
    celdas = [[P(a, "kpi") for a, _ in kpis], [P(t, "kpil") for _, t in kpis]]
    tk = Table(celdas, colWidths=[6.2 * cm] * 3)
    tk.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLARO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LINEAFTER", (0, 0), (1, -1), 0.6, white),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, 0), 8),
                            ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]))
    h += [tk, Spacer(1, 12)]

    h.append(P(f"Cómo se ve {municipio} frente a los demás municipios", "h"))
    if B:
        h.append(P(f"Comparación con los {B['n']} municipios de Cundinamarca que tienen suficientes "
                   "contratos en SECOP II para medirse (misma metodología para todos; en esta tabla se "
                   "cuentan todas las entidades con sede en cada municipio).", "p"))
        h.append(Spacer(1, 5))
        fila = lambda nombre, k, fmt: ([P(nombre, "pc"), P(fmt(B[k][0]), "pc"), P(fmt(B[k][1]), "pc"),
                                        P(f"{B[k][2]} de {B['n']}", "pc")] if B[k] else
                                       [P(nombre, "pc"), P("sin dato", "pc"), P("", "pc"), P("", "pc")])
        pct = lambda x: f"{x:.1f}%".replace(".", ",")
        h.append(tabla([
            [P(x, "pcb") for x in ("Indicador", municipio, "Mediana departamental", "Puesto (1 = más alto)")],
            fila("Obras con plazo vencido y aún abiertas en SECOP", "pct_obras_vencidas_abiertas", pct),
            fila("Valor adjudicado por contratación directa", "pct_directa_valor", pct),
            fila("Contratos con adiciones de plazo", "pct_con_adicion", pct),
            fila("Índice compuesto de alertas (0-100)", "indice_alertas", lambda x: f"{x:.1f}".replace(".", ",")),
        ], [7.6 * cm, 2.6 * cm, 4 * cm, 4.4 * cm]))
        h.append(Spacer(1, 6))
        if B["pct_obras_vencidas_abiertas"] and B["pct_directa_valor"]:
            h.append(P(f"{municipio} ocupa el puesto {B['pct_obras_vencidas_abiertas'][2]} del departamento "
                       f"en obras vencidas y abiertas, y el puesto {B['pct_directa_valor'][2]} en valor "
                       "adjudicado por contratación directa. Son indicadores que los entes de control usan "
                       "para escoger a quién revisar primero.", "p"))
    else:
        h.append(P(f"{municipio} no tiene suficientes contratos en SECOP II en el periodo para entrar "
                   "en el ranking departamental (mínimo 30), por lo que no se incluye la comparación.", "p"))

    # ---------- Página 2: obras
    h.append(PageBreak())
    h.append(P("Hallazgo 1 · Contratos de obra", "h"))
    if obras:
        contratistas = Counter(r["proveedor"] for r in obras)
        repiten = [(p_, k) for p_, k in contratistas.most_common() if k > 1][:3]
        txt_rep = (" Se repiten: " + ", ".join(f"{empresa(p_)} ({k})" for p_, k in repiten) + "."
                   if repiten else "")
        h.append(P(
            f"En el periodo se firmaron <b>{len(obras)} contratos de obra</b> por "
            f"<b>{millones(sum(r['valor'] for r in obras))}</b>, adjudicados a {len(contratistas)} "
            f"contratistas.{txt_rep} <b>{len(obras_v)} siguen figurando abiertos</b> en SECOP II después "
            f"de su fecha de terminación, y {sum(1 for r in obras_v if r['pagado'] == 0)} de ellos no "
            "tienen ningún pago reportado en la plataforma.", "p"))
        h.append(Spacer(1, 6))
        muestra = sorted(sorted(obras_v, key=lambda r: -r["valor"])[:14]
                         or sorted(obras, key=lambda r: -r["valor"])[:14], key=lambda r: r["fecha_firma"])
        h.append(P(f"{'Las obras vencidas y abiertas' if obras_v else 'Las obras'} de mayor valor:", "p"))
        h.append(Spacer(1, 4))
        filas = [[P(x, "pcb") for x in ("Contrato", "Firma", "Contratista", "Valor", "Fin pactado",
                                         "Estado en SECOP", "")]]
        for r in muestra[:12]:
            rojo = vencido(r, hoy)
            filas.append([P(f"<b>{r['numero']}</b>", "pc"), P(fecha(r["fecha_firma"]), "pc"),
                          P(empresa(r["proveedor"]), "pc"), P(pesos(r["valor"]), "pc"),
                          P(fecha(r["fecha_fin"]), "pc"),
                          P(f'<font color="#B23A30"><b>{r["estado"]}</b></font>' if rojo else r["estado"], "pc"),
                          link(r["url"])])
        h.append(tabla(filas, [3.2 * cm, 1.7 * cm, 3.6 * cm, 2.6 * cm, 1.8 * cm, 2.1 * cm, 2.2 * cm]))
    else:
        h.append(P("No hay contratos de tipo obra registrados en el periodo.", "p"))
    h.append(Spacer(1, 8))

    if repetidos:
        v0 = repetidos[0]["valor"]
        d1 = dt.date.fromisoformat(repetidos[0]["fecha_firma"][:10])
        d2 = dt.date.fromisoformat(repetidos[-1]["fecha_firma"][:10])
        semanas = max(1, round((d2 - d1).days / 7))
        h.append(caja(P(
            f"<b>Punto de atención:</b> {len(repetidos)} contratos de tipo "
            f"{TIPO_TXT[repetidos[0]['tipo']]} ({', '.join(r['numero'] for r in repetidos)}) tienen "
            f"prácticamente el mismo valor, <b>{pesos(v0)}</b>, y se firmaron en un lapso de "
            f"{semanas} semana{'s' if semanas > 1 else ''}. Un patrón así no prueba ninguna "
            "irregularidad, pero es de los primeros que revisa un auditor de la Contraloría para "
            "descartar fraccionamiento de contratos. Conviene tener documentada la justificación "
            "técnica de cada uno antes de que se la pidan.", "p")))
        h.append(Spacer(1, 10))

    grandes = sorted([r for r in obras_v if r["valor"] > 2e8], key=lambda r: -r["valor"])[:3]
    if grandes:
        h.append(P("Hallazgo 2 · Las obras vencidas de mayor valor, en detalle", "h"))
        for r in grandes:
            h.append(P(
                f"<b>Contrato {r['numero']}</b> — {r['objeto'].capitalize()[:170]}. Contratista: "
                f"{empresa(r['proveedor'])}. Valor: <b>{pesos(r['valor'])}</b>. Fin pactado: "
                f"{fecha(r['fecha_fin'])} ({dias(r, hoy)} días atrás). Prórrogas registradas: "
                f"{r['dias_adic'] or 0} días. Estado en SECOP: <b>{r['estado']}</b>; pagos reportados: "
                f"{'ninguno' if r['pagado'] == 0 else pesos(r['pagado'])}. "
                f'<link href="{r["url"]}" color="#1F5FBF"><u>Ver en SECOP</u></link>', "p"))
            h.append(Spacer(1, 5))

    # ---------- Cierres pendientes (salta de página solo si no queda espacio)
    h.append(CondPageBreak(9 * cm))
    num_h = 3 if grandes else 2
    h.append(P(f"Hallazgo {num_h} · Contratos terminados que SECOP II sigue mostrando abiertos", "h"))
    h.append(P(
        f"De los {n(len(V))} contratos con fecha de fin vencida y sin estado de cierre, "
        f"<b>{n(len(ps))} son de prestación de servicios</b>. Estos no requieren liquidación, pero "
        "su estado en SECOP II debe reflejar la terminación; mientras no se actualice, la plataforma "
        "muestra a la entidad con contratos \"en ejecución\" que ya no lo están. "
        f"Hay <b>{n(len(otros6))} contratos de otro tipo</b> (suministros, obras, convenios, consultorías "
        f"y otros) con más de seis meses vencidos, que suman <b>{millones(sum(r['valor'] for r in otros6))}"
        "</b>. Para los que requieren liquidación, el plazo bilateral y unilateral del artículo 11 de la "
        "Ley 1150 de 2007 ya habría corrido, y cada uno es una pregunta segura en una auditoría. Además, "
        f"{n(v_sin_pago)} de los {n(len(V))} contratos vencidos no tienen ningún pago registrado en SECOP II.",
        "p"))
    if otros6:
        h.append(Spacer(1, 6))
        h.append(P(f"Los {min(6, len(otros6))} de mayor valor (excluyendo prestación de servicios):", "p"))
        h.append(Spacer(1, 4))
        filas = [[P(x, "pcb") for x in ("Contrato", "Tipo", "Objeto (resumen)", "Valor", "Vencido hace", "")]]
        for r in otros6[:6]:
            filas.append([P(f"<b>{r['numero']}</b>", "pc"), P(r["tipo"], "pc"),
                          P(r["objeto"].capitalize()[:95] + "…", "pc"), P(pesos(r["valor"]), "pc"),
                          P(f"{dias(r, hoy)} días", "pc"), link(r["url"])])
        h.append(tabla(filas, [2.4 * cm, 2.1 * cm, 7.3 * cm, 2.6 * cm, 1.9 * cm, 2.3 * cm]))
    h.append(Spacer(1, 10))

    firma = [P(f"<b>{AUTOR}</b>", "p")] + [P(t, "pc") for t in TITULOS] + [
        Spacer(1, 3), P(f"Celular y WhatsApp: {TELEFONO} · Correo: {CORREO}", "pc")]
    h.append(KeepTogether([
        P("Lo que este diagnóstico dice y lo que no dice", "h"),
        P(f"Dice qué muestra hoy SECOP II sobre la contratación de {municipio} y cómo se compara con el "
          "resto del departamento. No afirma que haya irregularidades: muchos de estos casos pueden ser "
          "contratos ya ejecutados cuyo cierre no se ha cargado en la plataforma. Pero para un ente de "
          "control la diferencia entre \"obra inconclusa\" y \"obra terminada sin registrar\" solo se "
          "resuelve con soportes, y la carga de demostrarlo recae en la entidad.", "p"),
        Spacer(1, 8),
        P("Qué propongo", "h"),
        P("Una revisión mensual de la contratación del municipio en SECOP II, hecha con la mirada de "
          "quien ha trabajado en presupuesto y contratación pública, que entregue: (1) la lista de "
          "contratos que vencen en los próximos 30 días y de los que ya vencieron sin cierre, con "
          "responsable sugerido; (2) alertas de los patrones que miran los entes de control (valores "
          "repetidos, concentración en pocos contratistas, adiciones recurrentes, contratación directa); "
          f"y (3) la posición de {municipio} frente a los demás municipios mes a mes, para medir el avance.",
          "p"),
        Spacer(1, 6),
        P("Le propongo una <b>videollamada de 20 minutos</b> para revisar juntos, en SECOP II y en "
          "tiempo real, los contratos de este documento. Sin costo y sin compromiso.", "p"),
        Spacer(1, 10),
        *firma,
        Spacer(1, 8),
        P("Cómo verificar cualquier dato: haga clic en \"Ver en SECOP\" junto a cada contrato, o busque "
          "el número de proceso en community.secop.gov.co (Búsqueda pública de procesos). Los datos "
          "agregados provienen del conjunto abierto SECOP II – Contratos Electrónicos en datos.gov.co.",
          "nota"),
    ]))

    SALIDAS.mkdir(exist_ok=True)
    salida = SALIDAS / f"{slug}_diagnostico_detallado.pdf"
    doc = SimpleDocTemplate(str(salida), pagesize=letter, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.7 * cm,
                            title=f"Diagnóstico de contratación pública – {municipio}", author=AUTOR)
    doc.build(h, onFirstPage=pie, onLaterPages=pie)
    print(f"{municipio}: incluidas {dict(incluidas)}")
    print(f"{municipio}: excluidas {dict(excluidas)}")
    print("OK", salida)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("municipios", nargs="+", help="slug del archivo, ej. villeta")
    ap.add_argument("--alcalde", help="nombre del alcalde o alcaldesa (solo si se genera un municipio)")
    ap.add_argument("--alcaldesa", action="store_true", help="usar tratamiento femenino")
    a = ap.parse_args()
    for m in a.municipios:
        construir(m, a.alcalde if len(a.municipios) == 1 else None, a.alcaldesa)
