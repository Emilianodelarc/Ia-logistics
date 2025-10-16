"""
streamlit_app_pro_plus_charts.py
Dashboard PRO con:
- KPIs
- Rutas / Paradas
- Mapa
- Gráficos (Plotly): km por vehículo, costos, puntualidad, distribución de llegadas

Ejecutar:
  streamlit run streamlit_app_pro_plus_charts.py
"""
import os, json
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
import folium
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="IA Logística – Dashboard PRO+ Charts", layout="wide")
st.title("📦 IA Logística – Dashboard PRO+ (con gráficos)")

# ---------- Helpers ----------
@st.cache_data
def load_csv(p):
    return pd.read_csv(p) if os.path.exists(p) else None

@st.cache_data
def load_json(p):
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as f: 
            return json.load(f)
    return None

def ensure_costs(costs_obj):
    defaults = {
        "fuel_price_ars_per_litre": 1200,   # ARS/litro
        "maintenance_cost_ars_per_km": 40,  # ARS/km
        "toll_costs_ars_per_trip_avg": 300  # ARS/trayecto
    }
    if costs_obj is None:
        return defaults
    defaults.update(costs_obj)
    return defaults

def compute_cost_table(plan_df, vehicles_df, costs_cfg):
    """Devuelve un dataframe con km y costos por vehículo."""
    if plan_df is None or vehicles_df is None:
        return None
    df = plan_df.merge(vehicles_df, on='vehicle_id', how='left', suffixes=('_plan','_veh'))
    km_col = 'total_distance_km' if 'total_distance_km' in df.columns else None
    if km_col is None:
        df['km'] = 0.0
    else:
        df['km'] = df[km_col].fillna(0.0)

    # litros = km / km_por_litro
    df['litros'] = (df['km'] / df['km_per_litre'].replace(0, pd.NA)).fillna(0)

    # componentes
    df['combustible_ars']   = df['litros'] * float(costs_cfg['fuel_price_ars_per_litre'])
    df['mantenimiento_ars'] = df['km'] * float(costs_cfg['maintenance_cost_ars_per_km'])
    df['variable_km_ars']   = df['km'] * df['cost_per_km_ars'].fillna(0)
    df['peajes_ars']        = df['km'].apply(lambda x: float(costs_cfg['toll_costs_ars_per_trip_avg']) if x > 0 else 0)

    # prorrateo del fijo entre vehículos "usados"
    usados = int((df['km'] > 0).sum()) or 1
    df['fijo_diario_ars']   = (df['fixed_cost_per_day_ars'].fillna(0)) / usados

    partes = ['combustible_ars','mantenimiento_ars','variable_km_ars','peajes_ars','fijo_diario_ars']
    df['costo_total_ars']   = df[partes].sum(axis=1)
    return df[['vehicle_id','km'] + partes + ['costo_total_ars']]

def classify_punctuality(stops_df):
    """Devuelve stops_df con columna 'estado' = en_tiempo / temprano / tarde según ventana."""
    if stops_df is None or len(stops_df) == 0:
        return None
    df = stops_df.copy()
    # Solo evaluamos drops (entregas)
    if 'stop_type' in df.columns:
        df = df[df['stop_type'].astype(str).str.lower().eq('drop')].copy()

    for col in ['arrive_min','tw_start','tw_end']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    def etiqueta(row):
        a, s, e = row['arrive_min'], row['tw_start'], row['tw_end']
        if pd.isna(a) or pd.isna(s) or pd.isna(e):
            return 'sin_dato'
        if a < s:  return 'temprano'
        if a > e:  return 'tarde'
        return 'en_tiempo'

    df['estado'] = df.apply(etiqueta, axis=1)
    # También guardamos delta vs ventana
    df['min_antes_inicio'] = df['tw_start'] - df['arrive_min']
    df['min_despues_fin']  = df['arrive_min'] - df['tw_end']
    return df

# ---------- Carga de datos ----------
orders       = load_csv("orders.csv")
routes_adv   = load_csv("routes_plan_advanced.csv")
stops_adv    = load_csv("stops_plan_advanced.csv")
routes_simple= load_csv("routes_plan.csv")
vehicles     = load_csv("vehicles.csv")
costs_raw    = load_json("costs.json")
sucursales   = load_csv("sucursales.csv")
costs        = ensure_costs(costs_raw)

tab1, tab2, tab3, tab4 = st.tabs(["KPIs", "Rutas / Paradas", "Mapa", "Gráficos"])

# ---------- KPIs ----------
with tab1:
    st.header("KPIs")
    plan = routes_adv if routes_adv is not None else routes_simple
    if plan is not None:
        km_total = plan['total_distance_km'].sum() if 'total_distance_km' in plan.columns else 0.0
        st.metric("Km totales", f"{km_total:.2f} km")
    else:
        st.info("Cargá un plan para ver KPIs.")

    # Costos on-the-fly
    table_costos = compute_cost_table(plan, vehicles, costs)
    if table_costos is not None:
        st.metric("Costo total (ARS)", f"{table_costos['costo_total_ars'].sum():,.0f}")
        st.dataframe(table_costos)
    else:
        st.caption("Subí plan (routes_*), vehicles.csv y opcionalmente costs.json para ver costos aquí.")

