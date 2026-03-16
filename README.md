# 🏔️ Routing Algorithm for Ski Touring in Avalanche Terrain in Norway

This project develops a "proof of concept" of a **routing algorithm for ski touring in avalanche terrain** in Norway, inspired by [Skitourenguru](https://skitourenguru.com/) and the paper _“A Routing Algorithm for Backcountry Ski Tours”_ (Schmudlach & Eisenhut, ISSW 2024).  
The goal is to generate safe and efficient ascent routes based on terrain and avalanche parameters using **GRASS GIS** and **Python**.

---

## Background

Avalanche terrain strongly influences route safety for ski tourers.  
Following the principles of Skitourenguru’s routing system, this project adapts the concept to **Norwegian terrain and data**.  
A raster-based **cost surface** is created, where each cell (1–99) represents the relative suitability for travel, balancing safety and efficiency.

---

## How to get started

source .venv/bin/activate
from root: python -m uvicorn backend.api.main:app --reload --port 8000  
from frontend: npm run dev

python -m backend.scripts.run_full_pipeline --area jotunheimen_01    
python -m backend.scripts.run_full_pipeline --area isfjorden_01

python -m backend.scripts.run_routing --area jotunheimen_01                  
python -m backend.scripts.run_routing --area isfjorden_01

python -m backend.scripts.run_full_pipeline --area isfjorden_01
python -m backend.scripts.run_routing --area isfjorden_01

python -m backend.scripts.run_full_pipeline --area jotunheimen_01 
python -m backend.scripts.run_routing --area jotunheimen_01 

## Docker commands

set -euo pipefail

export AZ_RG="rg-routing-algorithm"
export ACR_NAME="skiroutingalgorithm"
export APP_NAME="api-routing-algorithm"
export IMAGE_REPO="image-routing-algorithm"
export APP_FQDN="api-routing-algorithm.mangohill-479de517.swedencentral.azurecontainerapps.io"

export TAG="$(date -u +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD 2>/dev/null || echo manual)"
export IMAGE="$ACR_NAME.azurecr.io/$IMAGE_REPO:$TAG"

az acr login -n "$ACR_NAME"

docker buildx build \
  --platform linux/amd64 \
  -f backend/Dockerfile \
  -t "$IMAGE" \
  --push \
  .

az containerapp update \
  -n "$APP_NAME" \
  -g "$AZ_RG" \
  --image "$IMAGE"

curl -i "https://$APP_FQDN/health"

az containerapp show \
  -n "$APP_NAME" \
  -g "$AZ_RG" \
  --query "properties.template.containers[0].image" -o tsv

---

## Features

- Raster-based cost surface using terrain parameters
- Factors include slope, curvature, PRA (release & runout) and more
- Integration with **GRASS GIS** (`r.walk`, `r.path`) for route optimization
- Adjustable parameter weighting and scaling functions
- Comparison of auto-generated vs expert routes (Fréchet / Hausdorff metrics)
- Modular and reproducible Python structure

---

## Author

Developed by Peder Undheim
NTNU – Department of Engineering Science and ICT, Geomatics specialization
2025
