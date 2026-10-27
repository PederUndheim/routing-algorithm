r"""The static data the validation app reads, built from data/corridors_final.

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m validation_app.prepare
    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m validation_app.prepare --skip-tracks

Writes:

    frontend/public/corridors/index.json   every corridor: id, region, length, image bounds
    frontend/public/corridors/NNNN.png     the corridor, drawn as the review drew it
    data/validation/tracks/{z}/{x}/{y}.png GPS track density around the corridors
    data/validation/tracks/index.json      which of those tiles exist

The track tiles are only to be shown behind the access code, so they go
neither to Pages nor into git - the repository is public, and data/ is
ignored. The API serves them (server.py, /tiles/tracks/) from the Azure
Files share, uploaded there with deploy/upload.sh; see the README.

## The corridor picture

Drawn exactly as the corridor review drew it (render.to_png): the corridor
GeoTIFF warped to Web Mercator, its 0..1 score classified at the twenty
breaks of data/styles_arcgis/blue.lyrx with its alpha ramp, so the band fades
out towards its edge the way the reviewers are used to seeing it.

## Blind by construction

The review is blind: a reviewer sets the KAST class without seeing what the
project chose. These files are public - Pages serves them to anyone - so
blind has to hold in the data, not just in what the page happens to draw.
The review coloured each corridor by its class; here every corridor is drawn
in the same blue, whatever its class, so the colour says nothing. (Blue was
the user's choice over a neutral violet.) Nothing in the index carries a
colour, a model, a width or a tour id either.

## Track tiles only near corridors

tracks.tif covers half the country. Tiled whole it is hundreds of thousands
of PNGs, nearly all of ground no corridor goes near. Only tiles within
TRACK_BUFFER_M of a corridor's bounds are drawn, which is everything a
reviewer zoomed to one corridor can pan to without trying.

## Every track, not just the busy ones

The corridor review drew tracks the way the cost model weighs them: below
config.TRACKS["min_density"] (3 passes) a cell was not a track at all, and
above it the per-tile percentile bands left everything under a tile's median
nearly transparent. That is right for routing and wrong for looking: in the
busy areas sampled, 55-77% of track cells have one or two passes, and all
of them vanished. Here any cell with a pass is drawn, and opacity follows
log(passes) from TRACK_ALPHA_MIN at one pass to TRACK_ALPHA_MAX at
TRACK_FULL_PASSES (the 99th percentile of track cells) and above. Same
magenta as the review.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
from osgeo import gdal

from app import corridor_tiles as tiles
from skimap import paths
from skimap.corridor_review import render

gdal.UseExceptions()

GPKG = paths.CORRIDORS_FINAL / "corridors_final.gpkg"
HERE = Path(__file__).resolve().parent
OUT = HERE / "frontend" / "public"
TRACKS_OUT = paths.DATA / "validation" / "tracks"

CORRIDOR_STYLE = "blue"   # one style for every corridor - see "Blind by construction"
MAX_PIXELS = 2048   # one corridor on screen, not three: the app's limit, not the review's

TRACK_BUFFER_M = 3000
TRACK_MAX_ZOOM = 13     # ~8 m a pixel at 65 N, the raster is 10 m
TRACK_MIN_ZOOM = 9
TRACK_ALPHA_MIN = 0.32
TRACK_ALPHA_MAX = 0.92
TRACK_FULL_PASSES = 75


def _corridor_png(tif: Path, png: Path, style: tuple[np.ndarray, np.ndarray]) -> dict:
    """render.to_png at MAX_PIXELS rather than the review's. Returns WGS84 bounds."""
    warped = gdal.Warp("", str(tif), format="MEM",
                       dstSRS=f"EPSG:{render.WEBMERCATOR_EPSG}", resampleAlg="bilinear")
    longest = max(warped.RasterXSize, warped.RasterYSize)
    if longest > MAX_PIXELS:
        scale = MAX_PIXELS / longest
        warped = gdal.Translate("", warped, format="MEM", resampleAlg="bilinear",
                                width=max(1, int(warped.RasterXSize * scale)),
                                height=max(1, int(warped.RasterYSize * scale)))
    band = warped.GetRasterBand(1)
    scores = band.ReadAsArray().astype(np.float64)
    inside = np.isfinite(scores) & (scores > 0.0)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        inside &= ~np.isclose(scores, nodata)

    bounds, colours = style
    classes = np.clip(np.searchsorted(bounds, np.clip(scores, 0.0, 1.0), side="left"),
                      0, len(bounds) - 1)
    rgba = colours[classes]
    rgba[~inside] = 0
    render._write_rgba(png, rgba)
    return render._bounds_wgs84(warped)


