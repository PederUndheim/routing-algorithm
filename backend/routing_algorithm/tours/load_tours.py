from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import json

Coord = Tuple[float, float]

@dataclass(frozen=True)
class Tour:
    name: str
    start: Coord
    end: Coord

def load_tours_json(path: Path) -> Dict[str, List[Tour]]:
    data = json.loads(path.read_text())
    areas = data.get("areas", {})

    out: Dict[str, List[Tour]] = {}

    for area_id, tours in areas.items():
        out[area_id] = [
            Tour(
                name=str(t["name"]),
                start=(float(t["start"][0]), float(t["start"][1])),
                end=(float(t["end"][0]), float(t["end"][1])),
            )
            for t in tours
        ]

    return out
