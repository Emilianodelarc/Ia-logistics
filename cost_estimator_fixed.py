
"""
Cost Estimator (fixed)
- Une por vehicle_id (no depende de 'type' en routes_plan.csv)
- Normaliza nombres de columnas (vehicle_type/type)
- Maneja ausencias con valores por defecto
Ejecutar:
    pip install pandas
    python cost_estimator_fixed.py
"""
import json
import pandas as pd

ROUTES = "routes_plan.csv"
VEH = "vehicles.csv"
COSTS = "costs.json"

def main():
    routes = pd.read_csv(ROUTES)
    veh = pd.read_csv(VEH)
    with open(COSTS, "r", encoding="utf-8") as f:
        costs = json.load(f)

    # Normalizar nombres en 'routes'
    # En vrp_or_tools_demo.py exportamos 'vehicle_type' (no 'type')
    if 'vehicle_type' not in routes.columns and 'type' in routes.columns:
        routes.rename(columns={'type':'vehicle_type'}, inplace=True)

    # Merge por vehicle_id (suficiente para recuperar specs/costos de vehículo)
    df = routes.merge(veh, on='vehicle_id', how='left', suffixes=('_route','_veh'))

    # Elegir las columnas de vehículo "válidas" (priorizar *_veh si existen)
    df['vehicle_type'] = df.get('vehicle_type', df.get('type_route', pd.Series(['unknown']*len(df))))
    if 'type_veh' in df.columns:
        df['vehicle_type'] = df['type_veh']

    # Tomar capacidades/costos desde vehículos si no están en routes
    for col in ['capacity_kg','km_per_litre','cost_per_km_ars','fixed_cost_per_day_ars']:
        if col not in df.columns or df[col].isna().all():
            # intentar desde versión *_veh
            alt = f"{col}_veh"
            if alt in df.columns:
                df[col] = df[alt]

    # Cálculos
    df['km'] = df['total_distance_km'].fillna(0)
    df['km_per_litre'] = df['km_per_litre'].replace(0, pd.NA)
    df['litros'] = (df['km'] / df['km_per_litre']).fillna(0)

    fuel = float(costs.get('fuel_price_ars_per_litre', 0))
    maint = float(costs.get('maintenance_cost_ars_per_km', 0))
    toll  = float(costs.get('toll_costs_ars_per_trip_avg', 0))

    df['combustible_ars'] = df['litros'] * fuel
    df['mantenimiento_ars'] = df['km'] * maint
    df['variable_km_ars'] = df['km'] * df['cost_per_km_ars'].fillna(0)
    df['peajes_ars'] = df['km'].apply(lambda x: toll if x > 0 else 0)

    used = int((df['km'] > 0).sum())
    used = used if used > 0 else 1
    df['fijo_diario_ars'] = (df['fixed_cost_per_day_ars'].fillna(0)) / used

    parts = ['combustible_ars','mantenimiento_ars','variable_km_ars','peajes_ars','fijo_diario_ars']
    df['costo_total_ars'] = df[parts].sum(axis=1)

    cols_out = ['vehicle_id','vehicle_type','route_sequence','km','total_load_kg'] + parts + ['costo_total_ars']
    for c in cols_out:
        if c not in df.columns:
            df[c] = 0
    df[cols_out].to_csv('route_costs.csv', index=False)

    kpis = {
        'vehiculos_usados': used,
        'km_totales': float(df['km'].sum()),
        'costo_total_ars': float(df['costo_total_ars'].sum()),
        'costo_promedio_por_km_ars': float(df['costo_total_ars'].sum() / max(1.0, df['km'].sum())),
        'costo_promedio_por_vehiculo_ars': float(df['costo_total_ars'].sum() / max(1, used)),
        'costo_medio_por_ruta_ars': float(df['costo_total_ars'].mean())
    }
    with open('kpis_resumen.txt','w',encoding='utf-8') as f:
        for k,v in kpis.items():
            f.write(f"{k}: {v}\n")

    print("OK -> route_costs.csv y kpis_resumen.txt generados (fixed).")

if __name__ == "__main__":
    main()
