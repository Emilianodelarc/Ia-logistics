
"""
ETA baseline (fixed) con rutas históricas.
- Lee routes_history.csv
- Calcula duración por viaje
- Calcula distancia con Haversine vectorizado (NumPy)
- Entrena un modelo simple (RandomForest) para predecir duración
Requisitos:
    pip install pandas numpy scikit-learn
Ejecución:
    python eta_baseline_skeleton_fixed.py
"""
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import RandomForestRegressor

RTE_PATH = "routes_history.csv"

# 1) Cargar datos
df = pd.read_csv(RTE_PATH, parse_dates=['timestamp'])

# Limpieza básica
df = df.dropna(subset=['trip_id','lat','lon','timestamp']).copy()
df['hour'] = df['timestamp'].dt.hour
df['dow'] = df['timestamp'].dt.dayofweek

# 2) Duración por viaje (en minutos)
durations = df.groupby('trip_id', as_index=False).agg(
    start=('timestamp','min'),
    end=('timestamp','max')
)
durations['duration_min'] = (durations['end'] - durations['start']).dt.total_seconds() / 60.0

# 3) Geometría por viaje (primera y última posición)
trip_geo = df.groupby('trip_id', as_index=False).agg(
    lat_first=('lat','first'), lon_first=('lon','first'),
    lat_last=('lat','last'),   lon_last=('lon','last'),
    hour=('hour','median'),    dow=('dow','median')
)

# 4) Haversine vectorizado (en km)
def haversine_km_vec(lat1, lon1, lat2, lon2):
    lat1 = np.radians(lat1.astype(float).to_numpy())
    lon1 = np.radians(lon1.astype(float).to_numpy())
    lat2 = np.radians(lat2.astype(float).to_numpy())
    lon2 = np.radians(lon2.astype(float).to_numpy())
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2.0)**2
    c = 2*np.arctan2(np.sqrt(a), np.sqrt(1-a))
    R = 6371.0
    return R * c

trip_geo['distance_km'] = haversine_km_vec(
    trip_geo['lat_first'], trip_geo['lon_first'],
    trip_geo['lat_last'],  trip_geo['lon_last']
)

# 5) Merge y filtrado
data = trip_geo.merge(durations[['trip_id','duration_min']], on='trip_id', how='inner')
# Filtrar viajes demasiado cortos o sin duración (ruido de GPS)
data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=['distance_km','duration_min','hour','dow'])
data = data[(data['distance_km'] > 0.05) & (data['duration_min'] > 2)]  # >50m y >2 min

if len(data) < 3:
    raise SystemExit(f"Hay muy pocos viajes válidos ({len(data)}) para entrenar. Agregá más histórico.")

X = data[['distance_km','hour','dow']].astype(float)
y = data['duration_min'].astype(float)

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=42)
mdl = RandomForestRegressor(n_estimators=300, random_state=42)
mdl.fit(Xtr, ytr)
pred = mdl.predict(Xte)
mae = mean_absolute_error(yte, pred)
print(f"MAE ETA (minutos): {mae:.2f} con {len(X)} viajes")

# 6) Ejemplo de uso
example = np.array([[12.3, 11, 2]], dtype=float)  # 12.3 km, 11hs, miércoles (2)
eta_min = mdl.predict(example)[0]
print(f"ETA estimada para 12.3 km @ 11hs dow=2: {eta_min:.1f} minutos")

# 7) Export mini-metricas
data[['trip_id','distance_km','duration_min','hour','dow']].to_csv('eta_training_data.csv', index=False)
print("Se exportó eta_training_data.csv con las features/targets usadas.")
