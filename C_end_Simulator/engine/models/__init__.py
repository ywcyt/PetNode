# engine/models 包 —— 业务模型层
# 包含狗的长期属性 (DogProfile) 和智能项圈模拟器 (SmartCollar)
# 对外暴露两个核心类，供调度器 (engine/main.py) 和测试直接导入使用

from .dog_profile import DogProfile
from .smart_collar import SmartCollar

__all__ = ["DogProfile", "SmartCollar"]
