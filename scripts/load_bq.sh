#!/usr/bin/env bash
# Idempotent BigQuery loader for Stark Food Services (SFS) synthetic dataset.
# Loads every *.jsonl file in data/ into its matching table in the target dataset
# using --replace (WRITE_TRUNCATE). Never hardcodes GCP project IDs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${REPO_ROOT}/data"

PROJECT_ID="${BQ_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
DATASET="${BQ_DATASET:-sfs_demo}"
LOCATION="${BQ_LOCATION:-US}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "ERROR: No active GCP project configured. Set BQ_PROJECT_ID or run 'gcloud config set project <PROJECT_ID>'." >&2
  exit 1
fi

if [[ ! -d "${DATA_DIR}" ]]; then
  echo "ERROR: Data directory not found at ${DATA_DIR}. Run 'make generate' first." >&2
  exit 1
fi

shopt -s nullglob
FILES=("${DATA_DIR}"/*.jsonl)
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "ERROR: No .jsonl files found in ${DATA_DIR}. Run 'make generate' first." >&2
  exit 1
fi

echo "======================================================================"
echo "Loading Stark Food Services data into BigQuery"
echo "  Project  : ${PROJECT_ID}"
echo "  Dataset  : ${DATASET}"
echo "  Location : ${LOCATION}"
echo "  Files    : ${#FILES[@]} JSONL files in ${DATA_DIR}"
echo "======================================================================"

LOG_DIR="$(mktemp -d)"
trap 'rm -rf "${LOG_DIR}"' EXIT

declare -a PIDS=()
declare -a TABLES=()

for filepath in "${FILES[@]}"; do
  filename="$(basename "${filepath}")"
  table="${filename%.jsonl}"
  echo "[load_bq] Starting load: ${filename} -> ${DATASET}.${table}"
  (
    bq --project_id="${PROJECT_ID}" \
       --location="${LOCATION}" \
       load \
       --replace \
       --source_format=NEWLINE_DELIMITED_JSON \
       "${DATASET}.${table}" \
       "${filepath}" >"${LOG_DIR}/${table}.log" 2>&1
  ) &
  PIDS+=("$!")
  TABLES+=("${table}")
done

FAILED=0
for i in "${!PIDS[@]}"; do
  pid="${PIDS[$i]}"
  table="${TABLES[$i]}"
  if wait "${pid}"; then
    echo "[load_bq] Completed : ${DATASET}.${table}"
  else
    echo "[load_bq] FAILED    : ${DATASET}.${table}" >&2
    cat "${LOG_DIR}/${table}.log" >&2
    FAILED=1
  fi
done

if [[ "${FAILED}" -ne 0 ]]; then
  echo "ERROR: One or more BigQuery load jobs failed." >&2
  exit 1
fi

echo ""
echo "======================================================================"
echo "BigQuery Table Row Counts & Storage Summary (${DATASET})"
echo "======================================================================"
bq --project_id="${PROJECT_ID}" \
   --location="${LOCATION}" \
   query \
   --use_legacy_sql=false \
   --format=pretty \
   "SELECT
      table_id AS table_name,
      row_count,
      size_bytes,
      ROUND(size_bytes / (1024 * 1024), 2) AS size_mb
    FROM \`${DATASET}.__TABLES__\`
    ORDER BY row_count DESC;"

bq --project_id="${PROJECT_ID}" \
   --location="${LOCATION}" \
   query \
   --use_legacy_sql=false \
   --format=pretty \
   "SELECT
      COUNT(*) AS total_tables,
      SUM(row_count) AS total_rows,
      SUM(size_bytes) AS total_bytes,
      ROUND(SUM(size_bytes) / (1024 * 1024), 2) AS total_mb
    FROM \`${DATASET}.__TABLES__\`;"
