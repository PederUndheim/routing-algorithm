from __future__ import annotations

from pathlib import Path

from data_preprocessing.utils._gdal_clip_merge import clip_merge_sources_to_region

TARGET_SRS = "EPSG:25833"
FKB_TRAKTOR_LAYER = "fkb_traktorvegsti_senterlinje"

NATIONAL_FKB_TRAKTOR_DIR = Path("data_preprocessing/data_cache/national/fkb_traktorvegsti_fylker")


def ensure_region_fkb_traktorvegsti(
    region_dir: Path,
    *,
    national_dir: Path = NATIONAL_FKB_TRAKTOR_DIR,
) -> Path:
    gdbs = sorted(national_dir.glob("**/*.gdb"))
    if not gdbs:
        raise FileNotFoundError(f"No .gdb found under {national_dir}")

    return clip_merge_sources_to_region(
        region_dir=region_dir,
        sources=gdbs,
        source_layer=FKB_TRAKTOR_LAYER,
        out_gpkg_name="tractorroads_trails.gpkg",
        out_layer_name="tractorroads_trails",
        target_srs=TARGET_SRS,
        tmp_dirname="_tmp_traktor",
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
        ensure_region_fkb_traktorvegsti(region)
