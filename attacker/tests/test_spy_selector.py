import pytest

from attacker.models import EdgeInfo, NodeInfo, Topology
from attacker.spy_selector import max_bribed_nodes, select_spies


def make_topology() -> Topology:
    nodes = tuple(NodeInfo(f"n{i}", cluster_id=str(i % 2)) for i in range(10))
    edges = tuple(EdgeInfo(f"n{i}", f"n{i + 1}", 0.01) for i in range(9))
    return Topology(nodes=nodes, edges=edges)


def test_thirty_percent_limit() -> None:
    topology = make_topology()
    assert max_bribed_nodes(10) == 3
    assert len(select_spies(topology, 3, "cluster_spread", seed=7)) == 3
    with pytest.raises(ValueError):
        select_spies(topology, 4, "random", seed=7)


def test_selection_is_reproducible() -> None:
    topology = make_topology()
    assert select_spies(topology, 3, "random", seed=11) == select_spies(
        topology, 3, "random", seed=11
    )
