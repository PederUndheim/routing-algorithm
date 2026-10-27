#!/usr/bin/env bash
# Sets up the Azure side of the validation app. Run it in Azure Cloud Shell
# (Bash), after the first image has been pushed by
# .github/workflows/deploy-validation-api.yml:
#
#   bash validation.sh storage        the storage account the verdicts live in
#   bash azure.sh upload-url          an upload URL for the track tiles; then,
#                                     locally in Git Bash, from skimap/:
#                                     bash deploy/upload.sh "<url>" data/validation/tracks
#   VALIDATION_ACCESS_CODE=... bash validation.sh app
#                                     the container app; prints its address,
#                                     the admin key and the GitHub settings
#
# And afterwards:
#
#   VALIDATION_ACCESS_CODE=... bash validation.sh code   change the access code
#   bash validation.sh admin-key                         print the admin key again
#
# What ends up where (rg-skimap, next to the routing app - nothing of that
# is touched):
#   skimapvalidering    storage account, zone-redundant (ZRS: three copies in
#                       three datacentres). Tables valcurrent, valhistory,
#                       valconfig; blob container snapshots, one file a day
#                       (see backend/snapshots.py). Blob versioning and 30-day
#                       soft delete on, and a CanNotDelete lock on the account
#   skimap-validation   the API, in env-skimap: 0-2 replicas, stateless
#   skimap-data share   azure.sh's share; validation/tracks holds the track
#                       tiles, mounted read-only. They are only to be seen
#                       behind the access code, so they are in neither git
#                       (the repository is public) nor the image
#
# The image is code only, so its GHCR package can be public - set that once
# in the package settings on GitHub. To keep it private instead, set
# GHCR_USER and GHCR_TOKEN (a GitHub token with read:packages) for `app`.
set -euo pipefail

SUBSCRIPTION=04f64357-64cc-48b9-9dba-7517166a3326   # Azure for Students
LOCATION=swedencentral
RG=rg-skimap
STORAGE=${VALIDATION_STORAGE:-skimapvalidering}      # globally unique
ENVIRONMENT=env-skimap
APP=skimap-validation          # also named in .github/workflows/deploy-validation-api.yml
IMAGE=ghcr.io/pederundheim/skimap-validation-api:latest
ORIGIN=https://pederundheim.github.io
SHARE=skimap-data              # azure.sh's share, already registered with the environment

az account set --subscription "$SUBSCRIPTION"

connection_string() {
  az storage account show-connection-string -n "$STORAGE" -g "$RG" --query connectionString -o tsv
}

app_url() {
  echo "https://management.azure.com$(az group show -n "$RG" --query id -o tsv)/providers/Microsoft.App/containerApps/$APP?api-version=2024-03-01"
}

storage() {
  az storage account create -n "$STORAGE" -g "$RG" -l "$LOCATION" \
    --sku Standard_ZRS --kind StorageV2 --min-tls-version TLS1_2 \
    --allow-blob-public-access false -o none
  # Every rewrite of a snapshot kept as a version, and deleted blobs and
  # containers recoverable for 30 days.
  az storage account blob-service-properties update -n "$STORAGE" -g "$RG" \
    --enable-versioning true \
    --enable-delete-retention true --delete-retention-days 30 \
    --enable-container-delete-retention true --container-delete-retention-days 30 -o none
  # Deleting the account - or the resource group with it - now needs the lock
  # removed first, on purpose.
  az lock create --name keep-validation-data --lock-type CanNotDelete \
    -g "$RG" --resource "$STORAGE" --resource-type Microsoft.Storage/storageAccounts -o none
  echo "Storage account $STORAGE ready (ZRS, versioning, soft delete, delete lock)."
}

existing_secret() {
  az containerapp secret show -n "$APP" -g "$RG" --secret-name "$1" --query value -o tsv 2>/dev/null || true
}

