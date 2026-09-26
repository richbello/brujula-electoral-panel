import pandas as pd
import os

ruta_proyecto = r"C:\RICHARD\RB\2026\Proyecto Software Elecciones 2027"
os.chdir(ruta_proyecto)

df23 = pd.read_parquet('rnec_bogota_2023.parquet')
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

print("=" * 100)
print("VOLATILIDAD 2023 vs 2026: CAMBIO VOTOS POR IDEOLOGIA (SIMPLE)")
print("=" * 100)

votos_23 = df23.groupby('ideologia')['votos'].sum()
votos_26 = df26.groupby('ideologia')['votos'].sum()

resultado = pd.DataFrame({'2023': votos_23, '2026': votos_26})
resultado['DELTA'] = resultado['2026'] - resultado['2023']
resultado['DELTA_PCT'] = ((resultado['2026'] - resultado['2023']) / resultado['2023'] * 100).round(1)

print("\n" + resultado.to_string())
print("\n✅ Análisis completado")