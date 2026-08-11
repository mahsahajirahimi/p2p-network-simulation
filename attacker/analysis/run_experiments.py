from __future__ import annotations

import argparse
import csv
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from attacker.advanced_attack import AdvancedTimingAttack
from attacker.attacker_service import AttackerService
from attacker.baseline_attack import FirstSpyAttack
from attacker.evaluator import evaluate_predictions
from attacker.io import (
    load_json,
    load_observations,
    load_predictions,
    load_topology,
    load_truth,
    write_predictions,
)


RESULT_FIELDS = [
    "run_name",
    "phase",
    "method",
    "p",
    "seed",
    "delay_mode",
    "spy_selection_method",
    "bribed_nodes",
    "total_packets",
    "correct_guesses",
    "accuracy",
    "score_adv",
    "mean_t80",
    "median_t80",
    "score_honest",
    "missing_observation_packets",
]


def evaluate_run(run_dir: Path, output_root: Path) -> list[dict[str, object]]:
    manifest = load_json(run_dir / "manifest.json")
    topology = load_topology(run_dir / "topology.json", run_dir / "node_ids.json")
    observations = load_observations(run_dir / "spy_observations.jsonl")
    truth = load_truth(run_dir / "reference_truth.jsonl")
    spy_nodes = tuple(str(node) for node in manifest["spy_nodes"])
    candidates = tuple(node for node in topology.node_ids if node not in spy_nodes)
    seed = int(manifest.get("seed", 0))
    p = float(manifest.get("p", 0.0))
    if not spy_nodes:
        t80_values = [item.t80 for item in truth]
        mean_t80 = statistics.fmean(t80_values)
        return [
            {
                "run_name": run_dir.name,
                "phase": manifest.get("phase", "unknown"),
                "method": "no_attack",
                "p": p,
                "seed": seed,
                "delay_mode": "none",
                "spy_selection_method": "none",
                "bribed_nodes": 0,
                "total_packets": len(truth),
                "correct_guesses": 0,
                "accuracy": 0.0,
                "score_adv": 0.0,
                "mean_t80": mean_t80,
                "median_t80": statistics.median(t80_values),
                "score_honest": (1.0 / mean_t80) if mean_t80 > 0 else 0.0,
                "missing_observation_packets": len(truth),
            }
        ]

    methods = [FirstSpyAttack(seed=seed)]
    if bool(manifest.get("run_advanced", True)):
        methods.append(
            AdvancedTimingAttack(
                topology=topology,
                spy_nodes=spy_nodes,
                p=p,
                mode=str(manifest.get("mode", "dandelion")),
                delay_mode=str(manifest.get("delay_mode", "none")),
                embargo_seconds=float(manifest.get("stem_embargo_seconds", 3.0)),
                simulations_per_candidate=int(
                    manifest.get("simulations_per_candidate", 75)
                ),
                seed=seed,
            )
        )

    rows: list[dict[str, object]] = []
    packet_ids = [item.packet_id for item in truth]
    for method in methods:
        prediction_path = output_root / run_dir.name / f"predictions_{method.name}.jsonl"
        if prediction_path.exists():
            cached = load_predictions(prediction_path)
            if {item.packet_id for item in cached} == set(packet_ids):
                predictions = cached
            else:
                predictions = []
        else:
            predictions = []
        if not predictions:
            service = AttackerService(method=method, candidate_nodes=candidates)
            service.register_many(observations)
            predictions = service.estimate_all(packet_ids)
            write_predictions(prediction_path, predictions)
        metrics = evaluate_predictions(predictions, truth, bribed_nodes=len(spy_nodes))
        rows.append(
            {
                "run_name": run_dir.name,
                "phase": manifest.get("phase", "unknown"),
                "method": method.name,
                "p": p,
                "seed": seed,
                "delay_mode": manifest.get("delay_mode", "none"),
                "spy_selection_method": manifest.get(
                    "spy_selection_method", "unknown"
                ),
                "bribed_nodes": len(spy_nodes),
                **metrics.to_dict(),
            }
        )
    return rows


def discover_runs(dataset_root: Path) -> list[Path]:
    return sorted(
        path.parent
        for path in dataset_root.glob("*/manifest.json")
        if (path.parent / "topology.json").exists()
        and (path.parent / "spy_observations.jsonl").exists()
        and (path.parent / "reference_truth.jsonl").exists()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate attacker experiment logs")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/attacker"))
    parser.add_argument(
        "--phase",
        action="append",
        help="only evaluate this manifest phase (repeatable, e.g. --phase phase2)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="number of run directories to evaluate in parallel",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")

    runs = discover_runs(args.dataset_root)
    if args.phase:
        wanted = set(args.phase)
        runs = [
            run_dir
            for run_dir in runs
            if str(load_json(run_dir / "manifest.json").get("phase")) in wanted
        ]
    if not runs:
        raise SystemExit(f"No complete run directories found under {args.dataset_root}")
    rows: list[dict[str, object]] = []
    if args.workers == 1:
        evaluated = (evaluate_run(run_dir, args.output) for run_dir in runs)
        for run_rows in evaluated:
            rows.extend(run_rows)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for run_rows in executor.map(
                evaluate_run,
                runs,
                [args.output] * len(runs),
            ):
                rows.extend(run_rows)

    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "raw_results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
