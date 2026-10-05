#!/usr/bin/env bash
# Sets up the Azure side of the skimap app. Run it in Azure Cloud Shell
# (Bash), in two steps with the raster upload in between:
#
#   bash azure.sh storage   resource group, storage account and file share;
#                           prints the upload URL azcopy needs
#   bash azure.sh app       Container Apps environment, the app itself, and
#                           the identity GitHub Actions deploys with; prints
#                           the API address and the GitHub settings to add
#
# The order matters: the server reads the cost surface on startup, so the app
# would only crash-loop if it came up before the rasters are on the share.
# Both steps are safe to re-run.
#
# What ends up where:
#   rg-skimap
#     skimapdata      storage account; share skimap-data holds the rasters,
#                     mounted read-only over data/input and data/cost_surface
#     log-skimap      Log Analytics, where the container's output goes
#     env-skimap      Container Apps environment
#     skimap-api      the backend: max one replica, scales to zero
#     id-skimap-github  what the deploy workflow signs in as (OIDC, no secret)
set -euo pipefail

SUBSCRIPTION=04f64357-64cc-48b9-9dba-7517166a3326   # Azure for Students
LOCATION=swedencentral
RG=rg-skimap
STORAGE=skimapdata            # globally unique: lowercase, no hyphens
SHARE=skimap-data
LOGS=log-skimap
ENVIRONMENT=env-skimap
APP=skimap-api                # also named in .github/workflows/deploy-skimap-api.yml
IDENTITY=id-skimap-github
REPO=PederUndheim/routing-algorithm
IMAGE=ghcr.io/pederundheim/skimap-api:latest
ORIGIN=https://pederundheim.github.io

az account set --subscription "$SUBSCRIPTION"

storage_key() {
  az storage account keys list -n "$STORAGE" -g "$RG" --query "[0].value" -o tsv
}

storage() {
  az group create -n "$RG" -l "$LOCATION" -o none
  az storage account create -n "$STORAGE" -g "$RG" -l "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 -o none
  az storage share-rm create --storage-account "$STORAGE" -g "$RG" \
    -n "$SHARE" --quota 100 -o none

  # Write access for two days: long enough to upload, short enough to forget.
  local sas
  sas=$(az storage share generate-sas -n "$SHARE" --account-name "$STORAGE" \
    --account-key "$(storage_key)" --permissions rcwdl --https-only \
    --expiry "$(date -u -d '+2 days' +%Y-%m-%dT%H:%MZ)" -o tsv)

  echo
  echo "Upload URL (valid two days):"
  echo "https://$STORAGE.file.core.windows.net/$SHARE?$sas"
}

