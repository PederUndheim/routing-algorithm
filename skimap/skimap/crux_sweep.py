r"""How many Cruxes a set of grouping settings leaves, over example routes.

The Crux Identifier's merge dials (config.CRUX: split_gap_m, steep_gap_m)
decide how a route's runs become areas, and so how many markers it ends up
with. This runs the identifier over a folder of GPX or GeoJSON routes, once
per setting, and prints the counts side by side - the quick loop before
opening the app and looking at where the markers actually land.

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m skimap.cli crux \
        --routes data/crux_identifier/trips

Add --detail to list one route's markers for each setting.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from skimap import config, crux

ABBREVIATION = {"steep_slope": "STEEP", "runout_area": "RUNOUT"}

# split_gap_m, steep_gap_m. The first is every run left as its own area -
# what the other rows are measured against.
SWEEP = (
    ("no merging", 0.0, 0.0),
    ("gaps only", 40.0, 0.0),
    ("default", 40.0, 100.0),
    ("firm", 40.0, 200.0),
    ("strong", 60.0, 300.0),
)


def read_routes(folder: Path) -> dict[str, dict]:
    """Every GPX and GeoJSON line under `folder`, as WGS84 LineStrings."""
    routes: dict[str, dict] = {}
    for path in sorted(folder.iterdir()):
        for i, coordinates in enumerate(_lines(path)):
            name = path.stem if i == 0 else f"{path.stem} [{i + 1}]"
            routes[name] = {"type": "LineString", "coordinates": coordinates}
    if not routes:
        raise SystemExit(f"No GPX or GeoJSON routes in {folder}.")
    return routes


def _lines(path: Path) -> Iterator[list[list[float]]]:
    if path.suffix.lower() == ".gpx":
        text = path.read_text(encoding="utf-8")
        # Attribute order is not fixed, so find each point then read its pair.
        for track in re.findall(r"<trk>.*?</trk>", text, re.S):
            points = [[float(m["lon"]), float(m["lat"])]
                      for m in re.finditer(
                          r'<trkpt[^>]*?lat="(?P<lat>[-\d.]+)"[^>]*?'
                          r'lon="(?P<lon>[-\d.]+)"', track)]
            if len(points) >= 2:
                yield points
    elif path.suffix.lower() in (".geojson", ".json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for feature in data.get("features", [data]):
            geometry = feature.get("geometry", feature)
            if geometry.get("type") == "LineString":
                yield [list(p[:2]) for p in geometry["coordinates"]]


def sweep(folder: Path, detail: str | None = None) -> None:
    routes = read_routes(folder)
    shipped = dict(config.CRUX)
    baseline = None

    print(f"{len(routes)} routes from {folder}\n")
    print("%-14s %7s %7s %7s %8s %9s"
          % ("", "cruxes", "steep", "runout", "per km", "vs none"))
    for label, split_gap, steep_gap in SWEEP:
        config.CRUX.clear()
        config.CRUX.update(shipped, split_gap_m=split_gap, steep_gap_m=steep_gap)
        results = {name: crux.identify(route) for name, route in routes.items()}
        found = [c for r in results.values() for c in r["cruxes"]]
        steep = sum(1 for c in found if c["class"] == "steep_slope")
        km = sum(r["length_m"] for r in results.values()) / 1000
        baseline = len(found) if baseline is None else baseline
        print("%-14s %7d %7d %7d %8.1f %8.0f%%"
              % (label, len(found), steep, len(found) - steep, len(found) / km,
                 100 * len(found) / baseline))
        if detail is not None:
            if detail not in results:
                raise SystemExit(
                    f"No route {detail!r}. Try one of: {', '.join(sorted(routes))}")
            print("      " + _markers(results[detail]) + "\n")

    config.CRUX.clear()
    config.CRUX.update(shipped)


def _markers(result: dict) -> str:
    """Each Crux as the app draws it: number, what it turns out to be, how
    steep, where it starts and how long the area is."""
    return "  ".join(
        "%d.%s%s@%.0fm/%.0fm"
        % (c["number"],
           ("!" if c.get("probable_release_area") else "")
           + ("F" if c.get("fall_hazard") else "")
           + ABBREVIATION[c["class"]],
           " %.0fdeg" % c["max_slope_deg"] if "max_slope_deg" in c else "",
           c["distance_m"], c["length_m"])
        for c in result["cruxes"]) or "(none)"
