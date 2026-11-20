# GCPS Daily Route Planner — System Architecture & Technical Documentation

An enterprise-grade, web-based route planning and route optimization application built for Gwinnett County Public Schools (GCPS). The system processes facilities data from Excel, geocodes real-world GPS coordinates, queries OpenStreetMap Road Routing Engines (OSRM) for real driving distances and durations, and calculates optimized travel itineraries to minimize driving mileage.

## 1. System Overview & Key Capabilities

* **Automated Facilities Ingestion:** Parses `location_list.xlsx` directly via Pandas, dynamically filtering visible schools and support facilities (`CentegixUIVisible == 1`).

* **Real Road Distance & Duration Engine:** Leverages the Open Source Routing Machine (OSRM) API to retrieve real turn-by-turn road distances and driving times instead of straight-line estimates.

* **Traveling Salesperson Problem (TSP) Optimization:** Uses a matrix-based Nearest-Neighbor heuristic solver to re-order selected stops into the shortest possible driving sequence.

* **Searchable Starting Hub Selector:** Allows field personnel to start routes from standard logistics hubs (e.g., J. Alvin Wilbanks ISC, Facilities & Operations, Transportation) or any of the 146 active GCPS locations via typeahead search.

* **Interactive Leaflet Map Interface:** Displays interactive vector road paths, start markers, and numbered stop pins overlaid on OpenStreetMap tiles.

* **Responsive & Accessible UI:** Designed with fixed-scale control buttons (`11x11` grid-aligned action handles) for consistent layout integrity across mobile devices and desktop screens.

* **Printer-Friendly Daily Checklist:** Formats printable paper checklists with single-click browser print integration (`window.print()`).

## 2. Technical Stack

| Layer | Technology | Purpose | 
| ----- | ----- | ----- | 
| **Frontend Framework** | React (Vite, JSX) | Component-driven user interface and state management. | 
| **Styling** | Tailwind CSS v4 | Utility-first styling with high contrast and explicit layout boundaries. | 
| **Mapping Engine** | Leaflet.js | Canvas/SVG vector polyline rendering and map tile interaction. | 
| **Icons** | Lucide React | Lightweight vector iconography. | 
| **Backend Framework** | FastAPI (Python 3.10+) | Asynchronous RESTful API endpoints and data middleware. | 
| **Data Processing** | Pandas, OpenPyXL | Excel parsing, string cleanup, and CSV/DataFrame conversions. | 
| **Geocoding & GIS** | Photon API (OSM) / Geopy | Automated latitude/longitude lookup with fallback cluster heuristics. | 
| **Routing Engine** | OSRM (Open Source Routing Machine) | Distance matrix calculation and road geometry polyline generation. | 

## 3. System Data Flow Architecture

```
                      +-----------------------------+
                      |   location_list.xlsx        |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  geocode_schools.py         |
                      |  (Photon API + Fallbacks)   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  gcps_coords_cache.json     |
                      +--------------+--------------+
                                     |
                                     v
  +--------------------+    HTTP GET |    +----------------------+
  | React Client App   |<------------------| FastAPI Backend      |
  | (App.jsx)          |    /api/locations | (main.py)            |
  +---------+----------+                   +----------+-----------+
            |                                         |
            | HTTP POST /api/optimize                 |
            | (Selected Depot + Stops)                |
            +---------------------------------------->|
                                                      |
                                                      v
                                           +----------------------+
                                           | OSRM Matrix API      |
                                           | Table Endpoint       |
                                           +----------+-----------+
                                                      |
                                                      v
                                           +----------------------+
                                           | Nearest Neighbor     |
                                           | Solver Algorithm     |
                                           +----------+-----------+
                                                      |
                                                      v
                                           +----------------------+
                                           | OSRM Route Engine    |
                                           | Polyline Geometry    |
                                           +----------+-----------+
                                                      |
            HTTP Response (Optimized Order,           |
            Driving Miles, Minutes, Polyline)         |
  <---------------------------------------------------+

```

## 4. Detailed Component Breakdown

### 4.1 Data Ingestion (`backend/main.py`)

When `GET /api/locations` is invoked:

1. Pandas opens `location_list.xlsx`.

2. Normalizes column headers and converts text values to sanitized strings.

3. Filters rows where `CentegixUIVisible == 1` (filtering out retired/testing locations).

4. Matches each location against `gcps_coords_cache.json` to assign exact GPS coordinates (`lat`, `lon`).

### 4.2 Geocoding Pipeline (`backend/geocode_schools.py`)

To prevent external API rate-limiting during active usage, coordinates are cached once in `gcps_coords_cache.json`:

1. **Exact Overrides:** Support facilities with non-standard address strings (e.g., J. Alvin Wilbanks ISC, Facilities & Operations) are pinned to verified coordinates.

2. **Photon Geocoder Query:** Queries `https://photon.komoot.io/api/` with string permutations constrained inside Gwinnett County boundaries ($33.72 \le \text{lat} \le 34.22$, $-84.32 \le \text{lon} \le -83.75$).