app() {
  az provider register -n Microsoft.App --wait
  az provider register -n Microsoft.OperationalInsights --wait

  # Named explicitly. Left to itself, env create makes a workspace called
  # workspace-<rg><random>.
  az monitor log-analytics workspace create -g "$RG" -n "$LOGS" -l "$LOCATION" -o none

  # The environment mode has to be named. Left out - and even with
  # --enable-workload-profiles - env create on Azure for Students makes an
  # Express environment, which cannot mount a file share. Only the
  # containerapp extension has --environment-mode; Cloud Shell's built-in
  # az does not, and does not report the mode either. An Express one left
  # over from before is replaced.
  az extension add --name containerapp --upgrade -y -o none
  is_express() {
    az containerapp env show -n "$ENVIRONMENT" -g "$RG" -o json 2>/dev/null | grep -qi '"express"'
  }
  if is_express; then
    echo "Replacing $ENVIRONMENT: it is an Express environment, which cannot mount the share."
    az containerapp env delete -n "$ENVIRONMENT" -g "$RG" --yes
  fi
  if ! az containerapp env show -n "$ENVIRONMENT" -g "$RG" -o none 2>/dev/null; then
    az containerapp env create -n "$ENVIRONMENT" -g "$RG" -l "$LOCATION" \
      --environment-mode WorkloadProfiles \
      --logs-workspace-id "$(az monitor log-analytics workspace show -g "$RG" -n "$LOGS" --query customerId -o tsv)" \
      --logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LOGS" --query primarySharedKey -o tsv)" \
      -o none
  fi
  if is_express; then
    echo "$ENVIRONMENT was created as Express again, and Express cannot mount the share." >&2
    exit 1
  fi

  az containerapp env storage set -n "$ENVIRONMENT" -g "$RG" \
    --storage-name "$SHARE" --access-mode ReadOnly \
    --azure-file-account-name "$STORAGE" --azure-file-account-key "$(storage_key)" \
    --azure-file-share-name "$SHARE" -o none

  # The YAML, because volume mounts with a subPath have no CLI flags.
  #
  # maxReplicas is 1 and must stay so: routes are serialized by a lock in the
  # process, and each corridor PNG is on the disk of the replica that drew it.
  #
  # The startup probe asks /health, which is not answered until GRASS is up
  # and the surface is linked; 10 tries 20 s apart allows a slow cold start.
  local spec=/tmp/skimap-api.yaml
  cat > "$spec" <<EOF
location: $LOCATION
properties:
  managedEnvironmentId: $(az containerapp env show -n "$ENVIRONMENT" -g "$RG" --query id -o tsv)
  workloadProfileName: Consumption
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      targetPort: 8000
      transport: http
  template:
    containers:
      - name: $APP
        image: $IMAGE
        resources:
          cpu: 2
          memory: 4Gi
        env:
          - name: SKIMAP_ALLOWED_ORIGIN
            value: $ORIGIN
        probes:
          - type: Startup
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 20
            timeoutSeconds: 10
            failureThreshold: 10
        volumeMounts:
          - volumeName: data
            mountPath: /app/data/input
            subPath: input
          - volumeName: data
            mountPath: /app/data/cost_surface
            subPath: cost_surface
    scale:
      minReplicas: 0
      maxReplicas: 1
    volumes:
      - name: data
        storageType: AzureFile
        storageName: $SHARE
EOF
  if az containerapp show -n "$APP" -g "$RG" -o none 2>/dev/null; then
    az containerapp update -n "$APP" -g "$RG" --yaml "$spec" -o none
  else
    az containerapp create -n "$APP" -g "$RG" --yaml "$spec" -o none
  fi

  # GitHub Actions signs in as this identity with a short-lived OIDC token,
  # so there is no password to store. It may only touch rg-skimap, and only
  # from a push to main.
  az identity create -n "$IDENTITY" -g "$RG" -l "$LOCATION" -o none
  if ! az identity federated-credential show --identity-name "$IDENTITY" -g "$RG" -n github-main -o none 2>/dev/null; then
    az identity federated-credential create --identity-name "$IDENTITY" -g "$RG" -n github-main \
      --issuer https://token.actions.githubusercontent.com \
      --subject "repo:$REPO:ref:refs/heads/main" \
      --audiences api://AzureADTokenExchange -o none
  fi
  az role assignment create --role Contributor \
    --assignee-object-id "$(az identity show -n "$IDENTITY" -g "$RG" --query principalId -o tsv)" \
    --assignee-principal-type ServicePrincipal \
    --scope "$(az group show -n "$RG" --query id -o tsv)" -o none

  echo
  echo "API: https://$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
  echo
  echo "GitHub, Settings > Secrets and variables > Actions:"
  echo "  secret    AZURE_CLIENT_ID        $(az identity show -n "$IDENTITY" -g "$RG" --query clientId -o tsv)"
  echo "  secret    AZURE_TENANT_ID        $(az account show --query tenantId -o tsv)"
  echo "  secret    AZURE_SUBSCRIPTION_ID  $SUBSCRIPTION"
  echo "  variable  AZURE_RESOURCE_GROUP   $RG"
}

case "${1:-}" in
  storage) storage ;;
  app) app ;;
  *) echo "usage: bash azure.sh storage|app" >&2; exit 2 ;;
esac
