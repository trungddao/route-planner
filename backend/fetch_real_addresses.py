import io
import json
import re
import shutil
import time
from pathlib import Path

import pandas as pd
import requests

# Gwinnett County Public Schools official NCES District ID
GCPS_LEAID = "1302550"

# Official GCPS support facilities & specialty campuses not listed in the standard K-12 directory
ADMIN_FACILITIES = {
    "01A": ("J. Alvin Wilbanks Instructional Support Center", "437 Old Peachtree Rd NW, Suwanee, GA 30024", 33.98631, -84.07892),
    "050": ("GCPS Facilities & Operations", "53 Gwinnett Dr, Lawrenceville, GA 30046", 33.95642, -83.99610),
    "024": ("GCPS Service Distribution Center / Transportation", "610 W Crogan St, Lawrenceville, GA 30046", 33.95481, -83.99502),
    "03D": ("Buice Center", "1160 Level Creek Rd, Sugar Hill, GA 30518", 34.10871, -84.04412),
    "631": ("Gwinnett School of Mathematics, Science, and Technology", "970 McElvaney Ln NW, Lawrenceville, GA 30044", 33.96312, -84.00691),
    "439.OS1": ("Phoenix at Sugarloaf Mills High", "5900 Sugarloaf Pkwy, Lawrenceville, GA 30043", 33.98050, -84.08100),
    "438": ("GIVE East High", "723 Hi Hope Rd, Lawrenceville, GA 30043", 33.97280, -83.98650),
    "497": ("GIVE West High", "5550 Peachtree Industrial Blvd, Norcross, GA 30071", 33.95350, -84.20550),
    "441": ("Gwinnett Online Campus Learning Center", "713 Hi Hope Rd, Lawrenceville, GA 30043", 33.97210, -83.98620),
}

NAME_ALIASES = {
    "gsmst": "gwinnett school of mathematics science and technology",
    "give east": "give center east",
    "give west": "give center west",
    "maxwell": "maxwell high school of technology",
    "grayson tech": "grayson technical education program",
    "phoenix hs": "phoenix high school",
    "mcclure health science hs": "mcclure health science high school",
    "paul duke stem hs": "paul duke stem high school",
}


def normalize_tokens(text: str) -> set:
    t = text.lower().split(" and ")[0]
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    words = t.split()
    mapping = {
        "es": "elementary",
        "elem": "elementary",
        "ms": "middle",
        "mid": "middle",
        "hs": "high",
        "ctr": "center",
        "acad": "academy",
        "tech": "technical",
    }
    expanded = [mapping.get(w, w) for w in words if w not in {"school", "the", "of", "at"}]
    return set(expanded)


def fetch_nces_gcps_directory() -> list:
    """Pulls all official Gwinnett County Public Schools + street addresses from NCES."""
    records = []
    for year in (2024, 2023, 2022):
        url = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{year}/?leaid={GCPS_LEAID}&per_page=200"
        try:
            while url:
                res = requests.get(url, timeout=15)
                if not res.ok:
                    break
                data = res.json()
                results = data.get("results", [])
                if not results:
                    break
                for r in results:
                    street = str(r.get("street_location") or "").strip().title()
                    city = str(r.get("city_location") or "").strip().title()
                    state = str(r.get("state_location") or "GA").strip().upper()
                    zipcode = str(r.get("zip_location") or "").strip().zfill(5)
                    full_addr = f"{street}, {city}, {state} {zipcode}".strip(", ")
                    records.append(
                        {
                            "name": str(r.get("school_name") or "").strip(),
                            "tokens": normalize_tokens(str(r.get("school_name") or "")),
                            "address": full_addr,
                            "lat": r.get("latitude"),
                            "lon": r.get("longitude"),
                        }
                    )
                url = data.get("next")
            if records:
                print(f"Downloaded {len(records)} official GCPS school records (NCES {year}).")
                return records
        except Exception:
            continue
    return records


def geocode_address_census(address: str):
    """Uses the official U.S. Census Bureau Geocoder (free, no API key) for exact street coordinates."""
    try:
        res = requests.get(
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
            params={
                "address": address,
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            timeout=8,
        )
        if res.ok:
            matches = res.json().get("result", {}).get("addressMatches", [])
            if matches:
                coords = matches[0]["coordinates"]
                return round(float(coords["y"]), 6), round(float(coords["x"]), 6), matches[0]["matchedAddress"]
    except Exception:
        pass
    return None


def search_nominatim_gwinnett(query_name: str):
    """Fallback lookup bounded strictly inside Gwinnett County, GA."""
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": f"{query_name}, Gwinnett County, GA",
                "format": "json",
                "addressdetails": 1,
                "viewbox": "-84.32,34.22,-83.75,33.72",
                "bounded": 1,
                "limit": 1,
            },
            headers={"User-Agent": "GCPS-Route-Planner/1.0"},
            timeout=8,
        )
        if res.ok and res.json():
            top = res.json()[0]
            addr_parts = top.get("address", {})
            street = " ".join(filter(None, [addr_parts.get("house_number"), addr_parts.get("road")]))
            city = addr_parts.get("city") or addr_parts.get("town") or addr_parts.get("suburb") or "Gwinnett County"
            postcode = addr_parts.get("postcode") or ""
            full_addr = ", ".join(filter(None, [street, city, f"GA {postcode}".strip()]))
            return round(float(top["lat"]), 6), round(float(top["lon"]), 6), full_addr
    except Exception:
        pass
    return None


