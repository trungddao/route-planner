import io
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CLUSTER_GPS = {
    "LANIER": (34.1165, -84.0345),
    "NORTH GWINNETT": (34.0628, -84.0725),
    "PEACHTREE RIDGE": (33.9985, -84.1012),
    "DULUTH": (33.9922, -84.1485),
    "NORCROSS": (33.9412, -84.2135),
    "BERKMAR": (33.9145, -84.1325),
    "MEADOWCREEK": (33.9185, -84.1782),
    "PARKVIEW": (33.8825, -84.1415),
    "SHILOH": (33.8185, -84.0645),
    "SOUTH GWINNETT": (33.8545, -84.0185),
    "BROOKWOOD": (33.8845, -84.0365),
    "GRAYSON": (33.8945, -83.9585),
    "ARCHER": (33.9285, -83.8925),
    "CENTRAL GWINNETT": (33.9562, -83.9880),
    "DISCOVERY": (33.9685, -84.0485),
    "COLLINS HILL": (34.0185, -84.0125),
    "MOUNTAIN VIEW": (34.0545, -83.9725),
    "SECKINGER": (34.0845, -83.9385),
    "MILL CREEK": (34.0925, -83.8885),
    "DACULA": (33.9885, -83.8980),
}

OSRM_BASE = "https://router.project-osrm.org"


def load_locations_from_excel() -> List[Dict[str, Any]]:
    base_dir = Path(__file__).resolve().parent
    excel_path = base_dir / "location_list.xlsx"
    cache_path = base_dir / "gcps_coords_cache.json"

    if not excel_path.exists():
        raise FileNotFoundError(f"Missing file: {excel_path}")

    coords_cache = {}
    if cache_path.exists():
        coords_cache = json.loads(cache_path.read_text(encoding="utf-8"))

    raw_df = pd.read_excel(excel_path)
    if len(raw_df.columns) == 1:
        raw_col = str(raw_df.columns[0])
        lines = [raw_col] + raw_df[raw_col].dropna().astype(str).tolist()
        df = pd.read_csv(io.StringIO("\n".join(lines)))
    else:
        df = raw_df

    df.columns = [str(c).strip() for c in df.columns]
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()

    active = (
        df[df["CentegixUIVisible"].astype(str).str.strip().isin(["1", "1.0"])].copy()
        if "CentegixUIVisible" in df.columns
        else df.copy()
    )

    locations = []
    for idx, row in active.iterrows():
        name = str(row.get("CentegixLocationName", "")).strip()
        if not name or name.lower() == "nan":
            continue

        gcps_id = str(row.get("GCPSLocationID", "")).strip()
        if gcps_id.lower() == "nan":
            gcps_id = ""

        loc_type = str(row.get("GCPS_LocationType", "")).strip()
        if loc_type.lower() == "nan":
            loc_type = ""

        cluster = str(row.get("Cluster_SafetySecurity", "")).strip().upper()
        if not cluster or cluster == "NAN":
            cluster = "CENTRAL GWINNETT"

        raw_id = str(row.get("ID", idx + 1)).strip()
        row_id = f"loc-{raw_id.split('.')[0] if raw_id.lower() != 'nan' else idx + 1}"

        if row_id in coords_cache:
            lat = coords_cache[row_id]["lat"]
            lon = coords_cache[row_id]["lon"]
        else:
            lat, lon = CLUSTER_GPS.get(cluster, (33.9562, -83.9880))

        locations.append(
            {
                "id": row_id,
                "gcpsId": gcps_id,
                "name": name,
                "type": loc_type,
                "cluster": cluster,
                "lat": float(lat),
                "lon": float(lon),
            }
        )

    return locations


