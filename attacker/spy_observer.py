from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .deliberate_delay import DeliberateDelayPolicy
from .io import append_jsonl
from .models import PacketState, SpyObservation


ObservationSink = Callable[[SpyObservation], None]


@dataclass(slots=True)
class SpyObserver:
    """Network-independent behavior mixed into a bribed node by the network module."""

    spy_id: str
    delay_policy: DeliberateDelayPolicy
    observation_path: Path | None = None
    sink: ObservationSink | None = None
    observations: list[SpyObservation] = field(default_factory=list, init=False)

    def record_receive(
        self,
        packet_id: str,
        from_node: str,
        received_at: float,
        state: PacketState,
    ) -> SpyObservation:
        observation = SpyObservation(
            packet_id=packet_id,
            spy_id=self.spy_id,
            from_node=from_node,
            received_at=received_at,
            state=state,
        )
        self.observations.append(observation)
        if self.observation_path is not None:
            append_jsonl(self.observation_path, observation.to_dict())
        if self.sink is not None:
            self.sink(observation)
        return observation

    def forwarding_delay(self, base_link_delay: float) -> float:
        """Returns only the extra malicious delay, never the normal link delay."""
        return self.delay_policy.delay_for(base_link_delay)
