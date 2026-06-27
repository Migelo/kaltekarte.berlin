#!/usr/bin/env python3
"""Convert the Google My Maps KML export of kaltekarte.berlin into a
category-tagged GeoJSON the site can load and filter.

Categories are derived heuristically from the business name, since the source
data carries no category field. Order of the rules matters: more specific
matches are checked before generic ones.
"""
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
KML = os.path.join(HERE, "kaltekarte.kml")             # source export, in tools/
OUT = os.path.join(HERE, os.pardir, "points.geojson")  # written to repo root


def norm(s: str) -> str:
    """lowercase, strip accents, collapse whitespace -> for matching."""
    s = s.replace("<![CDATA[", "").replace("]]>", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


# Each rule: (category, [substrings]). Checked top to bottom; first hit wins.
RULES = [
    ("drugstore", [
        "rossmann", "dm-drogerie", "drogerie", "drogeriemarkt", "apotheke",
        "pharmacy", "muller drogerie",
    ]),
    ("supermarket", [
        "lidl", "aldi", "rewe", "edeka", "netto", "penny", "kaufland", "real",
        "bio company", "biocompany", "denn's", "denns", "biomarkt", "alnatura",
        "veganz", "supermarket", "supermarkt", "go asia", "nah und gut",
        "ng markt", "kale gida", "schafer's", "schafer", "nahkauf",
        "edeka aktiv", "ed & fred", "fleischerei", "nussdepot",
    ]),
    # Order is load-bearing: bakery before restaurant before bar_cafe, so e.g.
    # "Hard Rock Cafe" -> restaurant (not bar_cafe) and a "Baeckerei Cafe" ->
    # bakery. The bar keywords moved here out of the old "restaurant" bucket.
    ("bakery", [
        "backerei", "baeckerei", "konditorei", "patisserie",
        "brotmeisterei", "pastry", "bakery", "kamps", "steinecke",
    ]),
    ("restaurant", [
        "mcdonald", "burger king", "kentucky fried chicken", "kfc", "vapiano",
        "hard rock cafe", "restaurant", "gyros", "mr. gyros", "sushi",
        "brasserie", "ryotei", "esskultur", "lindner", "eatery", "digital eatery",
        "savour", "spagos", "mon plaisir", "madame ngo", "nin hao", "yama",
        "japanisch", "good bank", "the reed",
    ]),
    ("bar_cafe", [
        # cafe side (the old "cafe" bucket, minus bakeries)
        "starbucks", "einstein kaffee", "cafe einstein", "einstein", "tchibo",
        "coffee", "kaffee", "cafe", "cafe ", "meyerbeer",
        "what do you fancy love", "fraulein schneefeld",
        # bar side (moved out of "restaurant")
        " bar", "bar ", "brauerei", "drinkery", "icebar", "eiswelten",
        "badfish", "dirty velvet", "du beast", "vagabund", "frannz",
        "dream baby dream", "waschkuche", "salami social",
    ]),
    ("cinema", [
        "cinemaxx", "cinestar", "cineplex", "uci kinowelt", "uci cinema",
        "kinowelt", "rollberg kino", "delphi lux", "yorck", "city kino",
        "zoo palast", "kino", "cinema", "movie theater", "imax",
    ]),
    ("fitness", [
        "john reed", "fitness first", "holmes place", "superfit", "becycle",
        "fitness", "gym", " wave",
    ]),
    ("hotel", [
        "motel one", "ritz-carlton", "ritz carlton", "cosmo hotel",
        "hotel orania", "soho house", "hotel ",
    ]),
    ("culture", [
        "museum", "bibliothek", "library", "galerie", "gallery",
        "staatsbibliothek", "grimm-zentrum", "schrodinger center", "planetarium",
        "kinemathek", "kindl", "kulturbrauerei", "memorial library",
        "philological", "zentrum fur zeitgenossische kunst", "berggruen",
        "neues museum", "bode museum", "historical museum", "decorative arts",
        "underworlds", "zoo berlin", "bundestag", "willy-brandt-haus",
        "deutsche kinemathek", "dussmann",
    ]),
    ("transport", [
        "airport", "flughafen", "central station", "hauptbahnhof", "bahnhof",
        "tegel", "schonefeld",
    ]),
    ("gas_station", [
        "tankstelle", "shell", "aral", "total tankstelle", "esso", "jet ",
    ]),
    ("office", [
        "zalando", "wework", "mindspace", "space shack", "co.lab", "colab",
        "microsoft", "delivery hero", "getyourguide", "groupon", "kayak",
        "cognizant", "talent.io", "mhp lab", "c3 creative", "telefonica",
        "basecamp", "headquarters", "recruitment", "technology center",
        "quartier zukunft", "targobank",
        "deutsche bank", "creative code",
    ]),
    ("shopping", [
        # malls / centers / department stores
        "alexa", "boulevard berlin", "gesundbrunnen-center", "mall of berlin",
        "arcaden", "arkaden", "ring-center", "east side mall", "schloss-strassen",
        "rathaus-center", "linden-center", "eastgate", "forum kopenick",
        "forum ", "hansa center", "schultheiss quartier", "springer-passage",
        "bikini berlin", "tempelhofer hafen", "moa bogen", "kaufpark",
        "victoria center", "biesdorf center", "center", "centre", "passage",
        "bogen", "kaufhaus des westens", "kadewe", "galeria kaufhof", "karstadt",
        "schultheiss", "quartier",
        # fashion
        "uniqlo", "primark", "h&m", "zara", "esprit", "monki", "new yorker",
        "topshop", "tk maxx", "sisley", "allsaints", "kik", "nudie jeans",
        "humana", "sandqvist", "rapha", "stoff & stil", "stoff and stil",
        # electronics / home / general retail
        "saturn", "conrad", "media markt", "ikea", "bolia", "hellweg",
        "baumarkt", "decathlon", "conrad electronic", "ocelot", "bookstore",
        "tchibo filiale", "secondhand", "vintage", "outopia", "escape room",
    ]),
]


# Generic, greedy keywords (legal suffixes, "club") that should decide a category
# ONLY when no specific brand/keyword above matched. Checking these last stops
# e.g. "KiK ... GmbH" (a shop) being tagged office, or "JOHN REED Women's Club"
# (a gym) being tagged restaurant.
FALLBACK_RULES = [
    ("office", ["gmbh", "co. kg", " ag", " se"]),
    ("bar_cafe", ["club"]),
]

# These categories are decided by the NAME rules only, never by the OSM cache:
# the cache stored only a coarse "cafe"/"restaurant" label (not the raw OSM tag),
# which can't tell a bar from a cafe from a bakery. OSM still supplies every
# OTHER category and the address/hours/website fields.
NAME_ONLY_CATEGORIES = {"cafe", "restaurant", "bar_cafe", "bakery"}


def categorize(name: str) -> str:
    n = norm(name)
    for cat, keys in RULES:
        for k in keys:
            if k in n:
                return cat
    for cat, keys in FALLBACK_RULES:
        for k in keys:
            if k in n:
                return cat
    return "other"


# Generous Berlin bounding box. Anything outside is bad data (e.g. the source
# once contained a point in Boulder, Colorado).
LAT_MIN, LAT_MAX = 52.25, 52.75
LON_MIN, LON_MAX = 13.00, 13.85


def main():
    from collections import Counter

    kml = open(KML, encoding="utf-8").read()
    placemarks = re.findall(r"<Placemark>(.*?)</Placemark>", kml, re.S)

    # Optional OSM enrichment (address / hours / website / better category),
    # produced offline by enrich_osm.py. Keyed by "lat,lon" at 6 decimals.
    enrich = {}
    epath = os.path.join(HERE, "osm_enrichment.json")
    if os.path.exists(epath):
        enrich = json.load(open(epath, encoding="utf-8"))

    # Manual category overrides (durable hand-corrections that survive KML
    # re-exports and OSM re-runs), keyed by place name.
    overrides = {}
    opath = os.path.join(HERE, "overrides.json")
    if os.path.exists(opath):
        overrides = {norm(k): v for k, v in
                     json.load(open(opath, encoding="utf-8")).items()}

    features = []
    counts = Counter()
    others = []
    rejected = []   # outside Berlin / unparseable
    dupes = []      # exact (name, coordinate) repeats
    seen = set()

    # Collect raw (name, lon, lat) points from the KML export...
    raw = []
    for pm in placemarks:
        nm = re.search(r"<name>(.*?)</name>", pm, re.S)
        co = re.search(r"<coordinates>(.*?)</coordinates>", pm, re.S)
        if not nm or not co:
            rejected.append(("<missing name or coordinates>", ""))
            continue
        name = nm.group(1).replace("<![CDATA[", "").replace("]]>", "").strip()
        try:
            lon, lat = (float(x) for x in co.group(1).strip().split(",")[0:2])
        except (ValueError, IndexError):
            rejected.append((name, co.group(1).strip()))
            continue
        raw.append((name, lon, lat))

    # ...plus community submissions added via the site's "Add a location" flow
    # (drop a pin -> GitHub issue -> Action appends here -> PR). Same shape:
    # [{"name": ..., "lat": ..., "lon": ...}, ...].
    extra_count = 0
    xpath = os.path.join(HERE, "extra_locations.json")
    if os.path.exists(xpath):
        for item in json.load(open(xpath, encoding="utf-8")):
            try:
                raw.append((str(item["name"]).strip(), float(item["lon"]), float(item["lat"])))
                extra_count += 1
            except (KeyError, TypeError, ValueError):
                rejected.append((str(item), "bad extra_locations entry"))

    for name, lon, lat in raw:
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            rejected.append((name, f"{lat},{lon}"))
            continue

        lon, lat = round(lon, 6), round(lat, 6)
        key = (norm(name), lon, lat)
        if key in seen:
            dupes.append(name)
            continue
        seen.add(key)

        cat = categorize(name)
        e = enrich.get("{:.6f},{:.6f}".format(lat, lon), {})
        source = "name"
        if e.get("category") and e["category"] not in NAME_ONLY_CATEGORIES:
            cat = e["category"]   # trust OSM for non-food categories
            source = "osm"
        if norm(name) in overrides:
            cat = overrides[norm(name)]   # manual override wins over everything
            source = "override"
        counts[cat] += 1
        if cat == "other":
            others.append(name)
        props = {"name": name, "category": cat, "category_source": source}
        for fld in ("address", "hours", "website"):
            if e.get(fld):
                props[fld] = e[fld]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    # Safety net: refuse to overwrite good data with a broken/empty fetch.
    if len(features) < 300:
        raise SystemExit(
            f"Only {len(features)} valid features parsed (<300); refusing to "
            f"overwrite {OUT}. Check the KML export."
        )

    geojson = {"type": "FeatureCollection", "features": features}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=1)

    print(f"wrote {len(features)} features to {OUT}  "
          f"({len(placemarks)} from KML + {extra_count} community submissions)")
    print("\n=== category counts ===")
    for cat, c in counts.most_common():
        print(f"{c:4d}  {cat}")
    print(f"\n=== {len(rejected)} rejected (outside Berlin / unparseable) ===")
    for name, info in rejected:
        print(f"    {name}  [{info}]")
    print(f"\n=== {len(dupes)} duplicates dropped ===")
    for d in dupes:
        print("   ", d)
    print(f"\n=== {len(others)} 'other' (uncategorized) ===")
    for o in others:
        print("   ", o)


if __name__ == "__main__":
    main()
