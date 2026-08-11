import pytest

from attacker.evaluator import evaluate_predictions
from attacker.models import AttackPrediction, PacketTruth


def test_project_scores() -> None:
    truth = [
        PacketTruth("p1", "n1", 0.0, 2.0),
        PacketTruth("p2", "n2", 0.0, 4.0),
    ]
    predictions = [
        AttackPrediction("p1", "n1", "test", observation_count=1),
        AttackPrediction("p2", "wrong", "test", observation_count=0),
    ]
    metrics = evaluate_predictions(predictions, truth, bribed_nodes=2)
    assert metrics.accuracy == pytest.approx(0.5)
    assert metrics.score_adv == pytest.approx(0.25)
    assert metrics.mean_t80 == pytest.approx(3.0)
    assert metrics.score_honest == pytest.approx((1.0 / 3.0) * 0.5)
    assert metrics.missing_observation_packets == 1
