from __future__ import annotations

import hashlib
import heapq
import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from .baseline_attack import _deterministic_fallback
from .models import AttackPrediction, SpyObservation, Topology


@dataclass(frozen=True, slots=True)
class _SimulatedObservation:
    spy_id: str
    from_node: str
    received_at: float
    state: str


class AdvancedTimingAttack:
    """Monte-Carlo source estimator using relative spy arrival times.

    Creation time is deliberately not used. Each candidate source is simulated
    repeatedly under the known topology, link delays, jitter, and Dandelion p.
    """

    name = "advanced_timing"

    def __init__(
        self,
        topology: Topology,
        spy_nodes: Sequence[str],
        p: float,
        mode: str = "dandelion",
        delay_mode: str = "none",
        embargo_seconds: float = 3.0,
        simulations_per_candidate: int = 75,
        seed: int = 0,
    ) -> None:
        if not 0.0 <= p <= 1.0:
            raise ValueError("p must be between 0 and 1")
        if simulations_per_candidate <= 0:
            raise ValueError("simulations_per_candidate must be positive")
        if mode not in {"broadcast", "dandelion"}:
            raise ValueError("mode must be broadcast or dandelion")
        if delay_mode not in {"none", "half", "maximum", "random"}:
            raise ValueError("Unsupported delay_mode")
        if embargo_seconds <= 0:
            raise ValueError("embargo_seconds must be positive")
        unknown_spies = set(spy_nodes) - set(topology.node_ids)
        if unknown_spies:
            raise ValueError(f"Unknown spy nodes: {sorted(unknown_spies)}")
        self.topology = topology
        self.spy_nodes = frozenset(spy_nodes)
        self.p = p
        self.mode = mode
        self.delay_mode = delay_mode
        self.embargo_seconds = embargo_seconds
        self.simulations_per_candidate = simulations_per_candidate
        self.seed = seed
        delays = [edge.base_delay for edge in topology.edges if edge.base_delay > 0]
        self._time_scale = statistics.median(delays) if delays else 1.0

    def estimate(
        self,
        packet_id: str,
        observations: Sequence[SpyObservation],
        candidate_nodes: Sequence[str],
    ) -> AttackPrediction:
        candidates = sorted(set(candidate_nodes) - self.spy_nodes)
        if not candidates:
            raise ValueError("At least one honest candidate node is required")
        relevant = [item for item in observations if item.packet_id == packet_id]
        observed = _first_observation_per_spy(relevant)
        if not observed:
            fallback = _deterministic_fallback(packet_id, candidates, self.seed)
            return AttackPrediction(
                packet_id=packet_id,
                predicted_source=fallback,
                method=self.name,
                confidence=1.0 / len(candidates),
                observation_count=0,
            )

        candidate_scores: list[tuple[float, str]] = []
        for candidate in candidates:
            trial_scores: list[float] = []
            for trial in range(self.simulations_per_candidate):
                rng = random.Random(_derived_seed(self.seed, packet_id, candidate, trial))
                simulated = self._simulate(candidate, rng)
                trial_scores.append(self._score(observed, simulated))
            trial_scores.sort()
            retained = max(1, math.ceil(len(trial_scores) * 0.10))
            candidate_scores.append((statistics.fmean(trial_scores[:retained]), candidate))

        candidate_scores.sort(key=lambda item: (item[0], item[1]))
        best_score, best_candidate = candidate_scores[0]
        if len(candidate_scores) == 1:
            confidence = 1.0
        else:
            second_score = candidate_scores[1][0]
            confidence = max(0.0, min(1.0, (second_score - best_score) / (second_score + 1e-12)))
        return AttackPrediction(
            packet_id=packet_id,
            predicted_source=best_candidate,
            method=self.name,
            confidence=confidence,
            observation_count=len(relevant),
        )

    def _simulate(
        self, source: str, rng: random.Random
    ) -> dict[str, _SimulatedObservation]:
        # (arrival_time, sequence, node, sender, state)
        queue: list[tuple[float, int, str, str, str]] = []
        sequence = 0
        source_neighbors = list(self.topology.neighbors(source))
        if not source_neighbors:
            return {}
        if self.mode == "broadcast":
            initial_forwards = [
                (target, delay, "FLUFF") for target, delay in source_neighbors
            ]
        else:
            target, delay = rng.choice(source_neighbors)
            initial_forwards = [(target, delay, "STEM")]
        for first_target, first_delay, first_state in initial_forwards:
            sequence += 1
            heapq.heappush(
                queue,
                (
                    _jittered(first_delay, rng)
                    + self._malicious_delay(source, first_delay, rng),
                    sequence,
                    first_target,
                    source,
                    first_state,
                ),
            )
        if self.mode == "dandelion":
            # Model the source-side fail-safe used by the real network node.
            for target, base_delay in source_neighbors:
                sequence += 1
                heapq.heappush(
                    queue,
                    (
                        self.embargo_seconds
                        + _jittered(base_delay, rng),
                        sequence,
                        target,
                        source,
                        "FLUFF",
                    ),
                )
        seen_stem: set[str] = {source}
        seen_fluff: set[str] = set()
        spy_observations: dict[str, _SimulatedObservation] = {}

        while queue:
            arrival, _, node_id, sender, state = heapq.heappop(queue)
            if state == "FLUFF":
                if node_id in seen_fluff:
                    continue
                seen_fluff.add(node_id)
            else:
                if node_id in seen_stem:
                    continue
                seen_stem.add(node_id)
            if node_id in self.spy_nodes and node_id not in spy_observations:
                spy_observations[node_id] = _SimulatedObservation(
                    spy_id=node_id,
                    from_node=sender,
                    received_at=arrival,
                    state=state,
                )

            neighbors = [
                (neighbor, delay)
                for neighbor, delay in self.topology.neighbors(node_id)
                if neighbor != sender
            ]
            if not neighbors:
                continue
            if self.mode == "dandelion" and state == "STEM" and rng.random() < self.p:
                forwards = [(*rng.choice(neighbors), "STEM")]
            else:
                if state == "STEM":
                    seen_fluff.add(node_id)
                forwards = [(neighbor, delay, "FLUFF") for neighbor, delay in neighbors]
            for target, base_delay, next_state in forwards:
                sequence += 1
                heapq.heappush(
                    queue,
                    (
                        arrival
                        + _jittered(base_delay, rng)
                        + self._malicious_delay(node_id, base_delay, rng),
                        sequence,
                        target,
                        node_id,
                        next_state,
                    ),
                )
        return spy_observations

    def _malicious_delay(
        self, sender: str, base_delay: float, rng: random.Random
    ) -> float:
        if sender not in self.spy_nodes or self.delay_mode == "none":
            return 0.0
        if self.delay_mode == "half":
            return 0.5 * base_delay
        if self.delay_mode == "maximum":
            return base_delay
        return rng.uniform(0.0, base_delay)

    def _score(
        self,
        observed: dict[str, SpyObservation],
        simulated: dict[str, _SimulatedObservation],
    ) -> float:
        common_spies = sorted(observed.keys() & simulated.keys())
        missing_count = len(observed.keys() ^ simulated.keys())
        if not common_spies:
            return 1000.0 + 10.0 * missing_count

        observed_origin = min(item.received_at for item in observed.values())
        simulated_origin = min(item.received_at for item in simulated.values())
        time_error = statistics.fmean(
            abs(
                (observed[spy].received_at - observed_origin)
                - (simulated[spy].received_at - simulated_origin)
            )
            / self._time_scale
            for spy in common_spies
        )
        sender_penalty = statistics.fmean(
            observed[spy].from_node != simulated[spy].from_node for spy in common_spies
        )
        state_penalty = statistics.fmean(
            observed[spy].state != simulated[spy].state for spy in common_spies
        )
        return time_error + 1.5 * sender_penalty + 0.5 * state_penalty + 2.0 * missing_count


def _first_observation_per_spy(
    observations: Sequence[SpyObservation],
) -> dict[str, SpyObservation]:
    result: dict[str, SpyObservation] = {}
    for observation in observations:
        previous = result.get(observation.spy_id)
        if previous is None or observation.received_at < previous.received_at:
            result[observation.spy_id] = observation
    return result


def _jittered(base_delay: float, rng: random.Random) -> float:
    return base_delay + rng.uniform(-0.2 * base_delay, 0.2 * base_delay)


def _derived_seed(base_seed: int, packet_id: str, candidate: str, trial: int) -> int:
    raw = f"{base_seed}:{packet_id}:{candidate}:{trial}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
