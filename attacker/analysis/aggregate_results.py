from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


GROUP_FIELDS = ["phase", "method", "p", "delay_mode", "spy_selection_method", "bribed_nodes"]
METRIC_FIELDS = ["accuracy", "score_adv", "mean_t80", "score_honest"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate five-or-more seeded experiment runs")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/attacker/summary.csv"))
    args = parser.parse_args()

    with args.input.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in GROUP_FIELDS)].append(row)

    output_rows: list[dict[str, object]] = []
    for key, group in sorted(grouped.items()):
        output: dict[str, object] = dict(zip(GROUP_FIELDS, key))
        output["run_count"] = len(group)
        for metric in METRIC_FIELDS:
            values = [float(row[metric]) for row in group]
            output[f"{metric}_mean"] = statistics.fmean(values)
            output[f"{metric}_median"] = statistics.median(values)
            output[f"{metric}_stdev"] = statistics.stdev(values) if len(values) > 1 else 0.0
        output_rows.append(output)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output_rows[0]) if output_rows else GROUP_FIELDS + ["run_count"]
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)


if __name__ == "__main__":
    main()
