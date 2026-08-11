from network import config
from network.topology import _bfs_connected, _cluster_has_redundant_links, generate_topology


def test_generated_topology_satisfies_project_constraints() -> None:
    topology = generate_topology(seed=101)
    count = topology["num_nodes"]
    assert config.MIN_NODES <= count <= config.MAX_NODES
    assert config.MIN_CLUSTERS <= topology["num_clusters"] <= config.MAX_CLUSTERS

    adjacency = [set() for _ in range(count)]
    for edge in topology["edges"]:
        adjacency[edge["a"]].add(edge["b"])
        adjacency[edge["b"]].add(edge["a"])
        assert edge["delay_base_ms"] == edge["distance"]
    assert _bfs_connected(count, adjacency)
    assert all(adjacency)

    cluster_of = [node["cluster"] for node in topology["nodes"]]
    for cluster_id in range(topology["num_clusters"]):
        assert _cluster_has_redundant_links(
            count, adjacency, cluster_of, cluster_id
        )


def test_seeded_topology_is_identical_when_node_count_is_reused() -> None:
    generated = generate_topology(seed=505)
    regenerated = generate_topology(
        num_nodes=generated["num_nodes"],
        seed=505,
    )
    assert regenerated == generated
