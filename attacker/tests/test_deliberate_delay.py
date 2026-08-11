import pytest

from attacker.deliberate_delay import DelayMode, DeliberateDelayPolicy


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (DelayMode.NONE, 0.0),
        (DelayMode.HALF, 0.05),
        (DelayMode.MAXIMUM, 0.1),
    ],
)
def test_deterministic_delay_modes(mode: DelayMode, expected: float) -> None:
    assert DeliberateDelayPolicy(mode=mode).delay_for(0.1) == pytest.approx(expected)


def test_random_delay_never_exceeds_base_delay() -> None:
    policy = DeliberateDelayPolicy(mode=DelayMode.RANDOM, seed=2)
    values = [policy.delay_for(0.1) for _ in range(100)]
    assert all(0.0 <= value <= 0.1 for value in values)
