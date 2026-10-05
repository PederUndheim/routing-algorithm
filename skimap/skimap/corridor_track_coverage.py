"""How much of Norway's recorded ski touring the reviewed corridors reach.

data/input/national/tracks/tracks.tif carries GPS density: a cell's value is
how many recorded passages crossed it, nodata (0) where nobody's GPS ever
did. This sums that value, not the count of cells it touches - a cell worth
59 counts as 59 people having been exactly there, so a corridor cutting
through a busy cell and one cutting through a quiet one are not weighed the
same just because both are one cell wide.

Coverage is measured against data/colored_corridors: the four rasters
`corridor_review colored-corridors` writes from the review's own picks, one
tour's winning model and final colour at a time - not a single national
model's classify() output. So this answers "of everyone who has ever skied
somewhere in Norway, what share of that skiing do the corridors the review
actually approved reach", which moves every time a round changes a verdict.

Runs over the national tile grid, the same one every other national stage
uses: one tile's tracks and one tile's window of each colour raster, summed
and discarded, so memory stays flat regardless of the country's size.

The same pass also ranks where the reviewed corridors are NOT: the
uncovered track weight left in each tile, worst first. A tile scoring high
here is recorded ski touring nothing routed has reached yet, so it is where
a new tour buys the most coverage per tour drawn - the fast way to raise
the percentage, rather than digitizing tours and finding out afterwards.

    python -m skimap.corridor_track_coverage

Writes data/review/stats/track_coverage.json and, unless --no-gap-raster:

    uncovered_tracks.tif        raw uncovered track weight, cell for cell
    uncovered_pct_of_gap.tif    the same, rescaled so every cell is what
                                percent of the NATIONAL gap sits right there
                                - summed over the whole country it is 100
    uncovered_pct_of_gap.png    a quicklook of that, the whole country in
                                one image, no GIS required
    uncovered_tracks_tiles.gpkg one polygon per uncovered tile, a 'rank'
                                field sorted worst first - the fast way to
                                find the top tiles in ArcGIS's attribute
                                table rather than eyeballing a raster

Both .tif are materialized COGs, not VRTs: a VRT is only a pointer at the
per-tile files under uncovered_tracks/, and ArcGIS either refuses to open
one (see lab.py) or reopens every tile behind it on each redraw - ruinous
over ~1300 of them. QGIS reads a VRT natively and does not pay that cost,
but a materialized file is never wrong to hand it either, so this writes
one rather than two kinds of output for two audiences.

A tour whose corridor has not been reviewed contributes nothing to the
"covered" side - see corridor_review.cli.colored_corridors for why a tour
is simply left out rather than filled in from a fallback model.
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal, ogr, osr

from skimap import config, grid, paths, raster

gdal.UseExceptions()
ogr.UseExceptions()

OUT = paths.DATA / "review" / "stats" / "track_coverage.json"
GAP_TILES = paths.DATA / "review" / "stats" / "uncovered_tracks" / "tiles"
GAP_VRT = paths.DATA / "review" / "stats" / "uncovered_tracks.vrt"
GAP_COG = paths.DATA / "review" / "stats" / "uncovered_tracks.tif"
GAP_OUTLINE = paths.DATA / "review" / "stats" / "uncovered_tracks_tiles.gpkg"
GAP_OUTLINE_LAYER = "gap_tiles"
GAP_PCT_TILES = paths.DATA / "review" / "stats" / "uncovered_tracks" / "pct_tiles"
GAP_PCT_VRT = paths.DATA / "review" / "stats" / "uncovered_pct_of_gap.vrt"
GAP_PCT_COG = paths.DATA / "review" / "stats" / "uncovered_pct_of_gap.tif"
GAP_PCT_PNG = paths.DATA / "review" / "stats" / "uncovered_pct_of_gap.png"
TILE_PX = int(config.TILE_SIZE / config.PIXEL_SIZE)

# Corridor levels are a 0..1 membership score, not a mask - lab.py draws
# them from 1e-6 up, and this uses the same floor for "inside the corridor".
MEMBERSHIP_FLOOR = 1e-6


@lru_cache(maxsize=1)
def _to_wgs84():
    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(config.CRS_EPSG)
    target.ImportFromEPSG(4326)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(source, target)


def _tile_centroid_wgs84(tile) -> tuple[float, float]:
    cx, cy = tile.x0 + config.TILE_SIZE / 2, tile.y0 + config.TILE_SIZE / 2
    lon, lat, _ = _to_wgs84().TransformPoint(cx, cy)
    return lon, lat


def _clear_stale(directory: Path) -> None:
    """Drop last run's tiles before writing new ones - skip, don't crash, on
    one QGIS still has open. It gets overwritten on the next run instead;
    the alternative is losing the rest of this one for a file left on screen.
    """
    locked = []
    for stale in directory.glob("*.tif"):
        try:
            stale.unlink()
        except OSError:
            locked.append(stale.name)
    if locked:
        print(f"  {len(locked)} old tile(s) still open elsewhere (e.g. in QGIS), "
              f"left in place and possibly stale: {locked[:5]}"
              f"{' ...' if len(locked) > 5 else ''}")


def _window(ds: gdal.Dataset, tile) -> np.ndarray:
    """One tile's worth of an already-open dataset, as raster.read_tile reads
    a national layer - same pixel lattice, but `ds` is not one of paths.SOURCES."""
    band = ds.GetRasterBand(1)
    px, py = raster.window(ds, tile)
    out = np.zeros((TILE_PX, TILE_PX), dtype=np.float32)

    sx0, sy0 = max(px, 0), max(py, 0)
    sx1, sy1 = min(px + TILE_PX, ds.RasterXSize), min(py + TILE_PX, ds.RasterYSize)
    if sx1 <= sx0 or sy1 <= sy0:
        return out

    arr = band.ReadAsArray(sx0, sy0, sx1 - sx0, sy1 - sy0).astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        arr = np.where(arr == np.float32(nodata), 0.0, arr)
    out[sy0 - py:sy1 - py, sx0 - px:sx1 - px] = arr
    return out


def analyze(corridor_dir: Optional[Path] = None, *, top: int = 15,
           write_gap_raster: bool = True) -> dict:
    """National track weight, how much of it the corridors reach, and the
    tiles carrying the most of what is left - overall, per colour, and
    ranked. Colours can share a few cells in overlap.py's cross-fade seams,
    so the by-colour shares can add up to slightly more than the overall
    figure; that is the seam, not double-counted skiing.

    Ranked by TILE (config.TILE_SIZE, 20 km) rather than a finer cluster: it
    is the unit every other national stage already works in, an area you can
    actually go look at, and cheap - no second pass, no clustering, just a
    running total kept beside the one this already computes.
    """
    corridor_dir = Path(corridor_dir) if corridor_dir else paths.COLORED_CORRIDORS
    colours = [name for _, name in config.EXPOSURE_CLASSES]

    datasets: dict[str, gdal.Dataset] = {}
    for colour in colours:
        path = corridor_dir / f"corridors_{colour}.tif"
        if path.is_file():
            datasets[colour] = gdal.Open(str(path))
        else:
            print(f"  no {path.name} in {corridor_dir} - treated as no coverage")

    total = 0.0
    covered = 0.0
    by_colour = {colour: 0.0 for colour in colours}
    gap_records: list[tuple[object, float]] = []   # (Tile, uncovered track weight)
    written: list[Path] = []

    if write_gap_raster:
        GAP_TILES.mkdir(parents=True, exist_ok=True)
        _clear_stale(GAP_TILES)

    tiles = list(grid.iter_tiles())
    for n, tile in enumerate(tiles, 1):
        tracks = raster.read_tile("tracks", tile, fill=0.0)
        tile_total = float(tracks.sum())
        total += tile_total

        uncovered = tracks
        if tile_total > 0.0:
            union = np.zeros(tracks.shape, dtype=bool)
            for colour, ds in datasets.items():
                mask = _window(ds, tile) > MEMBERSHIP_FLOOR
                if mask.any():
                    by_colour[colour] += float(tracks[mask].sum())
                    union |= mask
            covered += float(tracks[union].sum())
            uncovered = np.where(union, 0.0, tracks)

        gap_total = float(uncovered.sum())
        if gap_total > 0.0:
            gap_records.append((tile, gap_total))
            if write_gap_raster:
                out = GAP_TILES / f"{tile.tile_id}.tif"
                try:
                    raster.write_tile(uncovered.astype(np.float32), tile, out,
                                      dtype="Float32", nodata=0.0)
                    written.append(out)
                except OSError:
                    print(f"  {out.name}: locked elsewhere, skipped - may be stale")

        if n % 200 == 0 or n == len(tiles):
            print(f"  {n}/{len(tiles)} tiles")

    gap_records.sort(key=lambda row: -row[1])
    total_gap = total - covered

    ranked = []
    running = 0.0
    for tile, value in gap_records[:top]:
        running += value
        lon, lat = _tile_centroid_wgs84(tile)
        ranked.append({
            "tile_id": tile.tile_id, "easting": tile.x0, "northing": tile.y0,
            "lon": round(lon, 4), "lat": round(lat, 4),
            "uncovered_track_total": value,
            "pct_of_gap": (value / total_gap * 100.0) if total_gap else 0.0,
            "cumulative_pct_of_gap": (running / total_gap * 100.0) if total_gap else 0.0,
        })

    gap_vrt = None
    gap_cog = None
    if write_gap_raster and written:
        from skimap import mosaic

        gap_vrt = mosaic.rasters.build_vrt(written, GAP_VRT)
        gap_cog = mosaic.to_cog(gap_vrt, GAP_COG)

    return {
        "corridor_dir": str(corridor_dir),
        "national_track_total": total,
        "covered_track_total": covered,
        "covered_pct": (covered / total * 100.0) if total else 0.0,
        "total_gap": total_gap,
        "by_colour": {
            colour: {
                "track_total": by_colour[colour],
                "pct_of_national": (by_colour[colour] / total * 100.0) if total else 0.0,
            }
            for colour in colours
        },
        "gap_tiles_with_uncovered_tracks": len(gap_records),
        "top_gap_tiles": ranked,
        "gap_raster": str(gap_cog) if gap_cog else None,
    }


def write_gap_percent_raster(total_gap: float, *, tile_dir: Path = GAP_TILES,
                             out_dir: Path = GAP_PCT_TILES,
                             vrt_path: Path = GAP_PCT_VRT,
                             cog_path: Path = GAP_PCT_COG) -> Optional[Path]:
    """Rescale analyze()'s per-tile uncovered rasters into a share of the
    national gap: each cell becomes what percent of everything still
    uncovered in Norway sits right there. Summed over the whole country
    that is 100 by construction, so it reads the same wherever you look -
    a cell here is worth the same whether its tile is busy or empty.

    Returns the materialized COG - see the module docstring for why this
    does not stop at the VRT.
    """
    if not total_gap or not tile_dir.is_dir():
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    _clear_stale(out_dir)

    scale = np.float32(100.0 / total_gap)
    written = []
    for path in sorted(tile_dir.glob("*.tif")):
        src = gdal.Open(str(path))
        arr = src.GetRasterBand(1).ReadAsArray().astype(np.float32) * scale

        out_path = out_dir / path.name
        try:
            drv = gdal.GetDriverByName("GTiff")
            dst = drv.Create(str(out_path), src.RasterXSize, src.RasterYSize, 1,
                             gdal.GDT_Float32,
                             options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3"])
            dst.SetGeoTransform(src.GetGeoTransform())
            dst.SetProjection(src.GetProjection())
            band = dst.GetRasterBand(1)
            band.SetNoDataValue(0.0)
            band.WriteArray(arr)
            dst = band = None
            written.append(out_path)
        except (OSError, RuntimeError):
            print(f"  {out_path.name}: locked elsewhere, skipped - may be stale")
        finally:
            src = None

    if not written:
        return None
    from skimap import mosaic

    vrt = mosaic.rasters.build_vrt(written, vrt_path)
    return mosaic.to_cog(vrt, cog_path)


def write_uncovered_threshold(min_value: float, *, tile_dir: Path = GAP_TILES,
                              out_dir: Optional[Path] = None,
                              cog_path: Optional[Path] = None) -> Optional[Path]:
    """Just the uncovered cells worth more than `min_value` - everything else
    dropped to nodata, so the file is small and a load in ArcGIS shows only
    what is worth going and skiing to close.

    Reads analyze()'s per-tile rasters, not the merged COG: those are a few
    hundred small files rather than one raster the size of the country, so
    this is a quick follow-up on a run already done, not a second national
    pass.
    """
    if not tile_dir.is_dir():
        raise SystemExit(
            f"No tiles at {tile_dir}. Run 'python -m skimap.corridor_track_coverage' "
            f"first (without --no-gap-raster) to produce them."
        )
    label = f"{min_value:g}".replace(".", "_").replace("-", "m")
    out_dir = out_dir or (paths.DATA / "review" / "stats" / "uncovered_tracks" / f"gt{label}_tiles")
    cog_path = cog_path or (paths.DATA / "review" / "stats" / f"uncovered_tracks_gt{label}.tif")

    out_dir.mkdir(parents=True, exist_ok=True)
    _clear_stale(out_dir)

    written = []
    for path in sorted(tile_dir.glob("*.tif")):
        src = gdal.Open(str(path))
        arr = src.GetRasterBand(1).ReadAsArray()
        arr = np.where(arr > min_value, arr, 0.0)
        if not arr.any():
            src = None
            continue

        out_path = out_dir / path.name
        try:
            drv = gdal.GetDriverByName("GTiff")
            dst = drv.Create(str(out_path), src.RasterXSize, src.RasterYSize, 1,
                             gdal.GDT_Float32,
                             options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3"])
            dst.SetGeoTransform(src.GetGeoTransform())
            dst.SetProjection(src.GetProjection())
            band = dst.GetRasterBand(1)
            band.SetNoDataValue(0.0)
            band.WriteArray(arr)
            dst = band = None
            written.append(out_path)
        except (OSError, RuntimeError):
            print(f"  {out_path.name}: locked elsewhere, skipped - may be stale")
        finally:
            src = None

    if not written:
        print(f"No uncovered cell exceeds {min_value:g} - nothing written.")
        return None
    from skimap import mosaic

    vrt = cog_path.with_suffix(".vrt")
    tmp_vrt = mosaic.rasters.build_vrt(written, vrt)
    cog = mosaic.to_cog(tmp_vrt, cog_path)
    print(f"{len(written)} tiles have a cell over {min_value:g} -> {cog}")
    return cog


def write_gap_outline(*, tile_dir: Path = GAP_TILES,
                      out_path: Path = GAP_OUTLINE) -> Optional[Path]:
    """One polygon per tile with any uncovered track weight, ranked worst
    first - so the top tiles are a sort of an attribute table in ArcGIS,
    not a raster you eyeball for the brightest cell.

    Reads analyze()'s per-tile rasters for the totals: the same few hundred
    small files write_uncovered_threshold reads, not the merged COG, so this
    is a quick follow-up on a run already done rather than a second pass.
    """
    if not tile_dir.is_dir():
        raise SystemExit(
            f"No tiles at {tile_dir}. Run 'python -m skimap.corridor_track_coverage' "
            f"first (without --no-gap-raster) to produce them."
        )

    rows = []
    for path in sorted(tile_dir.glob("*.tif")):
        _, x0, y0 = path.stem.split("_")
        ds = gdal.Open(str(path))
        value = float(ds.GetRasterBand(1).ReadAsArray().sum())
        ds = None
        if value > 0.0:
            rows.append((grid.Tile(tile_id=path.stem, x0=float(x0), y0=float(y0)), value))

    if not rows:
        print("No uncovered tiles to outline.")
        return None
    rows.sort(key=lambda row: -row[1])
    total_gap = sum(value for _, value in rows)

    if out_path.exists():
        out_path.unlink()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    driver = ogr.GetDriverByName("GPKG")
    datasource = driver.CreateDataSource(str(out_path))
    layer = datasource.CreateLayer(GAP_OUTLINE_LAYER, srs, ogr.wkbPolygon)

    layer.CreateField(ogr.FieldDefn("tile_id", ogr.OFTString))
    layer.CreateField(ogr.FieldDefn("rank", ogr.OFTInteger))
    for name in ("uncovered_track_total", "pct_of_gap", "cumulative_pct_of_gap", "lon", "lat"):
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTReal))

    running = 0.0
    for rank, (tile, value) in enumerate(rows, 1):
        running += value
        x0, y0, x1, y1 = tile.bounds
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)):
            ring.AddPoint_2D(x, y)
        polygon = ogr.Geometry(ogr.wkbPolygon)
        polygon.AddGeometry(ring)

        lon, lat = _tile_centroid_wgs84(tile)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("tile_id", tile.tile_id)
        feature.SetField("rank", rank)
        feature.SetField("uncovered_track_total", value)
        feature.SetField("pct_of_gap", (value / total_gap * 100.0) if total_gap else 0.0)
        feature.SetField("cumulative_pct_of_gap", (running / total_gap * 100.0) if total_gap else 0.0)
        feature.SetField("lon", round(lon, 4))
        feature.SetField("lat", round(lat, 4))
        feature.SetGeometry(polygon)
        layer.CreateFeature(feature)
        feature = None

    datasource = None
    print(f"{len(rows)} tiles -> {out_path} (layer {GAP_OUTLINE_LAYER!r}, sort on 'rank')")
    return out_path


def render_quicklook(raster_path: Path, out_png: Path = GAP_PCT_PNG, *,
                     max_px: int = 1400) -> Path:
    """All of Norway in one PNG - a look, not a GIS layer; the VRT beside it
    is for that. Downsampled with `sum`, not the usual `average`: a percent
    is additive, so a coarser cell's share is what its finer cells add up
    to, not their mean.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    gdal.UseExceptions()
    src = gdal.Open(str(raster_path))
    gt = src.GetGeoTransform()
    width_m = gt[1] * src.RasterXSize
    height_m = abs(gt[5]) * src.RasterYSize
    res = max(width_m, height_m) / max_px

    warped = gdal.Warp("", str(raster_path), format="MEM",
                       xRes=res, yRes=res, resampleAlg="sum")
    arr = np.ma.masked_less_equal(warped.GetRasterBand(1).ReadAsArray(), 0.0)
    warped = src = None

    fig, ax = plt.subplots(figsize=(8, 8 * arr.shape[0] / max(arr.shape[1], 1)), dpi=140)
    if arr.count():
        im = ax.imshow(arr, cmap="inferno",
                       norm=LogNorm(vmin=max(float(arr.min()), 1e-6), vmax=float(arr.max())))
        fig.colorbar(im, ax=ax, shrink=0.6, label="% of the national gap, per cell")
    ax.set_axis_off()
    ax.set_title("Where Norway's still-uncovered ski touring is", fontsize=10, loc="left")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)
    return out_png


