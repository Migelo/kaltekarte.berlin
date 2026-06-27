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
        "ng markt", "nin hao", "kale gida", "schafer's", "schafer", "nahkauf",
        "edeka aktiv", "ed & fred", "fleischerei", "nussdepot",
    ]),
    ("cafe", [
        "starbucks", "einstein kaffee", "cafe einstein", "einstein", "tchibo",
        "coffee", "kaffee", "cafe", "cafe ", "bakery", "backerei", "baeckerei",
        "kamps", "steinecke", "brotmeisterei", "meyerbeer", "konditorei",
        "pastry", "what do you fancy love", "fraulein schneefeld",
    ]),
    ("restaurant", [
        "mcdonald", "burger king", "kentucky fried chicken", "kfc", "vapiano",
        "hard rock cafe", "restaurant", "gyros", "sushi", "brasserie", "ryotei",
        "esskultur", "eatery", "savour", "spagos", "mon plaisir", "madame ngo",
        "yama", " bar", "bar ", "brauerei", "drinkery", "icebar",
        "eiswelten", "badfish", "dirty velvet", "du beast", "vagabund",
        "frannz", "japanisch", "good bank", "the reed", "lindner",
        "dream baby dream", "waschkuche", "salami social", "digital eatery",
        "mr. gyros",
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
    ("restaurant", ["club"]),
]


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

    features = []
    counts = Counter()
    others = []
    rejected = []   # outside Berlin / unparseable
    dupes = []      # exact (name, coordinate) repeats
    seen = set()

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
        counts[cat] += 1
        if cat == "other":
            others.append(name)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"name": name, "category": cat},
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

    print(f"wrote {len(features)} features to {OUT}  ({len(placemarks)} placemarks in source)")
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
