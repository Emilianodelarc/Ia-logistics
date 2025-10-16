
"""
compute_distances_sucursales.py
Calcula distancias Haversine (km) entre todas las sucursales y exporta distancias_sucursales.csv.

Uso:
  python compute_distances_sucursales.py
"""
import pandas as pd
import math

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

def main():
    suc = pd.read_csv("sucursales.csv")
    rows = []
    for i, a in suc.iterrows():
        for j, b in suc.iterrows():
            if i == j: continue
            km = haversine_km(a['lat'], a['lon'], b['lat'], b['lon'])
            rows.append({"origen": a['sucursal'], "destino": b['sucursal'], "km": round(km, 3)})
    out = pd.DataFrame(rows)
    out.to_csv("distancias_sucursales.csv", index=False)
    print(f"OK -> distancias_sucursales.csv ({len(out)} filas)")

if __name__ == "__main__":
    main()
