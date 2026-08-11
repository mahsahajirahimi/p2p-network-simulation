"""Fail-fast validation of datasets before figures and report writing."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from attacker.io import load_json, load_truth


REQUIRED_RUN_FILES = (
    "manifest.json",
    "topology.json",
    "node_ids.json",
    "source_plan.json",
    "simulation.log",
    "ground_truth.log",
    "spy_observations.jsonl",
    "reference_truth.jsonl",
)
EXPECTED_P_VALUES = {0.9, 0.5, 0.1}
EXPECTED_DELAY_MODES = {"none", "half", "maximum", "random"}


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def _connected(adjacency: list[set[int]], ignored_edge: tuple[int, int] | None = None) -> bool:
    if not adjacency:
        return False
    seen = {0}
    queue = deque([0])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            if ignored_edge is not None and {node, neighbor} == set(ignored_edge):
                continue
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return len(seen) == len(adjacency)


def validate_topology(run_name: str, topology: dict[str, Any], errors: list[str]) -> int:
    nodes = topology.get("nodes", [])
    edges = topology.get("edges", [])
    node_count = len(nodes)
    if not 20 <= node_count <= 30:
        fail(errors, f"{run_name}: topology must contain 20-30 nodes, got {node_count}")
    if topology.get("plane_size") != 1000:
        fail(errors, f"{run_name}: plane_size must be 1000")
    cluster_count = int(topology.get("num_clusters", -1))
    if not 4 <= cluster_count <= 6:
        fail(errors, f"{run_name}: expected 4-6 clusters, got {cluster_count}")

    indices = {int(node["index"]) for node in nodes}
    if indices != set(range(node_count)):
        fail(errors, f"{run_name}: node indices must be contiguous from zero")
        return node_count
    ports = [int(node["port"]) for node in nodes]
    if len(ports) != len(set(ports)):
        fail(errors, f"{run_name}: every node must have a distinct UDP port")
    for node in nodes:
        x, y = node["position"]
        if not (0 <= float(x) <= 1000 and 0 <= float(y) <= 1000):
            fail(errors, f"{run_name}: node {node['index']} lies outside the 1000x1000 plane")

    adjacency = [set() for _ in range(node_count)]
    edge_pairs: set[tuple[int, int]] = set()
    for edge in edges:
        left, right = int(edge["a"]), int(edge["b"])
        pair = tuple(sorted((left, right)))
        if left == right or pair in edge_pairs:
            fail(errors, f"{run_name}: duplicate or self edge {left}-{right}")
            continue
        edge_pairs.add(pair)
        adjacency[left].add(right)
        adjacency[right].add(left)
        x1, y1 = nodes[left]["position"]
        x2, y2 = nodes[right]["position"]
        distance = math.hypot(float(x1) - float(x2), float(y1) - float(y2))
        if not math.isclose(float(edge["distance"]), distance, rel_tol=1e-9, abs_tol=1e-9):
            fail(errors, f"{run_name}: incorrect Euclidean distance on edge {left}-{right}")
        if not math.isclose(
            float(edge["delay_base_ms"]), distance, rel_tol=1e-9, abs_tol=1e-9
        ):
            fail(errors, f"{run_name}: base delay must be 1 ms per distance unit on {left}-{right}")

    if any(not neighbors for neighbors in adjacency):
        fail(errors, f"{run_name}: topology contains an isolated node")
    if adjacency and not _connected(adjacency):
        fail(errors, f"{run_name}: topology is disconnected")

    cluster_by_node = {int(node["index"]): node.get("cluster") for node in nodes}
    for cluster_id in range(cluster_count):
        members = {index for index, cluster in cluster_by_node.items() if cluster == cluster_id}
        if not members:
            fail(errors, f"{run_name}: cluster {cluster_id} has no nodes")
            continue
        external_edges = [
            pair
            for pair in edge_pairs
            if (pair[0] in members) != (pair[1] in members)
        ]
        if len(external_edges) < 2:
            fail(errors, f"{run_name}: cluster {cluster_id} has fewer than two external links")
        for edge in external_edges:
            if not _connected(adjacency, ignored_edge=edge):
                fail(
                    errors,
                    f"{run_name}: external link {edge[0]}-{edge[1]} is a single point of failure",
                )
    return node_count


def read_source_events(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    events = value.get("events", [])
    if not isinstance(events, list):
        raise ValueError(f"{path}: events must be a list")
    return events


def validate_run(
    run_dir: Path,
    expected_packets: int,
    errors: list[str],
) -> dict[str, Any] | None:
    missing_files = [name for name in REQUIRED_RUN_FILES if not (run_dir / name).is_file()]
    if missing_files:
        fail(errors, f"{run_dir.name}: missing files {missing_files}")
        return None

    manifest = load_json(run_dir / "manifest.json")
    topology = load_json(run_dir / "topology.json")
    node_ids = load_json(run_dir / "node_ids.json")
    phase = int(manifest["phase"])
    seed = int(manifest["seed"])
    p = float(manifest["p"])
    spies = {str(node) for node in manifest.get("spy_nodes", [])}
    node_count = validate_topology(run_dir.name, topology, errors)
    known_nodes = {str(node_id) for node_id in node_ids.values()}
    if len(known_nodes) != node_count:
        fail(errors, f"{run_dir.name}: node_ids.json must map every topology node uniquely")

    maximum_spies = math.floor(0.30 * node_count)
    if len(spies) > maximum_spies:
        fail(errors, f"{run_dir.name}: {len(spies)} spies exceeds 30% limit ({maximum_spies})")
    if not spies.issubset(known_nodes):
        fail(errors, f"{run_dir.name}: manifest contains unknown spy IDs")
    if phase in {1, 3} and spies:
        fail(errors, f"{run_dir.name}: phase {phase} must run without spies")
    if phase in {2, 4, 5} and not spies:
        fail(errors, f"{run_dir.name}: phase {phase} requires at least one spy")
    expected_mode = "broadcast" if phase in {1, 2} else "dandelion"
    if manifest.get("mode") != expected_mode:
        fail(errors, f"{run_dir.name}: phase {phase} must use {expected_mode}")
    if phase != 5 and manifest.get("delay_mode", "none") != "none":
        fail(errors, f"{run_dir.name}: malicious delay is allowed only in phase 5")

    truth = load_truth(run_dir / "reference_truth.jsonl")
    if len(truth) != expected_packets:
        fail(errors, f"{run_dir.name}: expected {expected_packets} truth records, got {len(truth)}")
    truth_ids = {item.packet_id for item in truth}
    if len(truth_ids) != len(truth):
        fail(errors, f"{run_dir.name}: duplicate packet ID in reference truth")
    if any(item.t80 < 0 for item in truth):
        fail(errors, f"{run_dir.name}: negative T80 value")
    dishonest_sources = {item.true_source for item in truth} & spies
    if dishonest_sources:
        fail(errors, f"{run_dir.name}: bribed sources found: {sorted(dishonest_sources)}")

    events = read_source_events(run_dir / "source_plan.json")
    if len(events) != expected_packets:
        fail(errors, f"{run_dir.name}: expected {expected_packets} source events, got {len(events)}")
    event_ids = {str(event["packet_id"]) for event in events}
    if len(event_ids) != len(events):
        fail(errors, f"{run_dir.name}: duplicate packet ID in source plan")
    if event_ids != truth_ids:
        fail(errors, f"{run_dir.name}: source plan packet IDs differ from reference truth")
    invalid_sources = {str(event["source"]) for event in events} - known_nodes
    if invalid_sources:
        fail(errors, f"{run_dir.name}: unknown source IDs {sorted(invalid_sources)}")
    planned_dishonest = {str(event["source"]) for event in events} & spies
    if planned_dishonest:
        fail(errors, f"{run_dir.name}: source plan uses spies {sorted(planned_dishonest)}")
    if int(manifest.get("packet_count", -1)) != expected_packets:
        fail(errors, f"{run_dir.name}: manifest packet_count must equal {expected_packets}")

    observed_packets: set[str] = set()
    with (run_dir / "spy_observations.jsonl").open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(errors, f"{run_dir.name}:{line_number}: invalid spy JSON: {exc}")
                continue
            forbidden = {"true_source", "created_at"} & record.keys()
            if forbidden:
                fail(errors, f"{run_dir.name}:{line_number}: leaked truth fields {sorted(forbidden)}")
            required = {"packet_id", "spy_id", "from_node", "received_at", "state"}
            if not required.issubset(record):
                fail(errors, f"{run_dir.name}:{line_number}: incomplete spy observation")
                continue
            if str(record["spy_id"]) not in spies:
                fail(errors, f"{run_dir.name}:{line_number}: observation from unselected spy")
            if str(record["from_node"]) not in known_nodes:
                fail(errors, f"{run_dir.name}:{line_number}: unknown direct sender")
            if str(record["state"]).upper() not in {"STEM", "FLUFF"}:
                fail(errors, f"{run_dir.name}:{line_number}: invalid packet state")
            observed_packets.add(str(record["packet_id"]))
    if observed_packets - truth_ids:
        fail(errors, f"{run_dir.name}: observations contain unknown packet IDs")

    return {
        "manifest": manifest,
        "phase": phase,
        "seed": seed,
        "p": p,
        "spies": spies,
        "node_count": node_count,
        "maximum_spies": maximum_spies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate final experiment coverage")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--expected-packets", type=int, default=200)
    parser.add_argument("--minimum-seeds", type=int, default=5)
    args = parser.parse_args()

    run_dirs = sorted(path.parent for path in args.dataset_root.glob("*/manifest.json"))
    errors: list[str] = []
    if not run_dirs:
        fail(errors, f"no experiment runs found under {args.dataset_root}")

    scenario_seeds: dict[tuple[Any, ...], set[int]] = defaultdict(set)
    topology_by_seed: dict[int, set[str]] = defaultdict(set)
    node_ids_by_seed: dict[int, set[str]] = defaultdict(set)
    sources_by_seed: dict[int, set[str]] = defaultdict(set)
    spy_sets_by_key: dict[tuple[int, int, str], set[tuple[str, ...]]] = defaultdict(set)
    phase2_counts_by_seed: dict[int, set[int]] = defaultdict(set)
    maximum_by_seed: dict[int, int] = {}
    observed_phases: set[int] = set()
    p_by_phase: dict[int, set[float]] = defaultdict(set)
    delays_in_phase5: set[str] = set()

    for run_dir in run_dirs:
        info = validate_run(run_dir, args.expected_packets, errors)
        if info is None:
            continue
        manifest = info["manifest"]
        phase = info["phase"]
        seed = info["seed"]
        p = info["p"]
        spies = info["spies"]
        method = str(manifest.get("spy_selection_method", "none"))
        delay_mode = str(manifest.get("delay_mode", "none"))
        observed_phases.add(phase)
        p_by_phase[phase].add(p)
        maximum_by_seed[seed] = info["maximum_spies"]
        if phase == 2:
            phase2_counts_by_seed[seed].add(len(spies))
        if phase == 5:
            delays_in_phase5.add(delay_mode)

        topology_by_seed[seed].add(fingerprint(run_dir / "topology.json"))
        node_ids_by_seed[seed].add(fingerprint(run_dir / "node_ids.json"))
        sources_by_seed[seed].add(fingerprint(run_dir / "source_plan.json"))
        if spies:
            spy_sets_by_key[(seed, len(spies), method)].add(tuple(sorted(spies)))
        scenario = (
            phase,
            p if phase >= 3 else "broadcast",
            len(spies),
            delay_mode,
            method,
        )
        scenario_seeds[scenario].add(seed)

    for seed, values in topology_by_seed.items():
        if len(values) != 1:
            fail(errors, f"seed {seed}: comparisons do not reuse one topology")
    for seed, values in node_ids_by_seed.items():
        if len(values) != 1:
            fail(errors, f"seed {seed}: comparisons do not reuse one node-ID mapping")
    for seed, values in sources_by_seed.items():
        if len(values) != 1:
            fail(errors, f"seed {seed}: comparisons do not reuse one source plan")
    for key, values in spy_sets_by_key.items():
        if len(values) != 1:
            fail(errors, f"seed/count/method {key}: corresponding runs use different spy sets")
    common_maximum = min(maximum_by_seed.values()) if maximum_by_seed else 0
    for seed in maximum_by_seed:
        # Node counts may differ between seeds. Sweeping to the smallest legal
        # maximum gives every spy count the required number of comparable seeds.
        expected_counts = set(range(1, common_maximum + 1))
        if phase2_counts_by_seed[seed] != expected_counts:
            fail(
                errors,
                f"seed {seed}: phase-2 spy sweep must cover {sorted(expected_counts)}, "
                f"got {sorted(phase2_counts_by_seed[seed])}",
            )
    for scenario, seeds in scenario_seeds.items():
        if len(seeds) < args.minimum_seeds:
            fail(errors, f"scenario {scenario}: only {len(seeds)} seeds")

    missing_phases = {1, 2, 3, 4, 5} - observed_phases
    if missing_phases:
        fail(errors, f"missing phases: {sorted(missing_phases)}")
    for phase in (3, 4, 5):
        missing_p = EXPECTED_P_VALUES - p_by_phase[phase]
        if missing_p:
            fail(errors, f"phase {phase}: missing p values {sorted(missing_p)}")
    missing_delays = EXPECTED_DELAY_MODES - delays_in_phase5
    if missing_delays:
        fail(errors, f"phase 5: missing delay modes {sorted(missing_delays)}")

    if errors:
        print("Experiment validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(f"Validated {len(run_dirs)} run directories successfully")


if __name__ == "__main__":
    main()
