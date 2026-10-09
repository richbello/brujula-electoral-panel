#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dejar solo un cuadro rojo con los elementos del módulo 04
"""

with open('modulos-3-integrados.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Reemplazar la sección generador con solo un cuadro
new_gen = '''<section class="pane" id="generador">
<div style="background:#C8003C;border-radius:16px;padding:40px;color:white;text-align:center;max-width:600px;margin:60px auto">
<div style="margin-bottom:40px">
<div style="font-size:48px;margin-bottom:20px">📊</div>
<h2 style="color:white;font-size:28px;margin-bottom:10px">Análisis Presupuestal CRP</h2>
<p style="color:rgba(255,255,255,.9);font-size:14px">Carga el reporte SAP con variables presupuestales</p>
</div>

<div style="background:rgba(255,255,255,.1);border:2px dashed rgba(255,255,255,.5);border-radius:12px;padding:30px;margin-bottom:20px;cursor:pointer" id="plantillaUploadArea">
<div style="font-size:16px;margin-bottom:8px">📤 Plantilla</div>
<div style="font-size:12px;opacity:.9">formato_estadocuenta.xlsx</div>
<input type="file" id="plantillaFile" accept=".xlsx,.xls" style="display:none">
<div id="plantillaName" style="font-size:12px;margin-top:10px;color:rgba(255,255,255,.8)"></div>
</div>

<div style="background:rgba(255,255,255,.1);border:2px dashed rgba(255,255,255,.5);border-radius:12px;padding:30px;margin-bottom:20px;cursor:pointer" id="historicoUploadArea">
<div style="font-size:16px;margin-bottom:8px">📤 Histórico</div>
<div style="font-size:12px;opacity:.9">Excel con todas las vigencias</div>
<input type="file" id="historicoFile" accept=".xlsx,.xls" style="display:none">
<div id="historicoName" style="font-size:12px;margin-top:10px;color:rgba(255,255,255,.8)"></div>
</div>

<input type="text" id="contrato" placeholder="Ej: 233-2026" autocomplete="off" style="width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;margin-bottom:20px">

<div class="loading" id="loading" style="color:white"><span class="spinner" style="border-top-color:white"></span>Procesando...</div>
<div class="error" id="error" style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.3);color:white"></div>
<div class="result" id="result" style="background:rgba(255,255,255,.15);border-radius:8px;padding:20px;text-align:left;color:white;display:none">
<h3 style="color:white;margin-bottom:15px">✓ ¡Éxito!</h3>
<div style="font-size:13px;margin-bottom:12px"><span style="opacity:.8">Contrato:</span> <strong id="resultContrato"></strong></div>
<div style="font-size:13px;margin-bottom:12px"><span style="opacity:.8">Contratista:</span> <strong id="resultContratista"></strong></div>
<div style="font-size:13px;margin-bottom:12px"><span style="opacity:.8">Transacciones:</span> <strong id="resultTransacciones"></strong></div>
<div style="font-size:13px;margin-bottom:12px"><span style="opacity:.8">Valor Inicial:</span> <strong id="resultValor"></strong></div>
<div style="font-size:13px"><span style="opacity:.8">Saldo Final:</span> <strong id="resultSaldo"></strong></div>
</div>

<div style="display:grid;grid-template-columns:1fr;gap:10px">
<button id="generarBtn" disabled style="background:#FFB020;color:#C8003C;border:none;padding:12px 20px;border-radius:8px;font-weight:600;cursor:pointer;font-size:14px;opacity:.7">🎯 Generar Estado de Cuenta</button>
<button id="resetBtn" style="background:rgba(255,255,255,.2);color:white;border:none;padding:12px 20px;border-radius:8px;font-weight:600;cursor:pointer;font-size:14px">🔄 Limpiar</button>
</div>
</div>
</section>'''

# Encontrar y reemplazar solo la sección generador
start = html.find('<section class="pane" id="generador">')
if start > -1:
    end = html.find('</section>', start) + len('</section>')
    html = html[:start] + new_gen + html[end:]

with open('modulos-3-integrados.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("✓ Solo cuadro rojo")
