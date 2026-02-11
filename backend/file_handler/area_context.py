from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from backend.file_handler.area_paths import AreaPaths
from backend.file_handler.area_inputs import get_input_rasters

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def load_area(area_id: str) -> tuple[AreaPaths, Dict[str, Path]]:
    """
    Load all paths + inputs for a given area 
    """
    paths = AreaPaths(area_id=area_id, project_root=PROJECT_ROOT)
    inputs = get_input_rasters(paths)
    return paths, inputs
