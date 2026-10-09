#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplificar el módulo 04 - remover encabezados, mantener solo upload y funcionalidad
"""

with open('modulos-3-integrados.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Encontrar y reemplazar la sección del generador por una versión simplificada
old_gen_section = '''<section class="pane" id="generador">
<h2>Generador de Estado de Cuenta</h2>
<p class="sub">Procesa datos de pagos del histórico · todo se ejecuta en tu navegador</p>
<div class="mod04-grid">
<div class="panel"><h3>Paso 1: Plantilla</h3><p style="font-size:13px;color:var(--muted);margin-bottom:15px">Sube el formato oficial en blanco (formato_estadocuenta.xlsx)</p>
<div class="upload-area" id="plantillaUploadArea">
<div class="upload-area-text">📤 Arrastra o haz clic</div>
<div class="upload-area-hint">formato_estadocuenta.xlsx</div>
<input type="file" id="plantillaFile" accept=".xlsx,.xls">
<div class="file-name" id="plantillaName"></div>
</div>
</div>
<div class="panel"><h3>Paso 2: Histórico</h3><p style="font-size:13px;color:var(--muted);margin-bottom:15px">Sube el histórico de pagos con todas las vigencias</p>
<div class="upload-area" id="historicoUploadArea">
<div class="upload-area-text">📤 Arrastra o haz clic</div>
<div class="upload-area-hint">Histórico de Pagos (Excel completo)</div>
<input type="file" id="historicoFile" accept=".xlsx,.xls">
<div class="file-name" id="historicoName"></div>
</div>
</div>
</div>
<div class="panel">
<h3>Paso 3: Generar Estado de Cuenta</h3>
<div class="info-box">ℹ️ Ingresa el número de contrato tal como aparece en el histórico (ej: 233-2026, 054-2026)</div>
<div class="form-group">
<label for="contrato">Número de Contrato</label>
<input type="text" id="contrato" placeholder="Ej: 233-2026" autocomplete="off">
</div>
<div class="loading" id="loading"><span class="spinner"></span>Procesando... esto puede tomar un momento</div>
<div class="error" id="error"></div>
<div class="result" id="result">
<h2><span style="font-size:24px">✓</span> ¡Éxito!</h2>
<div class="result-item">
<div class="result-label">Contrato:</div>
<div class="result-value" id="resultContrato"></div>
</div>
<div class="result-item">
<div class="result-label">Contratista:</div>
<div class="result-value" id="resultContratista"></div>
</div>
<div class="result-item">
<div class="result-label">Transacciones:</div>
<div class="result-value" id="resultTransacciones"></div>
</div>
<div class="result-item">
<div class="result-label">Valor Inicial:</div>
<div class="result-value" id="resultValor"></div>
</div>
<div class="result-item">
<div class="result-label">Saldo Final:</div>
<div class="result-value" id="resultSaldo"></div>
</div>
</div>
<div class="button-group">
<button class="btn-primary" id="generarBtn" disabled>🎯 Generar Estado de Cuenta</button>
<button class="btn-reset" id="resetBtn">🔄 Limpiar</button>
</div>
</div>
</section>'''

new_gen_section = '''<section class="pane" id="generador">
<div class="mod04-grid">
<div class="panel">
<div class="upload-area" id="plantillaUploadArea">
<div class="upload-area-text">📤 Plantilla</div>
<div class="upload-area-hint">formato_estadocuenta.xlsx</div>
<input type="file" id="plantillaFile" accept=".xlsx,.xls">
<div class="file-name" id="plantillaName"></div>
</div>
</div>
<div class="panel">
<div class="upload-area" id="historicoUploadArea">
<div class="upload-area-text">📤 Histórico de Pagos</div>
<div class="upload-area-hint">Excel con todas las vigencias</div>
<input type="file" id="historicoFile" accept=".xlsx,.xls">
<div class="file-name" id="historicoName"></div>
</div>
</div>
</div>
<div class="panel">
<div class="form-group">
<label for="contrato">Número de Contrato</label>
<input type="text" id="contrato" placeholder="Ej: 233-2026" autocomplete="off">
</div>
<div class="loading" id="loading"><span class="spinner"></span>Procesando...</div>
<div class="error" id="error"></div>
<div class="result" id="result">
<h2><span style="font-size:24px">✓</span> ¡Éxito!</h2>
<div class="result-item">
<div class="result-label">Contrato:</div>
<div class="result-value" id="resultContrato"></div>
</div>
<div class="result-item">
<div class="result-label">Contratista:</div>
<div class="result-value" id="resultContratista"></div>
</div>
<div class="result-item">
<div class="result-label">Transacciones:</div>
<div class="result-value" id="resultTransacciones"></div>
</div>
<div class="result-item">
<div class="result-label">Valor Inicial:</div>
<div class="result-value" id="resultValor"></div>
</div>
<div class="result-item">
<div class="result-label">Saldo Final:</div>
<div class="result-value" id="resultSaldo"></div>
</div>
</div>
<div class="button-group">
<button class="btn-primary" id="generarBtn" disabled>🎯 Generar Estado de Cuenta</button>
<button class="btn-reset" id="resetBtn">🔄 Limpiar</button>
</div>
</div>
</section>'''

html = html.replace(old_gen_section, new_gen_section)

with open('modulos-3-integrados.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("✓ Módulo generador simplificado")
