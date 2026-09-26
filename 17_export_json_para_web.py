import pandas as pd
import json
import os

ruta_proyecto = r"C:\RICHARD\RB\2026\Proyecto Software Elecciones 2027"
os.chdir(ruta_proyecto)

# Crear carpeta data si no existe
os.makedirs(r"C:\RICHARD\rb\2026\brujula-panel-web\data", exist_ok=True)
ruta_data = r"C:\RICHARD\rb\2026\brujula-panel-web\data"

print("=" * 100)
print("EXPORTANDO 3 ANÁLISIS A JSON PARA PANEL WEB")
print("=" * 100)

# ====== ANÁLISIS 1: DESAGREGACIÓN POR LOCALIDAD ======
print("\n1️⃣ Desagregación por localidad...")
desag = pd.read_parquet('desagregacion_localidad.parquet')
desag_dict = {
    'titulo': 'Impacto Petro 2023→2026 por Localidad',
    'descripcion': 'Cambio de votos hacia la izquierda en Bogotá, municipio a municipio',
    'localidades': desag.reset_index().to_dict('records')
}
with open(os.path.join(ruta_data, 'desagregacion_localidad.json'), 'w', encoding='utf-8') as f:
    json.dump(desag_dict, f, ensure_ascii=False, indent=2)
print(f"   ✅ Guardado: {os.path.join(ruta_data, 'desagregacion_localidad.json')}")

# ====== ANÁLISIS 2: VOLATILIDAD ELECTORAL ======
print("\n2️⃣ Volatilidad electoral 2023→2026...")
votos_23 = {'IZQUIERDA': 103036, 'DERECHA': 847900, 'CENTRO': 3341573, 'OTRO': 4444396}
votos_26 = {'IZQUIERDA': 660785, 'DERECHA': 474831, 'CENTRO': 554987, 'OTRO': 804487}

volatilidad_data = []
factores = {}
for ideologia in ['IZQUIERDA', 'DERECHA', 'CENTRO', 'OTRO']:
    delta = votos_26[ideologia] - votos_23[ideologia]
    factor = votos_26[ideologia] / votos_23[ideologia] if votos_23[ideologia] > 0 else 0
    factores[ideologia] = factor
    volatilidad_data.append({
        'ideologia': ideologia,
        'votos_2023': votos_23[ideologia],
        'votos_2026': votos_26[ideologia],
        'delta': delta,
        'cambio_pct': round((delta / votos_23[ideologia] * 100), 1) if votos_23[ideologia] > 0 else 0,
        'factor': round(factor, 3)
    })

volatilidad_dict = {
    'titulo': 'Volatilidad Electoral 2023→2026',
    'descripcion': 'Cambio de voto por ideología + factores de volatilidad aplicables a 2027',
    'datos': volatilidad_data,
    'factores_2027': factores
}
with open(os.path.join(ruta_data, 'volatilidad_electoral.json'), 'w', encoding='utf-8') as f:
    json.dump(volatilidad_dict, f, ensure_ascii=False, indent=2)
print(f"   ✅ Guardado: {os.path.join(ruta_data, 'volatilidad_electoral.json')}")

# ====== ANÁLISIS 3: PREDICCIÓN 2027 ======
print("\n3️⃣ Predicción 2027 (top 30 candidatos)...")
pred = pd.read_parquet('prediccion_2027_baseline.parquet')
top_30 = pred.nlargest(30, 'votos_2027_proyectado')[['candidato', 'partido', 'ideologia', 'votos', 'votos_2027_proyectado']].copy()
top_30['delta'] = top_30['votos_2027_proyectado'] - top_30['votos']

prediccion_dict = {
    'titulo': 'Predicción 2027 (Top 30 candidatos)',
    'descripcion': 'Proyección aplicando factores de volatilidad 2026 a candidatos 2023',
    'candidatos': top_30.to_dict('records'),
    'nota': 'BETA: Requiere candidatos oficiales 2027 de Registraduría para refinamiento'
}
with open(os.path.join(ruta_data, 'prediccion_2027.json'), 'w', encoding='utf-8') as f:
    json.dump(prediccion_dict, f, ensure_ascii=False, indent=2)
print(f"   ✅ Guardado: {os.path.join(ruta_data, 'prediccion_2027.json')}")

# ====== RESUMEN GENERAL ======
print("\n" + "=" * 100)
print("RESUMEN DE EXPORTACIÓN")
print("=" * 100)
resumen = {
    'fecha': '2026-09-26',
    'archivos': [
        'desagregacion_localidad.json',
        'volatilidad_electoral.json',
        'prediccion_2027.json'
    ],
    'url_github': 'https://richbello.github.io/brujula-electoral-panel/',
    'datos_disponibles': {
        'desagregacion': f"{len(desag_dict['localidades'])} localidades",
        'volatilidad': f"4 ideologías",
        'prediccion': f"30 candidatos top"
    }
}

with open(os.path.join(ruta_data, 'resumen.json'), 'w', encoding='utf-8') as f:
    json.dump(resumen, f, ensure_ascii=False, indent=2)

print("\n✅ Todos los archivos exportados a:")
print(f"   {ruta_data}/")
print("\n📋 Archivos generados:")
for archivo in resumen['archivos']:
    print(f"   - {archivo}")
print(f"   - resumen.json")