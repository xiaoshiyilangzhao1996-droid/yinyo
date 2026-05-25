#!/bin/bash
# YINYO test runner
# Usage: bash scripts/run_tests.sh

set -e

echo "=== YINYO Test Suite ==="
echo ""

# Run unit tests
echo "▶ Unit tests..."
pytest tests/ -v --tb=short

echo ""
echo "=== All tests passed ==="
