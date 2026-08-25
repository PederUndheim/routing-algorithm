"""Where everything lives on disk.

data/national/  is provided by you (see data/national/README.md).
data/derived, data/grid, data/tiles, data/output  are generated.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

NATIONAL = DATA / "national"      # sources you provide
DERIVED = DATA / "derived"        # national layers computed from them
GRID_DIR = DATA / "grid"
TILES = DATA / "tiles"
OUTPUT = DATA / "output"
DEBUG = DATA / "debug"
TOURS_DIR = DATA / "tours"
TOURS = TOURS_DIR / "tours.gpkg"   # hand-digitized start/end pairs; not reproducible
ROUTES = DATA / "routes"           # routed lines and corridors, one folder per tour

# Exposure output. Separate from data/routes so the routing stage owns one
# directory and the scoring stage another: re-scoring never touches what took
# hours to route, and deleting these costs nothing but a re-run.
CORRIDORS = DATA / "corridors"
CORRIDORS_COLORED = CORRIDORS / "corridors_colored"


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
        candidate = OUTPUT / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No national surface in {OUTPUT}. Build one with "
        "'python -m skimap.cli mosaic --cog'."
    )


def debug_layer(label: str, name: str) -> Path:
    """One component of a cost surface, under a readable label.

    `label` is a study area name where there is one, otherwise the tile id.
    These sit together in data/debug/ rather than inside each tile folder
    because you come looking for them by place, not by coordinate - and
    1334 folders named after their south-west corner in metres is not
    somewhere anyone can navigate.

    Written only when 'cost --debug' asks for it: they are Float32 and there
    are nine, so a national run with debug on would dwarf the surface.
    """
    return DEBUG / label / f"{name}.tif"
