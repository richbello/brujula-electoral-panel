#!/usr/bin/env python3
"""
Genera PDFs de diagnóstico para alcaldes de Cundinamarca.
Selecciona los 10 municipios con mayor índice de alertas (obras_vencidas/contratos).
"""

import json
import sys
from pathlib import Path
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
except ImportError:
    print("Error: reportlab no está instalado. Instalando...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "reportlab"])
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


RAIZ = Path(__file__).resolve().parent
ORIGEN = RAIZ / "data" / "cundinamarca" / "territorio"
DESTINO = RAIZ / "diagnosticos_pdf"

def calcular_indice_alertas(obras_vencidas, contratos):
    """Calcula índice de alertas (porcentaje de obras vencidas)."""
    if contratos == 0:
        return 0
    return round((obras_vencidas / contratos) * 100, 1)

def seleccionar_top_municipios(num=10):
    """Lee indice.json y retorna top N municipios por índice de alertas."""
    indice_path = ORIGEN / "indice.json"
    with open(indice_path, encoding="utf-8") as f:
        data = json.load(f)

    # Calcula índice de alertas para cada municipio
    municipios = []
    for m in data["municipios"]:
        indice = calcular_indice_alertas(m["obras_vencidas"], m["contratos"])
        municipios.append({
            "municipio": m["municipio"],
            "archivo": m["archivo"],
            "contratos": m["contratos"],
            "obras_vencidas": m["obras_vencidas"],
            "indice": indice
        })

    # Ordena por índice descendente y filtra por al menos 30 contratos (threshold SECOP II)
    municipios = [m for m in municipios if m["contratos"] >= 30]
    municipios.sort(key=lambda x: x["indice"], reverse=True)

    return municipios[:num]

def leer_datos_municipio(archivo):
    """Lee el JSON del municipio y extrae datos principales."""
    ruta = ORIGEN / archivo
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)

