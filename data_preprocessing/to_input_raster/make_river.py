from pathlib import Path

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.to_raster import (
    RasterizeSpec,
    make_template_raster_for_area,
    rasterize_vector_to_template,
)
from data_preprocessing.utils.iter_areas import iter_areas


def main() -> None:
    cfg = load_config()

    for area in iter_areas(cfg.study_areas, cfg.crs_epsg):
        print(f"\n=== River for {area.area_id} ===")

        area_where = f"area_id = '{area.area_id}'"

        area_dir = cfg.areas_root / area.area_id
        area_cache_dir = cfg.areas_cache_root / area.area_id
        template = area_cache_dir / "template.tif"

        make_template_raster_for_area(
            area_polygon_gpkg=cfg.study_areas,
            area_where=area_where,
            out_template=template,
            crs_epsg=cfg.crs_epsg,
            pixel_size=cfg.pixel_size,
            nodata=cfg.nodata,
        )

        water_vec = cfg.regions_root / area.region / "clean" / "water.gpkg"

        # Filter only rivers (and only wide enough)
        where_filter = "objtype = 'Elv' AND vannbredde >= 2"

        spec = RasterizeSpec(
            src_vector=water_vec,
            src_layer="water",
            where=where_filter,   # <-- key change: filter here, no pre-processing
            burn_value=1,
            dtype="Byte",
            nodata=0,
            init=0,
            out_name="river.tif",
        )

        out = area_dir / "input" / spec.out_name

        rasterize_vector_to_template(
            spec=spec,
            template=template,
            out_raster=out,
            crs_epsg=cfg.crs_epsg,
        )

        print("Wrote:", out)


if __name__ == "__main__":
    main()
