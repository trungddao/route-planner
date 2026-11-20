# GCPS Daily Route Planner — How the Product Works

## 1. Product Overview

The **GCPS Daily Route Planner** is a full-stack logistics and dispatch web application designed for **Gwinnett County Public Schools (GCPS)** field technicians, facilities crews, and delivery drivers. Instead of manually typing multiple school addresses into consumer map apps and guessing the best driving order, staff can select their starting hub, pick any combination of the **146 active GCPS campuses and support facilities**, automatically calculate the shortest real-road driving sequence, preview the route on an interactive map, and print a clipboard-ready driver checklist.

---

## 2. End-to-End System Flow

```text
┌──────────────────────────────┐
│  location_list.xlsx (146)    │  Master directory: GCPS IDs, names, clusters,
│  + gcps_coords_cache.json    │  verified street addresses & building GPS pins
└──────────────┬───────────────┘
               │ Loaded on API request
               ▼
┌──────────────────────────────┐      REST / JSON       ┌──────────────────────────────┐
│   FastAPI Backend (Python)   │ ◄────────────────────► │   React Frontend (Vite/UI)   │
│  • GET  /api/locations       │                        │  • Starting Hub Selector     │
│  • POST /api/route           │                        │  • Search & Cluster Filter   │
│  • POST /api/optimize        │                        │  • Stop List & Print Sheet   │
└──────────────┬───────────────┘                        │  • Leaflet Street Map        │
               │ Real-road matrix & geometry            └──────────────────────────────┘
               ▼
┌──────────────────────────────┐
│  OSRM Public Routing Engine  │  Computes actual turn-by-turn road mileage,
│  (router.project-osrm.org)   │  drive times, and street polyline coordinates
└──────────────────────────────┘
```

---

## 3. Step-by-Step User Workflow

### A. Setting the Starting Location (Depot)
- **Default Hub:** When the app loads, it fetches `/api/locations` and automatically sets **J. Alvin Wilbanks Instructional Support Center (`Loc #01A`)** as the starting location.
- **Quick Hubs:** Support Facilities (`type === "SF"`) appear as one-click pill buttons directly inside the header so dispatchers can switch between central hubs (ISC, Facilities & Operations, Transportation, Buice Center) in a single click.
- **Custom Start Point:** Drivers starting from a school can either type in the header search box or click **Set Start** on any school card in Step 1. If that location was already in the stop list, the app automatically removes it from the stops to prevent routing from a building to itself.

### B. Searching and Filtering Locations (Step 1)
- **Cluster Dropdown:** Dynamically extracts all 20 GCPS clusters from the dataset so users can narrow down to a single geographic area (e.g., `MILL CREEK`, `BROOKWOOD`, `NORCROSS`).
- **Instant Multi-Field Search:** Typing in the search bar filters all 146 active locations simultaneously across four fields:
  - School or facility name (e.g., `Alcova`, `GIVE East`)
  - Street address (e.g., `Old Peachtree`, `Hi Hope`)
  - ZIP code (e.g., `30043`)
  - Official GCPS Location ID (e.g., `01A`, `439.OS1`)
- **Duplicate Prevention:** Locations currently set as `Start` or already added to the route have their **Add** button disabled and labeled `Start` or `Added`.

### C. Building & Adjusting the Driving Route (Step 2)
- **Live Road Calculation:** Every time a stop is added, removed, or moved, the frontend sends the current `depot` and `stops` array to `POST /api/route`. The top badge updates immediately with total driving distance (miles) and estimated driving time (minutes), while each stop card displays its individual leg distance and drive time from the previous stop.
- **Manual Reordering & Tracking:** Drivers can fine-tune stop order with the **Move Up (`↑`)** and **Move Down (`↓`)** buttons, delete a stop with **Remove**, or tap the checkbox on the left of each card to mark completed stops during their shift.

### D. One-Click Route Optimization (`FIND SHORTEST DRIVING ROUTE`)
- Once **2 or more stops** are added, a high-visibility green **FIND SHORTEST DRIVING ROUTE** button appears.
- Clicking it calls `POST /api/optimize`, which rearranges the stops into the shortest real-road order starting from the depot.
- Upon completion:
  - A confirmation banner displays how many driving miles were saved compared to the original order (e.g., `Saves 6.4 driving miles`).
  - The route polyline and numbered pins on the map switch from **blue** (manual order) to **green** (optimized order).