def match_school(raw_name: str, directory: list):
    lower_clean = raw_name.lower().strip()
    aliased = NAME_ALIASES.get(lower_clean, raw_name)
    target_tokens = normalize_tokens(aliased)
    if not target_tokens:
        return None

    best_rec = None
    best_score = 0.0
    for rec in directory:
        rec_tokens = rec["tokens"]
        if not rec_tokens:
            continue
        overlap = len(target_tokens & rec_tokens)
        score = overlap / max(len(target_tokens), len(rec_tokens))
        if target_tokens.issubset(rec_tokens):
            score += 0.35
        if score > best_score:
            best_score = score
            best_rec = rec

    return best_rec if best_score >= 0.65 else None


def main():
    base_dir = Path(__file__).resolve().parent
    excel_path = base_dir / "location_list.xlsx"
    backup_path = base_dir / "location_list_backup.xlsx"
    cache_path = base_dir / "gcps_coords_cache.json"

    if not backup_path.exists():
        shutil.copy2(excel_path, backup_path)

    raw_df = pd.read_excel(excel_path)
    if len(raw_df.columns) == 1:
        raw_col = str(raw_df.columns[0])
        lines = [raw_col] + raw_df[raw_col].dropna().astype(str).tolist()
        df = pd.read_csv(io.StringIO("\n".join(lines)))
    else:
        df = raw_df

    df.columns = [str(c).strip() for c in df.columns]
    directory = fetch_nces_gcps_directory()

    addresses = []
    lats = []
    lons = []
    sources = []
    cache = {}
    unmatched = []

    for idx, row in df.iterrows():
        visible = str(row.get("CentegixUIVisible", "1")).strip()
        name = str(row.get("CentegixLocationName", "")).strip()
        gcps_id = str(row.get("GCPSLocationID", "")).strip()
        if gcps_id.lower() == "nan":
            gcps_id = ""
        elif gcps_id.endswith(".0"):
            gcps_id = gcps_id[:-2]

        row_id = f"loc-{str(row.get('ID', idx + 1)).strip().split('.')[0]}"

        if visible not in ("1", "1.0") or not name or name.lower() == "nan":
            addresses.append("")
            lats.append(None)
            lons.append(None)
            sources.append("inactive")
            continue

        # 1. Check official GCPS support facilities & specialty campuses
        if gcps_id in ADMIN_FACILITIES:
            _, addr, fallback_lat, fallback_lon = ADMIN_FACILITIES[gcps_id]
            census = geocode_address_census(addr)
            if census:
                lat, lon, _ = census
            else:
                lat, lon = fallback_lat, fallback_lon
            source = "gcps_official"
        else:
            # 2. Match against U.S. Dept. of Education (NCES) GCPS directory
            matched = match_school(name, directory)
            if matched:
                addr = matched["address"]
                lat, lon = matched["lat"], matched["lon"]
                source = "nces_official"
                if not lat or not lon:
                    census = geocode_address_census(addr)
                    if census:
                        lat, lon, _ = census
            else:
                # 3. Fallback to bounded Gwinnett search
                time.sleep(1.0)
                nom = search_nominatim_gwinnett(name)
                if nom:
                    lat, lon, addr = nom
                    source = "osm_bounded"
                else:
                    addr, lat, lon, source = "", None, None, "UNMATCHED"
                    unmatched.append((gcps_id, name))

        addresses.append(addr)
        lats.append(lat)
        lons.append(lon)
        sources.append(source)

        if lat is not None and lon is not None:
            cache[row_id] = {"lat": float(lat), "lon": float(lon), "address": addr, "source": source}
            print(f"[OK] {name} -> {addr} ({lat}, {lon})")
        else:
            print(f"[UNMATCHED] {name} (Loc #{gcps_id})")

    # Save pulled addresses and exact coordinates directly into location_list.xlsx
    df["Address"] = addresses
    df["Latitude"] = lats
    df["Longitude"] = lons
    df["GeocodeSource"] = sources
    df.to_excel(excel_path, index=False)

    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    print(f"\nUpdated {excel_path} and {cache_path} with {len(cache)} verified locations.")
    if unmatched:
        print("\nLocations needing manual address entry in location_list.xlsx:")
        for gid, uname in unmatched:
            print(f"  - Loc #{gid}: {uname}")


if __name__ == "__main__":
    main()