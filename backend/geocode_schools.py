import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

# Real Gwinnett County GPS centers for each cluster (fallback if a new school isn't in OSM yet)
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

# Known Gwinnett support facility & special center overrides for exact pin accuracy
EXACT_OVERRIDES = {
    "01A": (33.9863, -84.0789),  # J. Alvin Wilbanks ISC (437 Old Peachtree Rd NW)
    "050": (33.9564, -83.9961),  # Facilities & Operations (53 Gwinnett Dr)
    "024": (33.9548, -83.9950),  # Transportation / Service Distribution Center
    "03D": (34.1087, -84.0441),  # Buice Center (Buford Hwy, Sugar Hill)
    "631": (33.9631, -84.0069),  # GSMST (970 McElvaney Ln)
}


def in_gwinnett(lat: float, lon: float) -> bool:
    return 33.72 <= lat <= 34.22 and -84.32 <= lon <= -83.75


def lookup_school(name: str, gcps_id: str, cluster: str):
    if gcps_id in EXACT_OVERRIDES:
        return EXACT_OVERRIDES[gcps_id], "override"

    clean_name = name.split(" and ")[0].strip()
    queries = [
        f"{clean_name}, Gwinnett County, Georgia",
        f"{clean_name}, GA",
    ]

    for q in queries:
        try:
            res = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": q, "lat": 33.96, "lon": -84.02, "limit": 5},
                timeout=8,
            )
            if res.ok:
                features = res.json().get("features", [])
                for feat in features:
                    lon, lat = feat["geometry"]["coordinates"]
                    if in_gwinnett(lat, lon):
                        return (round(lat, 6), round(lon, 6)), "osm"
        except Exception:
            pass
        time.sleep(0.25)

    return CLUSTER_GPS.get(cluster, (33.9562, -83.9880)), "cluster_fallback"


def main():
    base_dir = Path(__file__).resolve().parent
    excel_path = base_dir / "location_list.xlsx"
    cache_path = base_dir / "gcps_coords_cache.json"

    raw_df = pd.read_excel(excel_path)
    if len(raw_df.columns) == 1:
        raw_col = str(raw_df.columns[0])
        lines = [raw_col] + raw_df[raw_col].dropna().astype(str).tolist()
        df = pd.read_csv(io.StringIO("\n".join(lines)))
    else:
        df = raw_df

    df.columns = [str(c).strip() for c in df.columns]
    active = df[df["CentegixUIVisible"].astype(str).str.strip().isin(["1", "1.0"])].copy()

    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    total = len(active)
    for idx, (_, row) in enumerate(active.iterrows(), start=1):
        row_id = f"loc-{str(row['ID']).strip().split('.')[0]}"
        name = str(row["CentegixLocationName"]).strip()
        gcps_id = str(row.get("GCPSLocationID", "")).strip()
        if gcps_id.lower() == "nan":
            gcps_id = ""
        cluster = str(row.get("Cluster_SafetySecurity", "CENTRAL GWINNETT")).strip().upper()

        if row_id in cache:
            continue

        (lat, lon), source = lookup_school(name, gcps_id, cluster)
        cache[row_id] = {"lat": lat, "lon": lon, "source": source}
        print(f"[{idx}/{total}] {name} -> ({lat}, {lon}) [{source}]")

    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    print(f"\nSaved {len(cache)} coordinates to {cache_path}")


if __name__ == "__main__":
    main()