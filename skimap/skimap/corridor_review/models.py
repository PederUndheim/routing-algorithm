"""The model set under review, and where each one's output already lives.

A model is a name and two directories: the routes.gpkg it produced and the
corridors beside it. Nothing here builds anything. Routing 842 tours against
a surface is the better part of a day (see skimap.track_variants), so a
review that rebuilt its models would be a multi-day tool rather than a
minutes-long one, and every round would re-do work already on disk.

That is the whole reason the config names paths instead of profiles: the
builds exist, and pointing at them is free. To review a model you do not
have yet, build it first - `skimap.lab` for a tour subset, or
`skimap.track_variants` for the country - then add it here.

Paths are relative to data/, so the config stays portable between machines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from skimap import paths

CONFIG = paths.DATA / "review" / "config.json"

# What `init` writes. These four are the national builds that exist in this
# repo today; the first three are the round-one set. Order is the order the
# panels appear in, left to right, so it is worth keeping production first -
# it is the one every other panel is implicitly compared against.
DEFAULT_MODELS = [
    {
        "name": "baseline",
        "label": "Production 3.0 / 3.0",
        "routes": "routing_output/routes.gpkg",
        "corridors": "routing_output/corridors",
    },
    {
        "name": "no_tracks",
        "label": "No track data",
        "routes": "test/track_reduction_test/routes.gpkg",
        "corridors": "test/track_reduction_test/corridors",
    },
    {
        "name": "forest_1_2",
        "label": "1.0 open / 2.0 forest",
        "routes": "test/track_variants/forest_1_2/routes.gpkg",
        "corridors": "test/track_variants/forest_1_2/corridors",
    },
]

DEFAULT_CONFIG = {
    "round": 1,
    "note": "round 1: does track weighting change which corridor is best?",
    "models": DEFAULT_MODELS,
}


@dataclass(frozen=True)
class Model:
    name: str
    label: str
    routes: Path
    corridors: Path

    @property
    def ok(self) -> bool:
        return self.routes.is_file() and self.corridors.is_dir()


@dataclass(frozen=True)
class Config:
    path: Path
    round: int
    note: str
    models: tuple[Model, ...]

    def model(self, name: str) -> Optional[Model]:
        return next((m for m in self.models if m.name == name), None)


def write_default(path: Optional[Path] = None, *, overwrite: bool = False) -> Path:
    out = Path(path) if path else CONFIG
    if out.exists() and not overwrite:
        raise SystemExit(f"{out} exists. Edit it, or pass --overwrite.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    return out


def load(path: Optional[Path] = None) -> Config:
    """Read the config, or explain what to do instead of raising a KeyError."""
    where = Path(path) if path else CONFIG
    if not where.is_file():
        raise SystemExit(
            f"No review config at {where}.\n"
            f"  python -m skimap.corridor_review init"
        )

    # utf-8-sig: hand-edited on Windows, where Notepad writes a BOM.
    body = json.loads(where.read_text(encoding="utf-8-sig"))

    entries = body.get("models") or []
    if not entries:
        raise SystemExit(f"{where.name} lists no models.")

    models, seen = [], set()
    for entry in entries:
        for key in ("name", "routes", "corridors"):
            if not entry.get(key):
                raise SystemExit(f"{where.name}: a model is missing {key!r}")
        name = str(entry["name"])
        if name in seen:
            raise SystemExit(f"{where.name}: two models are called {name!r}")
        seen.add(name)
        models.append(Model(
            name=name,
            label=str(entry.get("label") or name),
            routes=paths.DATA / entry["routes"],
            corridors=paths.DATA / entry["corridors"],
        ))

    missing = [m for m in models if not m.ok]
    if missing:
        lines = "\n".join(
            f"  {m.name}: "
            + ", ".join(part for part, ok in (
                (f"no routes at {m.routes}", m.routes.is_file()),
                (f"no corridors at {m.corridors}", m.corridors.is_dir()),
            ) if not ok)
            for m in missing
        )
        raise SystemExit(f"{where.name} names output that is not on disk:\n{lines}")

    return Config(path=where, round=int(body.get("round", 1)),
                  note=str(body.get("note", "")), models=tuple(models))
