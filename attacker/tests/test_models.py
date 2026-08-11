from attacker.models import EdgeInfo, NodeInfo, SpyObservation, Topology, group_observations


def test_topology_is_undirected() -> None:
    topology = Topology(
        nodes=(NodeInfo("n1"), NodeInfo("n2")),
        edges=(EdgeInfo("n1", "n2", 0.1),),
    )
    assert topology.neighbors("n1") == (("n2", 0.1),)
    assert topology.neighbors("n2") == (("n1", 0.1),)
    assert topology.base_delay("n2", "n1") == 0.1


def test_observations_are_grouped_and_sorted() -> None:
    observations = [
        SpyObservation("p1", "s2", "n2", 2.0, "FLUFF"),
        SpyObservation("p1", "s1", "n1", 1.0, "STEM"),
    ]
    grouped = group_observations(observations)
    assert [item.spy_id for item in grouped["p1"]] == ["s1", "s2"]
