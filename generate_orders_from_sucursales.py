
"""
generate_orders_from_sucursales.py
Genera pedidos sintéticos (orders.csv) a partir de sucursales.csv (sucursal, lat, lon).

Uso:
  python generate_orders_from_sucursales.py --n 30 --start "08:00" --end "20:00"
"""
import argparse, random
from datetime import datetime, timedelta
import pandas as pd
random.seed(123)

def today_iso(h, m=0):
    t = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    return t.isoformat()

def main(n, start_str, end_str, out):
    suc = pd.read_csv("sucursales.csv")
    if len(suc) < 2:
        raise SystemExit("Necesito al menos 2 sucursales para crear pickups y dropoffs.")

    # Ventana global base
    h_s, m_s = map(int, start_str.split(":"))
    h_e, m_e = map(int, end_str.split(":"))
    base_start = datetime.now().replace(hour=h_s, minute=m_s, second=0, microsecond=0)
    base_end   = datetime.now().replace(hour=h_e, minute=m_e, second=0, microsecond=0)

    orders = []
    for i in range(n):
        a, b = random.sample(range(len(suc)), 2)
        p = suc.iloc[a]; d = suc.iloc[b]
        # Subventanas aleatorias dentro del rango base
        w_start = base_start + timedelta(minutes=random.randint(0, 240))  # hasta +4h
        w_end   = min(base_end, w_start + timedelta(hours=random.choice([2,3,4])))
        orders.append({
            "order_id": f"ORD-SUC-{1000+i}",
            "client_name": d['sucursal'],
            "pickup_lat": round(float(p['lat']), 6),
            "pickup_lon": round(float(p['lon']), 6),
            "dropoff_lat": round(float(d['lat']), 6),
            "dropoff_lon": round(float(d['lon']), 6),
            "window_start": w_start.isoformat(),
            "window_end": w_end.isoformat(),
            "weight_kg": max(20, int(random.gauss(450, 200))),
            "volume_m3": round(max(0.2, abs(random.gauss(2.0, 0.9))), 2),
            "refrigerated_required": 1 if random.random() < 0.15 else 0,
            "priority": random.choice(["normal","alta","criticidad"]),
            "notes": random.choice(["", "Fragil", "Palletizado", "Apilable"])
        })
    out_df = pd.DataFrame(orders)
    out_df.to_csv(out, index=False)
    print(f"OK -> {out} con {len(out_df)} pedidos")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--start", type=str, default="08:00")
    ap.add_argument("--end", type=str, default="20:00")
    ap.add_argument("--out", type=str, default="orders.csv")
    args = ap.parse_args()
    main(args.n, args.start, args.end, args.out)
