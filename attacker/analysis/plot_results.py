from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"No summary rows found in {path}")
    return rows


def _phase(rows: list[dict[str, str]], phase: int) -> list[dict[str, str]]:
    return [row for row in rows if int(row["phase"]) == phase]


def _line_chart(
    rows: list[dict[str, str]],
    output: Path,
    *,
    x_key: str,
    metric: str,
    label_for: Callable[[dict[str, str]], str],
    title: str,
    x_label: str,
    y_label: str,
    categorical_x: bool = False,
) -> None:
    if not rows:
        raise ValueError(f"No rows available for chart {output.name}")
    series: dict[str, list[tuple[float | str, float, float]]] = defaultdict(list)
    for row in rows:
        raw_x: float | str = row[x_key] if categorical_x else float(row[x_key])
        series[label_for(row)].append(
            (
                raw_x,
                float(row[f"{metric}_mean"]),
                float(row[f"{metric}_stdev"]),
            )
        )

    figure, axis = plt.subplots(figsize=(9, 5.5))
    if categorical_x:
        preferred_order = ["none", "half", "maximum", "random"]
        categories = [item for item in preferred_order if any(item == point[0] for points in series.values() for point in points)]
        categories.extend(
            sorted(
                {
                    str(point[0])
                    for points in series.values()
                    for point in points
                    if str(point[0]) not in categories
                }
            )
        )
        positions = {category: index for index, category in enumerate(categories)}
        for label, points in sorted(series.items()):
            points.sort(key=lambda point: positions[str(point[0])])
            axis.errorbar(
                [positions[str(point[0])] for point in points],
                [point[1] for point in points],
                yerr=[point[2] for point in points],
                marker="o",
                capsize=3,
                label=label,
            )
        axis.set_xticks(range(len(categories)), categories)
    else:
        for label, points in sorted(series.items()):
            points.sort(key=lambda point: float(point[0]))
            axis.errorbar(
                [float(point[0]) for point in points],
                [point[1] for point in points],
                yerr=[point[2] for point in points],
                marker="o",
                capsize=3,
                label=label,
            )
    axis.set_title(title)
    axis.set_xlabel(x_label)
    axis.set_ylabel(y_label)
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _unique_network_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """T80 is attack-method independent; avoid drawing duplicate method lines."""
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        unique.setdefault((row["p"], row["delay_mode"]), row)
    return list(unique.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create report-ready project plots")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results/attacker/plots"))
    args = parser.parse_args()
    rows = load_rows(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    phase2 = _phase(rows, 2)
    _line_chart(
        phase2,
        args.output_dir / "phase2_accuracy_vs_spies.png",
        x_key="bribed_nodes",
        metric="accuracy",
        label_for=lambda row: row["method"],
        title="Phase 2: source-estimation accuracy",
        x_label="Number of bribed nodes",
        y_label="Accuracy",
    )
    _line_chart(
        phase2,
        args.output_dir / "phase2_score_adv_vs_spies.png",
        x_key="bribed_nodes",
        metric="score_adv",
        label_for=lambda row: row["method"],
        title="Phase 2: adversary score and optimal spy count",
        x_label="Number of bribed nodes",
        y_label="Score_adv",
    )

    phase3 = _unique_network_rows(_phase(rows, 3))
    _line_chart(
        phase3,
        args.output_dir / "phase3_t80_by_p.png",
        x_key="p",
        metric="mean_t80",
        label_for=lambda row: "Dandelion",
        title="Phase 3: Dandelion propagation time",
        x_label="Stem probability p",
        y_label="T80 (seconds)",
    )

    phase4 = _phase(rows, 4)
    _line_chart(
        phase4,
        args.output_dir / "phase4_accuracy_by_p.png",
        x_key="p",
        metric="accuracy",
        label_for=lambda row: row["method"],
        title="Phase 4: baseline versus advanced Dandelion attack",
        x_label="Stem probability p",
        y_label="Accuracy",
    )

    phase5 = _phase(rows, 5)
    _line_chart(
        phase5,
        args.output_dir / "phase5_accuracy_by_delay.png",
        x_key="delay_mode",
        metric="accuracy",
        label_for=lambda row: f"{row['method']} | p={row['p']}",
        title="Phase 5: malicious delay effect on attack accuracy",
        x_label="Malicious delay policy",
        y_label="Accuracy",
        categorical_x=True,
    )
    phase5_network = _unique_network_rows(phase5)
    _line_chart(
        phase5_network,
        args.output_dir / "phase5_t80_by_delay.png",
        x_key="delay_mode",
        metric="mean_t80",
        label_for=lambda row: f"p={row['p']}",
        title="Phase 5: malicious delay effect on propagation",
        x_label="Malicious delay policy",
        y_label="T80 (seconds)",
        categorical_x=True,
    )
    _line_chart(
        phase5,
        args.output_dir / "phase5_score_honest_by_delay.png",
        x_key="delay_mode",
        metric="score_honest",
        label_for=lambda row: f"{row['method']} | p={row['p']}",
        title="Phase 5: honest-network score",
        x_label="Malicious delay policy",
        y_label="Score_honest",
        categorical_x=True,
    )


if __name__ == "__main__":
    main()
