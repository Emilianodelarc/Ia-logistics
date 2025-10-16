MVP Logística – Datos Sintéticos
=================================

Archivos generados
------------------
- `vehicles.csv` – Flota con capacidades, costos y atributos.
- `orders.csv` – Órdenes con pickup/dropoff (lat/lon), ventanas horarias, peso/volumen, requisitos.
- `routes_history.csv` – 2–4 viajes simulados con timestamps y puntos GPS.
- `costs.json` – Tabla de costos aproximados (combustible, peaje, mantenimiento, chofer).
- `SOPs_BASE.md` – SOPs de ejemplo para usar en un asistente RAG.

Sugerencias de uso
------------------
1. Cargar `orders.csv` y `vehicles.csv` en tu solver (p.ej., OR-Tools) para armar un VRP básico.
2. Usar `routes_history.csv` para entrenar un ETA baseline (tabular: XGBoost/LightGBM).
3. Completar/ajustar `costs.json` con tus costos reales.
4. Reemplazar `SOPs_BASE.md` por tus SOPs (PDF/DOC) y crear un índice FAISS para un asistente.

Campos clave
------------
- Órdenes: `window_start` y `window_end` en ISO 8601; `refrigerated_required` (0/1).
- Vehículos: `refrigerated` (0/1), `km_per_litre`, `cost_per_km_ars`, `fixed_cost_per_day_ars`.
- Rutas históricas: `trip_id`, `vehicle_id`, `timestamp`, `lat`, `lon`, `event`.

Licencia
--------
Uso libre con fines educativos y de prueba. No representa datos reales.
