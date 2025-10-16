
"""
streamlit_app_pro_plus.py
Dashboard PRO con soporte a sucursales.csv (muestra marcadores).
Ejecutar:
  streamlit run streamlit_app_pro_plus.py
"""
import os, json
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
import folium

st.set_page_config(page_title="IA Logística – Dashboard PRO+", layout="wide")
st.title("📦 IA Logística – Dashboard PRO+")

def load_csv(p): return pd.read_csv(p) if os.path.exists(p) else None
def load_json(p):
    if os.path.exists(p):
        import json
        with open(p,"r",encoding="utf-8") as f: return json.load(f)
    return None

orders = load_csv("orders.csv")
routes_adv = load_csv("routes_plan_advanced.csv")
stops_adv  = load_csv("stops_plan_advanced.csv")
routes_simple = load_csv("routes_plan.csv")
vehicles = load_csv("vehicles.csv")
costs = load_json("costs.json")
sucursales = load_csv("sucursales.csv")

tab1, tab2, tab3 = st.tabs(["KPIs", "Rutas / Paradas", "Mapa"])

with tab1:
    st.header("KPIs")
    if routes_adv is not None:
        st.metric("Km totales (plan avanzado)", f"{routes_adv['total_distance_km'].sum():.2f} km")
    elif routes_simple is not None and "total_distance_km" in routes_simple.columns:
        st.metric("Km totales (plan simple)", f"{routes_simple['total_distance_km'].sum():.2f} km")
    else:
        st.info("Cargá un plan para ver KPIs.")
    if costs is not None and vehicles is not None:
       # CÁLCULO DE COSTOS ON-THE-FLY EN PRO+
        plan = routes_adv if routes_adv is not None else routes_simple
        if plan is not None and vehicles is not None:
            import json
            # Cargar costos (si no hay costs.json, usar defaults razonables)
            defaults = {
                "fuel_price_ars_per_litre": 1200,         # ARS/litro
                "maintenance_cost_ars_per_km": 40,        # ARS/km
                "toll_costs_ars_per_trip_avg": 300        # ARS/trayecto
            }
            if costs is None:
                costs = defaults
            else:
                defaults.update(costs)
                costs = defaults

            df = plan.merge(vehicles, on='vehicle_id', how='left', suffixes=('_plan','_veh'))
            if 'total_distance_km' in df.columns:
                df['km'] = df['total_distance_km'].fillna(0)
            else:
                df['km'] = 0  # si tu plan no trae km; (ideal: que el plan lo tenga)

            # litros = km / km_por_litro
            df['litros'] = (df['km'] / df['km_per_litre'].replace(0, pd.NA)).fillna(0)

            # componentes de costo
            df['combustible_ars']   = df['litros'] * float(costs['fuel_price_ars_per_litre'])
            df['mantenimiento_ars'] = df['km'] * float(costs['maintenance_cost_ars_per_km'])
            df['variable_km_ars']   = df['km'] * df['cost_per_km_ars'].fillna(0)
            df['peajes_ars']        = df['km'].apply(lambda x: float(costs['toll_costs_ars_per_trip_avg']) if x > 0 else 0)

            # prorrateo de fijo entre vehículos usados (al menos 1)
            usados = int((df['km'] > 0).sum()) or 1
            df['fijo_diario_ars']   = (df['fixed_cost_per_day_ars'].fillna(0)) / usados

            partes = ['combustible_ars','mantenimiento_ars','variable_km_ars','peajes_ars','fijo_diario_ars']
            df['costo_total_ars']   = df[partes].sum(axis=1)

            st.metric("Costo total (ARS)", f"{df['costo_total_ars'].sum():,.0f}")
            st.dataframe(df[['vehicle_id','km'] + partes + ['costo_total_ars']])
        else:
            st.caption("Subí plan (routes_*), vehicles.csv y opcionalmente costs.json para ver costos aquí.")


with tab2:
    st.header("Rutas / Paradas")
    if routes_adv is not None: st.subheader("Plan avanzado"); st.dataframe(routes_adv)
    if stops_adv is not None:  st.subheader("Paradas"); st.dataframe(stops_adv)
    if routes_simple is not None and routes_adv is None:
        st.subheader("Plan simple"); st.dataframe(routes_simple)
    if sucursales is not None:
        st.subheader("Sucursales"); st.dataframe(sucursales)

with tab3:
    st.header("Mapa")
    # Centro
    lat0, lon0 = -32.953, -60.650
    if stops_adv is not None and len(stops_adv) > 0:
        lat0 = stops_adv['lat'].mean(); lon0 = stops_adv['lon'].mean()
    elif orders is not None and len(orders) > 0:
        lat0 = orders['dropoff_lat'].mean(); lon0 = orders['dropoff_lon'].mean()
    elif sucursales is not None and len(sucursales) > 0:
        lat0 = sucursales['lat'].mean(); lon0 = sucursales['lon'].mean()

    m = folium.Map(location=[lat0, lon0], zoom_start=11)
    drew = False

    # Rutas avanzadas
    if stops_adv is not None and len(stops_adv) > 0:
        for veh_id, g in stops_adv.groupby('vehicle_id'):
            g = g.sort_values('arrive_min'); coords = g[['lat','lon']].values.tolist()
            folium.PolyLine(coords, tooltip=f"Vehículo {veh_id}").add_to(m)
            for _, r in g.iterrows():
                folium.CircleMarker([r['lat'],r['lon']], radius=4).add_to(m)
            drew = True

    # Rutas simples
    if not drew and routes_simple is not None and orders is not None:
        lookup = orders.set_index('order_id')[['dropoff_lat','dropoff_lon']].to_dict('index')
        for _, row in routes_simple.iterrows():
            seq = [p.strip() for p in str(row.get('route_sequence','')).split("->") if p.strip()]
            coords = []
            for t in seq:
                if t == "DEPOT":
                    coords.append([orders['dropoff_lat'].mean(), orders['dropoff_lon'].mean()])
                elif t in lookup:
                    coords.append([lookup[t]['dropoff_lat'], lookup[t]['dropoff_lon']])
            if len(coords) >= 2:
                folium.PolyLine(coords, tooltip=f"Vehículo {row['vehicle_id']}").add_to(m)
                for lat,lon in coords: folium.CircleMarker([lat,lon], radius=4).add_to(m)
                drew = True

    # Sucursales como marcadores
    if sucursales is not None and len(sucursales) > 0:
        for _, r in sucursales.iterrows():
            folium.Marker([r['lat'], r['lon']], popup=f"Sucursal: {r['sucursal']}").add_to(m)
        drew = True

    if not drew:
        st.warning("Subí un plan (avanzado o simple) o sucursales.csv para ver el mapa.")

    st_folium(m, height=650, use_container_width=True)
