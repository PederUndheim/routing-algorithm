r"""data/colored_corridors as map tiles, for the app's overlay of the same name.

The four class rasters (green, blue, red, black) cover the whole country at
10 m - 82 000 x 130 000 cells, a third of a percent of them corridor. One
picture of that is either too coarse to show a band a few hundred metres wide
or far too large for a browser to decode, so it is cut into ordinary XYZ PNG
tiles instead and the map fetches only the ones on screen.

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m app.corridor_tiles

Writes app/frontend/public/colored_corridors/{z}/{x}/{y}.png and an
index.json listing every tile that exists. The frontend reads the index and
asks for nothing else: most of the country is empty, and a request per empty
tile is a 404 per tile.

`MAX_ZOOM` tiles are warped from the rasters themselves, coloured with the
same data/styles_arcgis files the review draws them in, and stacked green
under black - the classes are disjoint outside overlap.py's seams, and in a
seam the harder colour goes on top. Every zoom above that is built from the
four tiles under it. Those keep the *strongest* alpha of the four children
rather than the mean: averaged, a band a few cells wide fades out within two
zoom levels, and the point of the low zooms is to show where there are
corridors at all.

Re-run after `python -m skimap.corridor_review colored-corridors`; the tiles
describe the rasters as they were when this ran.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from skimap import paths
from skimap.corridor_review import render

gdal.UseExceptions()

CLASSES = ("green", "blue", "red", "black")   # bottom to top

# z12 is ~16-20 m a pixel over Norway, so a corridor is tens of pixels across;
# past it Leaflet scales these up (maxNativeZoom), which costs nothing to look
# at and saves four times the tiles per level.
MAX_ZOOM = 12
MIN_ZOOM = 5   # the map's own minZoom

TILE = 256
ORIGIN = 20037508.342789244   # half the Web Mercator world, in metres

OUT = Path(__file__).resolve().parent / "frontend" / "public" / "colored_corridors"


def _tile_size(z: int) -> float:
    return 2 * ORIGIN / (1 << z)


def _tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    size = _tile_size(z)
    west = -ORIGIN + x * size
    north = ORIGIN - y * size
    return west, north - size, west + size, north


def _occupied_tiles(datasets: dict[str, gdal.Dataset]) -> set[tuple[int, int]]:
    """MAX_ZOOM tiles that might hold corridor, from a coarse read.

    Read at the overview nearest 160 m - fine enough not to step over a
    band, small enough to hold four of in memory - and padded by a tile each
    way, so a corridor that only shows up at full resolution near a tile edge
    still gets its tile. A tile that turns out empty is dropped when drawn.
    """
    first = next(iter(datasets.values()))
    width, height = first.RasterXSize // 16, first.RasterYSize // 16
    occupied = np.zeros((height, width), dtype=bool)
    for dataset in datasets.values():
        values = dataset.GetRasterBand(1).ReadAsArray(buf_xsize=width, buf_ysize=height)
        occupied |= np.isfinite(values) & (values > 0)

    rows, cols = np.nonzero(occupied)
    ox, px, _, oy, _, py = first.GetGeoTransform()
    cell_x = ox + (cols + 0.5) * px * 16
    cell_y = oy + (rows + 0.5) * py * 16

    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromWkt(first.GetProjection())
    target.ImportFromEPSG(render.WEBMERCATOR_EPSG)
    for srs in (source, target):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source, target)
    merc = np.array(transform.TransformPoints(np.column_stack([cell_x, cell_y])))

    size = _tile_size(MAX_ZOOM)
    tx = np.floor((merc[:, 0] + ORIGIN) / size).astype(np.int64)
    ty = np.floor((ORIGIN - merc[:, 1]) / size).astype(np.int64)
    seeds = set(zip(tx.tolist(), ty.tolist()))
    return {(x + dx, y + dy) for x, y in seeds for dx in (-1, 0, 1) for dy in (-1, 0, 1)}


def _over(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
    """`top` composited over `bottom`, both premultiplied float RGBA in 0..1."""
    return top + bottom * (1.0 - top[..., 3:4])


def _render_tile(datasets: dict[str, gdal.Dataset], x: int, y: int) -> np.ndarray | None:
    """One MAX_ZOOM tile as uint8 RGBA, or None if nothing in it is drawn."""
    west, south, east, north = _tile_bounds(MAX_ZOOM, x, y)
    stack = np.zeros((TILE, TILE, 4), dtype=np.float64)
    for colour, dataset in datasets.items():
        warped = gdal.Warp(
            "", dataset, format="MEM", dstSRS=f"EPSG:{render.WEBMERCATOR_EPSG}",
            outputBounds=(west, south, east, north), width=TILE, height=TILE,
            resampleAlg="bilinear", srcNodata=0, dstNodata=0,
            outputType=gdal.GDT_Float32,
        )
        scores = warped.GetRasterBand(1).ReadAsArray().astype(np.float64)
        inside = np.isfinite(scores) & (scores > 0.0)
        if not inside.any():
            continue
        rgba = render._colorize(np.clip(scores, 0.0, 1.0), inside, colour) / 255.0
        rgba[..., :3] *= rgba[..., 3:4]
        stack = _over(stack, rgba)
    return _to_uint8(stack)


def _to_uint8(premultiplied: np.ndarray) -> np.ndarray | None:
    alpha = premultiplied[..., 3:4]
    if not (alpha > 0.5 / 255).any():
        return None
    rgb = np.divide(premultiplied[..., :3], alpha,
                    out=np.zeros_like(premultiplied[..., :3]), where=alpha > 0)
    out = np.concatenate([rgb, alpha], axis=-1)
    return np.rint(np.clip(out, 0.0, 1.0) * 255).astype(np.uint8)


def _downsample(children: list[np.ndarray | None]) -> np.ndarray | None:
    """Four tiles (NW, NE, SW, SE; None for empty) as one at the zoom above.

    Colour is the alpha-weighted mean of each 2x2 block, alpha its maximum -
    see the module docstring for why not the mean.
    """
    block = np.zeros((2 * TILE, 2 * TILE, 4), dtype=np.float64)
    for index, child in enumerate(children):
        if child is not None:
            row, col = divmod(index, 2)
            block[row * TILE:(row + 1) * TILE, col * TILE:(col + 1) * TILE] = child / 255.0

    quads = block.reshape(TILE, 2, TILE, 2, 4)
    alpha = quads[..., 3]
    weight = alpha.sum(axis=(1, 3))
    rgb = (quads[..., :3] * alpha[..., None]).sum(axis=(1, 3))
    rgb = np.divide(rgb, weight[..., None], out=np.zeros_like(rgb), where=weight[..., None] > 0)
    top_alpha = alpha.max(axis=(1, 3))
    return _to_uint8(np.concatenate([rgb * top_alpha[..., None], top_alpha[..., None]], axis=-1))


def _write_png(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = gdal.GetDriverByName("MEM").Create("", TILE, TILE, 4, gdal.GDT_Byte)
    for band in range(4):
        image.GetRasterBand(band + 1).WriteArray(rgba[..., band])
    gdal.GetDriverByName("PNG").CreateCopy(str(path), image, options=["ZLEVEL=9"])


def _read_png(path: Path) -> np.ndarray | None:
    if not path.is_file():
        return None
    # Held in a name: a band does not keep its dataset alive, and one opened
    # inline is collected before the band is read.
    image = gdal.Open(str(path))
    return np.dstack([image.GetRasterBand(b + 1).ReadAsArray() for b in range(4)])


def build(source_dir: Path = paths.COLORED_CORRIDORS, out_dir: Path = OUT) -> dict:
    datasets = {}
    for colour in CLASSES:
        tif = source_dir / f"corridors_{colour}.tif"
        if not tif.is_file():
            raise SystemExit(f"No {tif} - run `python -m skimap.corridor_review "
                             f"colored-corridors` first.")
        datasets[colour] = gdal.Open(str(tif))

    # Emptied rather than removed: on Windows a directory anything has open -
    # a running dev server, an Explorer window - cannot be deleted itself.
    if out_dir.exists():
        for old in out_dir.iterdir():
            shutil.rmtree(old) if old.is_dir() else old.unlink()

    started = time.monotonic()
    candidates = sorted(_occupied_tiles(datasets))
    print(f"z{MAX_ZOOM}: {len(candidates)} candidate tiles")

    present: dict[int, set[tuple[int, int]]] = {MAX_ZOOM: set()}
    for done, (x, y) in enumerate(candidates, 1):
        rgba = _render_tile(datasets, x, y)
        if rgba is not None:
            _write_png(out_dir / str(MAX_ZOOM) / str(x) / f"{y}.png", rgba)
            present[MAX_ZOOM].add((x, y))
        if done % 500 == 0:
            print(f"  {done}/{len(candidates)}  ({time.monotonic() - started:.0f} s)")
    print(f"z{MAX_ZOOM}: {len(present[MAX_ZOOM])} tiles")

    for z in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        present[z] = set()
        parents = {(x // 2, y // 2) for x, y in present[z + 1]}
        for x, y in sorted(parents):
            children = [_read_png(out_dir / str(z + 1) / str(2 * x + dx) / f"{2 * y + dy}.png")
                        for dy in (0, 1) for dx in (0, 1)]
            rgba = _downsample(children)
            if rgba is not None:
                _write_png(out_dir / str(z) / str(x) / f"{y}.png", rgba)
                present[z].add((x, y))
        print(f"z{z}: {len(present[z])} tiles")

    index = {
        "minZoom": MIN_ZOOM,
        "maxZoom": MAX_ZOOM,
        "tiles": {str(z): sorted(f"{x}/{y}" for x, y in tiles)
                  for z, tiles in sorted(present.items())},
    }
    (out_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")),
                                        encoding="utf-8")

    total = sum(p.stat().st_size for p in out_dir.rglob("*.png"))
    print(f"\n{sum(len(t) for t in present.values())} tiles, {total / 1e6:.1f} MB "
          f"-> {out_dir}  ({time.monotonic() - started:.0f} s)")
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.corridor_tiles",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", type=Path, default=paths.COLORED_CORRIDORS,
                        help="directory holding corridors_<colour>.tif "
                             "(default data/colored_corridors)")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    build(args.source, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
