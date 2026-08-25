from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class AreaPaths:
    area_id: str
    project_root: Path

    
    @property
    def area_root(self) -> Path:
        return self.project_root / "data" / "areas" / self.area_id
    
    
    #--- RUNTIME DATA ----
    @property
    def runtime_area_root(self) -> Path:
        return self.project_root / "data" / "runtime" / "areas" / self.area_id
    
    @property
    def cost_surface(self) -> Path:
        return self.runtime_area_root / "cost_surface.tif"

    @property
    def cost_surface_output(self) -> Path:
        return self.cost_surface_dir / "cost_surface.tif"
    
    @property
    def dem(self) -> Path:
        return self.runtime_area_root / "dem.tif"
    

    #--- RUNS OUTPUT ----
    @property
    def data_root(self) -> Path:
        return self.project_root / "data"

    def run_root(self, run_id: str) -> Path:
        return self.data_root / "runs_output" / run_id
    
    
    # ---- INPUT ----
    @property
    def input(self) -> Path:
        return self.area_root / "input"
    
    
    # ---- OUTPUT ----
    @property
    def output(self) -> Path:
        return self.area_root / "output"
    
    @property
    def corridor(self) -> Path:
        return self.output / "corridor"
    
    @property
    def cost_surface_dir(self) -> Path:
        return self.output / "cost_surface"
    
    @property
    def debug_cost_layer_dir(self) -> Path:
        return self.cost_surface_dir / "debug_cost_layer"
    
    @property
    def route_dir(self) -> Path:
        return self.output / "route"
    
    @property
    def route_native(self) -> Path:
        return self.route_dir / "native"
    
    @property
    def route_wgs84(self) -> Path:
        return self.route_dir / "wgs84"
    
    @property
    def multirouting_dir(self) -> Path:
        return self.output / "multirouting"
    
    @property
    def multirouting_native(self) -> Path:
        return self.multirouting_dir / "native"
    
    @property
    def multirouting_wgs84(self) -> Path:
        return self.multirouting_dir / "wgs84"
    
    @property
    def multirouting_heatmap(self) -> Path:
        return self.multirouting_dir / "heatmap"
    
    # ---- EVALUATION ----
    @property
    def evaluation(self) -> Path:
        return self.area_root / "evaluation"
    
    @property
    def evaluation_results(self) -> Path:
        return self.evaluation / "evaluation_results"
    
    @property
    def evaluation_plots(self) -> Path:
        return self.evaluation / "plots"
    
    @property
    def evaluation_routes(self) -> Path:
        return self.evaluation / "evaluation_routes"