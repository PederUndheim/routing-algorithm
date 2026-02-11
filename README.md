# 🏔️ Routing Algorithm for Ski Touring in Avalanche Terrain in Norway

This project develops a "proof of concept" of a **routing algorithm for ski touring in avalanche terrain** in Norway, inspired by [Skitourenguru](https://skitourenguru.com/) and the paper *“A Routing Algorithm for Backcountry Ski Tours”* (Schmudlach & Eisenhut, ISSW 2024).  
The goal is to generate safe and efficient ascent routes based on terrain and avalanche parameters using **GRASS GIS** and **Python**.

---

## Background

Avalanche terrain strongly influences route safety for ski tourers.  
Following the principles of Skitourenguru’s routing system, this project adapts the concept to **Norwegian terrain and data**.  
A raster-based **cost surface** is created, where each cell (1–99) represents the relative suitability for travel, balancing safety and efficiency.

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