"""ALARM runout: 23 regional rasters per scenario -> one national raster.

The dump under `data/input/runout_ALARM/` is one folder per scenario, each
holding 23 regional simulations named `pft_<nn>_<Region>_<S>_...max.tif`:

    A  80-60_prox0_rel1.2m   the smaller, more frequent avalanche
    D  75-55_prox0_rel2.3m   the larger, rarer one

`pft` is peak flow thickness in metres and `max` is already a maximum over
that region's simulations, so values run 0..~25 m - and 0 means "no
avalanche reaches this pixel", a real answer, not a gap. Only -9999 means
not modelled.

Storage, as delivered: Float32, one band, LZW, **strip-organized** (a block
is the full raster width by 1-10 rows), 5 m pixels on EPSG:25833, nodata
-9999. Every origin is a multiple of 5, so all 46 files already share one
5 m lattice - but only half of them sit on the 10 m lattice at
config.RASTER_ORIGIN, so they cannot simply be cropped onto the national
grid, they have to be warped onto it.

Which is what this does by default: each region is resampled to 10 m on
config.RASTER_ORIGIN's lattice, so a tile window is an exact crop of this
file exactly as it is of the DEM. `native=True` keeps the delivered 5 m
instead, for looking at rather than computing with.

The extent is the data's own, snapped outward to that lattice - not the
full national grid. Same lattice, so nothing is resampled either way; the
national grid just adds 4.7 Gpx of nodata around the outside, which is
~30 MB of empty tiles for no information. When a national-extent view is
needed, derived.align_vrt is a crop-and-pad VRT that costs nothing.

**The resampler must be max.** Measured on a 20 x 20 km window of D, against
the 2x2 block max that is the correct answer for a max quantity: `max` is
exact and keeps 100% of the footprint; `average` keeps the footprint but
understates the thinnest 5% of cells by ~60%; `near` drops 2.6% of the
footprint outright; `bilinear` and `cubic` invent runout on 55-66k cells of
modelled-clean ground, and cubic rings negative. Only max neither loses a
hit nor manufactures one.

The regions overlap heavily (~80 000 km2 of bbox overlap in A, ~96 000 in
D) and the overlapping halves are not interchangeable: a region only
releases avalanches from inside its own domain, so near its edge it is
under-modelled while its neighbour, for which that ground is interior, is
complete. Last-source-wins - what gdalbuildvrt does - therefore silently
takes the emptier answer wherever the later file happens to be the thin
one: sampling the centre of all 29 substantial A overlaps, 12 of them lose
positive pixels that way, up to 24% of a 7.5 km window. This takes the
**max** instead, which is order-independent and the same operator the
inputs already are.

Max also handles nodata for free: -9999 is below every real value, so it
survives only where every source is missing.

The output is UInt8, one decimetre per step:

    0..254   peak flow thickness, metres = value / 10
    254      25.4 m *and everything above* - the national max is 60.8 m
    255      nodata, not modelled

so `0` still means "modelled, and no avalanche reaches here" and is not the
same answer as 255. That distinction is the reason there has to be a nodata
value at all: "not modelled" is the largest class in the dataset (~7.3 of
9.3 Gpx), and folding it into 0 would report the sea, Sweden and every
lowland outside the 23 domains as safe ground.

The cast happens last, on the finished Float32 merge, and it has to:
255 is *above* every real value, so a UInt8 nodata put into the max would
beat real data and blank out exactly the overlaps this module exists to
resolve.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence
from xml.sax.saxutils import escape

from osgeo import gdal

from skimap import config, paths
from skimap.data_preprocessing import rasters

gdal.UseExceptions()

SCENARIOS = ("A", "D")

NODATA = -9999.0
SOURCE_PIXEL = 5.0

# UInt8 output. STEP is metres per stored unit and BYTE_MAX is the last real
# value, so BYTE_MAX * STEP is where the scale saturates: everything deeper
# is one bucket. 25.4 m against a national max of 60.8 m sounds brutal, but
# it is 0.001% of the positive pixels and no decision changes between 25 m
# and 61 m of moving snow, whereas the 0.1 m step it buys keeps the thin
# outer fringe of the runout zones that a coarser one rounds away.
BYTE_NODATA = 255
BYTE_MAX = 254
STEP = 0.1

# The sources are strip-organized, so a square read window decompresses the
# full raster width for every row it touches - about 70x more than it
# returns on a 38 000 px wide region. A cache and swath this size make GDAL
# copy in full-width swaths instead, so each strip is decoded once.
_GDAL_ENV = {"GDAL_CACHEMAX": "2048", "GDAL_SWATH_SIZE": "1073741824"}


def sources(scenario: str, root: Optional[Path] = None) -> list[Path]:
    """The regional rasters of one scenario, in region-number order."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario!r}, expected one of {SCENARIOS}")
    src_dir = (root or paths.RUNOUT_ALARM) / scenario
    hits = sorted(src_dir.glob("*.tif"))
    if not hits:
        raise FileNotFoundError(f"No .tif in {src_dir}")
    return hits


