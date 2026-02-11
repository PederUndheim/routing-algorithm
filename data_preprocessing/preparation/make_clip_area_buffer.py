from __future__ import annotations

from pathlib import Path
import geopandas as gpd

from data_preprocessing.utils.config import load_config
from data_preprocessing.preparation.make_download_areas import (
    make_download_areas,
    export_download_area,
)

def main() -> None:
    cfg = load_config()

    download_areas_path = cfg.repo_root / "data_cache" / "download_areas.gpkg"

    out = make_download_areas(
        study_areas_path=cfg.study_areas,
        out_path=download_areas_path,
        buffer_m=2_000,
    )

    # Read the download regions and export one file per region
    regions = gpd.read_file(download_areas_path, layer="download_regions")

    for region in sorted(regions["region"].unique()):
        out_path = cfg.cache_root / region / "clip" / "download_area.gpkg"
        export_download_area(
            download_areas=download_areas_path,
            region=region,
            out_path=out_path,
        )
        print(f"Wrote clip for region: {region} -> {out_path}")

    print("Wrote:", out)

if __name__ == "__main__":
    main()
