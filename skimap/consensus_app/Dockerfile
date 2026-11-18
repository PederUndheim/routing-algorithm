# The consensus API: stdlib http.server plus the Azure SDKs. Code only - the
# track tiles are mounted from the file share (see deploy/consensus.sh), so
# the image can be public. backend/meetings.json (from prepare.py) holds the
# meetings' corridor ids and comes along with the code.
#
# Built from skimap/consensus_app:
#   docker build -t skimap-consensus-api skimap/consensus_app
FROM python:3.12-slim

# Links the GHCR package to the repository, so the workflow token may push to it.
LABEL org.opencontainers.image.source=https://github.com/PederUndheim/routing-algorithm

WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY __init__.py consensus_app/__init__.py
COPY backend consensus_app/backend

# The commit, so /health says which build is live - see the deploy workflow.
ARG VERSION=dev
ENV PYTHONUNBUFFERED=1 CONSENSUS_VERSION=$VERSION
EXPOSE 8000
CMD ["python", "-m", "consensus_app.backend.server", "--host", "0.0.0.0", "--port", "8000"]
