from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from .models import AttackPrediction, PacketTruth, SpyObservation, Topology


T = TypeVar("T")


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def read_jsonl(path: str | Path, factory: Callable[[dict[str, Any]], T]) -> list[T]:
    records: list[T] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError("record is not an object")
                records.append(factory(raw))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid JSONL record at {path}:{line_number}: {exc}") from exc
    return records


def append_jsonl(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
        stream.write("\n")


def write_jsonl(path: str | Path, values: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
            stream.write("\n")


def network_topology_to_model(
    value: dict[str, Any], node_ids: dict[int | str, str]
) -> Topology:
    """Convert the network team's index/ms schema to the attacker's ID/seconds schema."""
    normalized_ids = {int(index): node_id for index, node_id in node_ids.items()}
    nodes = []
    for item in value.get("nodes", []):
        index = int(item["index"])
        position = item.get("position", (None, None))
        nodes.append(
            {
                "node_id": normalized_ids[index],
                "cluster_id": (
                    None if item.get("cluster") is None else str(item.get("cluster"))
                ),
                "x": position[0],
                "y": position[1],
            }
        )
    edges = [
        {
            "source": normalized_ids[int(edge["a"])],
            "target": normalized_ids[int(edge["b"])],
            "base_delay": float(edge["delay_base_ms"]) / 1000.0,
        }
        for edge in value.get("edges", [])
    ]
    return Topology.from_dict({"nodes": nodes, "edges": edges})


def load_topology(
    path: str | Path, node_ids_path: str | Path | None = None
) -> Topology:
    value = load_json(path)
    raw_nodes = value.get("nodes", [])
    if raw_nodes and isinstance(raw_nodes[0], dict) and "index" in raw_nodes[0]:
        ids_path = Path(node_ids_path) if node_ids_path else Path(path).with_name("node_ids.json")
        if not ids_path.exists():
            raise ValueError(
                f"Network topology schema requires the matching node_ids.json: {ids_path}"
            )
        return network_topology_to_model(value, load_json(ids_path))
    return Topology.from_dict(value)


def load_observations(path: str | Path) -> list[SpyObservation]:
    return read_jsonl(path, SpyObservation.from_dict)


def load_truth(path: str | Path) -> list[PacketTruth]:
    return read_jsonl(path, PacketTruth.from_dict)


def load_predictions(path: str | Path) -> list[AttackPrediction]:
    return read_jsonl(
        path,
        lambda value: AttackPrediction(
            packet_id=str(value["packet_id"]),
            predicted_source=str(value["predicted_source"]),
            method=str(value["method"]),
            confidence=(
                None if value.get("confidence") is None else float(value["confidence"])
            ),
            observation_count=int(value.get("observation_count", 0)),
        ),
    )


def write_predictions(path: str | Path, values: Iterable[AttackPrediction]) -> None:
    write_jsonl(path, (value.to_dict() for value in values))
