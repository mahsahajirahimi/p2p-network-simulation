from attacker.baseline_attack import FirstSpyAttack
from attacker.models import SpyObservation


def test_first_spy_attack_guesses_first_sender() -> None:
    observations = [
        SpyObservation("p1", "s2", "n8", 2.0, "FLUFF"),
        SpyObservation("p1", "s1", "n3", 1.0, "STEM"),
    ]
    prediction = FirstSpyAttack(seed=1).estimate("p1", observations, ["n1", "n3", "n8"])
    assert prediction.predicted_source == "n3"
    assert prediction.observation_count == 2


def test_fallback_is_reproducible() -> None:
    attack = FirstSpyAttack(seed=9)
    first = attack.estimate("unseen", [], ["n1", "n2", "n3"])
    second = attack.estimate("unseen", [], ["n1", "n2", "n3"])
    assert first == second
