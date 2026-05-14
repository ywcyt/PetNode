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


@dataclass
class DogProfile:
    """
    狗的长期属性数据类。

    每只狗在创建时确定如下信息：
      - dog_id       : 唯一标识符（默认取 uuid4 前 12 位十六进制字符）
      - breed_size   : 体型大小（small / medium / large）
      - age_stage    : 年龄阶段（puppy / adult / senior）
      - traits       : 慢性体质特质列表（0~2 个，来自 CardiacRisk / RespiratoryRisk / OrthoRisk）
      - home_lat/lng : GPS 基准位置（默认重庆大学坐标）

    Trait 会通过下方的汇总属性（hr_mean_offset、rr_var_mult、steps_mult 等）
    把偏移值和倍率传递给 SmartCollar 的数据生成流水线。
    """

    dog_id: str = ""
    breed_size: str = "medium"          # small / medium / large
    age_stage: str = "adult"            # puppy / adult / senior
    traits: list[BaseTrait] = field(default_factory=list)
    home_lat: float = 29.57            # 默认重庆 CQU
    home_lng: float = 106.45

    def __post_init__(self) -> None:
        # 如果没有指定 dog_id，则自动生成一个 12 位的十六进制唯一标识
        if not self.dog_id:
            self.dog_id = uuid.uuid4().hex[:12]

    # ---------- 汇总 trait 提供的修正 ----------
    # 以下 property 将所有 trait 对基线指标的影响进行汇总：
    #   - 偏移量（offset）类采用加法累加
    #   - 倍率（multiplier）类采用乘法叠加

    @property
    def hr_mean_offset(self) -> float:
        """所有 trait 的心率均值偏移之和 (bpm)"""
        return sum(t.baseline.heart_rate_mean_offset for t in self.traits)

    @property
    def rr_mean_offset(self) -> float:
        """所有 trait 的呼吸频率均值偏移之和 (次/分钟)"""
        return sum(t.baseline.resp_rate_mean_offset for t in self.traits)

    @property
    def temp_mean_offset(self) -> float:
        """所有 trait 的体温均值偏移之和 (°C)"""
        return sum(t.baseline.temperature_mean_offset for t in self.traits)

    @property
    def hr_var_mult(self) -> float:
        """所有 trait 的心率方差倍率的乘积（>1 表示波动更大）"""
        m = 1.0
        for t in self.traits:
            m *= t.baseline.hr_variability_multiplier
        return m

    @property
    def rr_var_mult(self) -> float:
        """所有 trait 的呼吸频率方差倍率的乘积（>1 表示波动更大）"""
        m = 1.0
        for t in self.traits:
            m *= t.baseline.rr_variability_multiplier
        return m

    @property
    def steps_mult(self) -> float:
        """所有 trait 的步数倍率的乘积（<1 表示活动量降低）"""
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

        # 随机选择体型和年龄阶段
        breed = rng.choice(["small", "medium", "large"])
        age = rng.choice(["puppy", "adult", "senior"])

        # 按概率分布决定 trait 数量：30% 没有 trait，50% 有 1 个，20% 有 2 个
        # 0~2 个 trait
        n_traits = int(rng.choice([0, 1, 2], p=[0.3, 0.5, 0.2]))
        
        # ✅ 从自动注册表中获取所有可用的 Trait
        trait_pool = BaseTrait.get_all_trait_names()
        
        # 从 trait_pool 中不重复地随机抽取指定数量的 trait
        if n_traits > 0 and trait_pool:
            chosen_indices = rng.choice(
                len(trait_pool), size=min(n_traits, len(trait_pool)), replace=False
            )
            # 根据索引获取 Trait 类并实例化
            traits = [BaseTrait.get_trait(trait_pool[i])() for i in chosen_indices]
        else:
            traits = []

        return DogProfile(
            breed_size=str(breed),
            age_stage=str(age),
            traits=traits,
        )

    def __repr__(self) -> str:
        trait_names = [t.name for t in self.traits]
        return (
            f"DogProfile(id={self.dog_id},"
            f"breed={self.breed_size}, age={self.age_stage}, traits={trait_names})"
        )
