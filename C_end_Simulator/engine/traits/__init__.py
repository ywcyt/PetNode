# engine/traits 包 —— 特质层（慢性病/体质修正）
# 每个 Trait 代表一种终身属性（如心脏病倾向、呼吸道问题倾向、骨骼关节问题倾向），
# 会影响狗的基线生理指标、行为概率、事件触发概率、GPS 活动范围和步数等。
# BaseTrait 是抽象基类，CardiacRisk / RespiratoryRisk / OrthoRisk 是三种具体特质实现。

from .base_trait import BaseTrait
from .cardiac import CardiacRisk
from .respiratory import RespiratoryRisk
from .ortho import OrthoRisk

__all__ = ["BaseTrait", "CardiacRisk", "RespiratoryRisk", "OrthoRisk"]
