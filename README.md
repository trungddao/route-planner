# GCPS Daily Route Planner

A full-stack route planning and optimization web application built for **Gwinnett County Public Schools (GCPS)** field, facilities, and logistics teams. Drivers and dispatchers can select a starting hub, search across **146 active school and support facility locations**, reorder stops manually or automatically for the shortest real-road driving path, preview the route on an interactive Gwinnett County map, and print a paper driver checklist.

---

## Key Features

- **Flexible Starting Hub Selection:** Defaults to the J. Alvin Wilbanks Instructional Support Center (`Loc #01A`) with one-click quick-hub buttons for GCPS Support Facilities (`SF`) or search-to-set starting points for any campus.
- **Fast Search & Cluster Filtering:** Filter all 146 active locations by cluster (20 GCPS clusters) or search instantaneously by school name, street address, ZIP code, or GCPS Location ID.
- **Real-Road Route Optimization:** Uses the Open Source Routing Machine (**OSRM**) driving distance matrix to reorder multi-stop routes into the shortest real-road sequence and reports exact mileage and drive-time savings.
- **Verified Street Addresses & Building-Level Pins:** Combines official U.S. Department of Education (NCES) directory records, U.S. Census Bureau street geocoding, and verified GCPS building coordinates so map pins land directly on campus buildings.
- **Interactive Map & Printable Checklist:** Displays turn-by-turn road geometry with numbered pins and address popups on a Leaflet map, paired with a checkable, print-formatted driver manifest (`Print Paper Checklist`).

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React, Vite, Tailwind CSS, Leaflet, Lucide Icons |
| **Backend** | Python, FastAPI, Uvicorn, Pandas, OpenPyXL, Requests |
| **Routing & Geocoding** | OSRM Public Routing API, NCES Education Data API, U.S. Census Geocoder, OpenStreetMap Nominatim |
| **Dev & Deployment** | `concurrently` (unified local dev), Render Blueprint (`render.yaml`) with GitHub auto-deploy |

---

## Project Structure

```text
route-planner/
├── backend/
│   ├── main.py                       # FastAPI server (/api/locations, /api/route, /api/optimize)
│   ├── location_list.xlsx            # Master spreadsheet of 146 GCPS locations, addresses & GPS pins
│   ├── gcps_coords_cache.json        # Fast JSON coordinate & address cache
│   ├── fetch_real_addresses.py       # Pulls official NCES school street addresses into Excel
│   ├── sync_pins_from_addresses.py   # Syncs building-level GPS pins from verified street addresses
│   └── requirements.txt              # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx                   # Main UI, route builder, checklist & Leaflet map component
│   │   ├── index.css                 # Tailwind CSS & print stylesheet rules
│   │   └── main.jsx                  # React entry point
│   └── package.json                  # Frontend dependencies & Vite scripts
├── package.json                      # Root dev script launching backend + frontend together
├── render.yaml                       # Render Blueprint for automated cloud deployment
├── README.md                         # Project overview & quick start
└── DOCUMENTATION.md                  # Technical architecture, API reference & data maintenance guide
```

---

## Quick Start (Local Development)

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** and **npm**

### 1. Install Dependencies
From the root `route-planner` directory, install root, frontend, and backend packages:

```powershell
# Install root dev runner (concurrently)
npm install

# Install React frontend dependencies
npm --prefix frontend install

# Install Python backend dependencies
pip install -r backend/requirements.txt
```

### 2. Run Both Servers with One Command
Start the FastAPI backend (`http://127.0.0.1:8000`) and React frontend (`http://localhost:5173`) simultaneously in a single terminal:

```powershell
npm run dev
```

Open **`http://localhost:5173`** in your browser. Press **`Ctrl + C`** once in the terminal to stop both servers.

---

## Deployment (Render)

This repository includes a **`render.yaml`** Blueprint configured for automatic continuous deployment from the `main` branch:

1. **`gcps-route-backend` (Python Web Service):** Runs `uvicorn main:app --host 0.0.0.0 --port $PORT` from `backend/`.
2. **`gcps-route-frontend` (Static Site):** Builds `frontend/` via `npm install && npm run build` and connects to the backend using the `VITE_API_URL` environment variable.

Every `git push` to `main` automatically rebuilds and updates the affected service on Render. See **`DOCUMENTATION.md`** for environment variable configuration, data update workflows, and API details.