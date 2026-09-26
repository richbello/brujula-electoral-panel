import pandas as pd
import os

ruta_proyecto = r"C:\RICHARD\RB\2026\Proyecto Software Elecciones 2027"
os.chdir(ruta_proyecto)

df_hist = pd.read_parquet('rnec_bogota_2015_2023.parquet')

print("=" * 80)
print("DIAGNÓSTICO: AÑOS Y LOCALIDADES DISPONIBLES")
print("=" * 80)

print("\n📅 Años disponibles:")
print(sorted(df_hist['anio'].unique()))

print("\n📍 Localidades por año:")
for anio in sorted(df_hist['anio'].unique()):
    locales = df_hist[df_hist['anio'] == anio]['localidad'].nunique()
    print(f"  {anio}: {locales} localidades")

print("\nLocalidades con datos en TODOS los años (2015, 2019, 2023):")
for loc in sorted(df_hist['localidad'].unique()):
    años_disponibles = set(df_hist[df_hist['localidad'] == loc]['anio'].unique())
    todos_los_años = {2015, 2019, 2023}
    if todos_los_años.issubset(años_disponibles):
        print(f"  ✅ {loc}")
    else:
        print(f"  ❌ {loc} (tiene: {sorted(años_disponibles)})")