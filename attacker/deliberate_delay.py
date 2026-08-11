from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum


class DelayMode(str, Enum):
    NONE = "none"
    HALF = "half"
    MAXIMUM = "maximum"
    RANDOM = "random"


@dataclass(slots=True)
class DeliberateDelayPolicy:
    mode: DelayMode = DelayMode.NONE
    seed: int = 0
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def delay_for(self, base_link_delay: float) -> float:
        if base_link_delay < 0:
            raise ValueError("base_link_delay must be non-negative")
        if self.mode is DelayMode.NONE:
            delay = 0.0
        elif self.mode is DelayMode.HALF:
            delay = 0.5 * base_link_delay
        elif self.mode is DelayMode.MAXIMUM:
            delay = base_link_delay
        elif self.mode is DelayMode.RANDOM:
            delay = self._rng.uniform(0.0, base_link_delay)
        else:
            raise ValueError(f"Unsupported delay mode: {self.mode}")
        return min(max(delay, 0.0), base_link_delay)
