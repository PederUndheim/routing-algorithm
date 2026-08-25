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


def _feature_count(gpkg: Path, layer_name: str) -> int:
    ogrinfo = shutil.which("ogrinfo")
    if not ogrinfo:
        raise RuntimeError("ogrinfo not found. Install gdal with: brew install gdal")

    p = subprocess.run(
        [ogrinfo, "-so", str(gpkg), layer_name],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in p.stdout.splitlines():
        if line.strip().startswith("Feature Count:"):
            return int(line.split(":", 1)[1].strip())
    return 0


def _ogr2ogr_clip_to_gpkg(
    src: Path,
    dst: Path,
    *,
    layer: str,
    clip: Path,
    nln: str,
    append: bool,
    t_srs: str = TARGET_SRS,
) -> None:
    ogr2ogr = shutil.which("ogr2ogr")
    if not ogr2ogr:
        raise RuntimeError("ogr2ogr not found. Install gdal with: brew install gdal")

    cmd: list[str] = [ogr2ogr, "-f", "GPKG"]
    if append:
        cmd += ["-append"]

    cmd += [
        str(dst),
        str(src),
        layer,
        "-t_srs", t_srs,
        "-clipsrc", str(clip),
        "-nlt", "PROMOTE_TO_MULTI",
        "-skipfailures",
        "-nln", nln,
    ]
    _run(cmd)


def clip_merge_sources_to_region(
    *,
    region_dir: Path,
    sources: list[Path],
    source_layer: str,
    out_gpkg_name: str,
    out_layer_name: str,
    target_srs: str = TARGET_SRS,
    tmp_dirname: str,
) -> Path:
    rp = RegionPaths(
        region_dir=region_dir,
        clip_area=region_dir / "clip" / "download_area.gpkg",
        clean_dir=region_dir / "clean",
    )

    if not rp.clip_area.exists():
        raise FileNotFoundError(f"Missing clip area: {rp.clip_area}")

    rp.clean_dir.mkdir(parents=True, exist_ok=True)
    out = rp.clean_dir / out_gpkg_name
    if out.exists():
        out.unlink()

    if not sources:
        raise FileNotFoundError("No sources provided")

    tmp_dir = rp.clean_dir / tmp_dirname
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    wrote_any = False
    used = 0

    try:
        for i, src in enumerate(sources):
            tmp = tmp_dir / f"tmp_{i}.gpkg"

            # Clip + reproject into tmp
            _ogr2ogr_clip_to_gpkg(
                src=src,
                dst=tmp,
                layer=source_layer,
                clip=rp.clip_area,
                nln=out_layer_name,
                append=False,
                t_srs=target_srs,
            )

            cnt = _feature_count(tmp, out_layer_name)
            if cnt == 0:
                tmp.unlink(missing_ok=True)
                continue

            used += 1
            print(f"  + using {src.name} (features after clip: {cnt})")

            if not wrote_any:
                shutil.move(str(tmp), str(out))
                wrote_any = True
            else:
                # Append from tmp gpkg into final
                _ogr2ogr_clip_to_gpkg(
                    src=tmp,
                    dst=out,
                    layer=out_layer_name,  # layer inside tmp gpkg
                    clip=rp.clip_area,     # harmless, already clipped
                    nln=out_layer_name,
                    append=True,
                    t_srs=target_srs,
                )
                tmp.unlink(missing_ok=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"{region_dir.name}: used {used} / {len(sources)} sources")

    if not wrote_any:
        raise RuntimeError(f"No features found inside clip for region: {region_dir.name}")

    print("Wrote:", out)
    return out
