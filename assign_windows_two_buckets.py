
"""
assign_windows_two_buckets.py
Fuerza DOS ventanas de entrega para todos los pedidos:
  - Ventana TEMPRANA: 06:00–08:00
  - Ventana TARDE:    08:00–20:00

Asignación:
  --mode priority  -> usa columna 'priority' si existe (criticidad/alta -> temprano; normal -> tarde)
  --mode ratio     -> reparte al azar según --pct_early (0.0–1.0, default 0.4)

Uso:
  python assign_windows_two_buckets.py --mode priority
  python assign_windows_two_buckets.py --mode ratio --pct_early 0.35
  # Para aplicar directamente sobre orders.csv:
  python assign_windows_two_buckets.py --mode priority --apply
"""
import argparse
import pandas as pd
import random
from datetime import datetime

def day0(dt=None):
    if dt is None:
        dt = datetime.now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)

def main(mode: str, pct_early: float, apply: bool):
    src = "orders.csv"
    df = pd.read_csv(src)
    if 'window_start' not in df.columns or 'window_end' not in df.columns:
        # si no existen, las creamos
        df['window_start'] = ''
        df['window_end'] = ''

    base = day0()
    early_start = base.replace(hour=6)
    early_end   = base.replace(hour=8)
    late_start  = base.replace(hour=8)
    late_end    = base.replace(hour=23, minute=59)

    assign_early = [False] * len(df)

    if mode == 'priority' and 'priority' in df.columns:
        for i, p in enumerate(df['priority'].astype(str).str.lower().tolist()):
            assign_early[i] = p in ('alta', 'criticidad', 'critico', 'crítica', 'urgente')
    else:
        random.seed(42)
        for i in range(len(df)):
            assign_early[i] = (random.random() < max(0.0, min(1.0, pct_early)))

    for i, is_early in enumerate(assign_early):
        if is_early:
            df.at[i, 'window_start'] = early_start.isoformat()
            df.at[i, 'window_end']   = early_end.isoformat()
        else:
            df.at[i, 'window_start'] = late_start.isoformat()
            df.at[i, 'window_end']   = late_end.isoformat()

    out = "orders_two_windows.csv"
    df.to_csv(out, index=False)
    print(f"OK -> {out} ({len(df)} pedidos). Early={sum(assign_early)} Late={len(df)-sum(assign_early)}")

    if apply:
        df.to_csv("orders.csv", index=False)
        print("Se escribió también sobre orders.csv (apply=True).")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["priority","ratio"], default="priority")
    ap.add_argument("--pct_early", type=float, default=0.4)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    main(args.mode, args.pct_early, args.apply)
