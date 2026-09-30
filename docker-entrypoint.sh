#!/bin/sh
set -e
mkdir -p "${DATA_DIR:-/data}"
# Ignore chown failures on locked mounts
chmod 777 "${DATA_DIR:-/data}" 2>/dev/null || true
exec "$@"
