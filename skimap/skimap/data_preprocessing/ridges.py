"""Exposed ridges from a windshelter threshold.

windshelter is negative on convex ground and positive in bowls, so a cut
across it flags crests: at or below `config.RIDGE_COST["threshold"]` is an
exposed ridge. The cost surface takes the same cut from the windshelter tile
it already reads, so nothing here is required to build one - this writes it
out as `exposed_ridge.tif` to look at and to judge the threshold by.

This replaced a GRASS r.geomorphon build (eight lines of sight per cell, ten
landform classes, a cross-ridge steepness pass, and the halo both needed).
That asked the better question - one cell of windshelter cannot tell a crest
from any other convex patch - but it needed GRASS, per-tile work and ~31
hours nationally. A threshold needs none of that: no halo, so no tiling and
no mosaic, and the national build is one streamed pass.

windshelter is tightly peaked (sd ~0.067, 91% of cells within +/-0.1), so a
threshold sits far out in a thin tail and small moves matter. Measured on
Isfjorden and Jotunheimen: -0.15 flags ~2.6% of cells, -0.2 ~1.4%, -0.3
~0.5%, -0.4 ~0.21%, -0.6 ~0.03%.

    prep ridges --area 04_isfjorden --threshold -0.2 -0.3 -0.4
    prep ridges --bbox 99446 6946619 101567 6949740
    prep ridges --national

An area writes one mask per candidate into `candidates/`, the coverage into
`thresholds.json` - the eye cannot tell "only the sharpest crests" from
"nothing at all" on a dark screen - and `windshelter.tif` cut to the same
extent, so the values behind a mask are one layer away rather than somewhere
in a 16 GB national file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from osgeo import gdal

from skimap import config, paths
from skimap.data_preprocessing import derived
from skimap.data_preprocessing.rasters import _snap_bounds

gdal.UseExceptions()

Extent = tuple[float, float, float, float]   # minx, miny, maxx, maxy

# What a finished area build leaves behind:
#
#   exposed_ridge  0/1 at config.RIDGE_COST["threshold"]
#   windshelter    the values it was cut from, same extent
#   candidates/    one mask per --threshold, for the comparison
#   thresholds.json  what each candidate flagged, as a fraction of the area
LAYERS = ("exposed_ridge",)

EXPOSED_NODATA = 255

_CREATE_OPT = ["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512",
               "COMPRESS=DEFLATE", "PREDICTOR=2", "BIGTIFF=YES",
               "NUM_THREADS=ALL_CPUS"]


# --- areas ---------------------------------------------------------------
# The built-in five are the tiles skimap.track_scenarios already uses, which
# is not because track coverage matters here but because they are known
# ground that between them spans coast, forest, ordinary alpine and the high
# interior - and because a name that already means something to you beats
# five new ones.
#
# Add your own in data/ridges/areas.json, as either
#     {"lyngen": {"tile": "tile_644500_7719500"}}
# or  {"lyngen": {"bbox": [644500, 7719500, 664500, 7739500]}}
# Anything in that file replaces the whole set below.
AREAS: dict[str, dict] = {
    "01_etne": {"tile": "tile_4500_6659500", "place": "Etne / Sunnhordland, the south west coast"},
    "02_bykle": {"tile": "tile_64500_6599500", "place": "Bykle / Setesdal"},
    "03_voss": {"tile": "tile_44500_6739500", "place": "Voss"},
    "04_isfjorden": {"tile": "tile_124500_6959500", "place": "Isfjorden / Molde"},
    "05_sjodalen": {"tile": "tile_164500_6819500", "place": "Sjodalen / Vaaga, eastern Jotunheimen"},
    # Not a tile: a hand-picked 2 x 3 km of Romsdalen at 62.4486 N, 7.2451 E,
    # given as UTM 32V 408521 6923909 / 410372 6926865 and converted here,
    # since the project is on UTM 33. Knife-edge ground - the sharpest crests
    # in the set, so the place to see whether a cut is too generous.
    "06_romsdalen": {"bbox": [99446, 6946619, 101567, 6949740],
                     "place": "Romsdalen, the knife-edge test piece"},
}


def areas() -> dict[str, dict]:
    """The named areas, with data/ridges/areas.json replacing them if present."""
    if not paths.RIDGE_AREAS_FILE.exists():
        return AREAS
    # utf-8-sig for the same reason as everywhere else here: this is a file
    # you edit by hand on Windows, and Notepad leaves a BOM.
    override = json.loads(paths.RIDGE_AREAS_FILE.read_text(encoding="utf-8-sig"))
    return override or AREAS


def tile_extent(tile_id: str) -> Extent:
    """A tile's bounds, snapped out onto the raster lattice.

    Tile corners sit exactly half a pixel off it (config.RASTER_ORIGIN
    against config.GRID_ORIGIN), so this always grows by 5 m on each side and
    adjacent tiles overlap by one column of cells.
    """
    from skimap.grid import iter_tiles

    tile = next(iter(iter_tiles(only=[tile_id])))
    return _snap_bounds(*tile.bounds)


def resolve(*, area: Optional[Sequence[str]] = None,
            tile: Optional[Sequence[str]] = None,
            bbox: Optional[Sequence[float]] = None,
            label: Optional[str] = None) -> list[tuple[str, Extent]]:
    """Turn the CLI's area selectors into (label, extent) pairs."""
    out: list[tuple[str, Extent]] = []
    known = areas()

    for name in area or []:
        if name not in known:
            raise KeyError(f"No area {name!r}. Known: {sorted(known)}. "
                           f"Define your own in {paths.RIDGE_AREAS_FILE}.")
        spec = known[name]
        if "bbox" in spec:
            out.append((name, _snap_bounds(*(float(v) for v in spec["bbox"]))))
        else:
            out.append((name, tile_extent(spec["tile"])))

    for tile_id in tile or []:
        out.append((tile_id, tile_extent(tile_id)))

    if bbox:
        out.append((label or "bbox", _snap_bounds(*(float(v) for v in bbox))))

    if not out:
        raise SystemExit("Nothing selected: pass --area, --tile, --bbox or --national.")
    return out


