#!/usr/bin/env python3
"""Enrich the points with real data from OpenStreetMap (Overpass API).

The Google My Maps source has only a name + coordinates. This script looks each
point up in OSM (free, keyless) by proximity + name match and caches any
address / opening hours / website / category it finds into
``tools/osm_enrichment.json``. ``generate_geojson.py`` then merges that cache
into ``points.geojson`` so the live site makes no API calls.

Matching is conservative: a candidate must be within RADIUS metres AND share a
meaningful name token, or it is skipped (the heuristic category is kept and no
address is added). Re-run occasionally; review the diff.

Usage:  python3 tools/enrich_osm.py
"""
import json
import math
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
POINTS = os.path.join(HERE, os.pardir, "points.geojson")
OUT = os.path.join(HERE, "osm_enrichment.json")

OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "kaltekarte.berlin enrichment script (contact: via github.com/jessepinho)"
RADIUS = 70          # metres
BATCH = 40           # points per Overpass request
DELAY = 1.5          # seconds between requests (be polite)
MIN_SCORE = 0.34     # minimum name-token similarity to accept a match

# Generic words that shouldn't count toward a name match.
STOP = set("""berlin gmbh kg co se ag der die das und mit am im the of
filiale markt market store shop discounter supermarkt""".split())


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def tokens(s):
    return {t for t in norm(s).split() if len(t) >= 3 and t not in STOP}


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def osm_category(t):
    shop = t.get("shop"); amen = t.get("amenity"); leis = t.get("leisure")
    tour = t.get("tourism"); office = t.get("office")
    if amen == "cafe" or shop in ("bakery", "pastry", "confectionery", "coffee"):
        return "cafe"
    if amen in ("restaurant", "fast_food", "food_court", "biergarten", "ice_cream"):
        return "restaurant"
    if amen in ("bar", "pub", "nightclub"):
        return "restaurant"
    if amen == "pharmacy" or shop in ("chemist", "drugstore"):
        return "drugstore"
    if amen == "cinema":
        return "cinema"
    if amen == "fuel":
        return "gas_station"
    if shop in ("supermarket", "convenience", "greengrocer", "grocery",
                "deli", "butcher", "health_food", "frozen_food"):
        return "supermarket"
    if leis in ("fitness_centre", "sports_centre") or amen == "gym":
        return "fitness"
    if tour in ("hotel", "hostel", "motel") or amen == "hotel":
        return "hotel"
    if (amen in ("library", "arts_centre", "theatre", "community_centre")
            or tour in ("museum", "gallery", "attraction", "zoo")):
        return "culture"
    if (amen == "bus_station" or t.get("railway") == "station"
            or t.get("public_transport") or t.get("aeroway")):
        return "transport"
    if office:
        return "office"
    if shop:  # any other retail
        return "shopping"
    return None


def address(t):
    street = t.get("addr:street")
    num = t.get("addr:housenumber")
    line = " ".join(x for x in (street, num) if x).strip()
    plz = t.get("addr:postcode")
    city = t.get("addr:city")
    tail = " ".join(x for x in (plz, city) if x).strip()
    full = ", ".join(x for x in (line, tail) if x)
    return full or None


def overpass(points_batch):
    body = "[out:json][timeout:60];(" + "".join(
        'nwr(around:{r},{lat},{lon})[name];'.format(r=RADIUS, lat=p["lat"], lon=p["lon"])
        for p in points_batch
    ) + ");out tags center;"
    req = urllib.request.Request(
        OVERPASS, data=("data=" + urllib.parse.quote(body)).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r).get("elements", [])


def main():
    geo = json.load(open(POINTS, encoding="utf-8"))
    pts = []
    for f in geo["features"]:
        lon, lat = f["geometry"]["coordinates"]
        pts.append({"name": f["properties"]["name"], "lat": lat, "lon": lon,
                    "key": "{:.6f},{:.6f}".format(lat, lon)})

    enrichment = {}
    matched = 0
    for i in range(0, len(pts), BATCH):
        batch = pts[i:i + BATCH]
        try:
            elements = overpass(batch)
        except Exception as e:  # noqa: BLE001 - network is best-effort
            print(f"  batch {i // BATCH}: Overpass error {e!r}; skipping")
            time.sleep(DELAY)
            continue

        # index candidate elements with a usable name + position
        cands = []
        for el in elements:
            t = el.get("tags", {})
            nm = t.get("name")
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if nm and lat and lon:
                cands.append((nm, lat, lon, t))

        for p in batch:
            best, best_score = None, MIN_SCORE
            for nm, lat, lon, t in cands:
                if haversine(p["lat"], p["lon"], lat, lon) > RADIUS:
                    continue
                s = similarity(p["name"], nm)
                if s >= best_score:
                    best_score, best = s, t
            if not best:
                continue
            entry = {}
            addr = address(best)
            if addr:
                entry["address"] = addr
            if best.get("opening_hours"):
                entry["hours"] = best["opening_hours"]
            site = best.get("website") or best.get("contact:website")
            if site:
                entry["website"] = site
            cat = osm_category(best)
            if cat and best_score >= 0.5:
                entry["category"] = cat
            if entry:
                entry["match_score"] = round(best_score, 2)
                enrichment[p["key"]] = entry
                matched += 1

        print(f"  batch {i // BATCH + 1}/{(len(pts) + BATCH - 1) // BATCH}: "
              f"{matched} matched so far")
        time.sleep(DELAY)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(enrichment, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"\nwrote {len(enrichment)} enrichment records to {OUT} "
          f"({len(pts)} points, {100 * len(enrichment) // max(1, len(pts))}% matched)")


if __name__ == "__main__":
    main()
