from __future__ import annotations

from pathlib import Path

from data_preprocessing.utils._gdal_clip_merge import clip_merge_sources_to_region

TARGET_SRS = "EPSG:25833"
FKB_VANN_LAYER = "fkb_vann_omrade"

NATIONAL_FKB_VANN_DIR = Path("data_preprocessing/data_cache/national/fkb_vann_fylker")


def ensure_region_fkb_vann(
    region_dir: Path,
    *,
    national_dir: Path = NATIONAL_FKB_VANN_DIR,
) -> Path:
    gdbs = sorted(national_dir.glob("**/*.gdb"))
    if not gdbs:
        raise FileNotFoundError(f"No .gdb found under {national_dir}")

    return clip_merge_sources_to_region(
        region_dir=region_dir,
        sources=gdbs,
        source_layer=FKB_VANN_LAYER,
        out_gpkg_name="water.gpkg",
        out_layer_name="water",
        target_srs=TARGET_SRS,
        tmp_dirname="_tmp_vann",
    )


if __name__ == "__main__":
    regions_root = Path("data_preprocessing/data_cache/regions")

    for region in sorted(regions_root.iterdir()):
        if not region.is_dir():
            continue

        clip = region / "clip" / "download_area.gpkg"
        if not clip.exists():
            continue

        print(f"\n=== Processing {region.name} ===")
        ensure_region_fkb_vann(region)
