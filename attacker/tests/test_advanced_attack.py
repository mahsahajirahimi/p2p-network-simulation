import random

from attacker.advanced_attack import AdvancedTimingAttack
from attacker.models import EdgeInfo, NodeInfo, SpyObservation, Topology


def test_advanced_attack_is_reproducible_and_returns_honest_candidate() -> None:
    topology = Topology(
        nodes=(NodeInfo("n1"), NodeInfo("n2"), NodeInfo("spy")),
        edges=(EdgeInfo("n1", "n2", 0.1), EdgeInfo("n2", "spy", 0.1)),
    )
    observation = SpyObservation("p1", "spy", "n2", 1.2, "STEM")
    attack = AdvancedTimingAttack(
        topology=topology,
        spy_nodes=["spy"],
        p=0.9,
        simulations_per_candidate=10,
        seed=5,
    )
    first = attack.estimate("p1", [observation], ["n1", "n2"])
    second = attack.estimate("p1", [observation], ["n1", "n2"])
    assert first == second
    assert first.predicted_source in {"n1", "n2"}


def test_dandelion_simulation_has_fluff_embargo_fallback() -> None:
    topology = Topology(
        nodes=(
            NodeInfo("n1"),
            NodeInfo("n2"),
            NodeInfo("spy1"),
            NodeInfo("spy2"),
        ),
        edges=(
            EdgeInfo("n1", "n2", 0.1),
            EdgeInfo("n1", "spy1", 0.1),
            EdgeInfo("n1", "spy2", 0.1),
        ),
    )
    attack = AdvancedTimingAttack(
        topology=topology,
        spy_nodes=["spy1", "spy2"],
        p=1.0,
        embargo_seconds=3.0,
        simulations_per_candidate=1,
        seed=7,
    )
    simulated = attack._simulate("n1", random.Random(7))
    assert any(observation.state == "FLUFF" for observation in simulated.values())
