#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

ENERGY_KEYS = [
    "energy",
    "energy_joules",
    "joules",
    "total_joules",
    "watt_seconds",
]
DURATION_KEYS = [
    "duration",
    "duration_s",
    "seconds",
    "time",
    "elapsed_seconds",
]
POWER_KEYS = [
    "avg_watts",
    "average_watts",
    "watts",
    "power",
]
CO2_KEYS = [
    "co2",
    "co2_g",
    "carbon_g",
    "carbon",
]

def run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out.stdout

def walk_values(obj: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_values(item)

def find_first_numeric(obj: Any, candidate_keys: list[str]) -> float | None:
    candidate_keys_lower = {k.lower() for k in candidate_keys}
    for k, v in walk_values(obj):
        if str(k).lower() in candidate_keys_lower and isinstance(v, (int, float)):
            return float(v)
        if str(k).lower() in candidate_keys_lower and isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                pass
    return None

def download_artifact(repo: str, run_id: str, out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "gh", "run", "download", run_id,
                "-R", repo,
                "-D", str(out_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None

    matches = list(out_dir.rglob("experiment-result.json"))
    return matches[0] if matches else None

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--workflow", default="cache-exp-bcrypt-macos.yml")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out-dir", default="results")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)

    runs_json = run([
        "gh", "run", "list",
        "-R", args.repo,
        "--workflow", args.workflow,
        "--limit", str(args.limit),
        "--json", "databaseId,displayTitle,status,conclusion,createdAt"
    ])
    runs = json.loads(runs_json)

    rows: list[dict[str, Any]] = []

    for r in runs:
        if r.get("status") != "completed" or r.get("conclusion") != "success":
            continue

        run_id = str(r["databaseId"])
        run_dir = raw_dir / run_id
        result_file = download_artifact(args.repo, run_id, run_dir)
        if result_file is None:
            continue

        data = json.loads(result_file.read_text(encoding="utf-8"))
        install = data.get("install") or {}
        build = data.get("build") or {}
        total = data.get("total") or {}

        row = {
            "run_id": data.get("run_id"),
            "run_number": data.get("run_number"),
            "created_at": r.get("createdAt"),
            "variant": data.get("variant"),
            "rep": data.get("rep"),
            "sha": data.get("sha"),
            "node_version": data.get("node_version"),

            "install_energy_j": find_first_numeric(install, ENERGY_KEYS),
            "install_duration_s": find_first_numeric(install, DURATION_KEYS),
            "install_avg_watts": find_first_numeric(install, POWER_KEYS),
            "install_co2": find_first_numeric(install, CO2_KEYS),

            "build_energy_j": find_first_numeric(build, ENERGY_KEYS),
            "build_duration_s": find_first_numeric(build, DURATION_KEYS),
            "build_avg_watts": find_first_numeric(build, POWER_KEYS),
            "build_co2": find_first_numeric(build, CO2_KEYS),

            "total_energy_j": find_first_numeric(total, ENERGY_KEYS),
            "total_duration_s": find_first_numeric(total, DURATION_KEYS),
            "total_avg_watts": find_first_numeric(total, POWER_KEYS),
            "total_co2": find_first_numeric(total, CO2_KEYS),
        }
        rows.append(row)

    rows.sort(key=lambda x: (int(x["rep"]), x["variant"]))

    csv_path = out_dir / "eco_ci_results.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    # Summary excluding warmup rep=0
    usable = [r for r in rows if str(r.get("rep")) != "0"]

    def summarize(metric: str) -> list[dict[str, Any]]:
        groups = {}
        for row in usable:
            v = row.get(metric)
            if v is None:
                continue
            groups.setdefault(row["variant"], []).append(float(v))
        out = []
        for variant, vals in groups.items():
            n = len(vals)
            mean = sum(vals) / n
            var = sum((x - mean) ** 2 for x in vals) / (n - 1) if n > 1 else 0.0
            sd = var ** 0.5
            ci95 = 1.96 * sd / (n ** 0.5) if n > 1 else 0.0
            out.append({
                "metric": metric,
                "variant": variant,
                "n": n,
                "mean": mean,
                "sd": sd,
                "ci95": ci95,
            })
        return out

    metrics = [
        "install_energy_j",
        "install_duration_s",
        "total_energy_j",
        "total_duration_s",
    ]
    summary = []
    for m in metrics:
        summary.extend(summarize(m))

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")

if __name__ == "__main__":
    main()
