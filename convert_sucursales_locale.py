
"""
convert_sucursales_locale.py
Convierte un CSV con columnas 'Latitud' y 'Longitud' (con formatos locales: puntos de miles, coma decimal, etc.)
a 'sucursales.csv' estándar (sucursal, lat, lon). Auto-detecta delimitador y normaliza números.

Uso:
  python convert_sucursales_locale.py --in "mapas_sucursales_Denis - Hoja 1.csv" --out sucursales.csv
"""
import argparse
import pandas as pd
import re

def to_float_locale(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    # eliminar espacios y NBSP
    s = s.replace('\u00A0','').replace(' ', '')
    # normalizar separadores: si tiene coma y punto, asumimos "." miles y "," decimal
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        # solo coma -> decimal
        if ',' in s and '.' not in s:
            s = s.replace(',', '.')
        # solo punto -> ya decimal
    # remover cualquier caracter que no sea - . dígito
    s = re.sub(r'[^0-9\.\-]', '', s)
    if s.count('.') > 1:
        # si quedaron muchos puntos, quita todos menos el primero desde la izquierda
        first = s.find('.')
        s = s[:first+1] + s[first+1:].replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None

def main(inp, out):
    # auto-detectar delimitador
    df = pd.read_csv(inp, sep=None, engine='python')
    # normalizar nombres de columnas
    rename = {c: c.strip().lower() for c in df.columns}
    df.rename(columns=rename, inplace=True)

    # detectar columnas de lat/lon
    lat_col = None
    lon_col = None
    for cand in ['latitud','lat','latitude']:
        if cand in df.columns:
            lat_col = cand; break
    for cand in ['longitud','lon','lng','long','longitude']:
        if cand in df.columns:
            lon_col = cand; break

    if lat_col is None or lon_col is None:
        raise SystemExit("No encuentro columnas de latitud/longitud. Columnas detectadas: " + ", ".join(df.columns))

    # nombre (opcional)
    name_col = None
    for cand in ['nombre','sucursal','name','site']:
        if cand in df.columns:
            name_col = cand; break

    # convertir a float robusto
    lat_vals = df[lat_col].map(to_float_locale)
    lon_vals = df[lon_col].map(to_float_locale)

    bad = lat_vals.isna() | lon_vals.isna()
    if bad.any():
        # intentar una pasada extra eliminando caracteres raros
        lat_vals = lat_vals.fillna(df[lat_col].astype(str).str.replace(r'[^0-9,\.\-]','', regex=True).map(to_float_locale))
        lon_vals = lon_vals.fillna(df[lon_col].astype(str).str.replace(r'[^0-9,\.\-]','', regex=True).map(to_float_locale))
        bad = lat_vals.isna() | lon_vals.isna()

    if bad.any():
        print(f"[WARN] {bad.sum()} filas con coordenadas inválidas serán descartadas.")

    out_df = pd.DataFrame({
        'sucursal': df[name_col] if name_col else [f"Sucursal_{i+1}" for i in range(len(df))],
        'lat': lat_vals,
        'lon': lon_vals,
    })
    out_df = out_df.dropna(subset=['lat','lon'])
    out_df.to_csv(out, index=False)
    print(f"OK -> {out} ({len(out_df)} filas válidas)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Ruta del CSV original")
    ap.add_argument("--out", dest="out", default="sucursales.csv")
    args = ap.parse_args()
    main(args.inp, args.out)
