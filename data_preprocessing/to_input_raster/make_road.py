from __future__ import annotations

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.to_raster import (
    RasterizeSpec,
    make_template_raster_for_area,
    rasterize_vector_to_template,
)
from data_preprocessing.utils.iter_areas import iter_areas


def main() -> None:
    cfg = load_config()

    for area in iter_areas(cfg.study_areas, crs_epsg=cfg.crs_epsg):
        area_id = area.area_id
        region = area.region

        area_where = f"area_id = '{area_id}'"

        area_dir = cfg.areas_root / area_id
        area_cache_dir = cfg.areas_cache_root / area_id
        template = area_cache_dir / "template.tif"

        # 1) Ensure template exists for this area
        if not template.exists():
            make_template_raster_for_area(
                area_polygon_gpkg=cfg.study_areas,
                area_where=area_where,
                out_template=template,
                crs_epsg=cfg.crs_epsg,
                pixel_size=cfg.pixel_size,
                nodata=cfg.nodata,
            )

        # 2) Pick correct roads vector for this area's region
        roads_vec = cfg.regions_root / region / "clean" / "road.gpkg"
        if not roads_vec.exists():
            print(f"Skipping {area_id}: missing {roads_vec}")
            continue

        # 3) Rasterize
        spec = RasterizeSpec(
            src_vector=roads_vec,
            src_layer="roads",
            burn_value=1,
            dtype="Byte",
            nodata=0,
            init=0,
            out_name="road.tif",
        )

        out = area_dir / "input" / spec.out_name
        rasterize_vector_to_template(
            spec=spec,
            template=template,
            out_raster=out,
            crs_epsg=cfg.crs_epsg,
        )

        print(f"OK: {area_id} ({region}) -> {out}")


if __name__ == "__main__":
    main()
