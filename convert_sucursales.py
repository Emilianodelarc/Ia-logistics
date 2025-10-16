
"""
convert_sucursales.py
Convierte tu CSV con columnas 'Latitud' y 'Longitud' (y opcional 'Nombre') a 'sucursales.csv' estándar.

Uso:
  python convert_sucursales.py --in "mapas_sucursales_Denis - Hoja 1.csv" --out sucursales.csv
"""
import argparse
import pandas as pd

def main(inp, out):
    df = pd.read_csv(inp)
    cols = {c.lower().strip(): c for c in df.columns}
    lat_col = cols.get('latitud') or cols.get('lat') or cols.get('latitude')
    lon_col = cols.get('longitud') or cols.get('lon') or cols.get('lng') or cols.get('long')
    name_col = cols.get('nombre') or cols.get('sucursal') or None

    if lat_col is None or lon_col is None:
        raise SystemExit("No encuentro columnas Latitud/Longitud. Columnas vistas: " + ", ".join(df.columns))

    out_df = pd.DataFrame({
        'sucursal': df[name_col] if name_col else [f"Sucursal_{i+1}" for i in range(len(df))],
        'lat': df[lat_col].astype(float),
        'lon': df[lon_col].astype(float),
    })
    out_df.to_csv(out, index=False)
    print(f"OK -> {out} ({len(out_df)} filas)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Ruta del CSV original (Latitud, Longitud[, Nombre])")
    ap.add_argument("--out", dest="out", default="sucursales.csv")
    args = ap.parse_args()
    main(args.inp, args.out)