def haversine_miles(p1: dict, p2: dict) -> float:
    r = 3958.8
    lat1, lon1 = math.radians(float(p1["lat"])), math.radians(float(p1["lon"]))
    lat2, lon2 = math.radians(float(p2["lat"])), math.radians(float(p2["lon"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    # Multiply straight-line GPS by 1.25 road winding factor as fallback only
    return round(2 * r * math.asin(math.sqrt(a)) * 1.25, 1)


def get_osrm_matrix(points: List[dict]):
    coord_str = ";".join(f"{p['lon']},{p['lat']}" for p in points)
    url = f"{OSRM_BASE}/table/v1/driving/{coord_str}"
    res = requests.get(url, params={"annotations": "distance,duration"}, timeout=10)
    res.raise_for_status()
    data = res.json()
    if data.get("code") != "Ok":
        raise RuntimeError("OSRM matrix error")
    # Convert meters -> miles
    dist_miles = [[round((d or 0) * 0.000621371, 2) for d in row] for row in data["distances"]]
    return dist_miles


def get_osrm_route_details(ordered_points: List[dict]):
    if len(ordered_points) < 2:
        return {
            "total_miles": 0.0,
            "total_minutes": 0,
            "legs": [],
            "geometry": [[p["lat"], p["lon"]] for p in ordered_points],
        }

    try:
        coord_str = ";".join(f"{p['lon']},{p['lat']}" for p in ordered_points)
        url = f"{OSRM_BASE}/route/v1/driving/{coord_str}"
        res = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=10,
        )
        res.raise_for_status()
        data = res.json()
        route = data["routes"][0]

        legs = []
        for leg in route["legs"]:
            legs.append(
                {
                    "miles": round(leg["distance"] * 0.000621371, 1),
                    "minutes": max(1, round(leg["duration"] / 60)),
                }
            )

        # Flip GeoJSON [lon, lat] -> Leaflet [lat, lon]
        geometry = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]

        return {
            "total_miles": round(route["distance"] * 0.000621371, 1),
            "total_minutes": max(1, round(route["duration"] / 60)),
            "legs": legs,
            "geometry": geometry,
        }
    except Exception:
        # Fallback if OSRM server is temporarily unreachable
        legs = []
        total_mi = 0.0
        for i in range(len(ordered_points) - 1):
            mi = haversine_miles(ordered_points[i], ordered_points[i + 1])
            total_mi += mi
            legs.append({"miles": mi, "minutes": max(2, round(mi * 2.2))})

        return {
            "total_miles": round(total_mi, 1),
            "total_minutes": sum(l["minutes"] for l in legs),
            "legs": legs,
            "geometry": [[p["lat"], p["lon"]] for p in ordered_points],
        }


@app.get("/api/locations")
def get_locations():
    try:
        locations = load_locations_from_excel()
        default_depot = next(
            (loc for loc in locations if loc["gcpsId"] == "01A"),
            locations[0],
        )
        return {"depot": default_depot, "locations": locations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/route")
async def calculate_route(request: Request):
    payload = await request.json()
    depot = payload.get("depot")
    stops = payload.get("stops", [])
    if not depot or not stops:
        return {"stops": stops, "total_miles": 0.0, "total_minutes": 0, "legs": [], "geometry": []}

    details = get_osrm_route_details([depot, *stops])
    return {"stops": stops, **details}


@app.post("/api/optimize")
async def optimize_route(request: Request):
    payload = await request.json()
    depot = payload.get("depot")
    stops = payload.get("stops", [])

    if not depot or len(stops) <= 1:
        details = get_osrm_route_details([depot, *stops]) if depot and stops else {}
        return {"stops": stops, "saved_miles": 0.0, **details}

    all_pts = [depot, *stops]
    try:
        matrix = get_osrm_matrix(all_pts)
    except Exception:
        matrix = [
            [0.0 if i == j else haversine_miles(all_pts[i], all_pts[j]) for j in range(len(all_pts))]
            for i in range(len(all_pts))
        ]

    # Distance before optimization (0 -> 1 -> 2 -> ... -> n)
    before_miles = sum(matrix[i][i + 1] for i in range(len(all_pts) - 1))

    # Nearest-neighbor using REAL road distance matrix
    unvisited = list(range(1, len(all_pts)))
    ordered_indices = []
    curr = 0
    while unvisited:
        next_idx = min(unvisited, key=lambda j: matrix[curr][j])
        unvisited.remove(next_idx)
        ordered_indices.append(next_idx)
        curr = next_idx

    optimized_stops = [all_pts[i] for i in ordered_indices]
    details = get_osrm_route_details([depot, *optimized_stops])
    saved = max(0.0, round(before_miles - details["total_miles"], 1))

    return {
        "stops": optimized_stops,
        "saved_miles": saved,
        **details,
    }