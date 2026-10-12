#!/usr/bin/env bash
# Uploads a layer from data/ to the same place on the Azure Files share the
# deployed backend mounts. Run it locally in Git Bash, from skimap/:
#
#   bash deploy/upload.sh "<upload URL>" data/input/derived/road_network
#
# The URL comes from `bash azure.sh upload-url` in Cloud Shell - quote it,
# it is full of &. The share is laid out like data/, so the path under
# data/ is the path on the share; a folder goes up with everything in it,
# replacing what is there. Restart the app afterwards (`bash azure.sh
# restart`): the server only reads the share when it starts.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: bash deploy/upload.sh \"<upload URL>\" data/<path>" >&2
  exit 2
fi
url=$1
local_path=${2%/}

case "$local_path" in
  data/*) ;;
  *) echo "The path must be under data/, as the share is: got $local_path" >&2; exit 2 ;;
esac
if [ ! -e "$local_path" ]; then
  echo "No such file or folder: $local_path" >&2
  exit 1
fi
case "$url" in
  https://*.file.core.windows.net/*\?*) ;;
  *) echo "That does not look like the upload URL from 'azure.sh upload-url'." >&2; exit 2 ;;
esac

# Where it goes on the share: its parent under data/, so a folder lands as
# that folder rather than spilling its files into the parent.
share_parent=$(dirname "${local_path#data/}")
base=${url%%\?*}
sas=${url#*\?}
target="$base/$share_parent?$sas"

echo "Uploading $local_path -> ${base}/${share_parent}/$(basename "$local_path")"
azcopy copy "$local_path" "$target" --recursive --overwrite=true