def _warn_stubs(srcs: Sequence[Path]) -> None:
    """Flag regions far smaller than the rest.

    A few of the delivered files are 16 x 16 km crops sitting where a whole
    region should be. They mosaic without complaint and leave a
    region-shaped hole, so say so before it costs an hour of compute.
    """
    areas = []
    for s in srcs:
        ds = gdal.Open(str(s))
        areas.append((ds.RasterXSize * ds.RasterYSize, s))
        ds = None
    median = sorted(a for a, _ in areas)[len(areas) // 2]
    for px, s in areas:
        if px < median / 10:
            print(f"  ! {s.name}: {px / 1e6:.1f} Mpx against a median of "
                  f"{median / 1e6:.0f} - looks like a partial run")


def _warp_to_grid(src: Path, out_path: Path, grid: tuple) -> Path:
    """One region, virtually resampled onto the national 10 m grid.

    A warped VRT, so this costs a few kB and no pixels move until something
    reads through it. Doing it per source before the merge - rather than
    merging at 5 m and downsampling after - is the same answer, because max
    is associative, but a quarter of the pixels go through the one stage
    that actually writes.

    -r max for the reason in the module docstring. Declaring the nodata on
    both sides keeps it out of the kernel: gdalwarp excludes source nodata,
    so a 10 m cell straddling the edge of a region takes the max of the
    real 5 m pixels inside it and ignores the void, rather than letting
    -9999 count as a candidate.
    """
    gdal.Warp(
        str(out_path), str(src),
        format="VRT",
        dstSRS=f"EPSG:{config.CRS_EPSG}",
        xRes=config.PIXEL_SIZE, yRes=config.PIXEL_SIZE,
        outputBounds=grid,
        resampleAlg="max",
        srcNodata=NODATA, dstNodata=NODATA,
        outputType=gdal.GDT_Float32,
    )
    return out_path


def _bands_vrt(srcs: Sequence[Path], out_path: Path, *,
               pixel: float, bounds: Optional[tuple] = None) -> Path:
    """The sources stacked one band each on a shared lattice.

    -separate rather than a mosaic because the max below needs every region
    as its own band. Source paths are written relative to the VRT, as in
    rasters.build_vrt, so the set can be moved together.

    Setting both source and VRT nodata is what makes the stack safe to take
    a max over: each band then reads -9999 wherever its region does not
    reach, instead of the 0 an uninitialized VRT band hands back.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = os.getcwd()
    try:
        os.chdir(out_path.parent)
        gdal.BuildVRT(
            out_path.name,
            [os.path.relpath(s, out_path.parent) for s in srcs],
            separate=True,
            xRes=pixel, yRes=pixel,
            outputBounds=bounds,
            srcNodata=NODATA, VRTNodata=NODATA,
        )
    finally:
        os.chdir(cwd)
    return out_path


def _max_vrt(bands: Path, out_path: Path) -> Path:
    """One band holding the per-pixel max over every band of `bands`.

    GDAL has no max mosaic, but a derived band does. Every source here
    covers the whole extent - that is what _bands_vrt bought - so the pixel
    function sees a real value or -9999 from each region, never the
    zero-fill a partly-covering derived source would hand it.
    """
    ds = gdal.Open(str(bands))
    w, h, n = ds.RasterXSize, ds.RasterYSize, ds.RasterCount
    gt, wkt = ds.GetGeoTransform(), ds.GetProjection()
    ds = None

    src = "".join(f"""
    <SimpleSource>
      <SourceFilename relativeToVRT="1">{escape(bands.name)}</SourceFilename>
      <SourceBand>{i}</SourceBand>
      <SrcRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>
      <DstRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>
    </SimpleSource>""" for i in range(1, n + 1))

    out_path.write_text(
        f"""<VRTDataset rasterXSize="{w}" rasterYSize="{h}">
  <SRS>{escape(wkt)}</SRS>
  <GeoTransform>{", ".join(repr(v) for v in gt)}</GeoTransform>
  <VRTRasterBand dataType="Float32" band="1" subClass="VRTDerivedRasterBand">
    <Description>peak flow thickness (m), max over regions</Description>
    <NoDataValue>{NODATA:g}</NoDataValue>
    <PixelFunctionType>max</PixelFunctionType>
    <SourceTransferType>Float32</SourceTransferType>{src}
  </VRTRasterBand>
</VRTDataset>
""",
        encoding="utf-8",
    )
    return out_path


def _byte_vrt(merged: Path, out_path: Path) -> Path:
    """The Float32 merge seen as UInt8 decimetres, nodata 255.

    A ComplexSource does both halves in one read, which is why this is a
    view and not a second pass over 58 Gpixel:

    <NODATA> makes the source's -9999 pixels *skipped* rather than scaled,
    so the band's own init value - 255 - stays put and lands nodata at the
    top of the range instead of the bottom, where it would collide with a
    real 0.

    <LUT> rather than <ScaleRatio>, because a ratio has no ceiling below
    the data type's: at 10 units/m a 52 m flow scales to 520, saturates at
    255 and reads back as *nodata*, turning the deepest pixels in the
    country into holes. A LUT clamps to its last entry instead, so
    everything past 25.4 m parks on 254 and stays data.
    """
    ds = gdal.Open(str(merged))
    w, h = ds.RasterXSize, ds.RasterYSize
    gt, wkt = ds.GetGeoTransform(), ds.GetProjection()
    ds = None

    out_path.write_text(
        f"""<VRTDataset rasterXSize="{w}" rasterYSize="{h}">
  <SRS>{escape(wkt)}</SRS>
  <GeoTransform>{", ".join(repr(v) for v in gt)}</GeoTransform>
  <VRTRasterBand dataType="Byte" band="1">
    <Description>peak flow thickness, decimetres (metres = value / 10)</Description>
    <NoDataValue>{BYTE_NODATA}</NoDataValue>
    <ComplexSource>
      <SourceFilename relativeToVRT="1">{escape(merged.name)}</SourceFilename>
      <SourceBand>1</SourceBand>
      <SrcRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>
      <DstRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>
      <NODATA>{NODATA:g}</NODATA>
      <LUT>0:0,{BYTE_MAX * STEP:g}:{BYTE_MAX}</LUT>
    </ComplexSource>
  </VRTRasterBand>
</VRTDataset>
""",
        encoding="utf-8",
    )
    return out_path


def build(scenario: str, out_dir: Optional[Path] = None, *,
          root: Optional[Path] = None, native: bool = False,
          vrt_only: bool = False) -> Path:
    """Merge one scenario into runout_<scenario>.tif beside its A/ and D/.

    By default the result is 10 m on config.RASTER_ORIGIN's lattice, over
    the bounding box of the 23 regions rather than of Norway - the same
    lattice as every national layer, so it crops against them exactly,
    without carrying 4.7 Gpx of sea and Sweden it has nothing to say about.
    derived.align_vrt gives a national-extent view for free when one is
    wanted.

    It stays beside A/ and D/ rather than moving into national/ because it
    is not wired into paths.SOURCES - point that at this file when you want
    the tiler to use it.

    `native` keeps the delivered 5 m lattice instead. Four times the pixels
    and it lines up with nothing else in the project, but it is the
    faithful merge, which is what you want if the question is about the
    ALARM data rather than about routing.

    `vrt_only` stops at the virtual mosaic: seconds instead of hours, and
    runout_<scenario>.vrt reads as one finished UInt8 raster - but it is
    then the visible tip of ~26 chained files that only work in place,
    next to the 23 they ultimately point at.
    """
    root = root or paths.RUNOUT_ALARM
    out_dir = out_dir or root
    srcs = sources(scenario, root)
    print(f"{scenario}: {len(srcs)} regions")
    _warn_stubs(srcs)

    tmps: list[Path] = []
    if native:
        pixel, grid = SOURCE_PIXEL, None
    else:
        pixel = config.PIXEL_SIZE
        boxes = [rasters._bounds(s) for s in srcs]
        grid = rasters._snap_bounds(
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )
        print(f"  warping onto the national lattice, {pixel:g} m, "
              f"x {grid[0]:.0f}..{grid[2]:.0f} y {grid[1]:.0f}..{grid[3]:.0f} "
              f"(offset {grid[0] % pixel:g}, {grid[1] % pixel:g})")
        warped = []
        for i, s in enumerate(srcs):
            w = out_dir / f"runout_{scenario}.warp{i:02d}.vrt"
            warped.append(_warp_to_grid(s, w, grid))
        tmps += warped
        srcs = warped

    # bands -> max (Float32, -9999) -> byte (UInt8, 255). Three stages
    # because the max has to run before the cast, not after.
    bands = out_dir / f"runout_{scenario}.bands.vrt"
    merged = out_dir / f"runout_{scenario}.max.vrt"
    byte = out_dir / f"runout_{scenario}.vrt"
    _bands_vrt(srcs, bands, pixel=pixel, bounds=grid)
    _max_vrt(bands, merged)
    _byte_vrt(merged, byte)
    tmps += [bands, merged]

    ds = gdal.Open(str(byte))
    print(f"  {ds.RasterXSize} x {ds.RasterYSize} px at {pixel:g} m, "
          f"UInt8 {STEP:g} m/step to {BYTE_MAX * STEP:g} m -> {byte.name}")
    ds = None

    if vrt_only:
        return byte

    tmps.append(byte)
    out_path = out_dir / f"runout_{scenario}.tif"
    saved = {k: os.environ.get(k) for k in _GDAL_ENV}
    os.environ.update(_GDAL_ENV)
    try:
        # NEAREST overviews. MAX would be the honest resampler for a layer
        # that is thin filaments over mostly zero - averaging fades exactly
        # the pixels anyone opens the file to find, and here it would also
        # average the 255s and invent thickness out of nodata - but GDAL
        # 3.13 does not offer MIN/MAX/MED, in the COG driver or in gdaladdo.
        # Of what is left, NEAREST at least reports a thickness that is
        # really at that spot; it just subsamples, so a runout track thinner
        # than the zoom step can blink out. Zoom in before believing an
        # empty slope.
        rasters.to_cog(byte, out_path, compress="DEFLATE", resampling="NEAREST")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for tmp in tmps:
            tmp.unlink(missing_ok=True)
    return out_path


def build_all(only: Optional[Sequence[str]] = None, *,
              native: bool = False, vrt_only: bool = False) -> list[Path]:
    return [build(s, native=native, vrt_only=vrt_only) for s in (only or SCENARIOS)]
