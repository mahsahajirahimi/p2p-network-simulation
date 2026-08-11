import json

from attacker.io import load_topology, network_topology_to_model


def test_network_topology_adapter_converts_ids_and_milliseconds(tmp_path) -> None:
    network_topology = {
        "nodes": [
            {"index": 0, "position": [10, 20], "cluster": 0, "port": 15000},
            {"index": 1, "position": [30, 40], "cluster": None, "port": 15001},
        ],
        "edges": [{"a": 0, "b": 1, "delay_base_ms": 50.0}],
    }
    topology = network_topology_to_model(network_topology, {0: "n0", 1: "n1"})
    assert topology.base_delay("n0", "n1") == 0.05
    assert topology.node("n0").cluster_id == "0"

    topology_path = tmp_path / "topology.json"
    ids_path = tmp_path / "node_ids.json"
    topology_path.write_text(json.dumps(network_topology), encoding="utf-8")
    ids_path.write_text(json.dumps({"0": "n0", "1": "n1"}), encoding="utf-8")
    assert load_topology(topology_path).node_ids == ("n0", "n1")
