from __future__ import annotations

import argparse
from pathlib import Path

from attacker.io import load_topology, write_json
from attacker.spy_selector import max_bribed_nodes, select_spies


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reproducible spy sets for network runs")
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["random", "high_degree", "cluster_spread"],
        default=["random", "high_degree", "cluster_spread"],
    )
    args = parser.parse_args()

    topology = load_topology(args.topology)
    maximum = max_bribed_nodes(len(topology.nodes))
    plan = []
    for method in args.methods:
        for count in range(1, maximum + 1):
            plan.append(
                {
                    "method": method,
                    "count": count,
                    "seed": args.seed,
                    "spy_nodes": list(select_spies(topology, count, method, args.seed)),
                }
            )
    write_json(
        args.output,
        {
            "node_count": len(topology.nodes),
            "maximum_bribed_nodes": maximum,
            "plans": plan,
        },
    )


if __name__ == "__main__":
    main()