3. **Cluster Fallback:** If a school name fails external lookup, coordinates fall back to the geographic center of its assigned Safety & Security Cluster (`CLUSTER_GPS`).

### 4.3 Distance & Optimization Engine

#### Road Distance & Duration

For a sequence of points $P = [p_0, p_1, \dots, p_n]$, the system queries OSRM's table endpoint:

$$
\text{URL: } \texttt{/table/v1/driving/\{lon}_0\texttt{,}\{lat}_0\texttt{;\dots;}\{lon}_n\texttt{,}\{lat}_n\texttt{\}}
$$

OSRM returns an $(n+1) \times (n+1)$ matrix $M$, where $M_{i,j}$ represents the exact driving distance in meters from point $i$ to point $j$. Distances are converted to miles using:

$$
d_{\text{miles}} = M_{i,j} \times 0.000621371
$$

#### Traveling Salesperson Solver (Nearest Neighbor Heuristic)

Given starting depot $d = p_0$ and unvisited stop set $U = \{p_1, p_2, \dots, p_n\}$:

1. Set current location $c \leftarrow d$.

2. Find unvisited stop $s \in U$ that minimizes matrix cost $M_{c, s}$.

3. Append $s$ to optimized path $O$, set $c \leftarrow s$, and remove $s$ from $U$.

4. Repeat until $U = \emptyset$.

#### Haversine Fallback Equation

If OSRM is unreachable, the system computes spherical distances using the Haversine formula scaled by a $1.25$ road winding factor:

$$
a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)
$$

$$
d = 2 R \cdot \arcsin\left(\sqrt{a}\right) \times 1.25
$$


Where $R = 3958.8\text{ miles}$, $\phi$ is latitude, and $\lambda$ is longitude.

## 5. File Structure

```
route-planner/
├── backend/
│   ├── main.py                  # FastAPI server & OSRM routing handlers
│   ├── geocode_schools.py       # One-time GPS lookup & cache generator
│   ├── location_list.xlsx       # Source excel dataset
│   └── gcps_coords_cache.json   # Generated GPS coordinates cache
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx              # React UI & Leaflet map integration
        ├── main.jsx             # React DOM root entry
        └── index.css            # Tailwind CSS directives & print styles

```

## 6. Setup & Execution Guide

### Prerequisites

* **Python 3.10+**

* **Node.js 18+** & `npm`

### Step 1: Backend Setup

1. Open a terminal in the `backend` folder:

   ```
   cd backend
   
   ```

2. Install Python dependencies:

   ```
   pip install fastapi uvicorn pandas openpyxl requests
   
   ```

3. Generate the GPS coordinate cache (Run once):

   ```
   python geocode_schools.py
   
   ```

   *Output:* `Saved 146 coordinates to gcps_coords_cache.json`

4. Start the FastAPI development server:

   ```
   uvicorn main:app --reload
   
   ```

   The backend will start at `http://127.0.0.1:8000`.

### Step 2: Frontend Setup

1. Open a second terminal in the `frontend` folder:

   ```
   cd frontend
   
   ```

2. Install Node dependencies:

   ```
   npm install
   npm install leaflet lucide-react
   
   ```

3. Start the Vite development server:

   ```
   npm run dev
   
   ```

4. Open your browser to `http://localhost:5173`.

## 7. API Reference

### `GET /api/locations`

Returns default starting location (`depot`) and the full list of active GCPS locations.

**Sample Response:**

```
{
  "depot": {
    "id": "loc-144",
    "gcpsId": "01A",
    "name": "J. Alvin Wilbanks ISC (Start)",
    "type": "SF",
    "cluster": "PEACHTREE RIDGE",
    "lat": 33.9863,
    "lon": -84.0789
  },
  "locations": [ ... ]
}

```

### `POST /api/route`

Calculates unoptimized driving stats and road polyline geometry for a given starting depot and stop list.

**Request Payload:**

```
{
  "depot": { "id": "loc-144", "lat": 33.9863, "lon": -84.0789 },
  "stops": [
    { "id": "loc-11", "lat": 33.9922, "lon": -84.1485 },
    { "id": "loc-24", "lat": 33.9885, "lon": -83.898 }
  ]
}

```

### `POST /api/optimize`

Solves TSP for the shortest driving order, returning optimized stop order, total miles saved, driving time, and road polyline coordinates.

**Sample Response:**

```
{
  "stops": [ ... ],
  "saved_miles": 4.2,
  "total_miles": 18.6,
  "total_minutes": 27,
  "legs": [
    { "miles": 6.1, "minutes": 9 },
    { "miles": 12.5, "minutes": 18 }
  ],
  "geometry": [
    [33.9863, -84.0789],
    [33.9901, -84.0812],
    ...
  ]
}

```

## 8. Hardware & Browser Requirements

* **Supported Browsers:** Google Chrome 90+, Microsoft Edge 90+, Mozilla Firefox 88+, Safari 14+.

* **Display Resolutions:** Optimized for 1080p desktop monitors, tablets, and rugged handheld field devices.