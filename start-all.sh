#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting KMS prod..."
./start.sh

echo ""
echo "Starting KMS test..."
./start.sh --test
