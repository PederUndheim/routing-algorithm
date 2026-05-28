# A Routing Algorithm for Ski Touring in Norwegian Avalanche Terrain

Developing a scalable terrain-based framework for decision support.

This repository contains the source code for Peder Undheim's master's thesis on
generating ski-touring routes in Norwegian avalanche terrain. The system
combines geospatial preprocessing, raster-based terrain cost modelling, GRASS GIS
routing, route-corridor generation, evaluation against reference routes, and a
web interface for interactive route generation in the predefined study areas.

The README is intended as the public entry point for readers of the thesis. A
short [application guide](docs/application-guide.md) is available for using the
interactive map interface.

## Background

This project develops a terrain-based routing framework for ski touring in
Norwegian avalanche terrain. It is inspired by Skitourenguru and by the paper
"A Routing Algorithm for Backcountry Ski Tours" (Schmudlach and Eisenhut, ISSW
2024), but is adapted to Norwegian terrain, data availability, and ski-touring
practice. The method builds a raster cost surface where lower cost indicates
more suitable terrain for ski touring and higher cost indicates terrain that
should be avoided.

## Research Questions

The thesis addresses three research questions:

1. How can a cost surface and routing algorithm be designed to generate realistic
   and reliable ski touring routes in Norwegian avalanche terrain?
2. How can the routing framework be designed to enable scalable and practical use
   for ski touring across different regions in Norway?
3. How well do the generated routes correspond to expert route choices?

## Repository Layout

```text
backend/                         FastAPI backend, routing logic, evaluation scripts
backend/routing_algorithm/        Cost surface, GRASS routing, corridors, evaluation
data_preprocessing/               Scripts for preparing GIS inputs and study areas
frontend/                         React/Vite map interface
figures/                          Figures generated for analysis and reporting
data/                             Local generated data and outputs, not tracked by Git
data_preprocessing/data_cache/     Local raw/intermediate GIS data, not tracked by Git
```

## System Overview

The project is organized around four main stages:

1. Prepare study-area rasters from source geodata, including DEM-derived slope,
   avalanche-related layers, forest, water, roads, trails, and track-density
   inputs.
2. Build a terrain cost surface where lower cost represents more favorable
   ski-touring terrain and high cost represents terrain to avoid.
3. Generate routes and route corridors with GRASS GIS from start, stop, and end
   points.
4. Evaluate generated routes against reference ski-touring routes using
   distance, buffer coverage, corridor coverage, and manual inspection metrics.

## Interactive Application

The web application is an interactive way to test the routing algorithm for the
study areas used in the thesis. It is not the full result set or a standalone
validation of the method; the main thesis results come from the preprocessing,
cost-surface construction, generated route examples, route corridors, automatic
evaluation, and manual inspection.

Application URL:

```text
https://pederundheim.github.io/routing-algorithm/
```

![Overview of the routing application](docs/assets/application-guide/overview.png)

The application lets a user choose start, stop, and end points, adjust routing
settings, generate a least-cost route, inspect a near-optimal route corridor, and
download generated routes as GPX or GeoJSON. A short step-by-step guide is
available in [docs/application-guide.md](docs/application-guide.md).

## Data

Large raster and vector files are intentionally excluded from Git. A full local
run expects the generated data folders below to exist, either restored from a
data bundle or regenerated with the preprocessing scripts:

```text
data/
data_preprocessing/data_cache/
```

Most geospatial processing uses EPSG:25833 and a 10 m raster grid. Example study
area identifiers include `isfjorden_01`, `jotunheimen_01`, `hemsedal_01`,
`sogndal_01`, `svolvaer_01`, and `kattfjordeidet_01`.

## Quick Start

The backend requires Python, GDAL/OGR, GRASS GIS, and the local data products.
The frontend requires Node.js.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Run the API:

```bash
python -m uvicorn backend.api.main:app --reload --port 8000
```

Run the frontend:

```bash
cd frontend
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Then open the Vite development URL shown in the terminal.

## Reproducing Core Outputs

Build input layers and cost surfaces for one area:

```bash
python -m backend.scripts.run_full_pipeline --area isfjorden_01
```

Generate routes for configured tours in one area:

```bash
python -m backend.scripts.run_routing --area isfjorden_01
```

Run the evaluation for one area:

```bash
python -m backend.scripts.run_evaluation --area isfjorden_01
```

Run the thesis track-mode comparison across all available evaluation areas:

```bash
python -m backend.scripts.run_evaluation --force-reroute --all-track-modes
```

Evaluation tables and diagnostic outputs are written below:

```text
data/areas/<area_id>/evaluation/evaluation_results/
data/evaluation/evaluation_results/
```

## Notes For Thesis Readers

This repository contains the implementation used to develop and evaluate the
routing framework. The generated geospatial data products are large and are
handled outside Git, so the code alone is not a complete data archive. For
method details, parameter interpretation, and discussion of results, see the
associated thesis text.

## Author

Developed by Peder Undheim as part of a master's thesis at NTNU, Faculty of
Engineering, Department of Civil and Environmental Engineering, June 2026.

Supervisors: Håvard Boutera Toft, NVE, and Jan Ketil Rød, NTNU.
