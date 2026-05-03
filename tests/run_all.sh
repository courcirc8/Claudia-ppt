#!/bin/bash
# Run full test suite for PptxAtelier (the tool).
set -e
cd "$(dirname "$0")/.."

echo "════════════════════════════════════════════════════════"
echo " PptxAtelier — Test suite"
echo "════════════════════════════════════════════════════════"
command -v pytest >/dev/null 2>&1 || { echo "❌ pytest missing: pip install pytest python-pptx Pillow"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ node missing: brew install node"; exit 1; }

python3 -m pytest tests/ -v --tb=short --color=yes 2>&1 | tee /tmp/pptxatelier_tests.log

echo ""
echo "════════════════════════════════════════════════════════"
grep -E "(passed|failed|error|skipped)" /tmp/pptxatelier_tests.log | tail -1