# ---------- Rutas / Paradas ----------
with tab2:
    st.header("Rutas / Paradas")
    if routes_adv is not None: 
        st.subheader("Plan avanzado"); st.dataframe(routes_adv)
    if stops_adv is not None:  
        st.subheader("Paradas"); st.dataframe(stops_adv)
    if routes_simple is not None and routes_adv is None:
        st.subheader("Plan simple"); st.dataframe(routes_simple)
    if sucursales is not None:
        st.subheader("Sucursales"); st.dataframe(sucursales)

# ---------- Mapa ----------
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
                for lat,lon in coords: 
                    folium.CircleMarker([lat,lon], radius=4).add_to(m)
                drew = True

    # Sucursales
    if sucursales is not None and len(sucursales) > 0:
        for _, r in sucursales.iterrows():
            folium.Marker([r['lat'], r['lon']], popup=f"Sucursal: {r['sucursal']}").add_to(m)
        drew = True

    if not drew:
        st.warning("Subí un plan (avanzado o simple) o sucursales.csv para ver el mapa.")
    st_folium(m, height=650, use_container_width=True)

# ---------- Gráficos ----------
with tab4:
    st.header("Gráficos")
    plan = routes_adv if routes_adv is not None else routes_simple
    table_costos = compute_cost_table(plan, vehicles, costs)

    colA, colB = st.columns(2)

    # A) Km por vehículo
    with colA:
        st.subheader("Distancia por vehículo")
        if plan is not None and 'vehicle_id' in plan.columns:
            df_km = plan.groupby('vehicle_id')['total_distance_km'].sum().reset_index() if 'total_distance_km' in plan.columns else None
            if df_km is not None and len(df_km) > 0:
                fig_km = px.bar(df_km, x='vehicle_id', y='total_distance_km', labels={'vehicle_id':'Vehículo','total_distance_km':'Km'}, title="Km totales por vehículo")
                st.plotly_chart(fig_km, use_container_width=True)
            else:
                st.info("El plan no tiene columna total_distance_km.")
        else:
            st.info("Cargá un plan para ver kilometrajes.")

    # B) Desglose de costos (stacked)
    with colB:
        st.subheader("Desglose de costos por vehículo")
        if table_costos is not None and len(table_costos) > 0:
            cost_cols = ['combustible_ars','mantenimiento_ars','variable_km_ars','peajes_ars','fijo_diario_ars']
            df_melt = table_costos.melt(id_vars=['vehicle_id'], value_vars=cost_cols, var_name='concepto', value_name='ARS')
            fig_cost = px.bar(df_melt, x='vehicle_id', y='ARS', color='concepto', title="Costos por vehículo (stacked)")
            st.plotly_chart(fig_cost, use_container_width=True)
        else:
            st.info("Faltan vehicles.csv / plan para calcular costos.")

    st.divider()

    # C) Puntualidad
    st.subheader("Puntualidad de entregas (en tiempo / temprano / tarde)")
    punct = classify_punctuality(stops_adv) if stops_adv is not None else None
    if punct is not None and len(punct) > 0:
        df_p = punct.groupby('estado').size().reset_index(name='cantidad')
        fig_p = px.pie(df_p, names='estado', values='cantidad', title="Distribución de estados de llegada")
        st.plotly_chart(fig_p, use_container_width=True)

        # Distribución de retraso/adelanto (en minutos)
        col1, col2 = st.columns(2)
        with col1:
            # Atraso: minutos después del fin (solo tarde)
            atrasos = punct.loc[punct['estado'].eq('tarde'), 'min_despues_fin']
            if len(atrasos) > 0:
                fig_atraso = px.histogram(atrasos, nbins=20, title="Histograma de atraso (min)")
                st.plotly_chart(fig_atraso, use_container_width=True)
            else:
                st.caption("No hay atrasos en este plan.")

        with col2:
            # Adelanto: minutos antes del inicio (solo temprano)
            adelantos = punct.loc[punct['estado'].eq('temprano'), 'min_antes_inicio']
            # min_antes_inicio es positivo si el inicio está después; tomamos su valor absoluto para magnitud
            adelantos = adelantos.abs()
            if len(adelantos) > 0:
                fig_adelanto = px.histogram(adelantos, nbins=20, title="Histograma de adelanto (min)")
                st.plotly_chart(fig_adelanto, use_container_width=True)
            else:
                st.caption("No hay llegadas tempranas en este plan.")
    else:
        st.info("Para puntualidad necesitás paradas del plan avanzado (stops_plan_advanced.csv).")
