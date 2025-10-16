
"""
ETA baseline (skeleton) con rutas históricas.
- Extrae velocidades medias por tramo y por hora del día
- Entrena un modelo simple (LightGBM/XGBoost) para predecir duración
Requisitos:
    pip install pandas numpy scikit-learn lightgbm
Ejecutar:
    python eta_baseline_skeleton.py
"""
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import RandomForestRegressor  # placeholder; puedes cambiar a LightGBM

RTE_PATH = "routes_history.csv"

df = pd.read_csv(RTE_PATH, parse_dates=['timestamp'])

# 1) Features simples: hora, día_semana, velocidad observada
df['hour'] = df['timestamp'].dt.hour
df['dow'] = df['timestamp'].dt.dayofweek

# Duración por viaje = max(ts) - min(ts)
durations = df.groupby('trip_id').agg(
    start=('timestamp','min'),
    end=('timestamp','max')
).reset_index()
durations['duration_min'] = (durations['end'] - durations['start']).dt.total_seconds()/60

# Distancia aproximada del viaje (inicio-fin)
def haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

trip_geo = df.groupby('trip_id').agg(
    lat_first=('lat','first'), lon_first=('lon','first'),
    lat_last=('lat','last'), lon_last=('lon','last'),
    hour=('hour','median'), dow=('dow','median')
).reset_index()
trip_geo['distance_km'] = haversine_km(trip_geo['lat_first'], trip_geo['lon_first'],
                                       trip_geo['lat_last'], trip_geo['lon_last'])

data = trip_geo.merge(durations[['trip_id','duration_min']], on='trip_id')
data = data[(data['distance_km']>0.05)]  # filtrar outliers muy cortos

X = data[['distance_km','hour','dow']]
y = data['duration_min']

if len(data) < 2:
    raise SystemExit("Muy pocos viajes para entrenar. Agregá más histórico.")

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=42)
mdl = RandomForestRegressor(n_estimators=200, random_state=42)
mdl.fit(Xtr, ytr)
pred = mdl.predict(Xte)
mae = mean_absolute_error(yte, pred)
print(f"MAE ETA (minutos): {mae:.2f}")

# Ejemplo de predicción ETA para un nuevo pedido (distancia simulada 12.3 km, hora 11, dow 2)
example = np.array([[12.3, 11, 2]])
eta_min = mdl.predict(example)[0]
print(f"ETA estimada para 12.3 km @ 11hs dow=2: {eta_min:.1f} minutos")
