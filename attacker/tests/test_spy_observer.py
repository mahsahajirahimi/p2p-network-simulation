import json

from attacker.deliberate_delay import DelayMode, DeliberateDelayPolicy
from attacker.spy_observer import SpyObserver


def test_observer_writes_attacker_safe_record(tmp_path) -> None:
    output = tmp_path / "spy.jsonl"
    observer = SpyObserver(
        spy_id="s1",
        delay_policy=DeliberateDelayPolicy(DelayMode.NONE),
        observation_path=output,
    )
    observer.record_receive("p1", "n2", 1.5, "STEM")
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["packet_id"] == "p1"
    assert record["from_node"] == "n2"
    assert "true_source" not in record
    assert "created_at" not in record
