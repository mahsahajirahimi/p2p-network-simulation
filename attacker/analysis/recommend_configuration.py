from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the configuration with maximum Score_adv")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit("Summary file is empty")
    best = max(rows, key=lambda row: float(row["score_adv_mean"]))
    print("Recommended attacker configuration:")
    for field in (
        "phase",
        "method",
        "p",
        "delay_mode",
        "spy_selection_method",
        "bribed_nodes",
        "score_adv_mean",
        "accuracy_mean",
        "run_count",
    ):
        print(f"  {field}: {best[field]}")


if __name__ == "__main__":
    main()
