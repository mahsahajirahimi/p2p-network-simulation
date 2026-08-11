from __future__ import annotations

import statistics
from collections.abc import Sequence

from .models import AttackMetrics, AttackPrediction, PacketTruth


def evaluate_predictions(
    predictions: Sequence[AttackPrediction],
    truth: Sequence[PacketTruth],
    bribed_nodes: int,
) -> AttackMetrics:
    if bribed_nodes <= 0:
        raise ValueError("bribed_nodes must be positive")
    if not truth:
        raise ValueError("truth cannot be empty")

    prediction_by_packet = {item.packet_id: item for item in predictions}
    if len(prediction_by_packet) != len(predictions):
        raise ValueError("There must be exactly one prediction per packet_id")
    truth_ids = {item.packet_id for item in truth}
    missing = truth_ids - prediction_by_packet.keys()
    extra = prediction_by_packet.keys() - truth_ids
    if missing or extra:
        raise ValueError(
            f"Prediction/truth mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )

    correct = sum(
        prediction_by_packet[item.packet_id].predicted_source == item.true_source
        for item in truth
    )
    total = len(truth)
    accuracy = correct / total
    t80_values = [item.t80 for item in truth]
    mean_t80 = statistics.fmean(t80_values)
    median_t80 = statistics.median(t80_values)
    score_adv = accuracy / bribed_nodes
    score_honest = (1.0 / mean_t80) * (1.0 - accuracy) if mean_t80 > 0 else 0.0
    missing_observation_packets = sum(
        prediction_by_packet[item.packet_id].observation_count == 0 for item in truth
    )
    return AttackMetrics(
        total_packets=total,
        correct_guesses=correct,
        accuracy=accuracy,
        bribed_nodes=bribed_nodes,
        score_adv=score_adv,
        mean_t80=mean_t80,
        median_t80=median_t80,
        score_honest=score_honest,
        missing_observation_packets=missing_observation_packets,
    )