def generar_pdf(municipio_data, top_municipio):
    """Genera un PDF de diagnóstico para un municipio."""
    archivo_nombre = top_municipio["archivo"].replace(".json", ".pdf")
    ruta_pdf = DESTINO / archivo_nombre

    # Setup del documento
    doc = SimpleDocTemplate(
        str(ruta_pdf),
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=HexColor('#1F4788'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=HexColor('#1F4788'),
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        leading=12,
        alignment=TA_LEFT
    )

    right_style = ParagraphStyle(
        'RightAlign',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_RIGHT
    )

    # Contenido del PDF
    elements = []

    # Encabezado
    municipio = top_municipio["municipio"]
    elements.append(Paragraph(f"DIAGNÓSTICO FISCAL MUNICIPAL", title_style))
    elements.append(Paragraph(f"{municipio}", title_style))
    elements.append(Spacer(1, 0.2*inch))

    # Fecha
    fecha = datetime.now().strftime("%d de %B de %Y")
    elements.append(Paragraph(f"<b>Generado:</b> {fecha}", normal_style))
    elements.append(Spacer(1, 0.15*inch))

    # KPIs principales
    kpis = municipio_data.get("kpis", {})
    meta = municipio_data.get("meta", {})

    elements.append(Paragraph("INDICADORES PRINCIPALES", heading_style))

    kpi_table = [
        ["Métrica", "Valor", "Interpretación"],
        ["Total de Contratos", str(kpis.get("contratos", 0)), "Volumen de contratación"],
        ["Obras Vencidas", str(kpis.get("obras_vencidas", 0)), "Contratos sin cerrar pasada la fecha"],
        ["% Alertas", f"{top_municipio['indice']:.1f}%", "Ratio obras vencidas / contratos"],
        ["Valor Total", f"${kpis.get('valor_total', 0):,.0f}", "Pesos contratados"],
        ["Sectores Identificados", str(kpis.get("sectores", 0)), "Áreas de inversión"],
        ["% Contratos con Pago", f"{kpis.get('pct_contratos_con_pago', 0):.1f}%", "Ejecución presupuestal"],
    ]

    table = Table(kpi_table, colWidths=[2.2*inch, 1.3*inch, 2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1F4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F0F0F0')),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#CCCCCC')),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FFFFFF'), HexColor('#F9F9F9')]),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.2*inch))

    # Top 5 obras vencidas
    obras_vencidas = municipio_data.get("obras_vencidas", [])[:5]
    if obras_vencidas:
        elements.append(Paragraph("TOP 5 OBRAS VENCIDAS (sin cerrar)", heading_style))

        obras_table = [["Contrato", "Entidad", "Valor", "Vencida desde"]]
        for i, obra in enumerate(obras_vencidas, 1):
            referencia = obra.get("referencia_del_contrato", "")[:20]
            entidad = obra.get("nombre_entidad", "")[:25]
            valor = f"${obra.get('valor', 0):,.0f}"
            fecha_vencida = obra.get("fecha_vencida", "")[:10]
            obras_table.append([referencia, entidad, valor, fecha_vencida])

        obras_table_obj = Table(obras_table, colWidths=[1.5*inch, 2*inch, 1.5*inch, 1.5*inch])
        obras_table_obj.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#FF6B6B')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, HexColor('#CCCCCC')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#FFF5F5')]),
        ]))
        elements.append(obras_table_obj)
        elements.append(Spacer(1, 0.15*inch))

    # Top 3 sectores
    sectores = municipio_data.get("sectores", [])[:3]
    if sectores:
        elements.append(Paragraph("TOP 3 SECTORES POR INVERSIÓN", heading_style))

        sectores_table = [["Sector", "Contratos", "Valor Invertido"]]
        for sector in sectores:
            nombre = sector.get("sector", "")[:30]
            cantidad = str(sector.get("cantidad", 0))
            valor = f"${sector.get('valor', 0):,.0f}"
            sectores_table.append([nombre, cantidad, valor])

        sectores_table_obj = Table(sectores_table, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        sectores_table_obj.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1F4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, HexColor('#CCCCCC')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FFFFFF'), HexColor('#F9F9F9')]),
        ]))
        elements.append(sectores_table_obj)
        elements.append(Spacer(1, 0.15*inch))

    # Conclusiones
    elements.append(Paragraph("HALLAZGOS CLAVE", heading_style))

    indice = top_municipio["indice"]
    if indice > 15:
        color_alerta = "🔴"
        nivel = "ALTO"
    elif indice > 8:
        color_alerta = "🟡"
        nivel = "MEDIO"
    else:
        color_alerta = "🟢"
        nivel = "BAJO"

    hallazgos = [
        f"<b>{color_alerta} Índice de Alertas:</b> {indice}% ({nivel} riesgo). {top_municipio['obras_vencidas']} de {top_municipio['contratos']} contratos tienen obras vencidas sin cerrar.",
        f"<b>Ejecución:</b> {kpis.get('pct_contratos_con_pago', 0):.1f}% de contratos reportan pagos en SECOP II.",
        f"<b>Período de análisis:</b> {meta.get('ventana', {}).get('desde', 'N/A')} a {meta.get('ventana', {}).get('hasta', 'N/A')} (mínimo de contrato: $20M COP).",
    ]

    for hallazgo in hallazgos:
        elements.append(Paragraph(hallazgo, normal_style))
        elements.append(Spacer(1, 0.08*inch))

    elements.append(Spacer(1, 0.15*inch))

    # Pie de página
    elements.append(Paragraph("---", normal_style))
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph(
        "Este diagnóstico se generó automaticamente a partir de datos públicos de SECOP II. "
        "Todos los contratos y montos pueden verificarse en https://www.secop.gov.co/",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=HexColor('#666666'))
    ))

    # Build PDF
    doc.build(elements)
    print(f"✓ {municipio:<30} → {ruta_pdf.name}")

def main():
    DESTINO.mkdir(parents=True, exist_ok=True)

    print("Seleccionando top 10 municipios por índice de alertas...")
    top_municipios = seleccionar_top_municipios(10)

    print("\nGenerando PDFs de diagnóstico:\n")
    for top_mun in top_municipios:
        try:
            datos = leer_datos_municipio(top_mun["archivo"])
            generar_pdf(datos, top_mun)
        except Exception as e:
            print(f"✗ {top_mun['municipio']:<30} → Error: {e}")

    print(f"\n✅ {len(top_municipios)} PDFs generados en {DESTINO}/")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
