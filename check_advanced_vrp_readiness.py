
"""
check_advanced_vrp_readiness.py
Diagnostica por qué el VRP avanzado no encuentra solución.
- Verifica: ventanas horarias, capacidad (kg/m3), refrigeración, horizonte.
- Calcula tiempo mínimo requerido por pedido (pickup->drop + servicio).
Genera: orders_diagnostics.csv con flags por pedido.

Uso:
  pip install pandas geopy python-dateutil
  python check_advanced_vrp_readiness.py --speed_kmh 32
"""
import argparse, math
import pandas as pd
from geopy.distance import geodesic
from dateutil import parser as dtparser
from datetime import datetime

def iso_to_minutes_since_start(ts_str, day0=None):
    ts = dtparser.isoparse(str(ts_str))
    if day0 is None:
        day0 = datetime(ts.year, ts.month, ts.day, 0, 0, tzinfo=ts.tzinfo)
    delta = ts - day0
    return int(delta.total_seconds() // 60), day0

def main(speed_kmh):
    orders = pd.read_csv("orders.csv")
    vehicles = pd.read_csv("vehicles.csv")

    max_kg  = int(vehicles['capacity_kg'].max())
    max_m3  = float(vehicles['capacity_m3'].max())
    has_refrig = int((vehicles['refrigerated'] == 1).any())

    pickup_service = 10
    drop_service   = 10

    rows = []
    day0 = None
    for _, o in orders.iterrows():
        # Distancia y tiempo mínimo de viaje
        km = geodesic((o['pickup_lat'], o['pickup_lon']), (o['dropoff_lat'], o['dropoff_lon'])).km
        travel_min = int(math.ceil((km / max(1e-6, speed_kmh)) * 60))
        min_needed = travel_min + pickup_service + drop_service

        # Ventanas
        tws, day0 = iso_to_minutes_since_start(o['window_start'], day0)
        twe, _    = iso_to_minutes_since_start(o['window_end'],   day0)
        win_len   = twe - tws

        flags = []
        if win_len < min_needed:
            flags.append(f"ventana_corta({win_len}<{min_needed})")
        if int(o['weight_kg']) > max_kg:
            flags.append(f"peso_excede({o['weight_kg']}>{max_kg})")
        if float(o.get('volume_m3', 0.0)) > max_m3:
            flags.append(f"vol_excede({o.get('volume_m3', 0.0)}>{max_m3})")
        if int(o.get('refrigerated_required', 0)) == 1 and not has_refrig:
            flags.append("refrig_sin_vehiculo")
        if twe < tws:
            flags.append("tw_invertida")

        rows.append({
            "order_id": o['order_id'],
            "km_pick_drop": round(km, 2),
            "min_viaje": travel_min,
            "min_servicio": pickup_service + drop_service,
            "min_total_necesarios": min_needed,
            "tw_start_min": tws,
            "tw_end_min": twe,
            "tw_duracion_min": win_len,
            "peso_kg": int(o['weight_kg']),
            "vol_m3": float(o.get('volume_m3', 0.0)),
            "refrigerated_required": int(o.get('refrigerated_required', 0)),
            "flags": ";".join(flags) if flags else ""
        })

    df = pd.DataFrame(rows)
    df.to_csv("orders_diagnostics.csv", index=False)
    print("OK -> orders_diagnostics.csv generado.")
    print(df[['order_id','flags']].head(10))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed_kmh", type=float, default=32.0)
    args = ap.parse_args()
    main(args.speed_kmh)
