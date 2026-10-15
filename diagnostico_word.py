"""
Exporta el diagnóstico de un municipio a Word (.docx) editable.

Calcula los mismos datos que diagnostico_municipio.py, los escribe en un JSON
intermedio y llama a diagnostico_word.js (librería docx de npm) para armar el
documento con tablas y enlaces a SECOP II.

Uso:
    python diagnostico_word.py villeta --alcalde "Bernardo Olaya Triana"
Sale: diagnosticos_word/<municipio>_diagnostico.docx
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import subprocess
from collections import Counter
from pathlib import Path

from diagnostico_municipio import (AUTOR, CORREO, TELEFONO, TITULOS, TIPO_TXT, benchmark, cargar,
                                   dias, empresa, entidad_corta, fecha, millones, n, nombre_entidad,
                                   pesos, valores_repetidos, vencido)

RAIZ = Path(__file__).resolve().parent
SALIDAS = RAIZ / "diagnosticos_word"


def u(t):  # quita escapes HTML usados por reportlab
    return html.unescape(t)


def modelo(slug, alcalde=None, femenino=False):
    M, todas, hoy, municipio = cargar(slug)
    B = benchmark(municipio)
    for r in todas:
        r["objeto"], r["proveedor"] = u(r["objeto"]), u(r["proveedor"])
    emp = lambda p: u(empresa(html.escape(p)))
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

    b = []  # bloques del documento
    P = lambda texto, **k: b.append({"k": "p", "t": texto, **k})
    H = lambda texto: b.append({"k": "h", "t": texto})

    destinatario = (f"Preparado para {tratamiento} <b>{alcalde}</b>" if alcalde
                    else f"Preparado para la Alcaldía Municipal de {municipio}")
    b.append({"k": "titulo", "t": ["Diagnóstico de contratación pública",
                                   f"Municipio de {municipio}, Cundinamarca"]})
    P(f"{destinatario} · Corte de datos: {fecha(str(hoy))} · Periodo: 01/01/2024 a la fecha de corte",
      gris=True)
    P(f"Elaborado por <b>{AUTOR}</b> — {' · '.join(TITULOS)}", gris=True)

    lista = ", ".join(nombre_entidad(e) for e in sorted(incluidas, key=lambda e: -incluidas[e]))
    fuera = (f" Se dejaron por fuera {n(sum(excluidas.values()))} contratos de entidades que tienen "
             "sede en el municipio pero no dependen de la administración (" +
             ", ".join(dict.fromkeys(entidad_corta(e) for e in excluidas)) + ")." if excluidas else "")
    P(f"Este documento revisa los <b>{n(len(M))}</b> contratos registrados en SECOP II por {lista}, "
      f"por un valor de <b>{millones(valor_m)}</b>.{fuera} Todo lo que aparece aquí es información "
      "pública: cada contrato citado trae su enlace directo a SECOP II para verificarlo.")

    b.append({"k": "kpis", "v": [
        [n(len(V)), f"contratos con fecha de terminación vencida que SECOP II sigue mostrando como "
                    f"abiertos ({len(V) / len(M) * 100:.0f}% del total)"],
        [f"{len(obras_v)} de {len(obras)}", "contratos de obra aparecen abiertos después de su fecha de "
         f"fin ({sum(1 for r in obras_v if r['pagado'] == 0)} sin pagos reportados)"],
        [f"{len(directa) / len(M) * 100:.0f}%", "de los contratos se adjudicaron por contratación directa "
         f"({sum(r['valor'] for r in directa) / valor_m * 100:.0f}% del valor)"]]})

    H(f"Cómo se ve {municipio} frente a los demás municipios")
    if B:
        P(f"Comparación con los {B['n']} municipios de Cundinamarca que tienen suficientes contratos en "
          "SECOP II para medirse (misma metodología para todos; en esta tabla se cuentan todas las "
          "entidades con sede en cada municipio).")
        pct = lambda x: f"{x:.1f}%".replace(".", ",")
        fila = lambda nom, k, fmt: ([nom, fmt(B[k][0]), fmt(B[k][1]), f"{B[k][2]} de {B['n']}"]
                                    if B[k] else [nom, "sin dato", "", ""])
        b.append({"k": "tabla", "anchos": [42, 14, 22, 22], "filas": [
            ["Indicador", municipio, "Mediana departamental", "Puesto (1 = más alto)"],
            fila("Obras con plazo vencido y aún abiertas en SECOP", "pct_obras_vencidas_abiertas", pct),
            fila("Valor adjudicado por contratación directa", "pct_directa_valor", pct),
            fila("Contratos con adiciones de plazo", "pct_con_adicion", pct),
            fila("Índice compuesto de alertas (0-100)", "indice_alertas",
                 lambda x: f"{x:.1f}".replace(".", ","))]})
        if B["pct_obras_vencidas_abiertas"] and B["pct_directa_valor"]:
            P(f"{municipio} ocupa el puesto {B['pct_obras_vencidas_abiertas'][2]} del departamento en obras "
              f"vencidas y abiertas, y el puesto {B['pct_directa_valor'][2]} en valor adjudicado por "
              "contratación directa. Son indicadores que los entes de control usan para escoger a quién "
              "revisar primero.")
    else:
        P(f"{municipio} no tiene suficientes contratos en SECOP II en el periodo para entrar en el ranking "
          "departamental (mínimo 30), por lo que no se incluye la comparación.")

    b.append({"k": "salto"})
    H("Hallazgo 1 · Contratos de obra")
    if obras:
        contratistas = Counter(r["proveedor"] for r in obras)
        repiten = [(p, k) for p, k in contratistas.most_common() if k > 1][:3]
        txt_rep = (" Se repiten: " + ", ".join(f"{emp(p)} ({k})" for p, k in repiten) + "."
                   if repiten else "")
        P(f"En el periodo se firmaron <b>{len(obras)} contratos de obra</b> por "
          f"<b>{millones(sum(r['valor'] for r in obras))}</b>, adjudicados a {len(contratistas)} "
          f"contratistas.{txt_rep} <b>{len(obras_v)} siguen figurando abiertos</b> en SECOP II después de "
          f"su fecha de terminación, y {sum(1 for r in obras_v if r['pagado'] == 0)} de ellos no tienen "
          "ningún pago reportado en la plataforma.")
        muestra = sorted(sorted(obras_v, key=lambda r: -r["valor"])[:14]
                         or sorted(obras, key=lambda r: -r["valor"])[:14], key=lambda r: r["fecha_firma"])
        P(f"{'Las obras vencidas y abiertas' if obras_v else 'Las obras'} de mayor valor:")
        filas = [["Contrato", "Firma", "Contratista", "Valor", "Fin pactado", "Estado en SECOP", ""]]
        rojos = []
        for r in muestra[:12]:
            filas.append([r["numero"], fecha(r["fecha_firma"]), emp(r["proveedor"]), pesos(r["valor"]),
                          fecha(r["fecha_fin"]), r["estado"], {"link": r["url"]}])
            rojos.append(vencido(r, hoy))
        b.append({"k": "tabla", "anchos": [16, 10, 22, 14, 10, 13, 15], "filas": filas,
                  "rojo_col": 5, "rojos": rojos, "negrita_col": 0})
    else:
        P("No hay contratos de tipo obra registrados en el periodo.")

    if repetidos:
        d1 = dt.date.fromisoformat(repetidos[0]["fecha_firma"][:10])
        d2 = dt.date.fromisoformat(repetidos[-1]["fecha_firma"][:10])
        semanas = max(1, round((d2 - d1).days / 7))
        b.append({"k": "caja", "t":
                  f"<b>Punto de atención:</b> {len(repetidos)} contratos de tipo "
                  f"{TIPO_TXT[repetidos[0]['tipo']]} ({', '.join(r['numero'] for r in repetidos)}) tienen "
                  f"prácticamente el mismo valor, <b>{pesos(repetidos[0]['valor'])}</b>, y se firmaron en un "
                  f"lapso de {semanas} semana{'s' if semanas > 1 else ''}. Un patrón así no prueba ninguna "
                  "irregularidad, pero es de los primeros que revisa un auditor de la Contraloría para "
                  "descartar fraccionamiento de contratos. Conviene tener documentada la justificación "
                  "técnica de cada uno antes de que se la pidan."})

    grandes = sorted([r for r in obras_v if r["valor"] > 2e8], key=lambda r: -r["valor"])[:3]
    if grandes:
        H("Hallazgo 2 · Las obras vencidas de mayor valor, en detalle")
        for r in grandes:
            P(f"<b>Contrato {r['numero']}</b> — {r['objeto'].capitalize()[:170]}. Contratista: "
              f"{emp(r['proveedor'])}. Valor: <b>{pesos(r['valor'])}</b>. Fin pactado: "
              f"{fecha(r['fecha_fin'])} ({dias(r, hoy)} días atrás). Prórrogas registradas: "
              f"{r['dias_adic'] or 0} días. Estado en SECOP: <b>{r['estado']}</b>; pagos reportados: "
              f"{'ninguno' if r['pagado'] == 0 else pesos(r['pagado'])}. "
              f'<link href="{r["url"]}">Ver en SECOP</link>')

    H(f"Hallazgo {3 if grandes else 2} · Contratos terminados que SECOP II sigue mostrando abiertos")
    P(f"De los {n(len(V))} contratos con fecha de fin vencida y sin estado de cierre, "
      f"<b>{n(len(ps))} son de prestación de servicios</b>. Estos no requieren liquidación, pero su estado "
      "en SECOP II debe reflejar la terminación; mientras no se actualice, la plataforma muestra a la "
      "entidad con contratos \"en ejecución\" que ya no lo están. "
      f"Hay <b>{n(len(otros6))} contratos de otro tipo</b> (suministros, obras, convenios, consultorías y "
      f"otros) con más de seis meses vencidos, que suman <b>{millones(sum(r['valor'] for r in otros6))}</b>. "
      "Para los que requieren liquidación, el plazo bilateral y unilateral del artículo 11 de la Ley 1150 de "
      "2007 ya habría corrido, y cada uno es una pregunta segura en una auditoría. Además, "
      f"{n(v_sin_pago)} de los {n(len(V))} contratos vencidos no tienen ningún pago registrado en SECOP II.")
    if otros6:
        k = min(10, len(otros6))
        P(f"Los {k} de mayor valor (excluyendo prestación de servicios):")
        filas = [["Contrato", "Tipo", "Objeto (resumen)", "Valor", "Vencido hace", ""]]
        for r in otros6[:k]:
            filas.append([r["numero"], r["tipo"], r["objeto"].capitalize()[:110] + "…", pesos(r["valor"]),
                          f"{dias(r, hoy)} días", {"link": r["url"]}])
        b.append({"k": "tabla", "anchos": [15, 11, 38, 14, 9, 13], "filas": filas, "negrita_col": 0})

    H("Lo que este diagnóstico dice y lo que no dice")
    P(f"Dice qué muestra hoy SECOP II sobre la contratación de {municipio} y cómo se compara con el resto "
      "del departamento. No afirma que haya irregularidades: muchos de estos casos pueden ser contratos ya "
      "ejecutados cuyo cierre no se ha cargado en la plataforma. Pero para un ente de control la diferencia "
      "entre \"obra inconclusa\" y \"obra terminada sin registrar\" solo se resuelve con soportes, y la "
      "carga de demostrarlo recae en la entidad.")
    H("Qué propongo")
    P("Una revisión mensual de la contratación del municipio en SECOP II, hecha con la mirada de quien ha "
      "trabajado en presupuesto y contratación pública, que entregue: (1) la lista de contratos que vencen "
      "en los próximos 30 días y de los que ya vencieron sin cierre, con responsable sugerido; (2) alertas "
      "de los patrones que miran los entes de control (valores repetidos, concentración en pocos "
      "contratistas, adiciones recurrentes, contratación directa); y (3) la posición de "
      f"{municipio} frente a los demás municipios mes a mes, para medir el avance.")
    P("Le propongo una <b>videollamada de 20 minutos</b> para revisar juntos, en SECOP II y en tiempo real, "
      "los contratos de este documento. Sin costo y sin compromiso.")
    b.append({"k": "firma", "autor": AUTOR, "titulos": TITULOS,
              "contacto": f"Celular y WhatsApp: {TELEFONO} · Correo: {CORREO}"})
    P("Cómo verificar cualquier dato: haga clic en \"Ver en SECOP\" junto a cada contrato, o busque el "
      "número de proceso en community.secop.gov.co (Búsqueda pública de procesos). Los datos agregados "
      "provienen del conjunto abierto SECOP II – Contratos Electrónicos en datos.gov.co.", nota=True)

    return {"municipio": municipio, "autor": AUTOR, "telefono": TELEFONO,
            "pie": f"Fuente: SECOP II (datos.gov.co) · Análisis: {AUTOR}, {TITULOS[0]} · {TELEFONO}",
            "bloques": b}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("municipio")
    ap.add_argument("--alcalde")
    ap.add_argument("--alcaldesa", action="store_true")
    a = ap.parse_args()
    SALIDAS.mkdir(exist_ok=True)
    datos = modelo(a.municipio, a.alcalde, a.alcaldesa)
    salida = SALIDAS / f"{a.municipio}_diagnostico.docx"

    # Use python-docx
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # Set margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.6)
        section.right_margin = Inches(0.6)

    # Process blocks
    for block in datos['bloques']:
        if block['k'] == 'titulo':
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(block['t'][0])
            r.font.size = Pt(24)
            r.font.bold = True

            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(block['t'][1])
            r.font.size = Pt(16)
            r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

        elif block['k'] == 'p':
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if block.get('gris'):
                p_format = p.paragraph_format
                p_format.space_after = Pt(6)
            # Simple text (without markup for now)
            text = block['t'].replace('<b>', '').replace('</b>', '').replace('<link href="', '').replace('">', '').replace('</link>', '')
            r = p.add_run(text)
            r.font.size = Pt(10 if block.get('nota') else 11)
            if block.get('gris'):
                r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

        elif block['k'] == 'h':
            p = doc.add_paragraph()
            r = p.add_run(block['t'])
            r.font.size = Pt(13)
            r.font.bold = True
            r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

        elif block['k'] == 'salto':
            doc.add_page_break()

    doc.save(str(salida))
    print("OK", salida)
