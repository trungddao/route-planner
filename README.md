# GCPS Daily Route Planner

A full-stack web application built for **Gwinnett County Public Schools (GCPS)** field, facilities, and logistics teams to plan, reorder, and optimize daily multi-stop driving routes across **146 active school and support facility locations**.

The application combines a **FastAPI (Python)** backend, real road-network routing via **OSRM (Open Source Routing Machine)**, and an interactive **React + Tailwind CSS + Leaflet** street map interface with a print-ready driver checklist.

---

## Key Features

- **Flexible Starting Hub Selection:** Start a route from any of the main GCPS Support Facilities (`SF`) using one-click **Quick Hub** buttons, search across all 146 locations by school name, Loc #, or cluster, or click **Set Start** directly on any school card.
- **Compact School Picker Widget (Step 1):** Filter all 146 active GCPS locations in a fixed-height scrollable list using real-time search (by name, GCPS Loc #, or cluster) and a cluster dropdown menu.
- **Real Road Mileage & Drive Times (Step 2):** Calculates true turn-by-turn road distance (miles) and driving duration (minutes) between every stop—not straight-line estimates.
- **One-Click Route Optimization:** Reorders multi-stop routes into the shortest driving sequence using a real-road distance matrix and displays total miles saved.
- **Interactive Street Map:** Displays an OpenStreetMap view of Gwinnett County with numbered stop markers, popup details, and a road-following route line (blue for manual order, green for optimized).
- **Driver Checklist & Print Mode:** Check off completed stops on screen or click **Print Paper Checklist** (`no-print` rules automatically hide search controls and buttons for clean printing).

---

## Project Structure

```text
route-planner/
├── README.md                        # Project architecture & setup documentation
├── backend/
│   ├── main.py                      # FastAPI server, Excel parser, & OSRM routing endpoints
│   ├── geocode_schools.py           # One-time GPS lookup & caching utility for 146 locations
│   ├── location_list.xlsx           # Master GCPS location spreadsheet (CentegixUIVisible == 1)
│   └── gcps_coords_cache.json       # Cached (lat, lon) GPS coordinates for fast startup
└── frontend/
    ├── package.json                 # React, Vite, Tailwind CSS, Leaflet, & Lucide dependencies
    ├── index.html                   # App entry HTML
    └── src/
        ├── main.jsx                 # React DOM root mount
        └── App.jsx                  # Complete UI, state management, & Leaflet map component
```

---

## How It Works Under the Hood

### 1. Data Ingestion & GPS Geocoding (`geocode_schools.py` & `main.py`)
1. **Excel Parsing:** On startup, `main.py` reads `location_list.xlsx` using `pandas` and `openpyxl`. It automatically handles both standard multi-column spreadsheets and single-column CSV-formatted sheets, filtering rows where `CentegixUIVisible == 1` (146 active facilities).
2. **Coordinate Resolution:** Because `location_list.xlsx` stores location names, GCPS IDs, and cluster names without street addresses, `geocode_schools.py` resolves exact `(latitude, longitude)` pairs once and saves them to `gcps_coords_cache.json`:
   - **Exact Overrides:** Key administrative and support hubs (such as `01A` J. Alvin Wilbanks ISC, `050` Facilities & Operations, `024` Transportation/SDC, `03D` Buice Center, and `631` GSMST) use verified pin coordinates.
   - **OpenStreetMap Lookup:** Remaining schools are queried via the Photon geocoding API and validated against Gwinnett County's geographic bounding box (`33.72°–34.22° N`, `-84.32°–-83.75° W`).
   - **Cluster Fallback:** If a facility cannot be matched externally, it defaults to its GCPS cluster's geographic center.

### 2. Real Road Routing & Optimization Engine (`main.py`)
- **Manual Route Calculation (`POST /api/route`):**
  - Sends `[depot, ...stops]` to `router.project-osrm.org/route/v1/driving/...` with `overview=full` and `geometries=geojson`.
  - Converts meters to miles ($\text{meters} \times 0.000621371$) and seconds to rounded minutes for each leg and the overall trip, returning the GeoJSON road polyline for Leaflet.
  - **Offline Fallback:** If OSRM is temporarily unreachable, the backend automatically falls back to Haversine great-circle distance multiplied by a `1.25` road-winding factor so the app never crashes.
- **Shortest Route Solver (`POST /api/optimize`):**
  1. Requests an $N \times N$ driving distance matrix from OSRM (`/table/v1/driving/...`) covering the starting hub and all selected stops.
  2. Computes the baseline mileage of the user's current stop order.
  3. Runs a **Nearest Neighbor** heuristic starting at the selected depot—iteratively selecting the unvisited stop with the lowest actual road mileage from the current location.
  4. Fetches the full road geometry for the optimized sequence and returns `saved_miles` ($\max(0, \text{before} - \text{after})$).

### 3. Frontend Architecture (`frontend/src/App.jsx`)
- **State Synchronization:** Every stop addition, removal, manual reorder (`Move Up` / `Move Down`), or starting-hub change triggers `refreshRoadRoute()` to keep leg distances, travel times, and the map polyline in sync.
- **Duplicate Guard:** Selecting a location as the `Starting Location` automatically removes it from `selectedStops` (if present) and disables its **Add** button in Step 1.
- **Leaflet Integration (`StreetRouteMap`):** Renders OpenStreetMap tiles, fits map bounds dynamically around all active pins (`fitBounds`), and draws numbered circular markers and a `START` badge.

---

## Setup & Installation

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** and **npm**
- `location_list.xlsx` placed inside the `backend/` folder

### 1. Backend Setup
Open a terminal in `route-planner/backend`:

```powershell
cd backend
pip install fastapi uvicorn pandas openpyxl requests
```

Run the one-time geocoding script to generate `gcps_coords_cache.json` (~40 seconds):

```powershell
python geocode_schools.py
```

Start the FastAPI server:

```powershell
uvicorn main:app --reload
```
The API will run at **`http://127.0.0.1:8000`**.

### 2. Frontend Setup
Open a second terminal in `route-planner/frontend`:

```powershell
cd frontend
npm install
npm install leaflet lucide-react
npm run dev
```
Open **`http://localhost:5173`** in your browser.

---

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/locations` | Parses `location_list.xlsx`, merges cached GPS coordinates, and returns `{ "depot": {...}, "locations": [...] }`. |
| `POST` | `/api/route` | Accepts `{ "depot": {...}, "stops": [...] }` and returns `{ "stops", "total_miles", "total_minutes", "legs", "geometry" }`. |
| `POST` | `/api/optimize` | Accepts `{ "depot": {...}, "stops": [...] }`, reorders stops via OSRM road distance matrix, and returns the optimized route plus `saved_miles`. |