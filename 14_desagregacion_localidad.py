import pandas as pd
import numpy as np
import os

# Ruta correcta
ruta_proyecto = r"C:\RICHARD\RB\2026\Proyecto Software Elecciones 2027"
os.chdir(ruta_proyecto)

# Cargar datos
df23_bog = pd.read_parquet('rnec_bogota_2015_2023.parquet')
df23_bog = df23_bog[df23_bog['anio'] == 2023].copy()

df26_cong = pd.read_parquet('rnec_congreso_2026.parquet')

# Crear mapping de código localidad -> nombre localidad (desde 2023)
mapping_localidad = df23_bog[['cod_localidad', 'localidad']].drop_duplicates().set_index('cod_localidad')['localidad'].to_dict()
print("📍 Mapping localidades (2023):")
print(mapping_localidad)
print()

# Clasificar partidos
def clasificar_partido(partido):
    if pd.isna(partido):
        return 'OTRO'
    partido_clean = str(partido).upper().strip()
    
    if any(x in partido_clean for x in ['PARTIDO 03020', 'PARTIDO 03002', 'PARTIDO 03003', 
                                          'PARTIDO 03063', 'PARTIDO 03056', 'DIGNIDAD & COMPROMISO', 
                                          'MAIS', 'SALVACION NACIONAL', 'ALTERNATIVO INDIGENA']):
        return 'IZQUIERDA'
    elif any(x in partido_clean for x in ['CONSERVADOR', 'CENTRO DEMOCR', 'CENTRO DEMOC']):
        return 'DERECHA'
    elif any(x in partido_clean for x in ['LIBERAL', 'CAMBIO RADICAL', 'NUEVO LIBERALISMO', 'UNION POR LA GENTE']):
        return 'CENTRO'
    else:
        return 'OTRO'

df23_bog['ideologia'] = df23_bog['partido'].apply(clasificar_partido)
df26_cong['ideologia'] = df26_cong['partido'].apply(clasificar_partido)

# 2023 - por localidad
bog23 = df23_bog.groupby(['localidad', 'ideologia'])['votos'].sum().unstack(fill_value=0)
bog23['TOTAL'] = bog23.sum(axis=1)
bog23['%IZQ'] = (bog23.get('IZQUIERDA', 0) / bog23['TOTAL'] * 100).round(1)
bog23['%DER'] = (bog23.get('DERECHA', 0) / bog23['TOTAL'] * 100).round(1)
bog23['%CEN'] = (bog23.get('CENTRO', 0) / bog23['TOTAL'] * 100).round(1)

# 2026 - EXTRAER localidad de id_puesto
df26_bog = df26_cong[df26_cong['territorio'] == 'BOGOTA'].copy()

# id_puesto = "11001-1-1" -> extraer posiciones [3:5] = "01"
df26_bog['cod_localidad_ext'] = df26_bog['id_puesto'].str[3:5]

# Mapear a nombre de localidad
df26_bog['localidad'] = df26_bog['cod_localidad_ext'].map(mapping_localidad)

print(f"✅ Extraídas localidades de id_puesto")
print(f"   Registros totales 2026: {len(df26_bog)}")
print(f"   Registros con localidad mapeada: {df26_bog['localidad'].notna().sum()}")
print(f"   Localidades únicas: {df26_bog['localidad'].nunique()}")
print()

# Agrupar por localidad
bog26 = df26_bog.groupby(['localidad', 'ideologia'])['votos'].sum().unstack(fill_value=0)
bog26['TOTAL'] = bog26.sum(axis=1)
bog26['%IZQ'] = (bog26.get('IZQUIERDA', 0) / bog26['TOTAL'] * 100).round(1)
bog26['%DER'] = (bog26.get('DERECHA', 0) / bog26['TOTAL'] * 100).round(1)
bog26['%CEN'] = (bog26.get('CENTRO', 0) / bog26['TOTAL'] * 100).round(1)

# Comparación
print("=" * 100)
print("DONDE GANO MAS PETRO (IZQUIERDA): 2023 vs 2026 POR LOCALIDAD")
print("=" * 100)

comparacion = pd.DataFrame()
comparacion['%IZQ_2023'] = bog23['%IZQ']
comparacion['%IZQ_2026'] = bog26['%IZQ']
comparacion['DELTA'] = comparacion['%IZQ_2026'] - comparacion['%IZQ_2023']
comparacion['VOTOS_2023'] = bog23['TOTAL']
comparacion['VOTOS_2026'] = bog26['TOTAL']

comparacion = comparacion.sort_values('DELTA', ascending=False)

print("\n🔴 TOP 10 LOCALIDADES DONDE SUBIO MAS LA IZQUIERDA (GANANCIAS PETRO):\n")
for idx, (loc, row) in enumerate(comparacion.head(10).iterrows(), 1):
    print(f"{idx:2d}. {loc:35s} | 2023: {row['%IZQ_2023']:5.1f}% → 2026: {row['%IZQ_2026']:5.1f}% | Δ {row['DELTA']:+6.1f}pp | V23:{row['VOTOS_2023']:>8.0f} V26:{row['VOTOS_2026']:>8.0f}")

print("\n🔵 TOP 10 LOCALIDADES DONDE BAJO MAS LA IZQUIERDA (PERDIDAS PETRO):\n")
for idx, (loc, row) in enumerate(comparacion.tail(10).iterrows(), 1):
    print(f"{idx:2d}. {loc:35s} | 2023: {row['%IZQ_2023']:5.1f}% → 2026: {row['%IZQ_2026']:5.1f}% | Δ {row['DELTA']:+6.1f}pp | V23:{row['VOTOS_2023']:>8.0f} V26:{row['VOTOS_2026']:>8.0f}")

print("\n📊 RESUMEN POR LOCALIDAD (ORDENADO POR DELTA):\n")
print(comparacion.to_string())

# Guardar
comparacion.to_parquet('desagregacion_localidad.parquet')
print("\n✅ Guardado: desagregacion_localidad.parquet")