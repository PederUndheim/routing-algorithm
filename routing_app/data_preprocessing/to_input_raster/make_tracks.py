from __future__ import annotations

from pathlib import Path

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.iter_areas import iter_areas
from data_preprocessing.utils.to_raster import make_template_raster_for_area
from data_preprocessing.utils.resample_raster_to_reference import resample_raster_to_reference


def _tracks_raster_for_region(cfg, region: str) -> Path:
    p = cfg.national_root / "tracks" / f"tracks_{region}.tif"
    if not p.exists():
        raise FileNotFoundError(f"Missing tracks raster for region {region}: {p}")
    return p


def main() -> None:
    cfg = load_config()

    for area in iter_areas(cfg.study_areas, cfg.crs_epsg):
        print(f"\n=== Tracks for {area.area_id} ({area.region}) ===")

        area_where = f"area_id = '{area.area_id}'"

        area_dir = cfg.areas_root / area.area_id
        area_cache_dir = cfg.areas_cache_root / area.area_id
        template = area_cache_dir / "template.tif"
        out = area_dir / "input" / "tracks.tif"

        make_template_raster_for_area(
            area_polygon_gpkg=cfg.study_areas,
            area_where=area_where,
            out_template=template,
            crs_epsg=cfg.crs_epsg,
            pixel_size=cfg.pixel_size,
            nodata=cfg.nodata,
        )

        src_tracks = _tracks_raster_for_region(cfg, area.region)

        resample_raster_to_reference(
            src_path=src_tracks,
            ref_path=template,
            dst_path=out,
            resampling="bilinear",
            dst_nodata=cfg.nodata,
            dst_dtype="float32",
        )

        print("Wrote:", out)


if __name__ == "__main__":
    main()
