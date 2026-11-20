#!/usr/bin/env bash
# Runs the k6 load test from a container attached to the kind Docker network,
# so traffic reaches the NodePort directly (no kubectl port-forward bottleneck).
#   usage: scripts/run-k6.sh [ramp|stress|spike|all]
set -euo pipefail
SCENARIO="${1:-all}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/k6/results"
exec docker run --rm --network kind \
  --ulimit nofile=65536:65536 \
  -e SCENARIO="$SCENARIO" \
  -e BASE_URL="${BASE_URL:-http://sre-lab-control-plane:30080}" \
  -v "$ROOT/k6:/scripts:ro" -v "$ROOT/k6/results:/results" \
  grafana/k6:1.4.0 run /scripts/load-test.js
