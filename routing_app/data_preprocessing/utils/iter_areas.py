from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

@dataclass(frozen=True)
class AreaRow:
    area_id: str
    region: str
    geometry: BaseGeometry

def iter_areas(
    study_areas_path: Union[str, Path],
    crs_epsg: int,
    region: Optional[str] = None,
    area_ids: Optional[Sequence[str]] = None,
) -> Iterable[AreaRow]:

    gdf = gpd.read_file(study_areas_path)

    for col in ("area_id", "region"):
        if col not in gdf.columns:
            raise ValueError(f"study_areas must contain '{col}'")

    if gdf["area_id"].isna().any():
        raise ValueError("study_areas has NULL area_id values")

    if region is not None:
        gdf = gdf[gdf["region"] == region]

    if area_ids is not None:
        gdf = gdf[gdf["area_id"].isin(area_ids)]

    gdf = gdf.to_crs(crs_epsg)

    for row in gdf.itertuples(index=False):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        yield AreaRow(
            area_id=str(row.area_id),
            region=str(row.region),
            geometry=geom,
        )
