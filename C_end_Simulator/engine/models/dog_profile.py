"""
DogProfile —— 狗的长期属性

包含:
  - dog_id, breed_size, age_stage
  - traits (最多 1~2 个)
  - 基线 GPS 坐标
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from engine.traits.base_trait import BaseTrait
from engine.traits import CardiacRisk, RespiratoryRisk, OrthoRisk

_TRAIT_POOL = [CardiacRisk, RespiratoryRisk, OrthoRisk]


@dataclass
class DogProfile:
    dog_id: str = ""
    breed_size: str = "medium"          # small / medium / large
    age_stage: str = "adult"            # puppy / adult / senior
    traits: list[BaseTrait] = field(default_factory=list)
    home_lat: float = 29.57            # 默认重庆 CQU
    home_lng: float = 106.45

    def __post_init__(self) -> None:
        if not self.dog_id:
            self.dog_id = uuid.uuid4().hex[:12]

    # ---------- 汇总 trait 提供的修正 ----------

    @property
    def hr_mean_offset(self) -> float:
        return sum(t.baseline.heart_rate_mean_offset for t in self.traits)

    @property
    def rr_mean_offset(self) -> float:
        return sum(t.baseline.resp_rate_mean_offset for t in self.traits)

    @property
    def temp_mean_offset(self) -> float:
        return sum(t.baseline.temperature_mean_offset for t in self.traits)

    @property
    def hr_var_mult(self) -> float:
        m = 1.0
        for t in self.traits:
            m *= t.baseline.hr_variability_multiplier
        return m

    @property
    def rr_var_mult(self) -> float:
        m = 1.0
        for t in self.traits:
            m *= t.baseline.rr_variability_multiplier
        return m

    @property
    def steps_mult(self) -> float:
        m = 1.0
        for t in self.traits:
            m *= t.steps_multiplier
        return m

    @staticmethod
    def random_profile(
        rng: Optional[np.random.Generator] = None,
    ) -> DogProfile:
        """随机生成一个 DogProfile（含 0~2 个 trait）"""
        if rng is None:
            rng = np.random.default_rng()

        breed = rng.choice(["small", "medium", "large"])
        age = rng.choice(["puppy", "adult", "senior"])

        # 0~2 个 trait
        n_traits = int(rng.choice([0, 1, 2], p=[0.3, 0.5, 0.2]))
        chosen_indices = rng.choice(
            len(_TRAIT_POOL), size=min(n_traits, len(_TRAIT_POOL)), replace=False
        )
        traits = [_TRAIT_POOL[i]() for i in chosen_indices]

        return DogProfile(
            breed_size=str(breed),
            age_stage=str(age),
            traits=traits,
        )

    def __repr__(self) -> str:
        trait_names = [t.name for t in self.traits]
        return (
            f"DogProfile(id={self.dog_id}, breed={self.breed_size}, "
            f"age={self.age_stage}, traits={trait_names})"
        )
