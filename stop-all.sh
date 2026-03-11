#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping KMS test..."
./stop.sh --test

echo ""
echo "Stopping KMS prod..."
./stop.sh
