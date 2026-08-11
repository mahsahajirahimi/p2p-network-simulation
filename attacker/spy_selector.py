from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Literal

from .models import Topology


SelectionMethod = Literal["random", "high_degree", "cluster_spread"]


def max_bribed_nodes(total_nodes: int) -> int:
    if total_nodes <= 0:
        raise ValueError("total_nodes must be positive")
    return math.floor(0.30 * total_nodes)


def select_spies(
    topology: Topology,
    count: int,
    method: SelectionMethod = "cluster_spread",
    seed: int = 0,
) -> tuple[str, ...]:
    maximum = max_bribed_nodes(len(topology.nodes))
    if count < 1:
        raise ValueError("At least one spy must be selected")
    if count > maximum:
        raise ValueError(f"count={count} exceeds the 30% limit ({maximum})")

    if method == "random":
        rng = random.Random(seed)
        ranked = list(topology.node_ids)
        rng.shuffle(ranked)
        return tuple(sorted(ranked[:count]))
    if method == "high_degree":
        ranked = sorted(topology.node_ids, key=lambda node: (-topology.degree(node), node))
        return tuple(ranked[:count])
    if method == "cluster_spread":
        return _select_cluster_spread(topology, count, seed)
    raise ValueError(f"Unknown spy selection method: {method}")


def _select_cluster_spread(topology: Topology, count: int, seed: int) -> tuple[str, ...]:
    rng = random.Random(seed)
    clusters: dict[str, list[str]] = defaultdict(list)
    unclustered: list[str] = []
    for node in topology.nodes:
        if node.cluster_id is None:
            unclustered.append(node.node_id)
        else:
            clusters[node.cluster_id].append(node.node_id)

    if not clusters:
        return _farthest_first(topology, count, seed)

    for members in clusters.values():
        rng.shuffle(members)
        members.sort(key=lambda node: (-topology.degree(node), node))

    selected: list[str] = []
    ordered_clusters = sorted(clusters)
    while len(selected) < count and any(clusters.values()):
        for cluster_id in ordered_clusters:
            if clusters[cluster_id] and len(selected) < count:
                selected.append(clusters[cluster_id].pop(0))

    if len(selected) < count:
        remaining = sorted(
            (node for node in unclustered if node not in selected),
            key=lambda node: (-topology.degree(node), node),
        )
        selected.extend(remaining[: count - len(selected)])
    return tuple(sorted(selected))


def _farthest_first(topology: Topology, count: int, seed: int) -> tuple[str, ...]:
    positioned = [
        node for node in topology.nodes if node.x is not None and node.y is not None
    ]
    if len(positioned) != len(topology.nodes):
        ranked = sorted(topology.node_ids, key=lambda node: (-topology.degree(node), node))
        return tuple(ranked[:count])

    rng = random.Random(seed)
    highest_degree = max(topology.degree(node.node_id) for node in positioned)
    first_options = [node for node in positioned if topology.degree(node.node_id) == highest_degree]
    selected = [rng.choice(sorted(first_options, key=lambda item: item.node_id)).node_id]
    while len(selected) < count:
        candidates = [node for node in positioned if node.node_id not in selected]
        next_node = max(
            candidates,
            key=lambda candidate: (
                min(_distance(candidate, topology.node(chosen)) for chosen in selected),
                topology.degree(candidate.node_id),
                candidate.node_id,
            ),
        )
        selected.append(next_node.node_id)
    return tuple(sorted(selected))


def _distance(left: object, right: object) -> float:
    left_x = getattr(left, "x")
    left_y = getattr(left, "y")
    right_x = getattr(right, "x")
    right_y = getattr(right, "y")
    return math.hypot(left_x - right_x, left_y - right_y)
