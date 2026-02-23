#!/usr/bin/env python3
import json
from collections import defaultdict


def main():
    in_path = "data_preprocessing/data_cache/national/tours.geojson"
    out_path = "backend/routing_algorithm/tours/tours2.json"

    gj = json.load(open(in_path, "r", encoding="utf-8"))

    out = {"crs": "EPSG:25833", "areas": {}}
    areas = defaultdict(lambda: defaultdict(dict))

    for f in gj.get("features", []):
        p = f.get("properties", {})
        g = f.get("geometry", {})
        if g.get("type") != "Point":
            continue

        area_id = p.get("area_id")
        name = p.get("tour_name")
        role = p.get("role")
        if not (area_id and name and role in ("start", "end")):
            continue

        x, y = g.get("coordinates", [None, None])[:2]
        if x is None or y is None:
            continue

        areas[area_id][name][role] = [round(float(x), 1), round(float(y), 1)]

    for area_id, tours in areas.items():
        out_list = []
        for name, roles in tours.items():
            if "start" in roles and "end" in roles:
                out_list.append({
                    "name": name,
                    "start": roles["start"],
                    "end": roles["end"],
                })
        if out_list:
            out["areas"][area_id] = sorted(out_list, key=lambda d: d["name"])

    json.dump(out, open(out_path, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
