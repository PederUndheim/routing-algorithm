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

## Docker commands

export AZ_RG="rg-routing-algorithm"
export AZ_LOC="swedencentral"
export ACR_NAME="skiroutingalgorithm"
export APP_ENV="env-routing-algorithm"
export APP_NAME="api-routing-algorithm"
export IMAGE_REPO="image-routing-algorithm"
export APP_FQDN="api-routing-algorithm.mangohill-479de517.swedencentral.azurecontainerapps.io"

az acr login -n "$ACR_NAME"

docker buildx build \
 --platform linux/amd64 \
 -f backend/Dockerfile \
 -t "$ACR_NAME.azurecr.io/$IMAGE_REPO:latest" \
 --push \
 .

az containerapp update \
 -n "$APP_NAME" \
  -g "$AZ_RG" \
 --image "$ACR_NAME.azurecr.io/image-routing-algorithm:latest"

curl -s "https://$APP_FQDN/health"

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