def build_corridors(out_dir: Path) -> list[dict]:
    corridors = gpd.read_file(GPKG, layer="corridors").sort_values("corridor_id")
    style = render._style(CORRIDOR_STYLE)

    target = out_dir / "corridors"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    index = []
    started = time.monotonic()
    for done, row in enumerate(corridors.itertuples(), 1):
        cid = int(row.corridor_id)
        b = _corridor_png(paths.CORRIDORS_FINAL / row.location, target / f"{cid:04d}.png", style)
        index.append({
            "id": cid,
            "region": row.region,
            "regionId": None if row.region_id is None or np.isnan(row.region_id)
                        else int(row.region_id),
            "lengthM": round(float(row.length_m)),
            "bbox": [round(b[k], 6) for k in ("west", "south", "east", "north")],
        })
        if done % 200 == 0:
            print(f"  {done}/{len(corridors)}  ({time.monotonic() - started:.0f} s)")

    (target / "index.json").write_text(
        json.dumps(index, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    size = sum(p.stat().st_size for p in target.iterdir())
    print(f"{len(index)} corridors, {size / 1e6:.1f} MB -> {target}")
    return index


# --- track tiles -----------------------------------------------------------

def _track_tiles_wanted() -> set[tuple[int, int]]:
    """TRACK_MAX_ZOOM tiles within TRACK_BUFFER_M of any corridor's bounds."""
    corridors = gpd.read_file(GPKG, layer="corridors")
    boxes = corridors.geometry.envelope.buffer(TRACK_BUFFER_M).to_crs(render.WEBMERCATOR_EPSG)
    size = tiles._tile_size(TRACK_MAX_ZOOM)
    wanted = set()
    for west, south, east, north in boxes.bounds.itertuples(index=False):
        x0 = int(np.floor((west + tiles.ORIGIN) / size))
        x1 = int(np.floor((east + tiles.ORIGIN) / size))
        y0 = int(np.floor((tiles.ORIGIN - north) / size))
        y1 = int(np.floor((tiles.ORIGIN - south) / size))
        wanted.update((x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))
    return wanted


def _render_track_tile(source: gdal.Dataset, x: int, y: int) -> np.ndarray | None:
    west, south, east, north = tiles._tile_bounds(TRACK_MAX_ZOOM, x, y)
    # "max" for render.tracks_overlay's reason: a track is a cell or two wide.
    warped = gdal.Warp("", source, format="MEM", dstSRS=f"EPSG:{render.WEBMERCATOR_EPSG}",
                       outputBounds=(west, south, east, north),
                       width=tiles.TILE, height=tiles.TILE, resampleAlg="max", dstNodata=0)
    raw = np.nan_to_num(warped.GetRasterBand(1).ReadAsArray().astype(np.float64), nan=0.0)
    present = raw >= 1.0
    if not present.any():
        return None
    unit = np.clip(np.log(np.maximum(raw, 1.0)) / np.log(TRACK_FULL_PASSES), 0.0, 1.0)
    alpha = np.where(present, TRACK_ALPHA_MIN + (TRACK_ALPHA_MAX - TRACK_ALPHA_MIN) * unit, 0.0)
    rgba = np.zeros((tiles.TILE, tiles.TILE, 4), dtype=np.uint8)
    rgba[..., :3] = render.TRACK_RGB
    rgba[..., 3] = np.rint(np.clip(alpha, 0.0, 1.0) * 255.0).astype(np.uint8)
    return rgba


def build_tracks(target: Path) -> dict:
    if target.exists():
        shutil.rmtree(target)

    source = gdal.Open(str(paths.layer("tracks")))
    started = time.monotonic()
    wanted = sorted(_track_tiles_wanted())
    print(f"z{TRACK_MAX_ZOOM}: {len(wanted)} candidate tiles")

    present: dict[int, set[tuple[int, int]]] = {TRACK_MAX_ZOOM: set()}
    for done, (x, y) in enumerate(wanted, 1):
        rgba = _render_track_tile(source, x, y)
        if rgba is not None:
            tiles._write_png(target / str(TRACK_MAX_ZOOM) / str(x) / f"{y}.png", rgba)
            present[TRACK_MAX_ZOOM].add((x, y))
        if done % 1000 == 0:
            print(f"  {done}/{len(wanted)}  ({time.monotonic() - started:.0f} s)")
    print(f"z{TRACK_MAX_ZOOM}: {len(present[TRACK_MAX_ZOOM])} tiles")

    for z in range(TRACK_MAX_ZOOM - 1, TRACK_MIN_ZOOM - 1, -1):
        present[z] = set()
        for x, y in sorted({(x // 2, y // 2) for x, y in present[z + 1]}):
            children = [tiles._read_png(target / str(z + 1) / str(2 * x + dx) / f"{2 * y + dy}.png")
                        for dy in (0, 1) for dx in (0, 1)]
            rgba = tiles._downsample(children)
            if rgba is not None:
                tiles._write_png(target / str(z) / str(x) / f"{y}.png", rgba)
                present[z].add((x, y))
        print(f"z{z}: {len(present[z])} tiles")

    index = {
        # Goes into the tile URLs, so a rebuild is not hidden behind tiles
        # browsers cached from the last one (server.py caches tiles a day).
        "version": int(time.time()),
        "minZoom": TRACK_MIN_ZOOM,
        "maxZoom": TRACK_MAX_ZOOM,
        "tiles": {str(z): sorted(f"{x}/{y}" for x, y in t) for z, t in sorted(present.items())},
    }
    (target / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    total = sum(p.stat().st_size for p in target.rglob("*.png"))
    print(f"{sum(len(t) for t in present.values())} tiles, {total / 1e6:.1f} MB -> {target}  "
          f"({time.monotonic() - started:.0f} s)")
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m validation_app.prepare",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--skip-tracks", action="store_true",
                        help="only the corridor files; the track tiles take minutes")
    args = parser.parse_args(argv)
    build_corridors(args.out)
    if not args.skip_tracks:
        build_tracks(TRACKS_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
