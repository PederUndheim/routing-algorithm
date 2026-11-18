#!/usr/bin/env bash
# Sets up the Azure side of the consensus meeting app. Run it in Azure Cloud
# Shell (Bash), after the first image has been pushed by
# .github/workflows/deploy-consensus-api.yml:
#
#   bash consensus.sh storage        the storage account the decisions live in
#   CONSENSUS_ACCESS_CODE=... bash consensus.sh app
#                                    the container app; prints its address,
#                                    the admin key and the GitHub setting
#
# And afterwards:
#
#   CONSENSUS_ACCESS_CODE=... bash consensus.sh code   change the access code
#   bash consensus.sh admin-key                        print the admin key again
#   bash consensus.sh sas                              renew the read-only SAS
#
# What ends up where (rg-skimap; the validation app is not changed):
#   skimapkonsensus     this app's own storage account, ZRS, with blob
#                       versioning, 30-day soft delete and a delete lock.
#                       Tables konscurrent, konshistory; blob container
#                       snapshots
#   skimap-consensus    the API, in env-skimap: 0-2 replicas, stateless
#   valcurrent          the validation app's table of expert verdicts. This
#                       app gets a SAS for that one table with READ permission
#                       only - no key or connection string to the validation
#                       account - so it can read the experts live and is
#                       unable to change them
#   skimap-data share   the validation app's track tiles (validation/tracks),
#                       mounted the same way, served behind this app's code
set -euo pipefail

SUBSCRIPTION=04f64357-64cc-48b9-9dba-7517166a3326   # Azure for Students
LOCATION=swedencentral
RG=rg-skimap
STORAGE=${CONSENSUS_STORAGE:-skimapkonsensus}       # globally unique
VALIDATION_STORAGE=${VALIDATION_STORAGE:-skimapvalidering}
ENVIRONMENT=env-skimap
APP=skimap-consensus           # also named in .github/workflows/deploy-consensus-api.yml
IMAGE=ghcr.io/pederundheim/skimap-consensus-api:latest
ORIGIN=https://pederundheim.github.io
SHARE=skimap-data
SAS_EXPIRY=2027-12-31T00:00Z

az account set --subscription "$SUBSCRIPTION"

connection_string() {
  az storage account show-connection-string -n "$STORAGE" -g "$RG" --query connectionString -o tsv
}

app_url() {
  echo "https://management.azure.com$(az group show -n "$RG" --query id -o tsv)/providers/Microsoft.App/containerApps/$APP?api-version=2024-03-01"
}

# Read ("r") on valcurrent and nothing else. Signed with the validation
# account's key here in Cloud Shell; the key itself never leaves.
read_only_sas() {
  local key
  key=$(az storage account keys list -n "$VALIDATION_STORAGE" -g "$RG" --query "[0].value" -o tsv)
  az storage table generate-sas --name valcurrent --permission r --https-only \
    --expiry "$SAS_EXPIRY" --account-name "$VALIDATION_STORAGE" --account-key "$key" -o tsv
}

storage() {
  az storage account create -n "$STORAGE" -g "$RG" -l "$LOCATION" \
    --sku Standard_ZRS --kind StorageV2 --min-tls-version TLS1_2 \
    --allow-blob-public-access false -o none
  az storage account blob-service-properties update -n "$STORAGE" -g "$RG" \
    --enable-versioning true \
    --enable-delete-retention true --delete-retention-days 30 \
    --enable-container-delete-retention true --container-delete-retention-days 30 -o none
  az lock create --name keep-consensus-data --lock-type CanNotDelete \
    -g "$RG" --resource "$STORAGE" --resource-type Microsoft.Storage/storageAccounts -o none
  echo "Storage account $STORAGE ready (ZRS, versioning, soft delete, delete lock)."
}

existing_secret() {
  az containerapp secret show -n "$APP" -g "$RG" --secret-name "$1" --query value -o tsv 2>/dev/null || true
}

app() {
  : "${CONSENSUS_ACCESS_CODE:?set CONSENSUS_ACCESS_CODE to the code the meeting will type}"
  local admin_key sas
  admin_key=$(existing_secret admin-key)
  [ -n "$admin_key" ] || admin_key=$(openssl rand -hex 24)
  sas=$(read_only_sas)

  local registries="[]" registry_secret=""
  if [ -n "${GHCR_TOKEN:-}" ]; then
    : "${GHCR_USER:?set GHCR_USER with GHCR_TOKEN}"
    registries="[{\"server\": \"ghcr.io\", \"username\": \"$GHCR_USER\", \"passwordSecretRef\": \"ghcr-token\"}]"
    registry_secret=", {\"name\": \"ghcr-token\", \"value\": \"$GHCR_TOKEN\"}"
  fi

  # A direct ARM PUT, as for the other two apps - see azure.sh for why.
  local spec=/tmp/skimap-consensus.json
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
        {"name": "experts-sas", "value": "$sas"},
        {"name": "access-code", "value": "$CONSENSUS_ACCESS_CODE"},
        {"name": "admin-key", "value": "$admin_key"}$registry_secret
      ]
    },
    "template": {
      "containers": [{
        "name": "$APP",
        "image": "$IMAGE",
        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
        "env": [
          {"name": "CONSENSUS_TABLES_CONNECTION", "secretRef": "tables-connection"},
          {"name": "CONSENSUS_EXPERTS_ENDPOINT", "value": "https://$VALIDATION_STORAGE.table.core.windows.net"},
          {"name": "CONSENSUS_EXPERTS_SAS", "secretRef": "experts-sas"},
          {"name": "CONSENSUS_ACCESS_CODE", "secretRef": "access-code"},
          {"name": "CONSENSUS_ADMIN_KEY", "secretRef": "admin-key"},
          {"name": "CONSENSUS_ALLOWED_ORIGIN", "value": "$ORIGIN"},
          {"name": "CONSENSUS_TRACKS_DIR", "value": "/app/tracks"}
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
  echo "            keep it: consensus_app.admin needs it as CONSENSUS_ADMIN_KEY"
  echo
  echo "GitHub, Settings > Secrets and variables > Actions > Variables:"
  echo "  variable  CONSENSUS_API_URL     https://$fqdn"
}

restart() {
  local revision
  revision=$(az containerapp show -n "$APP" -g "$RG" --query properties.latestRevisionName -o tsv)
  az containerapp revision restart -n "$APP" -g "$RG" --revision "$revision" -o none
}

set_code() {
  : "${CONSENSUS_ACCESS_CODE:?set CONSENSUS_ACCESS_CODE to the new code}"
  az containerapp secret set -n "$APP" -g "$RG" --secrets "access-code=$CONSENSUS_ACCESS_CODE" -o none
  restart
  echo "Access code changed."
}

renew_sas() {
  az containerapp secret set -n "$APP" -g "$RG" --secrets "experts-sas=$(read_only_sas)" -o none
  restart
  echo "Read-only SAS renewed (expires $SAS_EXPIRY)."
}

case "${1:-}" in
  storage) storage ;;
  app) app ;;
  code) set_code ;;
  sas) renew_sas ;;
  admin-key) existing_secret admin-key ;;
  *) echo "usage: bash consensus.sh storage|app|code|sas|admin-key" >&2; exit 2 ;;
esac
