from __future__ import annotations
import os, re, glob
import geopandas as gpd
from typing import Dict, List, Optional
from shapely.geometry import LineString
from .geometry import ensure_single_line

MOUNTAIN_KEY_RE = re.compile(r"^([A-Za-z0-9\-]+)_")

def mountain_key_from_filename(path: str) -> Optional[str]:
    m = MOUNTAIN_KEY_RE.match(os.path.basename(path))
    return m.group(1).lower() if m else None

def list_auto_files(auto_dir: str) -> Dict[str, str]:
    out = {}
    for p in glob.glob(os.path.join(auto_dir, "*.geojson")):
        key = mountain_key_from_filename(p)
        if key: out[key] = p
    return out

def list_expert_files(expert_dir: str) -> Dict[str, str]:
    out = {}
    for p in glob.glob(os.path.join(expert_dir, "*.geojson")):
        key = mountain_key_from_filename(p)
        if key: out[key] = p
    return out

def load_expert_variants(path: str, force_crs: Optional[str]) -> List[LineString]:
    gdf = gpd.read_file(path)
    if force_crs: gdf = gdf.to_crs(force_crs)
    variants: List[LineString] = []
    for geom in gdf.geometry:
        if geom is None: continue
        if geom.geom_type == "LineString":
            variants.append(LineString(geom.coords))
        elif geom.geom_type == "MultiLineString":
            variants.extend([LineString(ln.coords) for ln in geom.geoms if ln.geom_type == "LineString"])
    if not variants:
        try: variants.append(ensure_single_line(gdf))
        except Exception: pass
    if not variants:
        raise ValueError(f"No line features in expert file: {path}")
    return variants
