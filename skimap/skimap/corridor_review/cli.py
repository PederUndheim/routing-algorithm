r"""Going through every corridor in Norway by eye, and keeping the verdict.

The router gives one corridor per tour per cost surface, and which surface
gives the best corridor is not the same answer for every tour: a setting that
finds the sensible line up one valley overshoots in the next. The national
metrics cannot see that - they average it away - so somebody has to look.

This is the looking. It puts one panel per model side by side over NVE's
slope tiles, all locked to the same pan and zoom, each corridor drawn in the
exposure class it scored. You pick the best one, adjust its class if you
disagree with what classify() said, and move on when you are ready to -
picking never advances on its own, because a drag across the map ends in a
click and that used to count as a verdict.

    python -m skimap.corridor_review init
    python -m skimap.corridor_review serve --port 8765
    python -m skimap.corridor_review status
    python -m skimap.corridor_review export

Nothing here builds a cost surface or routes a tour. The models it compares
are builds that already exist on disk - see models.py for why - so a round
starts in seconds rather than the several days routing them would take.

Everything lands under data/review/:

    config.json          the models under review, in panel order
    review.json          the verdicts, and every verdict they replaced
    cache/<model>/       corridor overlays, rendered once and kept
    export/              tours_reviewed.gpkg and the merged corridors

## Rounds

A round is a pass over the tours. `round` bumps the number; verdicts already
recorded stay, and each carries the round it was made in, so a second pass
that only revisits the doubtful ones leaves the rest standing as the current
answer. `status --shifted` lists where the reviewer disagreed with the
exposure classes, which is the feedback config.EXPOSURE_CLASSES never gets
any other way.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from skimap import paths, routing, tours as tours_module
from skimap.corridor_review import models as models_module
from skimap.corridor_review import render, server, sources
from skimap.corridor_review.store import LADDER, Store

EXPORT = paths.DATA / "review" / "export"

# Written beside each tour by `export`. The computed class and the shift are
# both kept, not just the result - see store.py.
REVIEW_FIELDS = (
    ("review_model", "OFTString"),      # which model's corridor won
    ("review_colour", "OFTString"),     # the class after the reviewer's shift
    ("review_computed", "OFTString"),   # what exposure.classify() had said
    ("review_shift", "OFTInteger"),     # -1, 0 or +1
    ("review_round", "OFTInteger"),
    ("review_note", "OFTString"),
    ("review_at", "OFTString"),
    ("review_geom", "OFTString"),       # "route" or "tour", see export()
    ("needs_fix", "OFTInteger"),        # 1 where tours.gpkg needs editing
    ("fix_note", "OFTString"),          # what is wrong with it
    ("exp_score", "OFTReal"),           # of the chosen corridor's route
    ("length_m", "OFTReal"),
    ("cost_opt", "OFTReal"),
)


def init(overwrite: bool = False) -> Path:
    out = models_module.write_default(overwrite=overwrite)
    print(f"Wrote {out}\n"
          f"It names the national builds this repo already has. Edit the list,\n"
          f"then:\n"
          f"  python -m skimap.corridor_review serve")
    return out


def prepare(*, render_all: bool = False) -> None:
    """Score every model, and optionally pre-render all of its overlays.

    Scoring is the part that must happen before a review: a corridor with no
    exposure class has no colour to be drawn in. Rendering is optional
    because the server does it on demand anyway - pre-rendering only trades
    a few minutes now for a smoother first pass later.
    """
    config = models_module.load()
    print(f"round {config.round}: {len(config.models)} models")

    for model in config.models:
        scored = sources.ensure_scored(model)
        rows = sources.model_rows(model)
        corridors = sources.corridor_paths(model)
        classed = sum(1 for row in rows.values() if row.get("colour"))
        print(f"  {model.name:14s} {len(rows):4d} routes, {classed:4d} classed, "
              f"{len(corridors):4d} corridors{'  (scored now)' if scored else ''}")

        if not render_all:
            continue
        done = 0
        for fid, corridor in sorted(corridors.items()):
            colour = (rows.get(fid) or {}).get("colour") or "blue"
            render.cached_png(model.name, fid, corridor, colour)
            done += 1
            if done % 100 == 0:
                print(f"    rendered {done}/{len(corridors)}")
        print(f"    rendered {done}/{len(corridors)}")


def status(*, shifted_only: bool = False, fix_only: bool = False) -> None:
    config = models_module.load()
    store = Store()
    total = len(sources.tour_order())
    reviewed = len(store.verdicts)

    print(f"round {store.round}"
          f"{f' - {config.note}' if config.note else ''}")
    print(f"  {reviewed} / {total} tours reviewed"
          f"  ({(reviewed / total * 100) if total else 0:.0f}%)")

    if fix_only:
        rows = store.fix_list()
        names = {t["fid"]: t["name"] for t in sources.tour_order()}
        print(f"\n{len(rows)} tours flagged as needing work in tours.gpkg:")
        for fid, entry in rows:
            print(f"  {fid:6d}  {names.get(fid, ''):28s} {entry.get('note', '')}")
        return

    if shifted_only:
        rows = store.shifted()
        print(f"\n{len(rows)} tours where the reviewer disagreed with classify():")
        print(f"  {'fid':>6}  {'model':14s} {'computed':8s} -> {'kept':8s} note")
        for fid, verdict in rows:
            print(f"  {fid:6d}  {verdict['model']:14s} "
                  f"{verdict['colour_computed']:8s} -> {verdict['colour']:8s} "
                  f"{verdict.get('note', '')}")
        return

    print("\nchosen model:")
    counts = store.counts_by_model()
    for model in config.models:
        picked = counts.get(model.name, 0)
        share = (picked / reviewed * 100) if reviewed else 0
        print(f"  {model.name:14s} {picked:4d}  {share:5.1f}%")
    unknown = set(counts) - {m.name for m in config.models}
    for name in sorted(unknown):
        print(f"  {name:14s} {counts[name]:4d}         (not in the current config)")

    print("\nexposure class as reviewed:")
    by_colour = store.counts_by_colour()
    for colour in LADDER:
        print(f"  {colour:8s} {by_colour.get(colour, 0):4d}")

    shifted = store.shifted()
    if shifted:
        print(f"\n{len(shifted)} class shifts - see `status --shifted`")
    if store.needs_fix:
        print(f"{len(store.needs_fix)} tours need work in tours.gpkg - "
              f"see `status --needs-fix`")


def new_round(number: Optional[int] = None) -> int:
    store = Store()
    was = store.round
    now = store.start_round(number)
    print(f"round {was} -> {now}. Verdicts from earlier rounds stand until "
          f"a tour is reviewed again.")
    return now


def export(out_dir: Optional[Path] = None, *, merge: bool = True) -> Path:
    """The reviewed set: one layer of tours, and the winning corridors merged.

    Geometry is the chosen model's route where a tour has a verdict, and the
    straight start-to-end line from tours.gpkg where it does not - the
    `review_geom` field says which, so a half-finished review is still a
    usable layer rather than a misleading one.
    """
    from osgeo import ogr

    ogr.UseExceptions()

    config = models_module.load()
    store = Store()
    out_dir = Path(out_dir) if out_dir else EXPORT
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = {m.name: sources.model_rows(m) for m in config.models}
    corridors = {m.name: sources.corridor_paths(m) for m in config.models}
    tour_list = tours_module.read_tours(paths.TOURS)

    out_path = out_dir / "tours_reviewed.gpkg"
    if out_path.exists():
        out_path.unlink()

    driver = ogr.GetDriverByName("GPKG")
    datasource = driver.CreateDataSource(str(out_path))

    from osgeo import osr

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(sources.PROJECT_EPSG)
    layer = datasource.CreateLayer("tours_reviewed", srs, ogr.wkbLineString)

    layer.CreateField(ogr.FieldDefn("tour_fid", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("name", ogr.OFTString))
    for name, kind in REVIEW_FIELDS:
        layer.CreateField(ogr.FieldDefn(name, getattr(ogr, kind)))

    winners: dict[str, list[Path]] = {colour: [] for colour in LADDER}
    written = missing_geometry = 0

    for tour in tour_list:
        verdict = store.get(tour.fid)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("tour_fid", tour.fid)
        feature.SetField("name", tour.label)

        # Independent of the verdict: an unreviewed tour can still be flagged.
        fix = store.fix(tour.fid)
        feature.SetField("needs_fix", 1 if fix else 0)
        if fix:
            feature.SetField("fix_note", fix.get("note", ""))

        geometry = None
        if verdict:
            model = config.model(verdict["model"])
            if model is not None:
                geometry = _route_geometry(model, tour.fid)
                row = rows[model.name].get(tour.fid) or {}
                for key in ("exp_score", "length_m", "cost_opt"):
                    if row.get(key) is not None:
                        feature.SetField(key, float(row[key]))
                corridor = corridors[model.name].get(tour.fid)
                if corridor is not None and verdict["colour"] in winners:
                    winners[verdict["colour"]].append(corridor)

            feature.SetField("review_model", verdict["model"])
            feature.SetField("review_colour", verdict["colour"])
            feature.SetField("review_computed", verdict["colour_computed"])
            feature.SetField("review_shift", int(verdict["shift"]))
            feature.SetField("review_round", int(verdict.get("round", 1)))
            feature.SetField("review_note", verdict.get("note", ""))
            feature.SetField("review_at", verdict.get("at", ""))

        if geometry is None:
            geometry = ogr.Geometry(ogr.wkbLineString)
            geometry.AddPoint_2D(*tour.start)
            geometry.AddPoint_2D(*tour.end)
            feature.SetField("review_geom", "tour")
            if verdict:
                missing_geometry += 1
        else:
            feature.SetField("review_geom", "route")

        feature.SetGeometry(geometry)
        layer.CreateFeature(feature)
        written += 1

    datasource = None

    print(f"{written} tours -> {out_path}")
    print(f"  {len(store.verdicts)} with a verdict")
    if store.needs_fix:
        print(f"  {len(store.needs_fix)} flagged as needing work in tours.gpkg "
              f"(needs_fix = 1)")
    if missing_geometry:
        print(f"  {missing_geometry} reviewed tours had no route geometry in "
              f"their chosen model - written as the straight tour line")

    if merge:
        corridor_dir = out_dir / "corridors"
        corridor_dir.mkdir(parents=True, exist_ok=True)
        for colour, files in winners.items():
            if not files:
                print(f"  no {colour} corridors")
                continue
            target = corridor_dir / f"corridors_{colour}.tif"
            print(f"  {colour}: {len(files)} corridors -> {target.name}")
            routing.merge_corridors(out_path=target, files=files)

    return out_path


def _route_geometry(model, fid: int):
    """The model's own line for one tour, in EPSG:25833, or None."""
    from osgeo import ogr

    datasource = ogr.Open(str(model.routes))
    layer = datasource.GetLayer(0)
    layer.SetAttributeFilter(f"tour_fid = {int(fid)}")
    feature = layer.GetNextFeature()
    geometry = feature.GetGeometryRef().Clone() if feature is not None else None
    datasource = None
    return geometry


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skimap.corridor_review",
        description=__doc__.split("\n\n")[0],
    )
    sub = parser.add_subparsers(dest="stage", required=True)

    p = sub.add_parser("init", help="write a starter config")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("prepare", help="score the models; optionally pre-render")
    p.add_argument("--render", action="store_true",
                   help="render every overlay now instead of on demand")

    p = sub.add_parser("serve", help="the review page")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--review", type=Path,
                   help="verdicts file to use instead of data/review/review.json. "
                        "Point a test instance at a throwaway path: anything "
                        "exercising the verdict endpoints writes real verdicts, "
                        "and a cleared one is only recoverable from history.")

    p = sub.add_parser("status", help="progress, chosen models, class shifts")
    p.add_argument("--shifted", action="store_true",
                   help="list only the tours whose class the reviewer moved")
    p.add_argument("--needs-fix", action="store_true", dest="needs_fix",
                   help="list only the tours flagged as needing work in tours.gpkg")

    p = sub.add_parser("round", help="start a new review round")
    p.add_argument("number", nargs="?", type=int)

    p = sub.add_parser("export", help="the reviewed tours and merged corridors")
    p.add_argument("--out", type=Path)
    p.add_argument("--no-merge", action="store_true",
                   help="write the layer only, skip the corridor rasters")

    p = sub.add_parser("cache", help="drop rendered overlays")
    p.add_argument("--model", help="just this model's")

    args = parser.parse_args(argv)

    if args.stage == "init":
        init(overwrite=args.overwrite)
    elif args.stage == "prepare":
        prepare(render_all=args.render)
    elif args.stage == "serve":
        server.serve(args.host, args.port, review_path=args.review)
    elif args.stage == "status":
        status(shifted_only=args.shifted, fix_only=args.needs_fix)
    elif args.stage == "round":
        new_round(args.number)
    elif args.stage == "export":
        export(args.out, merge=not args.no_merge)
    elif args.stage == "cache":
        gone = render.clear_cache(args.model)
        print(f"{gone} cached files removed")
    return 0
