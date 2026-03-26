#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt

def read_rows(path: Path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cleaned = {}
            for k, v in row.items():
                if v is None or v == "":
                    cleaned[k] = None
                    continue
                try:
                    cleaned[k] = float(v) if k not in {"variant", "sha", "created_at"} else v
                except ValueError:
                    cleaned[k] = v
            rows.append(cleaned)
    return [r for r in rows if str(r.get("rep")) != "0"]

def group_metric(rows, metric):
    groups = {"baseline": [], "cached": []}
    for r in rows:
        val = r.get(metric)
        variant = r.get("variant")
        if variant in groups and isinstance(val, (int, float)):
            groups[variant].append(float(val))
    return groups

def mean(xs):
    return sum(xs) / len(xs)

def ci95(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    sd = math.sqrt(var)
    return 1.96 * sd / math.sqrt(len(xs))

def plot_metric(groups, metric, ylabel, out_path):
    baseline = groups["baseline"]
    cached = groups["cached"]

    fig, ax = plt.subplots(figsize=(7, 5))

    ax.boxplot([baseline, cached], labels=["baseline", "cached"])

    # overlay points
    for i, values in enumerate([baseline, cached], start=1):
        jitter = [i + (j - len(values)/2) * 0.01 for j in range(len(values))]
        ax.scatter(jitter, values, alpha=0.7)

    ax.set_title(metric.replace("_", " "))
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)

def plot_summary(groups, metric, ylabel, out_path):
    labels = ["baseline", "cached"]
    values = [mean(groups["baseline"]), mean(groups["cached"])]
    errors = [ci95(groups["baseline"]), ci95(groups["cached"])]

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.bar(labels, values, yerr=errors, capsize=6)
    ax.set_title(f"{metric} mean ± 95% CI")
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="results/eco_ci_results.csv")
    parser.add_argument("--out-dir", default="results/plots")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_rows(csv_path)

    metrics = [
        ("install_energy_j", "Joules"),
        ("install_duration_s", "Seconds"),
        ("total_energy_j", "Joules"),
        ("total_duration_s", "Seconds"),
    ]

    for metric, ylabel in metrics:
        groups = group_metric(rows, metric)
        if not groups["baseline"] or not groups["cached"]:
            continue
        plot_metric(groups, metric, ylabel, out_dir / f"{metric}_boxplot.png")
        plot_summary(groups, metric, ylabel, out_dir / f"{metric}_mean_ci.png")

    print(f"Plots written to {out_dir}")

if __name__ == "__main__":
    main()
