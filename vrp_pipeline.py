# vrp_pipeline.py
"""
Pipeline robusto: siempre intenta dejarte un plan.
Orden:
  1) VRP avanzado (vrp_advanced_fixed.py)
  2) Si falla: relaja pedidos (ventanas y requisitos) y reintenta
  3) Si aún falla: VRP simple (vrp_or_tools_demo.py)

Uso:
  python vrp_pipeline.py --speed_kmh 32
Requisitos:
  vehicles.csv, costs.json y orders.csv (o sucursales -> generate_orders_from_sucursales.py)
"""
import argparse, os, sys, shutil, subprocess
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser as dtp

def run(cmd: list[str]) -> bool:
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd, text=True)
    return proc.returncode == 0

def exists_nonempty(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0

def relax_orders(in_path="orders.csv", out_path="orders_relaxed.csv"):
    """Relaja ventanas y requisitos básicos para hacer factible el VRP (no pisa tu orders.csv)."""
    if not os.path.exists(in_path):
        print(f"[RELAX] No existe {in_path}")
        return False
    df = pd.read_csv(in_path)
    if "window_start" not in df.columns or "window_end" not in df.columns:
        print("[RELAX] No encuentro window_start/window_end en orders.csv")
        return False

    # Ventana estándar 08:00–20:00 del mismo día de cada pedido
    def day0(ts):
        t = dtp.isoparse(str(ts))
        return datetime(t.year,t.month,t.day,0,0,tzinfo=t.tzinfo)

    out = df.copy()
    for i, r in out.iterrows():
        try:
            ws = dtp.isoparse(str(r["window_start"]))
            we = dtp.isoparse(str(r["window_end"]))
        except Exception:
            base = day0(datetime.now().isoformat())
            ws = base.replace(hour=8); we = base.replace(hour=20)
        if we <= ws:
            base = day0(ws)
            ws = base.replace(hour=8)
            we = base.replace(hour=20)
        # ampliar levemente
        ws = ws - timedelta(minutes=15)
        we = we + timedelta(minutes=30)
        out.at[i,"window_start"] = ws.isoformat()
        out.at[i,"window_end"]   = we.isoformat()

        # Si hay refrigerated_required pero no hay vehículos refrigerados, lo apaga (solo para pruebas)
        if "refrigerated_required" in out.columns:
            # Decidir si hay alguno refrigerado
            try:
                v = pd.read_csv("vehicles.csv")
                has_refrig = (v.get("refrigerated", pd.Series([0])).astype(int) == 1).any()
            except Exception:
                has_refrig = False
            if int(r.get("refrigerated_required", 0)) == 1 and not has_refrig:
                out.at[i,"refrigerated_required"] = 0

    out.to_csv(out_path, index=False)
    print(f"[RELAX] Generado {out_path} ({len(out)} filas)")
    return True

def main(speed_kmh: float) -> int:
    # 1) Intento avanzado
    ok = run([sys.executable, "vrp_advanced_fixed.py", "--speed_kmh", str(speed_kmh)])
    if ok and exists_nonempty("stops_plan_advanced.csv"):
        print("[OK] Plan avanzado generado (stops_plan_advanced.csv / routes_plan_advanced.csv).")
        return 0

    # 2) Relajar y reintentar avanzado
    print("[INFO] VRP avanzado falló o no generó archivos. Intentando relajar pedidos…")
    if not relax_orders("orders.csv", "orders_relaxed.csv"):
        print("[WARN] No se pudo relajar orders. Continuo al plan simple.")
    else:
        # backup temporal
        if os.path.exists("orders.csv"):
            shutil.copyfile("orders.csv", "orders_backup.csv")
        shutil.copyfile("orders_relaxed.csv", "orders.csv")
        ok2 = run([sys.executable, "vrp_advanced_fixed.py", "--speed_kmh", str(speed_kmh)])
        # restaurar
        if os.path.exists("orders_backup.csv"):
            shutil.copyfile("orders_backup.csv", "orders.csv")
            os.remove("orders_backup.csv")
        if ok2 and exists_nonempty("stops_plan_advanced.csv"):
            print("[OK] Plan avanzado generado tras relajar pedidos.")
            return 0

    # 3) Fallback: plan simple
    print("[INFO] Ejecutando VRP simple de respaldo…")
    ok3 = run([sys.executable, "vrp_or_tools_demo.py"])
    if ok3 and exists_nonempty("routes_plan.csv"):
        print("[OK] Plan simple generado (routes_plan.csv).")
        return 0

    print("[ERROR] No se pudo generar ningún plan. Revisa orders.csv y vehicles.csv.")
    return 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed_kmh", type=float, default=32.0)
    args = ap.parse_args()
    raise SystemExit(main(args.speed_kmh))