### E. Interactive Map & Printable Paper Checklist
- **Leaflet Street Map (`StreetRouteMap`):** Renders OpenStreetMap tiles with a dark `START` badge at the depot, numbered circular markers (`1`, `2`, `3`...) at each stop's verified building coordinates, and the full road-following polyline. Clicking any marker opens a popup with the school name, GCPS ID, and verified street address. Auto-zoom (`fitBounds`) frames the entire route whenever stops change.
- **Print Mode (`Print Paper Checklist`):** Clicking **Print Paper Checklist** triggers `window.print()`. Elements tagged with the `no-print` CSS class (search panels, buttons, arrows) are hidden automatically so the browser prints a clean, high-contrast manifest showing the Starting Location, ordered stops, street addresses, leg mileages, and checkboxes.

---

## 4. How the Routing & Optimization Engine Works

### 1. Verified Building Coordinates (`location_list.xlsx`)
- Consumer geocoders often fail on GCPS abbreviations (`ES`, `MS`, `HS`) or drop pins at city centers.
- To prevent this, `fetch_real_addresses.py` pulls official school street addresses from the U.S. Department of Education (NCES) directory (`leaid=1302550`), and `sync_pins_from_addresses.py` converts every street address into exact building-level `Latitude` and `Longitude` coordinates via the U.S. Census Bureau Geocoder and verified GCPS overrides.
- Both `location_list.xlsx` and `gcps_coords_cache.json` live inside `backend/`, so location lookups are instantaneous and require zero external API calls at runtime.

### 2. Real-Road Distance & Polyline Geometry (`POST /api/route`)
- The backend formats the ordered coordinates as `lon,lat;lon,lat...` and queries OSRM's driving route service (`/route/v1/driving/` with `overview=full` and `geometries=geojson`).
- OSRM returns exact road meters and seconds per leg, which `main.py` converts into miles (`meters * 0.000621371`) and rounded minutes (`seconds / 60`).
- Because GeoJSON stores coordinates as `[longitude, latitude]` while Leaflet expects `[latitude, longitude]`, the backend flips each coordinate pair before returning `geometry` to the frontend.

### 3. Nearest-Neighbor Matrix Optimization (`POST /api/optimize`)
1. **All-Pairs Road Matrix:** For a depot plus $N$ stops, the backend calls OSRM's `/table/v1/driving/` endpoint to retrieve an $(N+1) \times (N+1)$ matrix of real driving distances between every pair of locations.
2. **Baseline Mileage:** Sums the sequential distances `0 → 1 → 2 → ... → N` to record `before_miles`.
3. **Greedy Nearest-Neighbor Traversal:** Starting at index `0` (the depot), the algorithm repeatedly picks the closest unvisited campus by real road distance until all stops are ordered.
4. **Full Route Geometry & Savings:** Passes the newly ordered list to `get_osrm_route_details()` to obtain turn-by-turn road geometry and calculates `saved_miles = max(0, before_miles - total_miles)`.

### 4. Automatic Offline / Rate-Limit Fallback
- If the public OSRM server is temporarily unreachable or times out, `main.py` automatically falls back to **Haversine great-circle distance multiplied by a `1.25x` road-winding factor** (estimating drive time at ~2.2 minutes per mile). This ensures route building and optimization never fail during field operations.

---

## 5. Local Development & Cloud Deployment Lifecycle

- **Single-Command Local Environment:** Running `npm run dev` in the root folder uses `concurrently` to start both Uvicorn (`http://127.0.0.1:8000`) and Vite (`http://localhost:5173`) in one terminal with live auto-reload.
- **Automated Cloud CI/CD (`render.yaml`):** Pushing changes to the `main` branch on GitHub automatically triggers Render to rebuild the static frontend (`gcps-route-frontend`) and/or the Python API (`gcps-route-backend`), keeping live users synchronized with the latest code and `location_list.xlsx` updates.