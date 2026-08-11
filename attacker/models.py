from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal


PacketState = Literal["STEM", "FLUFF"]


@dataclass(frozen=True, slots=True)
class NodeInfo:
    node_id: str
    cluster_id: str | None = None
    x: float | None = None
    y: float | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NodeInfo":
        return cls(
            node_id=str(value["node_id"]),
            cluster_id=value.get("cluster_id"),
            x=_optional_float(value.get("x")),
            y=_optional_float(value.get("y")),
        )


@dataclass(frozen=True, slots=True)
class EdgeInfo:
    source: str
    target: str
    base_delay: float

    def __post_init__(self) -> None:
        if self.source == self.target:
            raise ValueError("Self-links are not supported")
        if self.base_delay < 0:
            raise ValueError("base_delay must be non-negative")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EdgeInfo":
        return cls(
            source=str(value["source"]),
            target=str(value["target"]),
            base_delay=float(value["base_delay"]),
        )


@dataclass(frozen=True, slots=True)
class Topology:
    nodes: tuple[NodeInfo, ...]
    edges: tuple[EdgeInfo, ...]
    _adjacency: dict[str, tuple[tuple[str, float], ...]] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Duplicate node_id in topology")
        known = set(node_ids)
        adjacency: dict[str, list[tuple[str, float]]] = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"Unknown endpoint in edge {edge.source}-{edge.target}")
            adjacency[edge.source].append((edge.target, edge.base_delay))
            adjacency[edge.target].append((edge.source, edge.base_delay))
        object.__setattr__(
            self,
            "_adjacency",
            {node_id: tuple(neighbors) for node_id, neighbors in adjacency.items()},
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Topology":
        raw_nodes = value.get("nodes", [])
        nodes = tuple(
            NodeInfo(node_id=str(node)) if isinstance(node, str) else NodeInfo.from_dict(node)
            for node in raw_nodes
        )
        return cls(
            nodes=nodes,
            edges=tuple(EdgeInfo.from_dict(edge) for edge in value.get("edges", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.node_id for node in self.nodes)

    def neighbors(self, node_id: str) -> tuple[tuple[str, float], ...]:
        try:
            return self._adjacency[node_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node_id: {node_id}") from exc

    def degree(self, node_id: str) -> int:
        return len(self.neighbors(node_id))

    def base_delay(self, source: str, target: str) -> float:
        for neighbor, delay in self.neighbors(source):
            if neighbor == target:
                return delay
        raise KeyError(f"No link between {source!r} and {target!r}")

    def node(self, node_id: str) -> NodeInfo:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(f"Unknown node_id: {node_id}")


@dataclass(frozen=True, slots=True)
class SpyObservation:
    packet_id: str
    spy_id: str
    from_node: str
    received_at: float
    state: PacketState

    def __post_init__(self) -> None:
        normalized = self.state.upper()
        if normalized not in {"STEM", "FLUFF"}:
            raise ValueError("state must be STEM or FLUFF")
        object.__setattr__(self, "state", normalized)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SpyObservation":
        return cls(
            packet_id=str(value["packet_id"]),
            spy_id=str(value["spy_id"]),
            from_node=str(value["from_node"]),
            received_at=float(value["received_at"]),
            state=str(value["state"]).upper(),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PacketTruth:
    packet_id: str
    true_source: str
    created_at: float
    t80: float

    def __post_init__(self) -> None:
        if self.t80 < 0:
            raise ValueError("t80 must be non-negative")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PacketTruth":
        return cls(
            packet_id=str(value["packet_id"]),
            true_source=str(value["true_source"]),
            created_at=float(value["created_at"]),
            t80=float(value["t80"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NetworkEvent:
    packet_id: str
    node_id: str
    action: str
    timestamp: float
    peer_id: str | None = None
    state: PacketState | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NetworkEvent":
        raw_state = value.get("state")
        return cls(
            packet_id=str(value["packet_id"]),
            node_id=str(value["node_id"]),
            action=str(value["action"]).upper(),
            timestamp=float(value["timestamp"]),
            peer_id=value.get("peer_id"),
            state=str(raw_state).upper() if raw_state is not None else None,  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class AttackPrediction:
    packet_id: str
    predicted_source: str
    method: str
    confidence: float | None = None
    observation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AttackMetrics:
    total_packets: int
    correct_guesses: int
    accuracy: float
    bribed_nodes: int
    score_adv: float
    mean_t80: float
    median_t80: float
    score_honest: float
    missing_observation_packets: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def group_observations(
    observations: Iterable[SpyObservation],
) -> dict[str, list[SpyObservation]]:
    grouped: dict[str, list[SpyObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.packet_id, []).append(observation)
    for packet_observations in grouped.values():
        packet_observations.sort(
            key=lambda item: (item.received_at, item.spy_id, item.from_node)
        )
    return grouped


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
