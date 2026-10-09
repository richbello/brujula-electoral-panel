#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrar módulo 04 (Estado de Cuenta) en modulos-3-integrados.html
Crea una pestaña adicional dentro de Análisis Fiscal
"""
import re

# Leer el archivo actual
with open('modulos-3-integrados.html', 'r', encoding='utf-8') as f:
    html = f.read()

# ===============================
# PASO 1: Expandir <style> con CSS adicional para el módulo 04
# ===============================

css_adicional = """
/* ==================== MÓDULO 04 - ESTADO DE CUENTA ==================== */
.upload-area{border:2px dashed var(--gold);border-radius:6px;padding:20px;text-align:center;cursor:pointer;transition:all 0.3s ease;background:rgba(255,176,32,.05)}
.upload-area:hover{border-color:#FFB020;background:rgba(255,176,32,.1)}
.upload-area input{display:none}
.upload-area-text{color:var(--gold);font-weight:500;margin-bottom:8px;font-size:14px}
.upload-area-hint{color:var(--muted);font-size:12px}
.file-name{color:var(--ok);font-size:13px;margin-top:10px;font-weight:500}
.form-group{margin-bottom:20px}
.form-group label{display:block;color:var(--navy);font-weight:500;margin-bottom:8px;font-size:14px}
.form-group input{width:100%;padding:12px;border:1px solid var(--line);border-radius:4px;font-size:14px;transition:border-color 0.3s ease}
.form-group input:focus{outline:none;border-color:var(--gold);box-shadow:0 0 0 3px rgba(255,176,32,.1)}
.button-group{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:25px}
.btn-primary{padding:12px 20px;border:none;border-radius:4px;font-size:14px;font-weight:500;cursor:pointer;transition:all 0.3s ease;background:var(--gold);color:var(--navy);grid-column:1 / -1}
.btn-primary:hover:not(:disabled){box-shadow:0 4px 12px rgba(255,176,32,.4);transform:translateY(-2px)}
.btn-primary:disabled{background:#ccc;cursor:not-allowed}
.btn-reset{background:#f0f0f0;color:#333;border:none;border-radius:4px;padding:12px 20px;cursor:pointer}
.btn-reset:hover{background:#e0e0e0}
.loading{display:none;text-align:center;color:var(--gold);font-weight:500;margin:20px 0}
.loading.active{display:block}
.spinner{display:inline-block;width:20px;height:20px;border:3px solid #f3f3f3;border-top:3px solid var(--gold);border-radius:50%;animation:spin 1s linear infinite;margin-right:10px;vertical-align:middle}
@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
.error{background:#FFDEE8;border:1px solid #FFD5DF;border-radius:4px;padding:15px;color:var(--crit);margin-top:15px;display:none}
.error.active{display:block}
.result{background:#fff;border:1px solid var(--line);border-radius:10px;padding:25px;display:none;margin-top:20px}
.result.active{display:block}
.result h2{color:var(--ok);font-size:20px;margin-bottom:20px;display:flex;align-items:center;gap:10px}
.result-item{display:grid;grid-template-columns:150px 1fr;margin-bottom:15px;padding-bottom:15px;border-bottom:1px solid var(--line)}
.result-item:last-child{border-bottom:none}
.result-label{font-weight:500;color:var(--muted)}
.result-value{color:var(--navy);font-weight:500}
.info-box{background:rgba(124,77,255,.05);border-left:4px solid var(--gold);padding:15px;border-radius:4px;margin-bottom:20px;font-size:13px;color:var(--navy)}
.mod04-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
@media(max-width:800px){.mod04-grid{grid-template-columns:1fr}.button-group{grid-template-columns:1fr}}
"""

# Buscar dónde termina el <style>
style_end = html.rfind('</style>')
if style_end > 0:
    html = html[:style_end] + css_adicional + html[style_end:]
    print("✓ CSS adicional integrado")

# ===============================
# PASO 2: Agregar pestaña "Generador de Estado de Cuenta" en nav
# ===============================

# Buscar la navegación de pestañas
nav_pattern = r'(<nav class="tabs">)(.*?)(<\/nav>)'
def add_gen_tab(match):
    nav_open = match.group(1)
    tabs = match.group(2)
    nav_close = match.group(3)
    # Agregar la nueva pestaña antes del cierre de nav
    new_tab = '<button data-t="generador">Generador de Estado de Cuenta</button>'
    return nav_open + tabs + new_tab + nav_close

html = re.sub(nav_pattern, add_gen_tab, html, flags=re.DOTALL)
print("✓ Pestaña 'Generador' agregada a nav")

# ===============================
# PASO 3: Agregar la sección "Generador de Estado de Cuenta"
# ===============================

gen_section = '''<section class="pane" id="generador">
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

# Buscar dónde está la última sección </section> antes de </main>
main_end = html.rfind('</main>')
last_section = html.rfind('</section>', 0, main_end)
if last_section > 0:
    html = html[:last_section+10] + '\n' + gen_section + '\n' + html[last_section+10:]
    print("✓ Sección generador integrada")

# ===============================
# PASO 4: Agregar script XLSX y lógica del módulo 04
# ===============================

script_adicional = '''
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script>
// ========== MÓDULO 04 - ESTADO DE CUENTA ==========

function formatCurrency(value) {
    return new Intl.NumberFormat('es-CO', {
        style: 'currency',
        currency: 'COP',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
}

function showError(msg) {
    const el = document.getElementById('error');
    el.textContent = msg;
    el.classList.add('active');
}

function clearError() {
    const el = document.getElementById('error');
    el.classList.remove('active');
}

function showLoading(show) {
    document.getElementById('loading').classList.toggle('active', show);
}

function showResult(data) {
    document.getElementById('resultContrato').textContent = data.contrato;
    document.getElementById('resultContratista').textContent = data.contratista;
    document.getElementById('resultTransacciones').textContent = data.pagos_encontrados;
    document.getElementById('resultValor').textContent = formatCurrency(data.valor_contrato);
    document.getElementById('resultSaldo').textContent = formatCurrency(data.saldo_final);
    document.getElementById('result').classList.add('active');
}

function enableGenerateBtn() {
    const plantilla = document.getElementById('plantillaFile').files[0];
    const historico = document.getElementById('historicoFile').files[0];
    const contrato = document.getElementById('contrato').value.trim();
    document.getElementById('generarBtn').disabled = !(plantilla && historico && contrato);
}

function setupUploadArea(areaId, inputId, nameId) {
    const area = document.getElementById(areaId);
    const input = document.getElementById(inputId);
    const nameEl = document.getElementById(nameId);

    area.addEventListener('click', () => input.click());
    area.addEventListener('dragover', (e) => {
        e.preventDefault();
        area.style.borderColor = '#FFB020';
        area.style.background = 'rgba(255,176,32,.1)';
    });
    area.addEventListener('dragleave', () => {
        area.style.borderColor = '#FFB020';
        area.style.background = 'rgba(255,176,32,.05)';
    });
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.style.borderColor = '#FFB020';
        area.style.background = 'rgba(255,176,32,.05)';
        if (e.dataTransfer.files.length) {
            input.files = e.dataTransfer.files;
            input.dispatchEvent(new Event('change'));
        }
    });

    input.addEventListener('change', () => {
        if (input.files[0]) {
            nameEl.textContent = `✓ ${input.files[0].name}`;
            enableGenerateBtn();
        }
    });
}

if (document.getElementById('plantillaUploadArea')) {
    setupUploadArea('plantillaUploadArea', 'plantillaFile', 'plantillaName');
    setupUploadArea('historicoUploadArea', 'historicoFile', 'historicoName');
    document.getElementById('contrato').addEventListener('input', enableGenerateBtn);

    document.getElementById('generarBtn').addEventListener('click', async () => {
        clearError();
        showLoading(true);

        try {
            const plantillaFile = document.getElementById('plantillaFile').files[0];
            const historicoFile = document.getElementById('historicoFile').files[0];
            const contratoBuscado = document.getElementById('contrato').value.trim();

            // Leer histórico
            const historicoArrayBuffer = await historicoFile.arrayBuffer();
            const historicoData = new Uint8Array(await historicoFile.arrayBuffer());
            const historicoWB = XLSX.read(historicoData, { type: 'array' });
            const historicoWS = historicoWB.Sheets[historicoWB.SheetNames[0]];
            const historico = XLSX.utils.sheet_to_json(historicoWS);

            // Filtrar por contrato
            const pagos = historico.filter(row => {
                const referencia = String(row.Referencia || '');
                return referencia.includes(contratoBuscado);
            });

            if (pagos.length === 0) {
                showError(`❌ No se encontró información para: ${contratoBuscado}`);
                showLoading(false);
                return;
            }

            const primer = pagos[0];

            // Leer plantilla
            const plantillaData = new Uint8Array(await plantillaFile.arrayBuffer());
            const plantillaWB = XLSX.read(plantillaData, { type: 'array' });
            const plantillaWS = plantillaWB.Sheets[plantillaWB.SheetNames[0]];

            // Escribir datos en plantilla
            plantillaWS['D5'] = { t: 's', v: contratoBuscado };
            plantillaWS['D6'] = { t: 's', v: String(primer['Nombre'] || '') };
            plantillaWS['D7'] = { t: 'n', v: primer['VALOR FINAL DEL CONTRATO'] || 0 };
            plantillaWS['D8'] = { t: 's', v: String(primer['FECHA INICIAL DE CONTRATO'] || '') };
            plantillaWS['H5'] = { t: 's', v: String(primer['Proveedor'] || '') };
            plantillaWS['H6'] = { t: 's', v: String(primer['Nº identificación'] || '') };
            plantillaWS['H7'] = { t: 's', v: String(primer['Numero RP'] || '') };
            plantillaWS['H8'] = { t: 's', v: String(primer['FECHA DE TERMINACION FINAL'] || '') };

            // Escribir transacciones
            let fila = 17;
            let saldoAcumulado = primer['VALOR FINAL DEL CONTRATO'] || 0;

            pagos.forEach((pago, idx) => {
                const monto = pago['Valor Bruto'] || 0;
                saldoAcumulado -= monto;

                plantillaWS[`B${fila}`] = { t: 'n', v: idx + 1 };
                plantillaWS[`C${fila}`] = { t: 's', v: String(pago['Texto cabecera documento'] || '') };
                plantillaWS[`D${fila}`] = { t: 'n', v: monto };
                plantillaWS[`E${fila}`] = { t: 'n', v: saldoAcumulado };
                plantillaWS[`F${fila}`] = { t: 's', v: String(pago['Doc.compensación'] || '') };
                plantillaWS[`G${fila}`] = { t: 's', v: String(pago['Fecha de pago'] || '') };
                plantillaWS[`H${fila}`] = { t: 's', v: String(pago['Numero RP'] || '') };
                plantillaWS[`I${fila}`] = { t: 's', v: String(pago['CDP Externo'] || '') };
                plantillaWS[`J${fila}`] = { t: 's', v: String(pago['CRP Externo'] || '') };

                fila++;
            });

            // Guardar y descargar
            const fileName = `Estado_de_Cuenta_${contratoBuscado}.xlsx`;
            XLSX.writeFile(plantillaWB, fileName);

            // Mostrar resultado
            showResult({
                contrato: contratoBuscado,
                contratista: String(primer['Nombre'] || ''),
                pagos_encontrados: pagos.length,
                valor_contrato: primer['VALOR FINAL DEL CONTRATO'] || 0,
                saldo_final: saldoAcumulado,
            });

        } catch (error) {
            showError(`❌ Error: ${error.message}`);
            console.error(error);
        } finally {
            showLoading(false);
        }
    });

    // Reset
    document.getElementById('resetBtn').addEventListener('click', () => {
        document.getElementById('plantillaFile').value = '';
        document.getElementById('historicoFile').value = '';
        document.getElementById('contrato').value = '';
        document.getElementById('plantillaName').textContent = '';
        document.getElementById('historicoName').textContent = '';
        document.getElementById('result').classList.remove('active');
        clearError();
        enableGenerateBtn();
    });
}
</script>'''

# Buscar el script existente que está antes de </body>
body_end = html.rfind('</body>')
# Buscar el último <script> existente
last_script_end = html.rfind('</script>')
if last_script_end > 0 and last_script_end < body_end:
    # Insertar nuevo script después del último script existente
    html = html[:last_script_end+9] + script_adicional + html[last_script_end+9:]
    print("✓ Script XLSX y lógica del módulo 04 integrados")

# Guardar el archivo actualizado
with open('modulos-3-integrados.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("✓ Archivo modulos-3-integrados.html actualizado exitosamente")
print("✓ Nueva pestaña 'Generador de Estado de Cuenta' disponible")
