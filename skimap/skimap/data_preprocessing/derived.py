"""National derived layers: slope, rasterized vectors, avalanche exposure.

Built nationally rather than per tile, because:
  - slope needs a 3x3 window, so per-tile it needs a halo or every tile
    edge gets wrong values and the mosaic shows a grid of seams;
  - rasterizing is one pass per vector layer instead of 1334 spatially
    filtered ones;
  - everything else is per-pixel math that streams in blocks.

The tile step then only crops windows out of these, which is why it needs
no GDAL process per tile per layer.

All outputs share one grid - the tile grid's extent snapped to
config.RASTER_ORIGIN - so any two can be combined without resampling.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np
from osgeo import gdal

from skimap import config, paths
from skimap.data_preprocessing.rasters import _run

gdal.UseExceptions()

Grid = tuple[float, float, float, float]


def national_grid() -> Grid:
    """Extent every derived layer is built on: the tile grid, on the raster lattice."""
    import geopandas as gpd

    b = gpd.read_file(paths.TILE_GRID, layer=paths.TILE_GRID_LAYER).total_bounds
    ox, oy = config.RASTER_ORIGIN
    p = config.PIXEL_SIZE
    return (
        ox + math.floor((b[0] - ox) / p) * p,
        oy + math.floor((b[1] - oy) / p) * p,
        ox + math.ceil((b[2] - ox) / p) * p,
        oy + math.ceil((b[3] - oy) / p) * p,
    )


def _creation_opts(dtype: str) -> list[str]:
    predictor = "3" if dtype.startswith("Float") else "2"
    return [
        "-co", "TILED=YES", "-co", "BLOCKXSIZE=512", "-co", "BLOCKYSIZE=512",
        "-co", "COMPRESS=DEFLATE", "-co", f"PREDICTOR={predictor}",
        "-co", "BIGTIFF=YES", "-co", "NUM_THREADS=ALL_CPUS",
    ]


def align_vrt(src: Path, out_path: Path, grid: Optional[Grid] = None) -> Path:
    """A virtual view of `src` on the national grid.

    Pure crop and pad - every national source already sits on
    config.RASTER_ORIGIN's lattice, so nothing is resampled. This is what
    lets block maths read two sources with different extents as if they
    were the same shape, without rewriting either.
    """
    grid = grid or national_grid()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "gdalbuildvrt", "-overwrite",
        "-te", *grid, "-tr", config.PIXEL_SIZE, config.PIXEL_SIZE,
        out_path, src,
    ])
    return out_path


def rasterize(vector: Path, out_path: Path, *, layer: str, where: Optional[str] = None,
              grid: Optional[Grid] = None) -> Path:
    """Burn a vector layer onto the national grid as a 0/1 Byte mask.

    all_touched is on: a river or road thinner than a pixel still has to
    register, or narrow features would vanish at 10 m.
    """
    grid = grid or national_grid()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gdal_rasterize", "-l", layer, "-burn", 1, "-at",
        "-ot", "Byte", "-a_nodata", 0, "-init", 0,
        "-te", *grid, "-tr", config.PIXEL_SIZE, config.PIXEL_SIZE,
        *_creation_opts("Byte"),
    ]
    if where:
        cmd += ["-where", where]
    cmd += [vector, out_path]
    _run(cmd)
    _add_overviews(out_path)
    return out_path


def slope(dem: Path, out_path: Path) -> Path:
    """Slope in degrees from the DEM, as Float32.

    -compute_edges keeps the national border pixels valid instead of
    leaving a nodata fringe.

    Stored unscaled on purpose. A scaled integer halves the file but band
    scale/offset is metadata most GIS tools ignore, so the layer reads as
    8998 instead of 89.98 in ArcGIS and any code that forgets the factor is
    silently 100x out. Degrees on disk are worth the bytes.

    The DEM's nodata must be declared correctly before this runs, or
    gdaldem reads the void sentinel as terrain and puts a ~90 degree cliff
    around every data edge.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(["gdaldem", "slope", dem, out_path, "-compute_edges", "-of", "GTiff",
          *_creation_opts("Float32")])
    _add_overviews(out_path)
    return out_path


def block_apply(
    inputs: dict[str, Path],
    out_path: Path,
    fn: Callable[[dict[str, np.ndarray]], np.ndarray],
    *,
    dtype: str,
    nodata: Optional[float] = None,
    scale: Optional[float] = None,
    block: int = 256,
) -> Path:
    """Stream per-pixel maths over rasters that share a grid.

    `fn` gets a dict of float64 blocks keyed like `inputs` and returns one
    block of results in REAL units. Nodata is NOT masked out first - the
    maths decides what each sentinel means, which differs per layer.

    If `scale` is set the result is divided by it before writing and the
    factor is recorded on the band, so readers get real units back.

    `block` is rows, not pixels: at national width one row is ~124k px, so
    256 rows is already a 32 Mpx float64 array per input. Raising it buys
    nothing - decompression dominates, not Python - and costs memory fast.
    """
    dss = {k: gdal.Open(str(v)) for k, v in inputs.items()}
    shapes = {(d.RasterXSize, d.RasterYSize) for d in dss.values()}
    if len(shapes) != 1:
        raise ValueError(f"inputs must share a grid, got {shapes} - align them with align_vrt first")
    w, h = shapes.pop()
    ref = next(iter(dss.values()))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    drv = gdal.GetDriverByName("GTiff")
    opts = [o for o in _creation_opts(dtype) if o != "-co"]
    dst = drv.Create(str(out_path), w, h, 1, gdal.GetDataTypeByName(dtype), options=opts)
    dst.SetGeoTransform(ref.GetGeoTransform())
    dst.SetProjection(ref.GetProjection())
    band = dst.GetRasterBand(1)
    if nodata is not None:
        band.SetNoDataValue(nodata)
    if scale is not None:
        band.SetScale(scale)

    n = 0
    for y in range(0, h, block):
        ny = min(block, h - y)
        blocks = {k: d.GetRasterBand(1).ReadAsArray(0, y, w, ny).astype(np.float64)
                  for k, d in dss.items()}
        result = fn(blocks)
        if scale is not None:
            result = np.round(result / scale)
        band.WriteArray(result, 0, y)
        n += 1
        if n % 10 == 0:
            print(f"  {100 * (y + ny) / h:5.1f}%", flush=True)

    band.FlushCache()
    dst = None
    for d in dss.values():
        del d
    _add_overviews(out_path)
    return out_path


