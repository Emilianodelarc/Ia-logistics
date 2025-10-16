
"""
VRP con OR-Tools (demo) usando los datos sintéticos.
- Lee vehicles.csv y orders.csv
- Construye un VRP simple (solo dropoffs) con capacidad por peso_kg
- Devuelve rutas_plan.csv con la secuencia de visitas por vehículo
Requisitos:
    pip install ortools pandas geopy
Ejecutar:
    python vrp_or_tools_demo.py
"""
import pandas as pd
import math
from geopy.distance import geodesic
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

VEH_PATH = "vehicles.csv"
ORD_PATH = "orders.csv"
OUT_PATH = "routes_plan.csv"

# 1) Cargar datos
vehicles = pd.read_csv(VEH_PATH)
orders = pd.read_csv(ORD_PATH)

# Usamos SOLO los dropoffs para el VRP (MVP). Luego podés extender a Pickup&Delivery.
stops = orders[['order_id', 'dropoff_lat', 'dropoff_lon', 'weight_kg']].copy()
stops.rename(columns={'dropoff_lat':'lat', 'dropoff_lon':'lon', 'weight_kg':'demand'}, inplace=True)

# Definimos un "depósito" como el centroide de los dropoffs (o una dirección propia)
depot_lat = stops['lat'].mean()
depot_lon = stops['lon'].mean()

# Construimos lista de nodos: [depot] + stops
nodes = [{'id': 'DEPOT', 'lat': depot_lat, 'lon': depot_lon, 'demand': 0}]
for _, r in stops.iterrows():
    nodes.append({'id': r['order_id'], 'lat': r['lat'], 'lon': r['lon'], 'demand': int(max(0, r['demand']))})

N = len(nodes)

# 2) Matriz de distancia (en metros) aprox con geodesic
def dist_m(i, j):
    if i == j: return 0
    return int(geodesic((nodes[i]['lat'], nodes[i]['lon']), (nodes[j]['lat'], nodes[j]['lon'])).km * 1000)

dist_matrix = [[dist_m(i, j) for j in range(N)] for i in range(N)]

# 3) Capacidades por vehículo (en kg)
caps = [int(c) for c in vehicles['capacity_kg'].tolist()]
n_veh = len(caps)

# 4) OR-Tools setup
manager = pywrapcp.RoutingIndexManager(N, n_veh, 0)  # 0 es el índice del depósito
routing = pywrapcp.RoutingModel(manager)

# Distancia
def transit_cb(from_i, to_i):
    f = manager.IndexToNode(from_i)
    t = manager.IndexToNode(to_i)
    return dist_matrix[f][t]
transit_idx = routing.RegisterTransitCallback(transit_cb)
routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

# Dimensión de distancia (opcional, si querés limitar km por vehículo)
routing.AddDimension(
    transit_idx, 0, 2_000_000, True, "Distance"
)

# Demandas/capacidad
def demand_cb(index):
    node = manager.IndexToNode(index)
    return int(nodes[node]['demand'])
demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
routing.AddDimensionWithVehicleCapacity(demand_idx, 0, caps, True, "Capacity")

# Búsqueda
search_params = pywrapcp.DefaultRoutingSearchParameters()
search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
search_params.time_limit.FromSeconds(20)

solution = routing.SolveWithParameters(search_params)
if solution is None:
    raise SystemExit("No se encontró solución. Probá reducir demandas o aumentar capacidades.")

# 5) Exportar rutas
rows = []
for v in range(n_veh):
    idx = routing.Start(v)
    seq = []
    load = 0
    dist = 0
    while not routing.IsEnd(idx):
        node = manager.IndexToNode(idx)
        seq.append(nodes[node]['id'])
        load += nodes[node]['demand']
        nxt = solution.Value(routing.NextVar(idx))
        dist += routing.GetArcCostForVehicle(idx, nxt, v)
        idx = nxt
    seq.append('DEPOT')
    rows.append({
        'vehicle_id': vehicles.iloc[v]['vehicle_id'],
        'vehicle_type': vehicles.iloc[v]['type'],
        'capacity_kg': vehicles.iloc[v]['capacity_kg'],
        'route_sequence': " -> ".join(seq),
        'total_distance_km': round(dist/1000, 2),
        'total_load_kg': int(load)
    })

pd.DataFrame(rows).to_csv(OUT_PATH, index=False)
print(f"OK. Rutas exportadas a {OUT_PATH}")
