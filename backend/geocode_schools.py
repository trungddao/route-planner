import csv
import io
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests

# Optional: Paste a Google Maps Geocoding API key here (or set GOOGLE_MAPS_API_KEY env var)
# Leave blank ("") to use upgraded OpenStreetMap + exact overrides
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

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

# Verified exact coordinates & street addresses by GCPSLocationID
EXACT_OVERRIDES = {
    "01A": (33.9863, -84.0789, "437 Old Peachtree Rd NW, Suwanee, GA 30024"),
    "050": (33.9564, -83.9961, "53 Gwinnett Dr, Lawrenceville, GA 30046"),
    "024": (33.9548, -83.9950, "610 W Crogan St, Lawrenceville, GA 30046"),
    "03D": (34.1087, -84.0441, "1160 Level Creek Rd, Sugar Hill, GA 30518"),
    "631": (33.9631, -84.0069, "970 McElvaney Ln NW, Lawrenceville, GA 30044"),
}


def expand_gcps_name(name: str) -> str:
    clean = name.split(" and ")[0].strip()
    replacements = [
        (r"\bES\b", "Elementary School"),
        (r"\bElem\b", "Elementary School"),
        (r"\bMS\b", "Middle School"),
        (r"\bMid\b", "Middle School"),
        (r"\bHS\b", "High School"),
        (r"\bCtr\b", "Center"),
        (r"\bAcad\b", "Academy"),
        (r"\bTech\b", "Technical"),
    ]
    for pattern, full_word in replacements:
        clean = re.sub(pattern, full_word, clean, flags=re.IGNORECASE)
    return clean


def in_gwinnett(lat: float, lon: float) -> bool:
    return 33.72 <= lat <= 34.22 and -84.32 <= lon <= -83.75


def geocode_with_google(expanded_name: str):
    if not GOOGLE_MAPS_API_KEY:
        return None
    try:
        res = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": f"{expanded_name}, Gwinnett County, GA",
                "bounds": "33.72,-84.32|34.22,-83.75",
                "key": GOOGLE_MAPS_API_KEY,
            },
            timeout=8,
        )
        data = res.json()
        if data.get("status") == "OK" and data.get("results"):
            top = data["results"][0]
            loc = top["geometry"]["location"]
            lat, lon = float(loc["lat"]), float(loc["lng"])
            if in_gwinnett(lat, lon):
                return round(lat, 6), round(lon, 6), top.get("formatted_address", ""), "google_maps"
    except Exception:
        pass
    return None


def geocode_with_osm(expanded_name: str):
    queries = [
        f"{expanded_name}, Gwinnett County, Georgia",
        f"{expanded_name}, GA",
    ]
    for q in queries:
        try:
            res = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": q, "lat": 33.96, "lon": -84.02, "limit": 5},
                timeout=8,
            )
            if res.ok:
                for feat in res.json().get("features", []):
                    lon, lat = feat["geometry"]["coordinates"]
                    props = feat.get("properties", {})
                    if in_gwinnett(lat, lon):
                        street = " ".join(
                            filter(None, [props.get("housenumber"), props.get("street")])
                        )
                        city = props.get("city") or props.get("locality") or "Gwinnett County"
                        postcode = props.get("postcode") or ""
                        addr = ", ".join(filter(None, [street, city, f"GA {postcode}".strip()]))
                        return round(lat, 6), round(lon, 6), addr, "osm_verified"
        except Exception:
            pass
        time.sleep(0.25)
    return None


def main():
    base_dir = Path(__file__).resolve().parent
    excel_path = base_dir / "location_list.xlsx"
    cache_path = base_dir / "gcps_coords_cache.json"
    audit_path = base_dir / "location_audit.csv"

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
    audit_rows = []
    total = len(active)

    for idx, (_, row) in enumerate(active.iterrows(), start=1):
        row_id = f"loc-{str(row['ID']).strip().split('.')[0]}"
        name = str(row["CentegixLocationName"]).strip()
        gcps_id = str(row.get("GCPSLocationID", "")).strip()
        if gcps_id.lower() == "nan":
            gcps_id = ""
        cluster = str(row.get("Cluster_SafetySecurity", "CENTRAL GWINNETT")).strip().upper()

        # Check if user already added manual Latitude/Longitude/Address columns to Excel
        excel_lat = pd.to_numeric(row.get("Latitude"), errors="coerce")
        excel_lon = pd.to_numeric(row.get("Longitude"), errors="coerce")
        excel_addr = str(row.get("Address", "")).strip()

        if pd.notna(excel_lat) and pd.notna(excel_lon):
            lat, lon = round(float(excel_lat), 6), round(float(excel_lon), 6)
            addr = excel_addr if excel_addr and excel_addr.lower() != "nan" else "From Excel"
            source = "excel_manual"
        elif gcps_id in EXACT_OVERRIDES:
            lat, lon, addr = EXACT_OVERRIDES[gcps_id]
            source = "exact_override"
        else:
            expanded = expand_gcps_name(name)
            result = geocode_with_google(expanded) or geocode_with_osm(expanded)
            if result:
                lat, lon, addr, source = result
            else:
                lat, lon = CLUSTER_GPS.get(cluster, (33.9562, -83.9880))
                addr = f"Approximate {cluster} Cluster Center"
                source = "NEEDS_REVIEW"

        cache[row_id] = {"lat": lat, "lon": lon, "address": addr, "source": source}
        status = "NEEDS_REVIEW" if source == "NEEDS_REVIEW" else "OK"

        audit_rows.append(
            {
                "Status": status,
                "GCPS_ID": gcps_id,
                "School_Name": name,
                "Matched_Address": addr,
                "Latitude": lat,
                "Longitude": lon,
                "Source": source,
                "Google_Maps_Check_Link": f"https://www.google.com/maps?q={lat},{lon}",
            }
        )
        print(f"[{idx}/{total}] {status:12} | {name} -> {addr} ({lat}, {lon})")

    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    with audit_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(audit_rows[0].keys()))
        writer.writeheader()
        writer.writerows(audit_rows)

    needs_review = sum(1 for r in audit_rows if r["Status"] == "NEEDS_REVIEW")
    print(f"\nDone! Saved {len(cache)} locations to {cache_path}")
    print(f"Audit report saved to {audit_path} ({needs_review} locations flagged NEEDS_REVIEW)")


if __name__ == "__main__":
    main()