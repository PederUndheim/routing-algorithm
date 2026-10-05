# The skimap app's backend: /route, /corridor and /crux.
#
# Built from the skimap/ directory - see .github/workflows/deploy-skimap-api.yml.
#
# The official GRASS image already carries what the QGIS-bundled Python does
# on a desktop: GRASS 8.5, a GDAL with matching osgeo bindings, and numpy.
# The backend needs nothing else, so there is no pip install.
#
# No rasters are baked in. The national layers are ~20 GB, so they live on an
# Azure Files share that the Container App mounts over data/input and
# data/cost_surface. Everything the server writes - the GRASS database and the
# corridor scratch - stays on the container's own disk under data/.
FROM osgeo/grass-gis:8.5.0-ubuntu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GISBASE=/usr/local/grass

WORKDIR /app

COPY skimap ./skimap
COPY app/__init__.py ./app/__init__.py
COPY app/backend ./app/backend
# The corridor PNGs are coloured from these; small, and tracked for that reason.
COPY data/styles_arcgis ./data/styles_arcgis

EXPOSE 8000

CMD ["python3", "-m", "app.backend.server", "--host", "0.0.0.0", "--port", "8000"]
