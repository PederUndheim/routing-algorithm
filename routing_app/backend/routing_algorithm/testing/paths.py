from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.file_handler.area_context import PROJECT_ROOT
from backend.routing_algorithm.testing.config import DEFAULT_EXPERIMENT


@dataclass(frozen=True)
class TestingAreaPaths:
    """
    Local-only paths for this experiment.

    All generated rasters and routes go under data/testing and do not overwrite
    data/runtime or data/areas outputs used by the main application.
    """

    area_id: str
    experiment: str = DEFAULT_EXPERIMENT
    project_root: Path = PROJECT_ROOT

    @property
    def root(self) -> Path:
        return self.project_root / "data" / "testing" / self.experiment / self.area_id

    @property
    def cost_surface_dir(self) -> Path:
        return self.root / "cost_surface"

    @property
    def input_layer_dir(self) -> Path:
        return self.root / "input_layers"

    @property
    def pra_runout_combined(self) -> Path:
        return self.input_layer_dir / "pra_runout_combined_testing.tif"

    @property
    def debug_cost_layer_dir(self) -> Path:
        return self.cost_surface_dir / "debug_layers"

    @property
    def cost_surface_output(self) -> Path:
        return self.cost_surface_dir / "cost_surface_v2.tif"

    @property
    def cost_surface(self) -> Path:
        return self.root / "runtime" / "cost_surface_v2.tif"

    @property
    def corridor(self) -> Path:
        return self.root / "routing" / "corridor"

    @property
    def route_dir(self) -> Path:
        return self.root / "routing" / "route" / "native"

    @property
    def route_wgs84(self) -> Path:
        return self.root / "routing" / "route" / "wgs84"

    @property
    def multirouting_dir(self) -> Path:
        return self.root / "routing" / "multirouting"

    @property
    def multirouting_native(self) -> Path:
        return self.multirouting_dir / "native"

    @property
    def multirouting_wgs84(self) -> Path:
        return self.multirouting_dir / "wgs84"

    @property
    def multirouting_heatmap(self) -> Path:
        return self.multirouting_dir / "heatmap"
