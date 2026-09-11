"""Where everything lives on disk.

data/input/national/  is provided by you (see its README.md).
data/input/derived, data/grid, data/cost_surface  are generated.
data/test/  holds the throwaway output of comparison runs.

The data root sits beside the package, not inside it, so ROOT climbs out of
skimap/skimap/ to skimap/. Anything that resolves a path relative to this
file has to account for that - the package is one level down from the
project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent   # the project dir, not the package
DATA = ROOT / "data"

# Sources you provide and the layers computed from them, both under input/.
# Everything else at the data root is generated.
INPUT = DATA / "input"
NATIONAL = INPUT / "national"     # sources you provide
DERIVED = INPUT / "derived"       # national layers computed from them

# The ALARM avalanche simulations: 23 regional rasters per scenario in A/
# and D/, plus the runout_A.tif and runout_D.tif that
# data_preprocessing.runout_alarm merges them into.
#
# Outside national/ because the delivered rasters are 5 m, off the lattice
# everything in there shares. The merged files are not - they come out at
# PIXEL_SIZE on RASTER_ORIGIN's lattice, so they are already eligible to be
# a national layer. They are not wired into SOURCES yet; point SOURCES
# ["runout"] here to route on ALARM instead of the Flow-Py runout.
RUNOUT_ALARM = INPUT / "runout_ALARM"
GRID_DIR = DATA / "grid"

# Where a study area's ridge build lands, so a threshold can be judged on
# ground you know before it is committed to the national layer. Scratch you
# can delete - each area is one cheap pass over the national windshelter.
#
# Outside derived/ because an area is not a national layer; the national one
# is a single streamed pass and paths.derived("exposed_ridge") is where it
# goes. (The old geomorphon build also kept tiles/ here, resumable across an
# overnight run. A per-cell threshold needs no tiling, so that is gone.)
RIDGES = DATA / "ridges"
RIDGE_AREAS = RIDGES / "areas"
RIDGE_AREAS_FILE = RIDGES / "areas.json"   # your own areas; overrides the built-in ones

# The cost surface and everything that is only an ingredient of it: the
# per-tile builds, the national mosaic, the colour ramp, the debug
# components. One directory, because none of it is meaningful without the
# rest and all of it is rebuilt by the same command.
COST_SURFACE = DATA / "cost_surface"
TILES = COST_SURFACE / "tiles"
DEBUG = COST_SURFACE / "debug"

# ArcGIS layer files, saved out of Pro. Read by skimap.lyrx so a figure is
# painted with the symbology you already have on screen; nothing writes them.
STYLES = DATA / "styles_arcgis"
COST_STYLE = STYLES / "cost_surface.tif.lyrx"

TOURS_DIR = DATA / "tours"
TOURS = TOURS_DIR / "tours.gpkg"   # hand-digitized start/end pairs; not reproducible

# Routing output: the routed lines, the per-tour corridors, and the merged
# corridors_all.tif built from them. All of it is rebuilt by `route`.
ROUTES = DATA / "routing_output"

# Exposure output, and *only* the exposure output: four rasters, one per
# class. Separate from routing_output so the routing stage owns one
# directory and the scoring stage another - re-scoring never touches what
# took hours to route, and deleting these costs nothing but a re-run.
#
# Nothing is copied in from routing_output. That means this directory does
# not stand alone: the colours here are only interpretable against the
# routes that produced them, so re-routing without re-scoring leaves the two
# disagreeing. That is the trade for keeping it to four files.
COLORED_CORRIDORS = DATA / "colored_corridors"

# Hand-divided corridors, one directory per area you draw over, named after
# the outline that defines it. Holds both what you draw into and what comes
# out, because the two are only meaningful together: the rasters are the
# drawing applied to the corridors of the day, and re-routing invalidates
# them exactly as it does COLORED_CORRIDORS.
SEGMENTS = DATA / "segments"


def segments(area: str) -> Path:
    """Where one area's templates and split rasters live."""
    return SEGMENTS / area


def derived(layer: str) -> Path:
    return DERIVED / f"{layer}.tif"


def source(theme: str) -> Path:
    """The single file in a national source directory."""
    hits = sorted(p for p in SOURCES[theme].iterdir() if p.suffix in (".tif", ".gpkg", ".geojson"))
    if not hits:
        raise FileNotFoundError(f"No dataset in {SOURCES[theme]}")
    return hits[0]

TILE_GRID = GRID_DIR / "tile_grid.gpkg"
TILE_GRID_LAYER = "tiles"

TRACK_SCALE = GRID_DIR / "track_scale.json"   # national track normalization, computed once

# National source directories. Contents are discovered by spatial
# intersection, so the number of files in each and how they are tiled does
# not matter - only which directory they sit in.
SOURCES = {
    "boundary": NATIONAL / "boundary",
    "dem": NATIONAL / "dem",
    "pra": NATIONAL / "pra",
    "forest": NATIONAL / "forest",
    "windshelter": NATIONAL / "windshelter",
    "runout": NATIONAL / "runout",
    "tracks": NATIONAL / "tracks",
    "roads": NATIONAL / "roads",
    "water": NATIONAL / "water",
    "tractor_trails": NATIONAL / "tractor_trails",
}


def layer(name: str) -> Path:
    """Resolve a layer name to its national raster.

    Derived layers win over sources of the same name; both are national and
    on one grid, so nothing downstream needs to know which a layer is.
    """
    p = derived(name)
    if p.exists():
        return p
    if name in SOURCES:
        return source(name)
    raise FileNotFoundError(
        f"No layer {name!r}. Build it with 'python -m skimap.data_preprocessing.cli derived'."
    )


def cost_surface(tile_id: str) -> Path:
    """The one per-tile output. Everything else is read from national layers."""
    return TILES / tile_id / "cost_surface.tif"


def national_surface() -> Path:
    """The finished national surface: the COG if it exists, else the VRT.

    The COG is preferred because it carries overviews and opens anywhere; the
    VRT is the fallback for when only `mosaic` has been run, not `--cog`.
    """
    for name in ("cost_surface.tif", "cost_surface.vrt"):
        candidate = COST_SURFACE / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No national surface in {COST_SURFACE}. Build one with "
        "'python -m skimap.cli mosaic --cog'."
    )


def debug_layer(label: str, name: str, *, root: Optional[Path] = None) -> Path:
    """One component of a cost surface, under a readable label.

    `label` is a study area name where there is one, otherwise the tile id.
    These sit together in data/cost_surface/debug/ rather than inside each tile folder
    because you come looking for them by place, not by coordinate - and
    1334 folders named after their south-west corner in metres is not
    somewhere anyone can navigate.

    Written only when 'cost --debug' asks for it: they are Float32 and there
    are nine, so a national run with debug on would dwarf the surface.
    """
    return (root or DEBUG) / label / f"{name}.tif"