def run(corridor_dir: Optional[Path] = None, out: Optional[Path] = None, *,
       top: int = 15, write_gap_raster: bool = True) -> Path:
    corridor_dir = Path(corridor_dir) if corridor_dir else paths.COLORED_CORRIDORS
    print(f"summing national track density against {corridor_dir}")
    result = analyze(corridor_dir, top=top, write_gap_raster=write_gap_raster)

    print(f"\n{result['covered_pct']:.2f}% of all recorded ski touring in Norway "
          f"falls inside the reviewed corridors")
    print(f"  national total  {result['national_track_total']:,.0f}")
    print(f"  covered         {result['covered_track_total']:,.0f}")
    print("\nby colour (share of the NATIONAL total, not of what's covered):")
    for colour, row in result["by_colour"].items():
        print(f"  {colour:8s} {row['track_total']:14,.0f}  {row['pct_of_national']:5.2f}%")

    print(f"\ntop {len(result['top_gap_tiles'])} tiles to draw a new tour in, ranked by "
          f"uncovered track weight ({result['gap_tiles_with_uncovered_tracks']} tiles have any):")
    print(f"  {'tile':24s} {'lon':>9} {'lat':>9} {'uncovered':>13} {'% of gap':>9} {'cumulative':>11}")
    for row in result["top_gap_tiles"]:
        print(f"  {row['tile_id']:24s} {row['lon']:9.4f} {row['lat']:9.4f} "
              f"{row['uncovered_track_total']:13,.0f} {row['pct_of_gap']:8.2f}% {row['cumulative_pct_of_gap']:9.1f}%")
    if result["gap_raster"]:
        print(f"\nuncovered track density, to open beside tracks.tif and place a tour "
              f"precisely within a tile: {result['gap_raster']}")

        pct_cog = write_gap_percent_raster(result["total_gap"])
        if pct_cog:
            print(f"the same, as % of the national gap per cell: {pct_cog}")
            png = render_quicklook(pct_cog)
            print(f"and a quicklook of the whole country: {png}")

        write_gap_outline()

    out_path = Path(out) if out else OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{out_path}")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skimap.corridor_track_coverage",
        description=__doc__.split("\n\n")[0],
    )
    parser.add_argument("--corridors", type=Path,
                        help="directory of corridors_<colour>.tif (default data/colored_corridors)")
    parser.add_argument("--out", type=Path, help="where to write the summary JSON")
    parser.add_argument("--top", type=int, default=15,
                        help="how many uncovered tiles to rank (default 15)")
    parser.add_argument("--no-gap-raster", action="store_true",
                        help="skip writing uncovered_tracks.vrt - just the ranked list")
    parser.add_argument("--threshold", type=float,
                        help="skip the national pass and just write "
                             "uncovered_tracks_gt<N>.tif from the last run's tiles, "
                             "keeping only cells over this uncovered track value")
    parser.add_argument("--outline", action="store_true",
                        help="skip the national pass and just rebuild "
                             "uncovered_tracks_tiles.gpkg from the last run's tiles")
    args = parser.parse_args(argv)
    if args.threshold is not None:
        write_uncovered_threshold(args.threshold)
        return 0
    if args.outline:
        write_gap_outline()
        return 0
    run(args.corridors, args.out, top=args.top, write_gap_raster=not args.no_gap_raster)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
