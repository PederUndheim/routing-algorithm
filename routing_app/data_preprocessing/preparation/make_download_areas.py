from __future__ import annotations

from pathlib import Path
import geopandas as gpd


def make_download_areas(
    study_areas_path: Path,
    out_path: Path,
    buffer_m: float,
    crs_epsg: int = 25833,
) -> Path:
    """
    Create download polygons per region:
      geometry = dissolve(study_areas by region) + buffer
    Writes to GeoPackage.
    """
    gdf = gpd.read_file(study_areas_path).to_crs(crs_epsg)

    required = {"region", "area_id"}
    missing = required - set(gdf.columns)
    if missing:
        raise ValueError(f"Missing fields in study_areas: {missing}")

   # Dissolve by region -> one polygon per region
    regions = gdf.dissolve(by="region", as_index=False)

    # Buffer
    buffered = regions.geometry.buffer(buffer_m)

    # Use bounding box (rectangular extent)
    regions["geometry"] = buffered.envelope

    # Add id field for convenience
    regions["download_id"] = regions["region"].str.lower().str.replace(" ", "_", regex=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    regions.to_file(out_path, layer="download_regions", driver="GPKG")
    return out_path


def export_download_area(
    download_areas: Path,
    region: str,
    out_path: Path,
) -> None:
    gdf = gpd.read_file(download_areas)
    one = gdf[gdf["region"] == region]

    if len(one) != 1:
        raise ValueError(f"Expected exactly one polygon for region={region}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    one.to_file(out_path, driver="GPKG")