app() {
  : "${VALIDATION_ACCESS_CODE:?set VALIDATION_ACCESS_CODE to the code the reviewers will type}"
  # Kept across re-runs, so admin.py keeps working; generated the first time.
  local admin_key
  admin_key=$(existing_secret admin-key)
  [ -n "$admin_key" ] || admin_key=$(openssl rand -hex 24)

  local registries="[]" registry_secret=""
  if [ -n "${GHCR_TOKEN:-}" ]; then
    : "${GHCR_USER:?set GHCR_USER with GHCR_TOKEN}"
    registries="[{\"server\": \"ghcr.io\", \"username\": \"$GHCR_USER\", \"passwordSecretRef\": \"ghcr-token\"}]"
    registry_secret=", {\"name\": \"ghcr-token\", \"value\": \"$GHCR_TOKEN\"}"
  fi

  # A direct ARM PUT, as for skimap-api - see azure.sh for why not
  # `az containerapp create`. It creates or replaces, so a re-run is the same.
  #
  # Stateless - everything is in the storage account - so more than one
  # replica is fine; two covers a deploy overlapping a session.
  local spec=/tmp/skimap-validation.json
  cat > "$spec" <<EOF
{
  "location": "$LOCATION",
  "properties": {
    "environmentId": "$(az containerapp env show -n "$ENVIRONMENT" -g "$RG" --query id -o tsv)",
    "workloadProfileName": "Consumption",
    "configuration": {
      "activeRevisionsMode": "Single",
      "ingress": {"external": true, "targetPort": 8000, "transport": "http"},
      "registries": $registries,
      "secrets": [
        {"name": "tables-connection", "value": "$(connection_string)"},
        {"name": "access-code", "value": "$VALIDATION_ACCESS_CODE"},
        {"name": "admin-key", "value": "$admin_key"}$registry_secret
      ]
    },
    "template": {
      "containers": [{
        "name": "$APP",
        "image": "$IMAGE",
        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
        "env": [
          {"name": "VALIDATION_TABLES_CONNECTION", "secretRef": "tables-connection"},
          {"name": "VALIDATION_ACCESS_CODE", "secretRef": "access-code"},
          {"name": "VALIDATION_ADMIN_KEY", "secretRef": "admin-key"},
          {"name": "VALIDATION_ALLOWED_ORIGIN", "value": "$ORIGIN"},
          {"name": "VALIDATION_TRACKS_DIR", "value": "/app/tracks"}
        ],
        "probes": [{
          "type": "Startup",
          "httpGet": {"path": "/health", "port": 8000},
          "initialDelaySeconds": 2,
          "periodSeconds": 5,
          "failureThreshold": 12
        }],
        "volumeMounts": [
          {"volumeName": "data", "mountPath": "/app/tracks", "subPath": "validation/tracks"}
        ]
      }],
      "scale": {"minReplicas": 0, "maxReplicas": 2},
      "volumes": [{"name": "data", "storageType": "AzureFile", "storageName": "$SHARE"}]
    }
  }
}
EOF
  az rest --method put --url "$(app_url)" --body @"$spec" -o none
  rm -f "$spec"
  local state=""
  for _ in $(seq 60); do
    state=$(az rest --method get --url "$(app_url)" --query properties.provisioningState -o tsv)
    [ "$state" = "Succeeded" ] || [ "$state" = "Failed" ] && break
    sleep 10
  done
  echo "   provisioning: $state"

  local fqdn
  fqdn=$(az rest --method get --url "$(app_url)" --query properties.configuration.ingress.fqdn -o tsv)
  echo
  echo "API:        https://$fqdn   (check: curl https://$fqdn/health)"
  echo "Admin key:  $admin_key"
  echo "            keep it: admin.py needs it as VALIDATION_ADMIN_KEY"
  echo
  echo "GitHub, Settings > Secrets and variables > Actions:"
  echo "  variable  VALIDATION_API_URL     https://$fqdn"
}

set_code() {
  : "${VALIDATION_ACCESS_CODE:?set VALIDATION_ACCESS_CODE to the new code}"
  az containerapp secret set -n "$APP" -g "$RG" --secrets "access-code=$VALIDATION_ACCESS_CODE" -o none
  local revision
  revision=$(az containerapp show -n "$APP" -g "$RG" --query properties.latestRevisionName -o tsv)
  az containerapp revision restart -n "$APP" -g "$RG" --revision "$revision" -o none
  echo "Access code changed. Reviewers are asked for the new one on their next change."
}

case "${1:-}" in
  storage) storage ;;
  app) app ;;
  code) set_code ;;
  admin-key) existing_secret admin-key ;;
  *) echo "usage: bash validation.sh storage|app|code|admin-key" >&2; exit 2 ;;
esac
