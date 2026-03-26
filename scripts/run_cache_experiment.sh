#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-YOUR_GITHUB_USERNAME/node.bcrypt.js}"
WORKFLOW_FILE="${2:-cache-exp-bcrypt-macos.yml}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd gh
require_cmd jq

wait_for_run() {
  local repo="$1"
  local workflow_file="$2"
  local rep="$3"
  local variant="$4"

  echo "Waiting for run: rep=${rep}, variant=${variant}"

  local run_id=""
  for _ in $(seq 1 60); do
    run_id="$(gh run list -R "$repo" --workflow "$workflow_file" --limit 20 --json databaseId,displayTitle \
      | jq -r --arg rep "rep-${rep}" --arg variant "$variant" '
          map(select(.displayTitle | contains($variant) and contains($rep)))
          | first
          | .databaseId // empty
        ')"
    if [[ -n "$run_id" ]]; then
      break
    fi
    sleep 5
  done

  if [[ -z "$run_id" ]]; then
    echo "Could not find run for rep=${rep}, variant=${variant}" >&2
    exit 1
  fi

  echo "Watching run id: $run_id"
  gh run watch "$run_id" -R "$repo" --exit-status
}

dispatch_run() {
  local repo="$1"
  local workflow_file="$2"
  local rep="$3"
  local variant="$4"

  echo "Dispatching rep=${rep}, variant=${variant}"
  gh workflow run "$workflow_file" -R "$repo" \
    -f variant="$variant" \
    -f rep="$rep"

  wait_for_run "$repo" "$workflow_file" "$rep" "$variant"
}

echo "Repo: $REPO"
echo "Workflow: $WORKFLOW_FILE"

# Warm-up cached run, excluded from analysis
dispatch_run "$REPO" "$WORKFLOW_FILE" "0" "cached"

# 10 paired measurements
for i in $(seq 1 10); do
  dispatch_run "$REPO" "$WORKFLOW_FILE" "$i" "baseline"
  dispatch_run "$REPO" "$WORKFLOW_FILE" "$i" "cached"
done

echo "All runs completed."
