from __future__ import annotations

from collections.abc import Iterable, Sequence

from .advanced_attack import AdvancedTimingAttack
from .baseline_attack import FirstSpyAttack
from .models import AttackPrediction, SpyObservation, group_observations


AttackMethod = FirstSpyAttack | AdvancedTimingAttack


class AttackerService:
    def __init__(self, method: AttackMethod, candidate_nodes: Sequence[str]) -> None:
        if not candidate_nodes:
            raise ValueError("candidate_nodes cannot be empty")
        self.method = method
        self.candidate_nodes = tuple(candidate_nodes)
        self._observations: list[SpyObservation] = []

    def register_observation(self, observation: SpyObservation) -> None:
        self._observations.append(observation)

    def register_many(self, observations: Iterable[SpyObservation]) -> None:
        self._observations.extend(observations)

    def estimate_packet(self, packet_id: str) -> AttackPrediction:
        grouped = group_observations(self._observations)
        return self.method.estimate(
            packet_id,
            grouped.get(packet_id, []),
            self.candidate_nodes,
        )

    def estimate_all(self, packet_ids: Iterable[str]) -> list[AttackPrediction]:
        grouped = group_observations(self._observations)
        return [
            self.method.estimate(
                packet_id,
                grouped.get(packet_id, []),
                self.candidate_nodes,
            )
            for packet_id in sorted(set(packet_ids))
        ]
