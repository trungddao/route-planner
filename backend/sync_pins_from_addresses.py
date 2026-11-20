import io
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

# Verified building-level coordinates by GCPSLocationID (used if street geocoders fail or drift)
VERIFIED_PINS = {
    "01A": (34.01604, -84.05593, "437 Old Peachtree Rd NW, Suwanee, GA 30024"),   # J. Alvin Wilbanks ISC
    "050": (33.95642, -83.99610, "53 Gwinnett Dr, Lawrenceville, GA 30046"),         # Facilities & Operations
    "024": (33.95481, -83.99502, "610 W Crogan St, Lawrenceville, GA 30046"),       # Service Distribution / Transportation
    "03D": (34.10871, -84.04412, "1160 Level Creek Rd, Sugar Hill, GA 30518"),      # Buice Center
    "631": (33.96312, -84.00691, "970 McElvaney Ln NW, Lawrenceville, GA 30044"),   # GSMST
    "439.OS1": (33.98185, -84.07655, "5900 Sugarloaf Pkwy, Lawrenceville, GA 30043"),
    "438": (33.97285, -83.98645, "723 Hi Hope Rd, Lawrenceville, GA 30043"),
    "497": (33.95355, -84.20545, "5550 Peachtree Industrial Blvd, Norcross, GA 30071"),
    "441": (33.97215, -83.98615, "713 Hi Hope Rd, Lawrenceville, GA 30043"),
}


def in_gwinnett(lat: float, lon: float) -> bool:
    return 33.72 <= lat <= 34.22 and -84.32 <= lon <= -83.75


def clean_address_for_geocoder(address: str) -> str:
    """Removes suite numbers and directional suffixes that confuse Census/OSM street parsers."""
    cleaned = re.sub(r",?\s*(Suite|Ste|Unit|#)\s*[A-Za-z0-9-]+", "", address, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(NW|NE|SW|SE)\b", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).replace(" ,", ",").strip()
    return cleaned


def geocode_census(address: str):
    query_addr = clean_address_for_geocoder(address)
    try:
        res = requests.get(
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
            params={
                "address": query_addr,
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            timeout=8,
        )
        if res.ok:
            matches = res.json().get("result", {}).get("addressMatches", [])
            if matches:
                coords = matches[0]["coordinates"]
                lat, lon = round(float(coords["y"]), 6), round(float(coords["x"]), 6)
                if in_gwinnett(lat, lon):
                    return lat, lon, "census_street"
    except Exception:
        pass
    return None


def geocode_nominatim(address: str):
    query_addr = clean_address_for_geocoder(address)
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query_addr,
                "format": "json",
                "viewbox": "-84.32,34.22,-83.75,33.72",
                "bounded": 1,
                "limit": 1,
            },
            headers={"User-Agent": "GCPS-Route-Planner-PinSync/1.0"},
            timeout=8,
        )
        if res.ok and res.json():
            top = res.json()[0]
            lat, lon = round(float(top["lat"]), 6), round(float(top["lon"]), 6)
            if in_gwinnett(lat, lon):
                return lat, lon, "osm_street"
    except Exception:
        pass
    return None


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

    new_lats = []
    new_lons = []
    new_sources = []
    cache = {}
    updated_count = 0

    for idx, row in df.iterrows():
        visible = str(row.get("CentegixUIVisible", "1")).strip()
        name = str(row.get("CentegixLocationName", "")).strip()
        gcps_id = str(row.get("GCPSLocationID", "")).strip()
        if gcps_id.lower() == "nan":
            gcps_id = ""
        elif gcps_id.endswith(".0"):
            gcps_id = gcps_id[:-2]

        row_id = f"loc-{str(row.get('ID', idx + 1)).strip().split('.')[0]}"
        addr = str(row.get("Address", "")).strip()
        if addr.lower() == "nan":
            addr = ""

        old_lat = pd.to_numeric(row.get("Latitude"), errors="coerce")
        old_lon = pd.to_numeric(row.get("Longitude"), errors="coerce")

        if visible not in ("1", "1.0") or not name or name.lower() == "nan":
            new_lats.append(old_lat if pd.notna(old_lat) else None)
            new_lons.append(old_lon if pd.notna(old_lon) else None)
            new_sources.append("inactive")
            continue

        # 1. Verified exact building pin override (fixes ISC 01A and support hubs)
        if gcps_id in VERIFIED_PINS:
            lat, lon, verified_addr = VERIFIED_PINS[gcps_id]
            if not addr:
                addr = verified_addr
                df.at[idx, "Address"] = addr
            source = "verified_pin"
        elif addr:
            # 2. Geocode directly from the street address in Excel
            res = geocode_census(addr)
            if not res:
                time.sleep(1.0)
                res = geocode_nominatim(addr)

            if res:
                lat, lon, source = res
            elif pd.notna(old_lat) and pd.notna(old_lon) and in_gwinnett(float(old_lat), float(old_lon)):
                lat, lon, source = round(float(old_lat), 6), round(float(old_lon), 6), "kept_existing"
            else:
                lat, lon, source = None, None, "UNRESOLVED"
        else:
            lat = round(float(old_lat), 6) if pd.notna(old_lat) else None
            lon = round(float(old_lon), 6) if pd.notna(old_lon) else None
            source = "no_address"

        new_lats.append(lat)
        new_lons.append(lon)
        new_sources.append(source)

        if lat is not None and lon is not None:
            cache[row_id] = {"lat": float(lat), "lon": float(lon), "address": addr, "source": source}
            if pd.isna(old_lat) or abs(float(old_lat) - lat) > 0.002 or abs(float(old_lon) - lon) > 0.002:
                updated_count += 1
                print(f"[MOVED PIN] {name} (#{gcps_id}): {addr} -> ({lat}, {lon}) [{source}]")
            else:
                print(f"[OK]        {name} (#{gcps_id}) -> ({lat}, {lon})")

    df["Latitude"] = new_lats
    df["Longitude"] = new_lons
    df["GeocodeSource"] = new_sources
    df.to_excel(excel_path, index=False)
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    print(f"\nFinished! Updated {updated_count} shifted pins across {len(cache)} total locations.")


if __name__ == "__main__":
    main()