import pandas as pd
import numpy as np
import os

ruta_proyecto = r"C:\RICHARD\RB\2026\Proyecto Software Elecciones 2027"
os.chdir(ruta_proyecto)

# Cargar datos
df23 = pd.read_parquet('rnec_bogota_2015_2023.parquet')
df23 = df23[df23['anio'] == 2023].copy()

# Datos 2026 para calibrar factor de volatilidad
df26 = pd.read_parquet('rnec_congreso_2026.parquet')

def clasificar_partido(partido):
    if pd.isna(partido):
        return 'OTRO'
    partido_clean = str(partido).upper().strip()
    if any(x in partido_clean for x in ['PARTIDO 03020', 'PARTIDO 03002', 'PARTIDO 03003', 'PARTIDO 03063', 'PARTIDO 03056', 'DIGNIDAD & COMPROMISO', 'MAIS', 'SALVACION NACIONAL', 'ALTERNATIVO INDIGENA']):
        return 'IZQUIERDA'
    elif any(x in partido_clean for x in ['CONSERVADOR', 'CENTRO DEMOCR']):
        return 'DERECHA'
    elif any(x in partido_clean for x in ['LIBERAL', 'CAMBIO RADICAL', 'NUEVO LIBERALISMO']):
        return 'CENTRO'
    else:
        return 'OTRO'

df23['ideologia'] = df23['partido'].apply(clasificar_partido)
df26['ideologia'] = df26['partido'].apply(clasificar_partido)

# PASO 1: Calcular % de voto por candidato 2023 (baseline)
candidatos_2023 = df23.groupby(['candidato', 'partido', 'puesto']).agg({
    'votos': 'sum',
    'ideologia': 'first'
}).reset_index()

candidatos_2023['rank_puesto'] = candidatos_2023.groupby('puesto')['votos'].rank(ascending=False)

print("=" * 120)
print("PREDICCION VOTO 2027 - BASELINE 2023 (61 candidatos JAL 2023 Bogotá)")
print("=" * 120)

print(f"\nTotal candidatos 2023: {candidatos_2023['candidato'].nunique()}")
print(f"Votos totales 2023: {candidatos_2023['votos'].sum():,}")

# PASO 2: Calcular factores de volatilidad por ideologia
votos_23_total = df23.groupby('ideologia')['votos'].sum()
votos_26_total = df26.groupby('ideologia')['votos'].sum()

factores_volatilidad = {}
for ideologia in ['IZQUIERDA', 'DERECHA', 'CENTRO', 'OTRO']:
    if ideologia in votos_23_total.index and ideologia in votos_26_total.index:
        factor = votos_26_total[ideologia] / votos_23_total[ideologia]
        factores_volatilidad[ideologia] = factor
    else:
        factores_volatilidad[ideologia] = 1.0

print("\n📊 FACTORES DE VOLATILIDAD 2023→2026 (aplicable 2027):")
for ideologia, factor in sorted(factores_volatilidad.items(), key=lambda x: x[1], reverse=True):
    print(f"  {ideologia:15s}: {factor:.3f}x")

# PASO 3: Proyectar voto 2027 con factores de volatilidad
candidatos_2023['votos_2027_proyectado'] = candidatos_2023.apply(
    lambda row: row['votos'] * factores_volatilidad.get(row['ideologia'], 1.0),
    axis=1
).round(0).astype(int)

# PASO 4: Ranking 2027 por puesto
candidatos_2023['rank_2027_puesto'] = candidatos_2023.groupby('puesto')['votos_2027_proyectado'].rank(ascending=False)

# Top 20 ganadores proyectados 2027
top_20_2027 = candidatos_2023.nlargest(20, 'votos_2027_proyectado')[['candidato', 'partido', 'ideologia', 'votos', 'votos_2027_proyectado', 'rank_puesto', 'rank_2027_puesto']]

print("\n" + "=" * 120)
print("TOP 20 CANDIDATOS 2027 PROYECTADOS (si aplican factores de volatilidad 2026)")
print("=" * 120 + "\n")

for idx, (_, row) in enumerate(top_20_2027.iterrows(), 1):
    delta = row['votos_2027_proyectado'] - row['votos']
    print(f"{idx:2d}. {row['candidato']:35s} | {row['partido'][:30]:30s} | {row['ideologia']:10s} | 2023:{row['votos']:>7,} | 2027:{row['votos_2027_proyectado']:>7,} | Δ{delta:+7,}")

# Guardar
candidatos_2023.to_parquet('prediccion_2027_baseline.parquet', index=False)
print("\n✅ Guardado: prediccion_2027_baseline.parquet")
print(f"\n📌 NOTA: Proyección BETA basada en factores de volatilidad 2026.")
print(f"   Requiere candidatos confirmados 2027 de Registraduría para refinamiento.")