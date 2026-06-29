#!/usr/bin/env bash
# Local CI/CD pipeline for the CTI Bot.
# Runs ingestion, freshness check, and smoke test.
#
# Schedule with cron (every 6 hours):
#   0 */6 * * * /path/to/mlops/ci_local.sh >> /path/to/logs/ci.log 2>&1

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "=========================================="
echo " CTI Bot — Local CI/CD Pipeline"
echo " $TIMESTAMP"
echo "=========================================="

# ── Step 1: Ingest latest advisories ──────────────────────────────────────────
echo ""
echo "[1/3] Running ingestion pipeline..."
python -m scripts.ingest
echo "      Ingestion complete."

# ── Step 2: Check advisory freshness ──────────────────────────────────────────
echo ""
echo "[2/3] Checking advisory freshness..."
python mlops/freshness_check.py
echo "      Freshness check complete."

# ── Step 3: Smoke test — verify retrieval still works ─────────────────────────
echo ""
echo "[3/3] Running smoke test..."
python - <<'EOF'
from rag.retriever import retrieve

tests = [
    ("phishing techniques ATT&CK", None),
    ("Emotet malware indicators", "ThreatFox"),
    ("critical Windows vulnerability CVE", "MSRC"),
]

all_passed = True
for query, source in tests:
    chunks = retrieve(query, top_k=3, source_filter=source)
    status = "PASS" if chunks else "FAIL"
    if not chunks:
        all_passed = False
    print(f"  [{status}] '{query}' (filter={source or 'all'}) → {len(chunks)} chunks")

if not all_passed:
    raise SystemExit("Smoke test FAILED: one or more queries returned no results.")
EOF
echo "      Smoke test passed."

echo ""
echo "=========================================="
echo " Pipeline complete."
echo "=========================================="