# --- the threshold -------------------------------------------------------


def thresholds(override: Optional[Sequence[float]] = None) -> list[float]:
    """The candidates an area build writes, committed threshold first.

    config.RIDGE_CANDIDATES is the default spread; --threshold replaces
    it. Either way the committed value is included, because the point of the
    comparison is to see what you have against what you might have.
    """
    wanted = list(override) if override else list(config.RIDGE_CANDIDATES)
    committed = float(config.RIDGE_COST["threshold"])
    if committed not in wanted:
        wanted = [committed] + wanted
    # Deduplicate but keep order: dict preserves insertion order.
    return list(dict.fromkeys(float(t) for t in wanted))


def _mask(windshelter: np.ndarray, threshold: float, nodata: float) -> np.ndarray:
    """0/1 where windshelter is at or below `threshold`, EXPOSED_NODATA elsewhere.

    NaN as well as the sentinel, because the national file carries both and
    a comparison against NaN is False - which would quietly write 0 (not a
    ridge) over ground where the answer is not known.
    """
    valid = np.isfinite(windshelter) & (windshelter != nodata)
    out = np.full(windshelter.shape, EXPOSED_NODATA, dtype=np.float64)
    out[valid] = (windshelter[valid] <= threshold).astype(np.float64)
    return out


def _write(arr: np.ndarray, out_path: Path, ref: gdal.Dataset, *,
           dtype: int, nodata: Optional[float]) -> Path:
    """One array onto `ref`'s grid, with overviews.

    NEAREST overviews for the masks: averaging a 0/1 layer invents ridges
    that are 0.4 of a ridge, and at national zoom that reads as a haze over
    ground where there is nothing.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    drv = gdal.GetDriverByName("GTiff")
    dst = drv.Create(str(out_path), ref.RasterXSize, ref.RasterYSize, 1, dtype,
                     options=_CREATE_OPT)
    dst.SetGeoTransform(ref.GetGeoTransform())
    dst.SetProjection(ref.GetProjection())
    band = dst.GetRasterBand(1)
    if nodata is not None:
        band.SetNoDataValue(nodata)
    band.WriteArray(arr)
    band.FlushCache()
    dst = None

    ds = gdal.Open(str(out_path), gdal.GA_Update)
    ds.BuildOverviews("NEAREST" if dtype == gdal.GDT_Byte else "AVERAGE",
                      [2, 4, 8, 16, 32])
    ds = None
    return out_path


def build_extent(label: str, extent: Extent, out_dir: Path, *,
                 candidates: Optional[Sequence[float]] = None,
                 force: bool = False) -> Optional[Path]:
    """One extent, start to finish.

    No halo: a per-cell cut needs no neighbours, so the extent is read as
    given and the output is identical to the same ground cut out of a
    national run. Returns exposed_ridge.tif, or None if it was already there
    and `force` is off.
    """
    out_path = out_dir / "exposed_ridge.tif"
    if out_path.exists() and not force:
        print(f"-- {label}: exists, skipping")
        return None

    minx, miny, maxx, maxy = extent
    print(f"== {label}  {(maxx - minx) / 1000:g} x {(maxy - miny) / 1000:g} km "
          f"at [{minx:.0f} {miny:.0f}]")

    src = paths.layer("windshelter")
    # A window onto the national file, not a copy of it: gdal.Translate with
    # projWin reads only the blocks it needs, so the 16 GB source costs the
    # same here as a small one.
    cut = gdal.Translate("", str(src), format="VRT",
                         projWin=[minx, maxy, maxx, miny])
    band = cut.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    values = band.ReadAsArray().astype(np.float64)

    out_dir.mkdir(parents=True, exist_ok=True)
    # The values behind the masks, same extent, so ArcGIS has both in one
    # folder. Float32 with its own nodata: this is the layer you stretch.
    #
    # Written once and not again, --force included: it is a crop of a source
    # that does not change, so a rebuild would write the same bytes back. It
    # is also the layer most likely to be open in ArcGIS while you re-cut the
    # masks beside it, and GDAL's Create() deletes before it writes - which
    # ArcGIS permits for neither.
    ws_path = out_dir / "windshelter.tif"
    if not ws_path.exists():
        _write(np.where(np.isfinite(values), values, nodata), ws_path,
               cut, dtype=gdal.GDT_Float32, nodata=nodata)

    committed = float(config.RIDGE_COST["threshold"])
    valid_count = int((np.isfinite(values) & (values != nodata)).sum())

    stats = []
    for t in thresholds(candidates):
        mask = _mask(values, t, nodata)
        flagged = int((mask == 1).sum())
        pct = 100.0 * flagged / valid_count if valid_count else 0.0
        target = (out_path if t == committed
                  else out_dir / "candidates" / f"exposed_ridge_{t:+.2f}.tif")
        _write(mask, target, cut, dtype=gdal.GDT_Byte, nodata=EXPOSED_NODATA)
        stats.append({"threshold": t, "flagged_px": flagged,
                      "valid_px": valid_count, "flagged_pct": round(pct, 4),
                      "committed": t == committed,
                      "file": str(target.relative_to(out_dir)).replace("\\", "/")})
        print(f"   {t:+.2f}  {pct:6.2f}% of the area"
              f"{'   <- config.RIDGE_COST[\"threshold\"]' if t == committed else ''}")

    (out_dir / "thresholds.json").write_text(
        json.dumps({"area": label, "extent": list(extent), "source": str(src),
                    "thresholds": stats}, indent=2) + "\n", encoding="utf-8")

    cut = None
    return out_path


def build_areas(selected: Sequence[tuple[str, Extent]], *,
                candidates: Optional[Sequence[float]] = None,
                force: bool = False) -> list[Path]:
    """Build the named areas into data/ridges/areas/<label>/."""
    out = []
    for label, extent in selected:
        made = build_extent(label, extent, paths.RIDGE_AREAS / label,
                            candidates=candidates, force=force)
        if made:
            print(f"   {made}")
            out.append(made)
    return out


def build_national(*, force: bool = False) -> list[Path]:
    """The whole country, in one streamed pass, into derived/exposed_ridge.tif.

    No tiles and no mosaic. The old geomorphon build needed both because a
    landform is a function of everything within its search radius, so a tile
    had to be grown by a halo and cropped back; a threshold is a function of
    one cell, so the national windshelter can simply be read block by block.
    """
    out_path = paths.derived("exposed_ridge")
    if out_path.exists() and not force:
        print(f"-- exposed_ridge: exists, skipping ({out_path})")
        return []

    src = paths.layer("windshelter")
    threshold = float(config.RIDGE_COST["threshold"])
    # Held in a name: chaining off gdal.Open() frees the Dataset before the
    # Band is used, and the Band then raises on its own dangling pointer.
    src_ds = gdal.Open(str(src))
    nodata = src_ds.GetRasterBand(1).GetNoDataValue()
    src_ds = None
    print(f"== national exposed_ridge at windshelter <= {threshold:+.2f}  <- {src}")

    def cut(blocks: dict[str, np.ndarray]) -> np.ndarray:
        return _mask(blocks["windshelter"], threshold, nodata)

    made = derived.block_apply({"windshelter": src}, out_path, cut,
                               dtype="Byte", nodata=EXPOSED_NODATA)
    print(f"   {made}")
    return [made]
