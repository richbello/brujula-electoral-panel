"""
Diagnóstico detallado de contratación pública — Villeta (Cundinamarca).

Solo incluye las entidades bajo la órbita del alcalde (Alcaldía, Instituto
Municipal de Turismo/Cultura/Deporte y Empresa de Servicios Públicos).
Excluye SENA, INPEC, Concejo y Personería, que tienen sede en el municipio
pero no dependen de la administración municipal.

Uso:  python diagnostico_villeta.py
Sale: diagnosticos_pdf/villeta_diagnostico_detallado.pdf
"""
from __future__ import annotations

import csv
import html
import datetime as dt
import json
import statistics as st
from collections import Counter
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

RAIZ = Path(__file__).resolve().parent
CONTRATOS = RAIZ / "data/cundinamarca/contratos/villeta.json"
RANKING = RAIZ / "data/cundinamarca/analisis/ranking_municipios.csv"
SALIDA = RAIZ / "diagnosticos_pdf/villeta_diagnostico_detallado.pdf"

CERRADOS = ("terminad", "liquidad", "cedido", "suspendid", "cerrado", "anulad")
AZUL, ROJO, GRIS, CLARO = HexColor("#1F3A5F"), HexColor("#B23A30"), HexColor("#5B6470"), HexColor("#F2F4F7")
AMBAR = HexColor("#FFF6E5")


# ---------------------------------------------------------------- datos
def cargar():
    d = json.loads(CONTRATOS.read_text(encoding="utf-8"))
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
    propias = cat["entidad"][:3]          # Alcaldía, Instituto, ESP
    corte = dt.date.fromisoformat(d["generado"][:10])
    return [r for r in filas if r["entidad"] in propias], filas, corte


def vencido(r, hoy):
    f = r["fecha_fin"]
    return bool(f) and dt.date.fromisoformat(f[:10]) < hoy and not any(
        t in (r["estado"] or "").lower() for t in CERRADOS)


def dias(r, hoy):
    return (hoy - dt.date.fromisoformat(r["fecha_fin"][:10])).days


def benchmark():
    filas = list(csv.DictReader(open(RANKING, encoding="utf-8-sig"), delimiter=";"))
    num = lambda x: float(x.replace(",", ".")) if x else None
    rk = [r for r in filas if r["posicion"]]
    v = next(r for r in filas if r["municipio"] == "Villeta")
    out = {"n": len(rk), "pos": int(num(v["posicion"]))}
    for k in ("pct_directa_valor", "pct_obras_vencidas_abiertas", "pct_con_adicion", "indice_alertas"):
        vals = sorted((num(r[k]) for r in rk if r[k]), reverse=True)
        out[k] = (num(v[k]), st.median(vals), vals.index(num(v[k])) + 1)
    return out


# ---------------------------------------------------------------- formato
def pesos(x):
    return "$" + f"{x:,.0f}".replace(",", ".")


def empresa(p):
    t = p.title()
    for a, b in ((" Sas", " SAS"), (" S.A.S", " S.A.S"), ("G&Amp;C", "G&amp;C")):
        t = t.replace(a, b)
    return t


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
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRIS)
    canvas.drawString(1.5 * cm, 1.0 * cm,
                      "Fuente: SECOP II – Contratos Electrónicos (datos.gov.co). "
                      "Análisis: Richard Bello Roncancio · +57 320 830 3847")
    canvas.drawRightString(20.1 * cm, 1.0 * cm, f"Página {doc.page}")
    canvas.restoreState()


