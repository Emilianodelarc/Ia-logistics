
"""
extend_windows_nextday.py
Ajusta ventanas de entrega para que sean factibles según la distancia pickup->drop y tiempos de servicio.
- Si la ventana es muy corta, extiende window_end hasta cubrir (viaje + servicio + buffer).
- Si la ventana es la "temprana" (≈06:00–08:00) y es inviable, mueve a una ventana "tarde" del MISMO día o del DÍA SIGUIENTE.
- Mantiene formato ISO-8601.

Uso:
  python extend_windows_nextday.py --speed_kmh 50 --service_pick 5 --service_drop 5 --buffer_min 60 --roll_to_nextday 1
Salida:
  orders_fixed_windows.csv  (no sobreescribe orders.csv)
  Para aplicar: copia manualmente sobre orders.csv
"""
import argparse
import pandas as pd
from datetime import datetime, timedelta
import math

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

def parse_iso(ts):
    # tolerar strings sin tz
    try:
        from dateutil import parser as dtp
        return dtp.isoparse(str(ts))
    except Exception:
        # fallback: hoy
        now = datetime.now()
        return now.replace(hour=8, minute=0, second=0, microsecond=0)

def main(speed_kmh, service_pick, service_drop, buffer_min, roll_to_nextday):
    df = pd.read_csv("orders.csv")
    rows = []
    for i, r in df.iterrows():
        ws = parse_iso(r['window_start'])
        we = parse_iso(r['window_end'])
        km = haversine_km(r['pickup_lat'], r['pickup_lon'], r['dropoff_lat'], r['dropoff_lon'])
        travel_min = math.ceil((km / max(1e-6, speed_kmh)) * 60)
        min_needed = travel_min + service_pick + service_drop + buffer_min

        win_len = (we - ws).total_seconds() / 60.0
        early_bucket = (ws.hour == 6 and we.hour == 8)

        # Caso 1: ventana suficiente -> dejar igual
        if win_len >= min_needed and we > ws:
            rows.append(r.to_dict())
            continue

        # Caso 2: temprana inviable -> mover a tarde
        if early_bucket:
            # tarde mismo día
            new_ws = ws.replace(hour=8, minute=0, second=0, microsecond=0)
            new_we = new_ws + timedelta(minutes=min_needed)
            if roll_to_nextday and (new_we.date() != new_ws.date() or min_needed > (24-8)*60):
                # mover a día siguiente, 08:00
                nd = new_ws + timedelta(days=1)
                new_ws = nd.replace(hour=8, minute=0, second=0, microsecond=0)
                new_we = new_ws + timedelta(minutes=min_needed)
            r['window_start'] = new_ws.isoformat()
            r['window_end'] = new_we.isoformat()
            rows.append(r.to_dict())
            continue

        # Caso 3: ventana tarde corta -> estirar end
        new_we = ws + timedelta(minutes=min_needed)
        if roll_to_nextday and new_we.date() != ws.date():
            # permitir cruzar al día siguiente
            pass
        r['window_end'] = new_we.isoformat()
        rows.append(r.to_dict())

    out = pd.DataFrame(rows)
    out.to_csv("orders_fixed_windows.csv", index=False)
    print("OK -> orders_fixed_windows.csv generado. Revisá y, si te sirve, copiálo sobre orders.csv")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed_kmh", type=float, default=50.0)
    ap.add_argument("--service_pick", type=int, default=5)
    ap.add_argument("--service_drop", type=int, default=5)
    ap.add_argument("--buffer_min", type=int, default=60)
    ap.add_argument("--roll_to_nextday", type=int, default=1)
    args = ap.parse_args()
    main(args.speed_kmh, args.service_pick, args.service_drop, args.buffer_min, bool(args.roll_to_nextday))
