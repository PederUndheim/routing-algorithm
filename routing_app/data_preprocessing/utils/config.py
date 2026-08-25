from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    repo_root: Path

    # Roots
    areas_root: Path           
    dp_root: Path     
    cache_root: Path
    areas_cache_root: Path              
    regions_root: Path       
    national_root: Path         
    outlines_root: Path          

    # Outlines
    study_areas: Path             # study_areas.gpkg
    download_areas: Path          # download_areas.gpkg

    # Raster / area products (if you use them)
    to_input_raster_root: Path    # <repo>/data_preprocessing/to_input_raster

    # Defaults
    crs_epsg: int = 25833
    pixel_size: float = 10.0
    nodata: float = -9999.0

    @property
    def crs(self) -> str:
        return f"EPSG:{self.crs_epsg}"


def load_config() -> Config:
    # config.py is in <repo>/data_preprocessing/utils/config.py
    repo_root = Path(__file__).resolve().parents[2]
    dp_root = repo_root / "data_preprocessing"
    cache_root = dp_root / "data_cache"
    outlines_root = cache_root / "outlines"

    return Config(
        repo_root=repo_root,
        areas_root=repo_root / "data" / "areas",
        dp_root=dp_root,
        cache_root=cache_root,
        areas_cache_root=cache_root / "areas",
        regions_root=cache_root / "regions",
        national_root=cache_root / "national",
        outlines_root=outlines_root,
        study_areas=outlines_root / "study_areas.gpkg",
        download_areas=outlines_root / "download_areas.gpkg",
        to_input_raster_root=dp_root / "to_input_raster",
    )
