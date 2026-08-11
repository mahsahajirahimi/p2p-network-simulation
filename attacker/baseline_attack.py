from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence

from .models import AttackPrediction, SpyObservation


class FirstSpyAttack:
    """Baseline: guess the sender that delivered the first observation to a spy."""

    name = "first_spy"

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    def estimate(
        self,
        packet_id: str,
        observations: Sequence[SpyObservation],
        candidate_nodes: Sequence[str],
    ) -> AttackPrediction:
        if not candidate_nodes:
            raise ValueError("candidate_nodes cannot be empty")
        relevant = [item for item in observations if item.packet_id == packet_id]
        if relevant:
            earliest = min(
                relevant,
                key=lambda item: (item.received_at, item.spy_id, item.from_node),
            )
            guess = earliest.from_node
            confidence = 1.0 if len(relevant) == 1 else 1.0 / len(relevant)
        else:
            guess = _deterministic_fallback(packet_id, candidate_nodes, self.seed)
            confidence = 1.0 / len(candidate_nodes)
        return AttackPrediction(
            packet_id=packet_id,
            predicted_source=guess,
            method=self.name,
            confidence=confidence,
            observation_count=len(relevant),
        )


def _deterministic_fallback(packet_id: str, candidates: Sequence[str], seed: int) -> str:
    digest = hashlib.sha256(f"{seed}:{packet_id}".encode("utf-8")).digest()
    local_seed = int.from_bytes(digest[:8], "big")
    return random.Random(local_seed).choice(sorted(candidates))
