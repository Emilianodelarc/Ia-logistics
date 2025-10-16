# vrp_advanced_soft.py
"""
VRP con Ventanas Horarias SUAVES (soft): siempre intenta planear aplicando penalizaciones por llegar
temprano o tarde, en lugar de fallar por restricciones duras.
Incluye: Pickup&Delivery, capacidades kg/m3, refrigerado (opcional), penalizaciones por TW.

Uso:
  pip install ortools pandas geopy python-dateutil
  python vrp_advanced_soft.py --speed_kmh 50 --late_penalty 6 --early_penalty 1 --ignore_refrigerated 0 --search_seconds 120

Parámetros:
  --late_penalty         penalización por minuto de atraso (p. ej. 6)
  --early_penalty        penalización por minuto de espera antes del TW (p. ej. 1)
  --ignore_refrigerated  1 para ignorar requisito de frío (solo pruebas)
  --search_seconds       tiempo máximo de búsqueda
Salida:
  routes_plan_advanced.csv, stops_plan_advanced.csv
"""
import argparse, math, sys
import pandas as pd
from geopy.distance import geodesic
from dateutil import parser as dtparser
from datetime import datetime
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

def iso_to_minutes_since_start(ts_str, day0=None):
    ts = dtparser.isoparse(str(ts_str))
    if day0 is None:
        day0 = datetime(ts.year, ts.month, ts.day, 0, 0, tzinfo=ts.tzinfo)
    delta = ts - day0
    return int(delta.total_seconds() // 60), day0

def build_vrp(speed_kmh=50.0, late_penalty=6, early_penalty=1, ignore_refrig=False, search_seconds=120):
    vehicles = pd.read_csv("vehicles.csv")
    orders = pd.read_csv("orders.csv")

    # Servicios cortos para mejorar factibilidad
    pickup_service_min = 5
    drop_service_min = 5

    # Base temporal
    day0 = None

    # Depot = centroide de pickups
    depot_lat = orders['pickup_lat'].mean()
    depot_lon = orders['pickup_lon'].mean()

    # Nodos
    nodes = [{
        'node_id': 'DEPOT', 'type':'depot', 'order_id':'', 'lat': depot_lat, 'lon': depot_lon,
        'tw_start': 0, 'tw_end': 72*60, 'service_min': 0, 'demand_kg': 0, 'demand_m3': 0, 'refrig_req': 0
    }]
    pd_pairs = []
    for _, o in orders.iterrows():
        tw_s, day0 = iso_to_minutes_since_start(o['window_start'], day0)
        tw_e, _    = iso_to_minutes_since_start(o['window_end'],   day0)

        # Pickup
        p_idx = len(nodes)
        nodes.append({
            'node_id': f"P_{o['order_id']}",
            'type':'pickup', 'order_id': o['order_id'],
            'lat': float(o['pickup_lat']), 'lon': float(o['pickup_lon']),
            'tw_start': 0, 'tw_end': max(0, int(tw_e) - drop_service_min),
            'service_min': pickup_service_min,
            'demand_kg': int(o['weight_kg']),
            'demand_m3': float(o.get('volume_m3', 0.0)),
            'refrig_req': int(o.get('refrigerated_required', 0))
        })

        # Drop
        d_idx = len(nodes)
        nodes.append({
            'node_id': f"D_{o['order_id']}",
            'type':'drop', 'order_id': o['order_id'],
            'lat': float(o['dropoff_lat']), 'lon': float(o['dropoff_lon']),
            'tw_start': int(tw_s), 'tw_end': int(tw_e),
            'service_min': drop_service_min,
            'demand_kg': -int(o['weight_kg']),
            'demand_m3': -float(o.get('volume_m3', 0.0)),
            'refrig_req': int(o.get('refrigerated_required', 0))
        })
        pd_pairs.append((p_idx, d_idx))

    N = len(nodes)

    # Distancias y tiempos
    def km(i, j):
        if i == j: return 0.0
        return geodesic((nodes[i]['lat'], nodes[i]['lon']), (nodes[j]['lat'], nodes[j]['lon'])).km
    dist_km = [[km(i,j) for j in range(N)] for i in range(N)]
    travel_min = [[int(math.ceil((dist_km[i][j] / max(1e-6, speed_kmh)) * 60)) for j in range(N)] for i in range(N)]
    service_min = [nodes[i]['service_min'] for i in range(N)]

    # Vehículos
    caps_kg = [int(x) for x in vehicles['capacity_kg'].tolist()]
    caps_m3 = [float(x) for x in vehicles['capacity_m3'].tolist()]
    refrig   = [int(x) for x in vehicles['refrigerated'].tolist()]
    n_veh = len(caps_kg)

    manager = pywrapcp.RoutingIndexManager(N, n_veh, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Tiempo de tránsito = viaje + servicio del nodo origen
    def transit_time(from_i, to_i):
        f = manager.IndexToNode(from_i); t = manager.IndexToNode(to_i)
        return int(travel_min[f][t] + service_min[f])
    time_cb = routing.RegisterTransitCallback(transit_time)
    routing.SetArcCostEvaluatorOfAllVehicles(time_cb)

    # Dimensión de tiempo con gran slack (esperas)
    horizon = 72 * 60
    routing.AddDimension(
        time_cb,
        slack_max=600,  # hasta 10h de esperas
        capacity=horizon,
        fix_start_cumul_to_zero=True,
        name="Time"
    )
    time_dim = routing.GetDimensionOrDie("Time")

    # Ventanas suaves: penalización por salir de la ventana
    for i in range(N):
        index = manager.NodeToIndex(i)
        tws = max(0, int(nodes[i]['tw_start']))
        twe = min(horizon, int(nodes[i]['tw_end'])) if nodes[i]['tw_end'] > 0 else horizon
        if twe < tws: twe = tws
        if early_penalty > 0:
            time_dim.SetCumulVarSoftLowerBound(index, tws, int(early_penalty))
        if late_penalty > 0:
            time_dim.SetCumulVarSoftUpperBound(index, twe, int(late_penalty))

    # Capacidades
    def demand_kg_cb(index):
        node = manager.IndexToNode(index)
        return int(nodes[node]['demand_kg'])
    def demand_m3_cb(index):
        node = manager.IndexToNode(index)
        return int(round(nodes[node]['demand_m3'] * 100))

    kg_idx = routing.RegisterUnaryTransitCallback(demand_kg_cb)
    m3_idx = routing.RegisterUnaryTransitCallback(demand_m3_cb)
    routing.AddDimensionWithVehicleCapacity(kg_idx, 0, caps_kg, True, "CapKG")
    routing.AddDimensionWithVehicleCapacity(m3_idx, 0, [int(c*100) for c in caps_m3], True, "CapM3")

    # Pickup & Delivery
    for (p, d) in pd_pairs:
        p_i = manager.NodeToIndex(p); d_i = manager.NodeToIndex(d)
        routing.AddPickupAndDelivery(p_i, d_i)
        routing.solver().Add(routing.VehicleVar(p_i) == routing.VehicleVar(d_i))
        routing.solver().Add(time_dim.CumulVar(p_i) <= time_dim.CumulVar(d_i))

    # Refrigerado (opcional)
    if not ignore_refrig:
        for i in range(1, N):
            if nodes[i]['refrig_req'] == 1:
                allowed = [v for v in range(n_veh) if refrig[v] == 1]
                if allowed:
                    routing.SetAllowedVehiclesForIndex(allowed, manager.NodeToIndex(i))
                else:
                    print("[WARN] Hay pedidos refrigerados pero no hay vehículos refrigerados. Considerá --ignore_refrigerated 1 para pruebas.")

    # Búsqueda
    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.FromSeconds(int(search_seconds))

    solution = routing.SolveWithParameters(search)
    if solution is None:
        sys.exit("No se encontró solución (soft). Revisa capacidades extremas o coordenadas.")

    # Exportar
    rows_routes, rows_stops = [], []
    for v in range(n_veh):
        idx = routing.Start(v)
        seq_ids = []
        load_kg = 0
        total_km = 0.0
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            seq_ids.append(nodes[node]['node_id'])
            if node != 0:
                load_kg += nodes[node]['demand_kg']
            nxt = solution.Value(routing.NextVar(idx))
            node_next = manager.IndexToNode(nxt)
            total_km += dist_km[node][node_next]
            tarr = solution.Value(time_dim.CumulVar(idx))
            rows_stops.append({
                'vehicle_id': vehicles.iloc[v]['vehicle_id'],
                'stop_node': nodes[node]['node_id'],
                'stop_type': nodes[node]['type'],
                'order_id': nodes[node]['order_id'],
                'arrive_min': tarr,
                'tw_start': nodes[node]['tw_start'],
                'tw_end': nodes[node]['tw_end'],
                'lat': nodes[node]['lat'],
                'lon': nodes[node]['lon']
            })
            idx = nxt
        # fin depot
        node = manager.IndexToNode(idx)
        tarr = solution.Value(time_dim.CumulVar(idx))
        rows_stops.append({
            'vehicle_id': vehicles.iloc[v]['vehicle_id'],
            'stop_node': nodes[node]['node_id'],
            'stop_type': nodes[node]['type'],
            'order_id': nodes[node]['order_id'],
            'arrive_min': tarr,
            'tw_start': nodes[node]['tw_start'],
            'tw_end': nodes[node]['tw_end'],
            'lat': nodes[node]['lat'],
            'lon': nodes[node]['lon']
        })
        seq_ids.append(nodes[node]['node_id'])
        rows_routes.append({
            'vehicle_id': vehicles.iloc[v]['vehicle_id'],
            'vehicle_type': vehicles.iloc[v]['type'],
            'route_sequence': " -> ".join(seq_ids),
            'total_distance_km': round(total_km, 2),
            'total_load_kg': int(max(0, load_kg))
        })

    pd.DataFrame(rows_routes).to_csv("routes_plan_advanced.csv", index=False)
    pd.DataFrame(rows_stops).to_csv("stops_plan_advanced.csv", index=False)
    print("OK -> routes_plan_advanced.csv y stops_plan_advanced.csv generados (soft TW).")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed_kmh", type=float, default=50.0)
    ap.add_argument("--late_penalty", type=float, default=6.0)
    ap.add_argument("--early_penalty", type=float, default=1.0)
    ap.add_argument("--ignore_refrigerated", type=int, default=0)
    ap.add_argument("--search_seconds", type=int, default=120)
    args = ap.parse_args()
    build_vrp(speed_kmh=args.speed_kmh, late_penalty=args.late_penalty, early_penalty=args.early_penalty,
              ignore_refrig=bool(args.ignore_refrigerated), search_seconds=args.search_seconds)
