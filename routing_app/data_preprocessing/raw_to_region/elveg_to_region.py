from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import shutil

TARGET_SRS = "EPSG:25833"


@dataclass(frozen=True)
class RegionPaths:
    region_dir: Path
    clip_area: Path
    clean_dir: Path


def _run(cmd: list[str]) -> None:
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _layer_name_from_shp(shp: Path) -> str:
    return shp.stem  # shapefile layer name is the filename stem

def _ogr2ogr_clip_merge_files_to_gpkg(
    sources: list[Path],
    dst: Path,
    clip: Path,
    t_srs: str = TARGET_SRS,
) -> None:
    ogr2ogr = shutil.which("ogr2ogr")
    if not ogr2ogr:
        raise RuntimeError("ogr2ogr not found. Install gdal with: brew install gdal")

    if not sources:
        raise FileNotFoundError("No sources provided")

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()

    first, rest = sources[0], sources[1:]

    def cmd_for(src: Path, append: bool) -> list[str]:
        layer = _layer_name_from_shp(src)

        sql = f"SELECT geometry FROM '{layer}'"

        cmd = [ogr2ogr, "-f", "GPKG"]
        if append:
            cmd += ["-append"]

        cmd += [
            str(dst),
            str(src),
            "-dialect", "SQLITE",
            "-sql", sql,
            "-t_srs", t_srs,
            "-clipsrc", str(clip),
            "-nlt", "PROMOTE_TO_MULTI",
            "-makevalid",
            "-skipfailures",
            "-nln", "roads",
        ]
        return cmd

    _run(cmd_for(first, append=False))
    for src in rest:
        _run(cmd_for(src, append=True))




def ensure_region_elveg_only(
    region_dir: Path,
    national_elveg_dir: Path = Path("data_preprocessing/data_cache/national/forenklet_elveg_norge"),
    pattern: str = "*_Veglenke_KURVE.shp",
    out_name: str = "roads.gpkg",
) -> Path:
    rp = RegionPaths(
        region_dir=region_dir,
        clip_area=region_dir / "clip" / "download_area.gpkg",
        clean_dir=region_dir / "clean",
    )

    if not rp.clip_area.exists():
        raise FileNotFoundError(f"Missing clip area: {rp.clip_area}")
    if not national_elveg_dir.exists():
        raise FileNotFoundError(f"Missing national elveg dir: {national_elveg_dir}")

    rp.clean_dir.mkdir(parents=True, exist_ok=True)

    all_shps = sorted(national_elveg_dir.glob(pattern))
    if not all_shps:
        raise FileNotFoundError(f"No shapefiles matched {pattern} in {national_elveg_dir}")

    print(f"{region_dir.name}: merging {len(all_shps)} road files (no bbox prefilter)")

    out = rp.clean_dir / out_name
    _ogr2ogr_clip_merge_files_to_gpkg(
        sources=all_shps,
        dst=out,
        clip=rp.clip_area,
    )

    print("Wrote:", out)
    return out


def ensure_all_regions_elveg_only(
    regions_root: Path = Path("data_preprocessing/data_cache/regions"),
    national_elveg_dir: Path = Path("data_preprocessing/data_cache/national/forenklet_elveg_norge"),
) -> None:
    region_dirs = sorted([p for p in regions_root.iterdir() if p.is_dir()])

    for region_dir in region_dirs:
        clip = region_dir / "clip" / "download_area.gpkg"
        if not clip.exists():
            print(f"Skipping {region_dir.name}: missing {clip}")
            continue

        ensure_region_elveg_only(
            region_dir=region_dir,
            national_elveg_dir=national_elveg_dir,
            pattern="*_Veglenke_KURVE.shp",
            out_name="roads.gpkg",
        )


if __name__ == "__main__":
    ensure_all_regions_elveg_only()
