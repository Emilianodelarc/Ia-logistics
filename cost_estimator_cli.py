
"""
Cost Estimator (CLI) – acepta --routes
Uso:
  pip install pandas
  python cost_estimator_cli.py --routes routes_plan_advanced.csv
Si no se pasa --routes, intenta routes_plan.csv
"""
import argparse, json, os
import pandas as pd

def main(routes_file=None):
    if routes_file is None:
        routes_file = "routes_plan.csv" if os.path.exists("routes_plan.csv") else "routes_plan_advanced.csv"
    routes = pd.read_csv(routes_file)
    veh = pd.read_csv("vehicles.csv")
    with open("costs.json","r",encoding="utf-8") as f:
        costs = json.load(f)

    df = routes.merge(veh, on='vehicle_id', how='left', suffixes=('_route','_veh'))
    if 'vehicle_type' not in df.columns:
        if 'type_route' in df.columns: df.rename(columns={'type_route':'vehicle_type'}, inplace=True)
        if 'type' in df.columns: df.rename(columns={'type':'vehicle_type'}, inplace=True)
        if 'type_veh' in df.columns: df['vehicle_type'] = df['type_veh']

    # Campos desde veh si faltan
    for col in ['capacity_kg','km_per_litre','cost_per_km_ars','fixed_cost_per_day_ars']:
        if col not in df.columns or df[col].isna().all():
            alt = f"{col}_veh"
            if alt in df.columns:
                df[col] = df[alt]

    df['km'] = df['total_distance_km'].fillna(0)
    df['litros'] = (df['km'] / df['km_per_litre'].replace(0, pd.NA)).fillna(0)

    fuel = float(costs.get('fuel_price_ars_per_litre', 0))
    maint = float(costs.get('maintenance_cost_ars_per_km', 0))
    toll  = float(costs.get('toll_costs_ars_per_trip_avg', 0))

    df['combustible_ars'] = df['litros'] * fuel
    df['mantenimiento_ars'] = df['km'] * maint
    df['variable_km_ars'] = df['km'] * df['cost_per_km_ars'].fillna(0)
    df['peajes_ars'] = df['km'].apply(lambda x: toll if x > 0 else 0)

    used = int((df['km'] > 0).sum()) or 1
    df['fijo_diario_ars'] = (df['fixed_cost_per_day_ars'].fillna(0)) / used
    parts = ['combustible_ars','mantenimiento_ars','variable_km_ars','peajes_ars','fijo_diario_ars']
    df['costo_total_ars'] = df[parts].sum(axis=1)

    cols_out = ['vehicle_id','vehicle_type','route_sequence','km','total_load_kg'] + parts + ['costo_total_ars']
    for c in cols_out:
        if c not in df.columns:
            df[c] = 0
    df[cols_out].to_csv('route_costs.csv', index=False)

    kpis = {
        'vehiculos_usados': int((df['km']>0).sum()),
        'km_totales': float(df['km'].sum()),
        'costo_total_ars': float(df['costo_total_ars'].sum()),
        'costo_promedio_por_km_ars': float(df['costo_total_ars'].sum() / max(1.0, df['km'].sum())),
        'costo_promedio_por_vehiculo_ars': float(df['costo_total_ars'].sum() / max(1, int((df['km']>0).sum()))),
        'costo_medio_por_ruta_ars': float(df['costo_total_ars'].mean())
    }
    with open('kpis_resumen.txt','w',encoding='utf-8') as f:
        for k,v in kpis.items():
            f.write(f"{k}: {v}\n")

    print(f"OK -> route_costs.csv y kpis_resumen.txt generados desde {routes_file}.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", type=str, default=None, help="Archivo de rutas (routes_plan_advanced.csv o routes_plan.csv)")
    args = ap.parse_args()
    main(args.routes)
