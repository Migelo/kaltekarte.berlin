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
        "yama", " bar", "bar ", "brauerei", "club", "drinkery", "icebar",
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
        "quartier zukunft", "gmbh", "co. kg", " ag", " se", "targobank",
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


def categorize(name: str) -> str:
    n = norm(name)
    for cat, keys in RULES:
        for k in keys:
            if k in n:
                return cat
    return "other"


def main():
    kml = open(KML, encoding="utf-8").read()
    placemarks = re.findall(r"<Placemark>(.*?)</Placemark>", kml, re.S)
    features = []
    from collections import Counter
    counts = Counter()
    others = []
    for pm in placemarks:
        name = re.search(r"<name>(.*?)</name>", pm, re.S).group(1)
        name = name.replace("<![CDATA[", "").replace("]]>", "").strip()
        coords = re.search(r"<coordinates>(.*?)</coordinates>", pm, re.S).group(1).strip()
        lon, lat = coords.split(",")[0:2]
        cat = categorize(name)
        counts[cat] += 1
        if cat == "other":
            others.append(name)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(float(lon), 6), round(float(lat), 6)]},
            "properties": {"name": name, "category": cat},
        })

    geojson = {"type": "FeatureCollection", "features": features}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=1)

    print(f"wrote {len(features)} features to {OUT}")
    print("\n=== category counts ===")
    for cat, c in counts.most_common():
        print(f"{c:4d}  {cat}")
    print(f"\n=== {len(others)} 'other' (uncategorized) ===")
    for o in others:
        print("   ", o)


if __name__ == "__main__":
    main()
