
"""
VRP avanzado (FIXED): Pickup&Delivery + Ventanas + Capacidad kg/m3 + Refrigerado
Cambios vs versión previa (para evitar CP Solver fail):
- El tiempo de servicio se suma en el callback de tránsito (no en SlackVar).
- Ventanas horarias se CLAMP a [0, horizon] y garantizamos twe >= tws (+1 min si hace falta).
- Horizonte ampliado a 72h para tolerar múltiples días.
- Mensajes de depuración si se ajustan ventanas.

Uso:
  pip install ortools pandas geopy python-dateutil
  python vrp_advanced_fixed.py --speed_kmh 32
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

def build_vrp(speed_kmh=30.0):
    vehicles = pd.read_csv("vehicles.csv")
    orders = pd.read_csv("orders.csv")

    # Parámetros
    pickup_service_min = 5
    drop_service_min = 5

    # Base temporal (día 0 = median de window_start)
    day0 = None

    # Nodos: depot (centroide pickups) + pickups + drops
    depot_lat = orders['pickup_lat'].mean()
    depot_lon = orders['pickup_lon'].mean()

    nodes = [{
        'node_id': 'DEPOT', 'type':'depot', 'order_id':'', 'lat': depot_lat, 'lon': depot_lon,
        'tw_start': 0, 'tw_end': 0, 'service_min': 0, 'demand_kg': 0, 'demand_m3': 0, 'refrig_req': 0
    }]

    pd_pairs = []
    for _, o in orders.iterrows():
        tw_s, day0 = iso_to_minutes_since_start(o['window_start'], day0)
        tw_e, _   = iso_to_minutes_since_start(o['window_end'], day0)

        # Pickup (ventana amplia, hasta el fin del drop)
        p_idx = len(nodes)
        nodes.append({
            'node_id': f"P_{o['order_id']}",
            'type':'pickup', 'order_id': o['order_id'],
            'lat': float(o['pickup_lat']), 'lon': float(o['pickup_lon']),
            'tw_start': 0, 'tw_end': max(0, tw_e - drop_service_min),
            'service_min': pickup_service_min,
            'demand_kg': int(o['weight_kg']),
            'demand_m3': float(o.get('volume_m3', 0.0)),
            'refrig_req': int(o.get('refrigerated_required', 0))
        })

        # Drop (usa la ventana real)
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

    # Distancias y tiempos base (sin servicio)
    def km(i, j):
        if i == j: return 0.0
        return geodesic((nodes[i]['lat'], nodes[i]['lon']), (nodes[j]['lat'], nodes[j]['lon'])).km
    dist_km = [[km(i,j) for j in range(N)] for i in range(N)]
    travel_min = [[int(math.ceil((dist_km[i][j] / max(1e-6, speed_kmh)) * 60)) for j in range(N)] for i in range(N)]

    # Servicio por nodo
    service_min = [nodes[i]['service_min'] for i in range(N)]

    # Vehículos
    caps_kg = [int(x) for x in vehicles['capacity_kg'].tolist()]
    caps_m3 = [float(x) for x in vehicles['capacity_m3'].tolist()]
    refrig   = [int(x) for x in vehicles['refrigerated'].tolist()]
    n_veh = len(caps_kg)

    # Modelo
    manager = pywrapcp.RoutingIndexManager(N, n_veh, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Tiempo de tránsito = viaje + servicio EN EL ORIGEN del arco
    def transit_time(from_i, to_i):
        f = manager.IndexToNode(from_i); t = manager.IndexToNode(to_i)
        return int(travel_min[f][t] + service_min[f])
    time_cb = routing.RegisterTransitCallback(transit_time)
    routing.SetArcCostEvaluatorOfAllVehicles(time_cb)

    # Dimensión tiempo
    horizon = 72 * 60  # 72 horas
    routing.AddDimension(
        time_cb,
        slack_max=120,       # hasta 2h de espera
        capacity=horizon,
        fix_start_cumul_to_zero=True,
        name="Time"
    )
    time_dim = routing.GetDimensionOrDie("Time")

    # Ventanas: clamp a [0, horizon], y twe >= tws
    adjusted = 0
    for i in range(N):
        tws, twe = nodes[i]['tw_start'], nodes[i]['tw_end']
        # depot: ventana amplia si no definida
        if i == 0 and (tws == 0 and twe == 0):
            tws, twe = 0, horizon
        # clamp
        new_tws = max(0, min(horizon, int(tws)))
        new_twe = max(0, min(horizon, int(twe)))
        if new_twe < new_tws:
            new_twe = new_tws + 1  # mínimo 1 minuto
        if new_tws != tws or new_twe != twe:
            adjusted += 1
        ct = time_dim.CumulVar(manager.NodeToIndex(i))
        ct.SetRange(new_tws, new_twe)

    if adjusted > 0:
        print(f"[INFO] Se ajustaron {adjusted} ventanas para que encajen en [0, {horizon}] y twe>=tws.")

    # Capacidades kg y m3
    def demand_kg_cb(index):
        node = manager.IndexToNode(index)
        return int(nodes[node]['demand_kg'])
    def demand_m3_cb(index):
        node = manager.IndexToNode(index)
        return int(round(nodes[node]['demand_m3'] * 100))  # centésimas de m3

    kg_idx = routing.RegisterUnaryTransitCallback(demand_kg_cb)
    m3_idx = routing.RegisterUnaryTransitCallback(demand_m3_cb)
    routing.AddDimensionWithVehicleCapacity(kg_idx, 0, caps_kg, True, "CapKG")
    routing.AddDimensionWithVehicleCapacity(m3_idx, 0, [int(c*100) for c in caps_m3], True, "CapM3")

    # Pickup & Delivery: misma unidad y precedencia tiempo
    for (p, d) in pd_pairs:
        p_i = manager.NodeToIndex(p); d_i = manager.NodeToIndex(d)
        routing.AddPickupAndDelivery(p_i, d_i)
        routing.solver().Add(routing.VehicleVar(p_i) == routing.VehicleVar(d_i))
        routing.solver().Add(time_dim.CumulVar(p_i) <= time_dim.CumulVar(d_i))

    # Refrigerado
    for i in range(1, N):
        if nodes[i]['refrig_req'] == 1:
            allowed = [v for v in range(n_veh) if refrig[v] == 1]
            if not allowed:
                sys.exit("No hay vehículos refrigerados pero existen pedidos refrigerados.")
            routing.SetAllowedVehiclesForIndex(allowed, manager.NodeToIndex(i))

    # Búsqueda
    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.FromSeconds(60)

    solution = routing.SolveWithParameters(search)
    if solution is None:
        sys.exit("No se encontró solución. Sugerencias: aumentar --speed_kmh, revisar ventanas/capacidades, o quitar refrigerado.")

    # Export
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
            tdep = tarr  # el servicio ya se consideró en el tránsito saliente
            rows_stops.append({
                'vehicle_id': vehicles.iloc[v]['vehicle_id'],
                'stop_node': nodes[node]['node_id'],
                'stop_type': nodes[node]['type'],
                'order_id': nodes[node]['order_id'],
                'arrive_min': tarr,
                'depart_min': tdep,
                'tw_start': nodes[node]['tw_start'],
                'tw_end': nodes[node]['tw_end'],
                'lat': nodes[node]['lat'],
                'lon': nodes[node]['lon']
            })
            idx = nxt
        # fin de ruta (depot)
        node = manager.IndexToNode(idx)
        tarr = solution.Value(time_dim.CumulVar(idx))
        rows_stops.append({
            'vehicle_id': vehicles.iloc[v]['vehicle_id'],
            'stop_node': nodes[node]['node_id'],
            'stop_type': nodes[node]['type'],
            'order_id': nodes[node]['order_id'],
            'arrive_min': tarr,
            'depart_min': tarr,
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
    print("OK -> routes_plan_advanced.csv y stops_plan_advanced.csv generados.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed_kmh", type=float, default=30.0)
    args = ap.parse_args()
    build_vrp(speed_kmh=args.speed_kmh)
