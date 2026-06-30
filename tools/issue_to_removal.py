#!/usr/bin/env python3
"""Parse a GitHub "Suggest a removal" issue-form body and append the place to
tools/removed_locations.json. Used by .github/workflows/removal-to-pr.yml.

Reads the issue body from the ISSUE_BODY env var. Exits non-zero with a clear
message on invalid input so the workflow can report back on the issue.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "removed_locations.json")

# Keep in sync with generate_geojson.py.
LAT_MIN, LAT_MAX = 52.25, 52.75
LON_MIN, LON_MAX = 13.00, 13.85


def parse_form(body):
    """Return {label: value} from a GitHub issue-form markdown body."""
    fields, label, buf = {}, None, []
    for line in body.splitlines():
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            if label is not None:
                fields[label] = "\n".join(buf).strip()
            label, buf = m.group(1).strip(), []
        elif label is not None:
            buf.append(line)
    if label is not None:
        fields[label] = "\n".join(buf).strip()
    return fields


def main():
    fields = parse_form(os.environ.get("ISSUE_BODY", ""))
    name = fields.get("Place name", "").strip()
    coords = fields.get("Coordinates (lat,lon)", "").strip()
    reason = fields.get("Why should it be removed?", "").strip()

    if not name or name.lower() == "_no response_":
        sys.exit("No place name provided.")
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", coords)
    if not m:
        sys.exit(f"Could not parse coordinates from {coords!r} (expected 'lat,lon').")
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        sys.exit(f"Coordinates {lat},{lon} are outside the Berlin area.")

    data = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else []
    key = (round(lat, 6), round(lon, 6))
    for it in data:
        try:
            if (round(float(it["lat"]), 6), round(float(it["lon"]), 6)) == key:
                sys.exit(f"{name} at {lat},{lon} is already flagged for removal.")
        except (KeyError, TypeError, ValueError):
            continue

    entry = {"name": name, "lat": round(lat, 6), "lon": round(lon, 6)}
    if reason and reason.lower() != "_no response_":
        entry["reason"] = reason
    data.append(entry)
    data.sort(key=lambda d: (d["lat"], d["lon"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"Flagged '{name}' at {lat},{lon} for removal ({len(data)} total).")


if __name__ == "__main__":
    main()