def _add_overviews(path: Path) -> None:
    ds = gdal.Open(str(path), gdal.GA_Update)
    ds.BuildOverviews("AVERAGE", [2, 4, 8, 16, 32, 64, 128, 256])
    ds = None


# --- the per-pixel maths -----------------------------------------------


def _rescale(x: np.ndarray, in_lo: float, in_hi: float, out_lo: float, out_hi: float) -> np.ndarray:
    t = np.clip((x - in_lo) / (in_hi - in_lo), 0.0, 1.0)
    return out_lo + t * (out_hi - out_lo)


def pra_runout(blocks: dict[str, np.ndarray]) -> np.ndarray:
    """Release areas and runout distance combined into one cost layer.

    Release areas take the upper cost band, scaled by release probability.
    Everything else within reach of one takes the lower band, scaled by a
    Weibull decay on distance. Neither: MIN_COST, i.e. no avalanche cost -
    not nodata, because "no avalanche terrain here" is an answer.
    """
    p = config.PRA_RUNOUT
    pra, dist = blocks["pra"], blocks["runout"]

    is_release = pra >= p["release_threshold"]
    is_runout = (~is_release) & (dist > 0) & (dist < p["runout_max_distance"])

    out = np.full(pra.shape, config.MIN_COST, dtype=np.float64)
    out[is_release] = _rescale(pra, *p["release_in"], *p["release_out"])[is_release]

    decay = np.exp(-np.power(p["weibull_lambda"] * np.maximum(dist, 0.0), p["weibull_alpha"]))
    out[is_runout] = _rescale(decay, *p["runout_in"], *p["runout_out"])[is_runout]
    return out


def intersect(blocks: dict[str, np.ndarray]) -> np.ndarray:
    """1 where every input is non-zero. Used for bridge and trails-in-forest."""
    out = np.ones(next(iter(blocks.values())).shape, dtype=np.float64)
    for arr in blocks.values():
        out *= (arr > 0)
    return out


# --- driver ------------------------------------------------------------


def build_all(*, only: Optional[Sequence[str]] = None, force: bool = False) -> None:
    """Build every derived layer, in dependency order."""
    grid = national_grid()
    w = int((grid[2] - grid[0]) / config.PIXEL_SIZE)
    h = int((grid[3] - grid[1]) / config.PIXEL_SIZE)
    print(f"national grid: {w} x {h} px ({w * h / 1e9:.2f} Gpx), extent {grid}\n")
    paths.DERIVED.mkdir(parents=True, exist_ok=True)

    def wanted(name: str) -> bool:
        if only and name not in only:
            return False
        if paths.derived(name).exists() and not force:
            print(f"-- {name}: exists, skipping")
            return False
        return True

    for name, (theme, where) in config.VECTOR_LAYERS.items():
        if wanted(name):
            print(f"== {name}  <- {theme}")
            rasterize(paths.source(theme), paths.derived(name),
                      layer=paths.source(theme).stem, where=where, grid=grid)

    if wanted("slope"):
        print("== slope  <- dem")
        slope(paths.source("dem"), paths.derived("slope"))

    if wanted("pra_runout"):
        print("== pra_runout  <- pra + runout")
        aligned = {k: align_vrt(paths.source(k), paths.DERIVED / f"_{k}.vrt", grid)
                   for k in ("pra", "runout")}
        try:
            # No nodata: every pixel gets a defined cost, MIN_COST where
            # there is no avalanche terrain at all. Float32 for the same
            # reason as slope - see that function.
            block_apply(aligned, paths.derived("pra_runout"), pra_runout,
                        dtype="Float32")
        finally:
            for v in aligned.values():
                v.unlink(missing_ok=True)

    if wanted("tractorroad_trail_forest"):
        print("== tractorroad_trail_forest  <- tractorroad_trail + forest")
        srcs = {
            "trail": paths.derived("tractorroad_trail"),
            "forest": align_vrt(paths.source("forest"), paths.DERIVED / "_forest.vrt", grid),
        }
        try:
            block_apply(srcs, paths.derived("tractorroad_trail_forest"), intersect,
                        dtype="Byte", nodata=0)
        finally:
            srcs["forest"].unlink(missing_ok=True)

    if wanted("bridge"):
        print("== bridge  <- river + tractorroad_trail")
        block_apply(
            {"river": paths.derived("river"), "trail": paths.derived("tractorroad_trail")},
            paths.derived("bridge"), intersect, dtype="Byte", nodata=0,
        )
