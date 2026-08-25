"""The national tile grid: a regular fishnet, and iteration over it.

Tile ids encode the south-west corner in metres (tile_-35500_6699500), so
regenerating the grid yields identical ids and extending coverage never
renumbers an existing tile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Sequence

import geopandas as gpd
from shapely.geometry import box

from skimap import config, paths

_TOL = 1e-6  # metres; below this is float noise, not a real offset


def tile_id(x0: float, y0: float) -> str:
    return f"tile_{int(round(x0))}_{int(round(y0))}"


@dataclass(frozen=True)
class Tile:
    tile_id: str
    x0: float
    y0: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x0 + config.TILE_SIZE, self.y0 + config.TILE_SIZE)


def lattice_origin(reference: Path, *, layer: Optional[str] = None) -> tuple[float, float]:
    """Lattice offset of an existing grid, for config.GRID_ORIGIN.

    Raises if the reference is not one regular lattice of config.TILE_SIZE -
    aligning to an irregular or overlapping tile layout is meaningless.
    """
    ref = gpd.read_file(reference, layer=layer)
    if ref.empty:
        raise ValueError(f"Reference grid is empty: {reference}")

    b = ref.bounds
    sizes = set((b.maxx - b.minx).round(3)) | set((b.maxy - b.miny).round(3))
    if sizes != {config.TILE_SIZE}:
        raise ValueError(f"Reference cells are {sorted(sizes)[:5]} m, expected {config.TILE_SIZE:g} m")

    offsets_x = set((b.minx % config.TILE_SIZE).round(3))
    offsets_y = set((b.miny % config.TILE_SIZE).round(3))
    if len(offsets_x) != 1 or len(offsets_y) != 1:
        raise ValueError(f"Reference sits on several offsets (x {offsets_x}, y {offsets_y}); it is not one lattice")

    return offsets_x.pop(), offsets_y.pop()


def _snap_down(value: float, origin: float) -> float:
    """Largest lattice coordinate <= value."""
    return origin + math.floor((value - origin) / config.TILE_SIZE + _TOL) * config.TILE_SIZE


def build_grid(
    boundary: Path,
    *,
    boundary_layer: Optional[str] = None,
    origin: tuple[float, float] = config.GRID_ORIGIN,
    out_path: Path = paths.TILE_GRID,
) -> Path:
    """Write a fishnet clipped to `boundary`, one cell per tile.

    Cells land on origin + k * TILE_SIZE. Cells that only touch the boundary
    edge-on, with nothing inside, are dropped.
    """
    bnd = gpd.read_file(boundary, layer=boundary_layer).to_crs(config.CRS_EPSG)
    bnd = bnd[bnd.geom_type.isin(["Polygon", "MultiPolygon"])][["geometry"]]
    if bnd.empty:
        raise ValueError(
            f"No polygons in {boundary}. Mixed SOSI exports carry the boundary "
            "LINESTRINGs too; the fishnet needs the areal features."
        )
    bnd["geometry"] = bnd.geometry.make_valid()

    minx, miny, maxx, maxy = bnd.total_bounds
    start_x, start_y = _snap_down(minx, origin[0]), _snap_down(miny, origin[1])
    n_cols = math.ceil((maxx - start_x) / config.TILE_SIZE - _TOL)
    n_rows = math.ceil((maxy - start_y) / config.TILE_SIZE - _TOL)

    corners = [
        (start_x + c * config.TILE_SIZE, start_y + r * config.TILE_SIZE)
        for c in range(n_cols)
        for r in range(n_rows)
    ]
    cells = gpd.GeoDataFrame(
        {
            "tile_id": [tile_id(x, y) for x, y in corners],
            "x0": [x for x, _ in corners],
            "y0": [y for _, y in corners],
        },
        geometry=[box(x, y, x + config.TILE_SIZE, y + config.TILE_SIZE) for x, y in corners],
        crs=config.CRS_EPSG,
    )
    print(f"Candidate lattice: {n_cols} x {n_rows} = {len(cells)} cells of {config.TILE_SIZE:g} m")

    # Spatial join, not one giant union: same answer, uses an index.
    cells = cells.loc[sorted(set(gpd.sjoin(cells, bnd, predicate="intersects").index))].copy()

    # Boundary parts do not overlap, so summing per-cell intersections is exact.
    hit = gpd.overlay(cells[["tile_id", "geometry"]], bnd, how="intersection", keep_geom_type=True)
    cells["area_km2"] = cells.tile_id.map((hit.area / 1e6).groupby(hit.tile_id).sum()).fillna(0.0).round(4)

    dropped = int((cells.area_km2 <= 0.0).sum())
    if dropped:
        print(f"Dropping {dropped} cells that only touch the boundary edge-on")
        cells = cells[cells.area_km2 > 0.0]
    if cells.empty:
        raise RuntimeError("Fishnet produced no cells intersecting the boundary")

    cells = cells.sort_values(["x0", "y0"], ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cells.to_file(out_path, layer=paths.TILE_GRID_LAYER, driver="GPKG")
    print(f"Wrote {len(cells)} tiles -> {out_path}")
    return out_path


def iter_tiles(grid_path: Path = paths.TILE_GRID, *, only: Optional[Sequence[str]] = None) -> Iterator[Tile]:
    """Yield tiles from the grid, optionally filtered to specific ids."""
    gdf = gpd.read_file(grid_path, layer=paths.TILE_GRID_LAYER)
    if only is not None:
        wanted = set(only)
        missing = wanted - set(gdf.tile_id)
        if missing:
            raise KeyError(f"Not in the grid: {sorted(missing)}")
        gdf = gdf[gdf.tile_id.isin(wanted)]

    for row in gdf.itertuples(index=False):
        yield Tile(tile_id=row.tile_id, x0=float(row.x0), y0=float(row.y0))
