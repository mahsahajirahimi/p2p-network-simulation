"""Reproducible experiment-matrix runner for the five project phases."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from attacker.io import network_topology_to_model
from attacker.spy_selector import max_bribed_nodes, select_spies

from . import config
from . import node as node_mod
from . import topology as topology_mod
from .simulator import create_source_plan


DEFAULT_SEEDS = (101, 202, 303, 404, 505)
P_VALUES = (0.9, 0.5, 0.1)
DELAY_MODES = ("none", "half", "maximum", "random")


def build_common_source_plan(seed, spy_method, packets, duration, plan_path):
    topology = topology_mod.generate_topology(seed=seed)
    node_ids = {
        item["index"]: node_mod.new_node_id(item["index"], seed)
        for item in topology["nodes"]
    }
    attack_topology = network_topology_to_model(topology, node_ids)
    maximum = max_bribed_nodes(topology["num_nodes"])
    maximum_spies = select_spies(
        attack_topology, maximum, method=spy_method, seed=seed
    )
    events = create_source_plan(node_ids, maximum_spies, packets, duration, seed)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps({"events": events}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return topology["num_nodes"], maximum


def simulator_command(
    output_dir,
    plan_path,
    phase,
    seed,
    nodes,
    packets,
    duration,
    grace,
    p=0.5,
    spy_count=None,
    spy_method="cluster_spread",
    delay_mode="none",
):
    command = [
        sys.executable,
        "-m",
        "network.simulator",
        "--phase",
        str(phase),
        "--seed",
        str(seed),
        "--nodes",
        str(nodes),
        "--packets",
        str(packets),
        "--duration",
        str(duration),
        "--grace",
        str(grace),
        "--p",
        str(p),
        "--delay-mode",
        delay_mode,
        "--source-plan",
        str(plan_path),
        "--output-dir",
        str(output_dir),
    ]
    if spy_count is not None:
        command.extend(
            ["--spy-count", str(spy_count), "--spy-method", spy_method]
        )
    return command


def build_commands(args):
    commands = []
    prepared = []
    for seed in args.seeds:
        plan_path = args.dataset_root / "_plans" / f"source_plan_seed{seed}.json"
        node_count, allowed_maximum = build_common_source_plan(
            seed, args.spy_method, args.packets, args.duration, plan_path
        )
        prepared.append((seed, plan_path, node_count, allowed_maximum))

    common_maximum = min(item[3] for item in prepared)
    maximum = min(args.max_spy_count or common_maximum, common_maximum)
    chosen = args.spy_count or maximum
    for seed, plan_path, node_count, allowed_maximum in prepared:
        if not 1 <= chosen <= allowed_maximum:
            raise ValueError(
                f"--spy-count must be between 1 and {allowed_maximum} for seed {seed}"
            )

        if args.stage in {"all", "phase1"}:
            commands.append(
                simulator_command(
                    args.dataset_root / f"phase1_seed{seed}",
                    plan_path,
                    1,
                    seed,
                    node_count,
                    args.packets,
                    args.duration,
                    args.grace,
                )
            )
        if args.stage in {"all", "phase2"}:
            for count in range(1, maximum + 1):
                commands.append(
                    simulator_command(
                        args.dataset_root / f"phase2_seed{seed}_spies{count}",
                        plan_path,
                        2,
                        seed,
                        node_count,
                        args.packets,
                        args.duration,
                        args.grace,
                        spy_count=count,
                        spy_method=args.spy_method,
                    )
                )
        if args.stage in {"all", "phase3"}:
            for p in P_VALUES:
                commands.append(
                    simulator_command(
                        args.dataset_root / f"phase3_p{p}_seed{seed}",
                        plan_path,
                        3,
                        seed,
                        node_count,
                        args.packets,
                        args.duration,
                        args.grace,
                        p=p,
                    )
                )
        if args.stage in {"all", "phase4"}:
            for p in P_VALUES:
                commands.append(
                    simulator_command(
                        args.dataset_root / f"phase4_p{p}_seed{seed}_spies{chosen}",
                        plan_path,
                        4,
                        seed,
                        node_count,
                        args.packets,
                        args.duration,
                        args.grace,
                        p=p,
                        spy_count=chosen,
                        spy_method=args.spy_method,
                    )
                )
        if args.stage in {"all", "phase5"}:
            for p in P_VALUES:
                for delay_mode in DELAY_MODES:
                    commands.append(
                        simulator_command(
                            args.dataset_root
                            / f"phase5_p{p}_seed{seed}_spies{chosen}_delay_{delay_mode}",
                            plan_path,
                            5,
                            seed,
                            node_count,
                            args.packets,
                            args.duration,
                            args.grace,
                            p=p,
                            spy_count=chosen,
                            spy_method=args.spy_method,
                            delay_mode=delay_mode,
                        )
                    )
    return commands


def parse_args():
    parser = argparse.ArgumentParser(description="Run the required seeded experiment matrix")
    parser.add_argument(
        "--stage",
        choices=["all", "phase1", "phase2", "phase3", "phase4", "phase5"],
        required=True,
    )
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets"))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--packets", type=int, default=config.DEFAULT_NUM_PACKETS)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument(
        "--grace",
        type=float,
        default=config.DEFAULT_PROPAGATION_GRACE_SECONDS,
        help="seconds to wait after the last packet is injected",
    )
    parser.add_argument("--spy-count", type=int, default=None)
    parser.add_argument("--max-spy-count", type=int, default=None)
    parser.add_argument(
        "--spy-method",
        choices=["random", "high_degree", "cluster_spread"],
        default="cluster_spread",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    commands = build_commands(args)
    print(f"Prepared {len(commands)} runs")
    for command in commands:
        print(" ".join(command))
        if not args.dry_run:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