# ---------------------------------------------------------------- documento
def construir():
    M, todas, hoy = cargar()
    B = benchmark()
    P = lambda t, s="p": Paragraph(t, S[s])
    h = []

    valor_m = sum(r["valor"] for r in M)
    V = [r for r in M if vencido(r, hoy)]
    v_sin_pago = sum(1 for r in V if r["pagado"] == 0)
    ps = [r for r in V if r["tipo"] == "Prestación de servicios"]
    otros6 = sorted([r for r in V if r["tipo"] != "Prestación de servicios" and dias(r, hoy) > 180],
                    key=lambda r: -r["valor"])
    directa = [r for r in M if "irecta" in r["modalidad"]]
    vias = sorted([r for r in M if r["tipo"] == "Obra" and "VÍA" in r["objeto"].upper()
                   and ("VEREDA" in r["objeto"].upper() or "RURALES" in r["objeto"].upper())
                   and r["fecha_firma"][:4] == "2025"], key=lambda r: r["fecha_firma"])
    vias_v = [r for r in vias if vencido(r, hoy)]
    iguales = [r for r in vias if round(r["valor"]) in (99996984, 99996983)]
    contratistas_vias = Counter(r["proveedor"] for r in vias)
    ids = {id(r) for r in M}
    excluidas = Counter(r["entidad"] for r in todas if id(r) not in ids)

    # ---------- Página 1: portada y resumen
    h += [P("Diagnóstico de contratación pública", "t"),
          P("Municipio de Villeta, Cundinamarca", "t"), Spacer(1, 4),
          P(f"Preparado para el señor Alcalde <b>Bernardo Olaya Triana</b> · Corte de datos: "
            f"{fecha(str(hoy))} · Periodo: 01/01/2024 a la fecha de corte", "st"),
          Spacer(1, 10)]

    h.append(P(
        f"Este documento revisa los <b>{n(len(M))}</b> contratos registrados en SECOP II por la "
        f"Alcaldía de Villeta, el Instituto Municipal de Turismo, Cultura, Recreación y Deporte y la "
        f"Empresa de Servicios Públicos, por un valor de <b>{millones(valor_m)}</b>. Se dejaron por "
        f"fuera los contratos del SENA, el INPEC, el Concejo y la Personería, que tienen sede en el "
        f"municipio pero no dependen de la administración. Todo lo que aparece aquí es información "
        f"pública: cada contrato citado trae su enlace directo a SECOP II para verificarlo.", "p"))
    h.append(Spacer(1, 10))

    kpis = [
        (n(len(V)), f"contratos con fecha de terminación vencida que SECOP II "
         f"sigue mostrando como abiertos ({len(V) / len(M) * 100:.0f}% del total)"),
        (f"{len(vias_v)} de {len(vias)}", "obras de vías rurales de 2025 aparecen abiertas meses "
         "después de su fecha de fin, sin pagos reportados"),
        (f"{len(directa) / len(M) * 100:.0f}%", f"de los contratos se adjudicaron por contratación "
         f"directa ({sum(r['valor'] for r in directa) / valor_m * 100:.0f}% del valor)"),
    ]
    celdas = [[P(n, "kpi") for n, _ in kpis], [P(t, "kpil") for _, t in kpis]]
    tk = Table(celdas, colWidths=[6.2 * cm] * 3)
    tk.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLARO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LINEAFTER", (0, 0), (1, -1), 0.6, white),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, 0), 8),
                            ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]))
    h += [tk, Spacer(1, 12)]

    h.append(P("Cómo se ve Villeta frente a los demás municipios", "h"))
    h.append(P(f"Comparación con los {B['n']} municipios de Cundinamarca que tienen suficientes "
               "contratos en SECOP II para medirse (misma metodología para todos; en esta tabla se "
               "cuentan todas las entidades con sede en cada municipio).", "p"))
    h.append(Spacer(1, 5))
    fila = lambda nombre, k, fmt: [P(nombre, "pc"), P(fmt(B[k][0]), "pc"), P(fmt(B[k][1]), "pc"),
                                   P(f"{B[k][2]} de {B['n']}", "pc")]
    pct = lambda x: f"{x:.1f}%".replace(".", ",")
    h.append(tabla([
        [P(x, "pcb") for x in ("Indicador", "Villeta", "Mediana departamental", "Puesto (1 = más alto)")],
        fila("Obras con plazo vencido y aún abiertas en SECOP", "pct_obras_vencidas_abiertas", pct),
        fila("Valor adjudicado por contratación directa", "pct_directa_valor", pct),
        fila("Contratos con adiciones de plazo", "pct_con_adicion", pct),
        fila("Índice compuesto de alertas (0-100)", "indice_alertas", lambda x: f"{x:.1f}".replace(".", ",")),
    ], [7.6 * cm, 2.6 * cm, 4 * cm, 4.4 * cm]))
    h.append(Spacer(1, 6))
    h.append(P(f"Villeta ocupa el puesto {B['pct_obras_vencidas_abiertas'][2]} del departamento en obras vencidas y "
               f"abiertas, y el puesto {B['pct_directa_valor'][2]} en valor adjudicado por contratación directa. "
               "Son exactamente los indicadores con los que un ente de control escoge a quién revisar "
               "primero.", "p"))

    # ---------- Página 2: vías rurales
    h.append(PageBreak())
    h.append(P("Hallazgo 1 · Once obras de vías rurales contratadas en 2025", "h"))
    h.append(P(
        f"Entre abril y noviembre de 2025 la Alcaldía firmó <b>{len(vias)} contratos de obra</b> "
        f"para mejorar vías entre veredas, por <b>{millones(sum(r['valor'] for r in vias))}</b>, todos "
        f"por selección abreviada de menor cuantía. Los adjudicaron "
        f"{len(contratistas_vias)} firmas; tres de ellas se repiten "
        f"({', '.join(f'{empresa(p)} ({k})' for p, k in contratistas_vias.most_common(3))}). "
        f"<b>{len(vias_v)} siguen figurando abiertos</b> en SECOP II después de su fecha de "
        "terminación y ninguno tiene pagos reportados en la plataforma.", "p"))
    h.append(Spacer(1, 6))
    filas = [[P(x, "pcb") for x in ("Contrato", "Firma", "Contratista", "Valor", "Fin pactado",
                                     "Estado en SECOP", "")]]
    for r in vias:
        rojo = vencido(r, hoy)
        filas.append([P(f"<b>{r['numero']}</b>", "pc"), P(fecha(r["fecha_firma"]), "pc"),
                      P(empresa(r["proveedor"]), "pc"), P(pesos(r["valor"]), "pc"),
                      P(fecha(r["fecha_fin"]), "pc"),
                      P(f'<font color="#B23A30"><b>{r["estado"]}</b></font>' if rojo else r["estado"], "pc"),
                      link(r["url"])])
    h.append(tabla(filas, [1.9 * cm, 1.8 * cm, 4.2 * cm, 2.7 * cm, 1.9 * cm, 2.6 * cm, 2.4 * cm]))
    h.append(Spacer(1, 8))
    h.append(caja(P(
        f"<b>Punto de atención:</b> {len(iguales)} de estos contratos ("
        f"{', '.join(r['numero'] for r in iguales)}) tienen prácticamente el mismo valor, "
        f"<b>$99.996.984</b>, el mismo tipo de objeto y se firmaron en un lapso de seis semanas. "
        "Un patrón así no prueba ninguna irregularidad, pero es de los primeros que revisa un auditor "
        "de la Contraloría para descartar fraccionamiento de contratos. Conviene que la administración "
        "tenga documentada la justificación técnica de cada tramo antes de que se la pidan.", "p")))
    h.append(Spacer(1, 10))

    h.append(P("Hallazgo 2 · Obras urbanas de mayor valor", "h"))
    grandes = sorted([r for r in M if r["tipo"] == "Obra" and vencido(r, hoy) and r["valor"] > 5e8],
                     key=lambda r: -r["valor"])
    for r in grandes:
        h.append(P(
            f"<b>Contrato {r['numero']}</b> — {r['objeto'].capitalize()[:170]}. Contratista: "
            f"{empresa(r['proveedor'])}. Valor: <b>{pesos(r['valor'])}</b>. Fin pactado: "
            f"{fecha(r['fecha_fin'])} ({dias(r, hoy)} días atrás). Prórrogas registradas: "
            f"{r['dias_adic'] or 0} días. Estado en SECOP: <b>{r['estado']}</b>; pagos reportados: "
            f"{'ninguno' if r['pagado'] == 0 else pesos(r['pagado'])}. "
            f'<link href="{r["url"]}" color="#1F5FBF"><u>Ver en SECOP</u></link>', "p"))
        h.append(Spacer(1, 5))

    # ---------- Página 3: cierres pendientes
    h.append(PageBreak())
    h.append(P("Hallazgo 3 · Contratos terminados que SECOP II sigue mostrando abiertos", "h"))
    h.append(P(
        f"De los {n(len(V))} contratos con fecha de fin vencida y sin estado de cierre, "
        f"<b>{n(len(ps))} son de prestación de servicios</b>. Estos no requieren liquidación, pero "
        "su estado en SECOP II debe reflejar la terminación; mientras no se actualice, la plataforma "
        "muestra a la entidad con cientos de contratos \"en ejecución\" que ya no lo están. "
        f"Los <b>{len(otros6)} contratos restantes</b> (suministros, obras, convenios, consultorías y "
        f"otros) llevan más de seis meses vencidos y suman <b>{millones(sum(r['valor'] for r in otros6))}"
        "</b>. Para ellos el plazo de liquidación bilateral y unilateral del artículo 11 de la Ley 1150 "
        "de 2007 ya habría corrido, y cada uno es una pregunta segura en una auditoría. Además, "
        f"{n(v_sin_pago)} de los {n(len(V))} contratos vencidos no tienen ningún pago registrado en SECOP II.", "p"))
    h.append(Spacer(1, 6))
    h.append(P("Los ocho de mayor valor (excluyendo prestación de servicios):", "p"))
    h.append(Spacer(1, 4))
    filas = [[P(x, "pcb") for x in ("Contrato", "Tipo", "Objeto (resumen)", "Valor", "Vencido hace", "")]]
    for r in otros6[:8]:
        filas.append([P(f"<b>{r['numero']}</b>", "pc"), P(r["tipo"], "pc"),
                      P(r["objeto"].capitalize()[:95] + "…", "pc"), P(pesos(r["valor"]), "pc"),
                      P(f"{dias(r, hoy)} días", "pc"), link(r["url"])])
    h.append(tabla(filas, [2.4 * cm, 2.1 * cm, 7.3 * cm, 2.6 * cm, 1.9 * cm, 2.3 * cm]))
    h.append(Spacer(1, 10))

    h.append(KeepTogether([
        P("Lo que este diagnóstico dice y lo que no dice", "h"),
        P("Dice qué muestra hoy SECOP II sobre la contratación de Villeta y cómo se compara con el resto "
          "del departamento. No afirma que haya irregularidades: muchos de estos casos pueden ser "
          "contratos ya ejecutados cuyo cierre no se ha cargado en la plataforma. Pero para un ente de "
          "control la diferencia entre \"obra inconclusa\" y \"obra terminada sin registrar\" solo se "
          "resuelve con soportes, y la carga de demostrarlo recae en la entidad.", "p"),
        Spacer(1, 8),
        P("Qué propongo", "h"),
        P("Una revisión mensual de la contratación del municipio en SECOP II que entregue: (1) la lista "
          "de contratos que vencen en los próximos 30 días y de los que ya vencieron sin cierre, con "
          "responsable sugerido; (2) alertas de patrones que miran los entes de control (valores "
          "repetidos, concentración en pocos contratistas, adiciones recurrentes, contratación directa); "
          "y (3) la posición de Villeta frente a los demás municipios mes a mes, para medir el avance.",
          "p"),
        Spacer(1, 6),
        P("Le propongo una <b>videollamada de 20 minutos</b> para revisar juntos, en SECOP II y en "
          "tiempo real, los contratos de este documento. Sin costo y sin compromiso.", "p"),
        Spacer(1, 8),
        P("<b>Richard Bello Roncancio</b> · Economista, especialista en presupuesto y contratación "
          "pública · +57 320 830 3847 (llamada y WhatsApp) · richbello@gmail.com", "p"),
        Spacer(1, 6),
        P("Cómo verificar cualquier dato: haga clic en \"Ver en SECOP\" junto a cada contrato, o busque "
          "el número de proceso en community.secop.gov.co (Búsqueda pública de procesos). Los datos "
          "agregados provienen del conjunto abierto SECOP II – Contratos Electrónicos en datos.gov.co.",
          "nota"),
    ]))

    SALIDA.parent.mkdir(exist_ok=True)
    doc = SimpleDocTemplate(str(SALIDA), pagesize=letter, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.7 * cm,
                            title="Diagnóstico de contratación pública – Villeta",
                            author="Richard Bello Roncancio")
    doc.build(h, onFirstPage=pie, onLaterPages=pie)
    print("Excluidas:", dict(excluidas))
    print("OK", SALIDA)


if __name__ == "__main__":
    construir()
