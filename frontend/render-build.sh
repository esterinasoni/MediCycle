#!/usr/bin/env bash
set -euo pipefail

PUBLISH_DIR="dist"
BACKEND_URL="${RENDER_BACKEND_URL:-}"

rm -rf "$PUBLISH_DIR"
mkdir -p "$PUBLISH_DIR/assets"

cp ./*.html "$PUBLISH_DIR/"
cp -R ./assets/. "$PUBLISH_DIR/assets/"

if [ -z "$BACKEND_URL" ]; then
  BACKEND_URL="http://127.0.0.1:8000"
fi

sed "s|__RENDER_BACKEND_URL__|$BACKEND_URL|g" ./config.template.js > "$PUBLISH_DIR/config.js"
