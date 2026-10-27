# The validation API: stdlib http.server plus the Azure SDKs. Code only - the
# track tiles are mounted from the file share (see deploy/validation.sh), so
# the image can be public. Nothing from the skimap package - no GDAL, no
# GRASS - so it is a plain slim Python image.
#
# Built from skimap/validation_app:
#   docker build -t skimap-validation-api skimap/validation_app
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY __init__.py validation_app/__init__.py
COPY backend validation_app/backend

# The commit, so /health says which build is live - see the deploy workflow.
ARG VERSION=dev
ENV PYTHONUNBUFFERED=1 VALIDATION_VERSION=$VERSION
EXPOSE 8000
CMD ["python", "-m", "validation_app.backend.server", "--host", "0.0.0.0", "--port", "8000"]
