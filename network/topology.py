import json
import math
import random
from collections import deque

from . import config


class TopologyGenerationError(RuntimeError):
    pass


def _euclidean(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _place_nodes(rng, num_nodes):
    num_clusters = rng.randint(config.MIN_CLUSTERS, config.MAX_CLUSTERS)
    margin = config.CLUSTER_STD * 2
    cluster_centers = [
        (
            rng.uniform(margin, config.PLANE_SIZE - margin),
            rng.uniform(margin, config.PLANE_SIZE - margin),
        )
        for _ in range(num_clusters)
    ]

    positions = []
    cluster_of = []
    for _ in range(num_nodes):
        if rng.random() < config.CLUSTERED_NODE_RATIO:
            c_idx = rng.randrange(num_clusters)
            cx, cy = cluster_centers[c_idx]
            x = _clip(rng.gauss(cx, config.CLUSTER_STD), 0, config.PLANE_SIZE)
            y = _clip(rng.gauss(cy, config.CLUSTER_STD), 0, config.PLANE_SIZE)
            positions.append((x, y))
            cluster_of.append(c_idx)
        else:
            positions.append((rng.uniform(0, config.PLANE_SIZE), rng.uniform(0, config.PLANE_SIZE)))
            cluster_of.append(None)

    counts = [cluster_of.count(i) for i in range(num_clusters)]
    if any(c < 3 for c in counts):
        return None  
    return positions, cluster_of, cluster_centers


def _nearest_pair_between_groups(positions, group_a, group_b, forbidden_pairs=frozenset()):
    best = None
    for a in group_a:
        for b in group_b:
            if (a, b) in forbidden_pairs or (b, a) in forbidden_pairs:
                continue
            d = _euclidean(positions[a], positions[b])
            if best is None or d < best[2]:
                best = (a, b, d)
    return best


def _bfs_connected(num_nodes, adjacency, start=0):
    seen = {start}
    q = deque([start])
    while q:
        u = q.popleft()
        for v in adjacency[u]:
            if v not in seen:
                seen.add(v)
                q.append(v)
    return len(seen) == num_nodes


def _add_edge(edges, adjacency, degree, a, b, positions):
    if b in adjacency[a]:
        return  
    dist = _euclidean(positions[a], positions[b])
    edges.append((a, b, dist))
    adjacency[a].add(b)
    adjacency[b].add(a)
    degree[a] += 1
    degree[b] += 1


def _build_edges(rng, positions, cluster_of, num_clusters):
    n = len(positions)
    adjacency = [set() for _ in range(n)]
    degree = [0] * n
    edges = []  
    groups = {}
    for idx, c in enumerate(cluster_of):
        groups.setdefault(c, []).append(idx)

    for c, members in groups.items():
        if c is None:
            continue
        for node in members:
            candidates = sorted(
                (m for m in members if m != node),
                key=lambda m: _euclidean(positions[node], positions[m]),
            )
            for cand in candidates:
                if degree[node] >= config.MAX_DEGREE:
                    break
                if cand in adjacency[node]:
                    continue
                if degree[cand] >= config.MAX_DEGREE:
                    continue
                _add_edge(edges, adjacency, degree, node, cand, positions)
                if degree[node] >= config.MIN_DEGREE:
                    break

    scattered = [i for i, c in enumerate(cluster_of) if c is None]
    all_idx = list(range(n))
    for node in scattered:
        candidates = sorted(
            (m for m in all_idx if m != node),
            key=lambda m: _euclidean(positions[node], positions[m]),
        )
        for cand in candidates:
            if degree[node] >= config.MIN_DEGREE:
                break
            if degree[cand] >= config.MAX_DEGREE:
                continue
            _add_edge(edges, adjacency, degree, node, cand, positions)

    for node in range(n):
        attempts = 0
        while degree[node] < 1 and attempts < n:
            candidates = sorted(
                (m for m in all_idx if m != node and m not in adjacency[node]),
                key=lambda m: _euclidean(positions[node], positions[m]),
            )
            placed = False
            for cand in candidates:
                if degree[cand] < config.HARD_DEGREE_CEILING:
                    _add_edge(edges, adjacency, degree, node, cand, positions)
                    placed = True
                    break
            if not placed and candidates:
                _add_edge(edges, adjacency, degree, node, candidates[0], positions)
                placed = True
            attempts += 1
            if not placed:
                break

    cluster_groups = []
    for c in range(num_clusters):
        if c in groups:
            cluster_groups.append(groups[c])
    for node in scattered:
        cluster_groups.append([node]) 

    used_pairs = set()
    if len(cluster_groups) > 1:
        in_tree = [0]
        remaining = list(range(1, len(cluster_groups)))
        while remaining:
            best = None
            for gi in in_tree:
                for gj in remaining:
                    pair = _nearest_pair_between_groups(
                        positions, cluster_groups[gi], cluster_groups[gj], used_pairs
                    )
                    if pair is None:
                        continue
                    a, b, d = pair
                    if best is None or d < best[3]:
                        best = (gi, gj, pair, d)
            if best is None:
                break
            gi, gj, (a, b, d), _ = best
            _add_edge(edges, adjacency, degree, a, b, positions)
            used_pairs.add((a, b))
            in_tree.append(gj)
            remaining.remove(gj)


    for c in range(num_clusters):
        members = groups.get(c, [])
        if not members:
            continue
        others = [i for i in range(n) if cluster_of[i] != c]
        if not others:
            continue
        pair = _nearest_pair_between_groups(positions, members, others, used_pairs)
        if pair is not None:
            a, b, d = pair
            _add_edge(edges, adjacency, degree, a, b, positions)
            used_pairs.add((a, b))

    return edges, adjacency, degree


def _cluster_has_redundant_links(n, adjacency, cluster_of, cluster_id):

    inter_edges = []
    for a in range(n):
        if cluster_of[a] != cluster_id:
            continue
        for b in adjacency[a]:
            if cluster_of[b] != cluster_id:
                inter_edges.append((a, b))
    if len(inter_edges) < config.MIN_INDEPENDENT_CLUSTER_LINKS:
        return False
    for (a, b) in inter_edges:
        adjacency[a].discard(b)
        adjacency[b].discard(a)
        ok = _bfs_connected(n, adjacency)
        adjacency[a].add(b)
        adjacency[b].add(a)
        if not ok:
            return False
    return True


def generate_topology(num_nodes=None, seed=None, max_attempts=100):

    if num_nodes is not None and not config.MIN_NODES <= num_nodes <= config.MAX_NODES:
        raise ValueError(
            f"num_nodes must be between {config.MIN_NODES} and {config.MAX_NODES}"
        )

    if seed is None:
        seed = random.randrange(1_000_000_000)
    base_rng = random.Random(seed)
    # Draw the random node count exactly once, outside the retry loop. Consuming
    # this value even when num_nodes is explicit keeps seeded regeneration
    # identical to the original random-sized topology.
    randomly_selected_count = base_rng.randint(config.MIN_NODES, config.MAX_NODES)
    n = num_nodes if num_nodes is not None else randomly_selected_count

    for attempt in range(max_attempts):
        attempt_seed = base_rng.randrange(1_000_000_000)
        rng = random.Random(attempt_seed)

        placement = _place_nodes(rng, n)
        if placement is None:
            continue
        positions, cluster_of, cluster_centers = placement
        num_clusters = len(cluster_centers)

        edges, adjacency, degree = _build_edges(rng, positions, cluster_of, num_clusters)

        if not _bfs_connected(n, adjacency):
            continue
        if any(degree[i] == 0 for i in range(n)):
            continue
        if not all(
            _cluster_has_redundant_links(n, adjacency, cluster_of, c)
            for c in range(num_clusters)
        ):
            continue

        nodes = []
        for i in range(n):
            nodes.append({
                "index": i,
                "position": positions[i],
                "cluster": cluster_of[i],
                "port": config.NODE_BASE_PORT + i,
            })

        edge_list = []
        for (a, b, dist) in edges:
            edge_list.append({
                "a": a,
                "b": b,
                "distance": dist,
                "delay_base_ms": dist * config.DELAY_MS_PER_UNIT_DISTANCE,
            })

        return {
            "seed": seed,
            "attempt_seed": attempt_seed,
            "num_nodes": n,
            "num_clusters": num_clusters,
            "cluster_centers": cluster_centers,
            "plane_size": config.PLANE_SIZE,
            "nodes": nodes,
            "edges": edge_list,
        }

    raise TopologyGenerationError(
        f"Could not generate a valid topology satisfying all constraints after {max_attempts} attempts."
    )


def peers_of(topology, node_index):
    """Return list of {peer_index, delay_base_ms} for a given node."""
    peers = []
    for e in topology["edges"]:
        if e["a"] == node_index:
            peers.append({"peer_index": e["b"], "delay_base_ms": e["delay_base_ms"]})
        elif e["b"] == node_index:
            peers.append({"peer_index": e["a"], "delay_base_ms": e["delay_base_ms"]})
    return peers


def save_topology(topology, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(topology, f, ensure_ascii=False, indent=2)


def load_topology(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    topo = generate_topology(seed=42)
    n = topo["num_nodes"]
    degrees = [0] * n
    for e in topo["edges"]:
        degrees[e["a"]] += 1
        degrees[e["b"]] += 1
    print(f"nodes={n} clusters={topo['num_clusters']} edges={len(topo['edges'])}")
    print(f"degree min={min(degrees)} max={max(degrees)} avg={sum(degrees)/n:.2f}")
