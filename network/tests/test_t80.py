import json

import pytest

from network.simulator import SimulatorControlProtocol


def test_t80_uses_the_chronological_eighty_percent_arrival(tmp_path) -> None:
    truth = tmp_path / "truth.log"
    reference = tmp_path / "reference.jsonl"
    spies = tmp_path / "spies.jsonl"
    protocol = SimulatorControlProtocol(truth, reference, spies, 0.0, node_count=5)
    protocol._record_origin({"pid": "p1", "node_id": "n0", "t": 1.0})
    protocol._record_delivery({"pid": "p1", "node_id": "n1", "t": 1.4})
    protocol._record_delivery({"pid": "p1", "node_id": "n2", "t": 1.2})
    protocol._record_delivery({"pid": "p1", "node_id": "n3", "t": 1.3})
    assert protocol.close() == []
    record = json.loads(reference.read_text(encoding="utf-8"))
    assert record["t80"] == pytest.approx(0.4)


def test_missing_origin_is_reported_as_incomplete(tmp_path) -> None:
    protocol = SimulatorControlProtocol(
        tmp_path / "truth.log",
        tmp_path / "reference.jsonl",
        tmp_path / "spies.jsonl",
        0.0,
        node_count=5,
    )
    assert protocol.close({"missing-packet"}) == ["missing-packet"]
