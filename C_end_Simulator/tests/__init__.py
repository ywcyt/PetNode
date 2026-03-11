# tests 包 —— PetNode C端模拟器的测试套件
#
# 测试按开发流程分步组织，每个测试文件对应一个阶段的功能验证：
#
#   test_step1_data_generation.py  : 第 1 步——数据生成（DogProfile / Traits / Events / SmartCollar）
#   test_step2_file_exporter.py    : 第 2 步——文件导出（FileExporter JSONL 写入与读取）
#   test_step3_scheduler.py        : 第 3 步——调度器集成（main.py 的 run() 函数端到端测试）
#   test_step4_docker_build.py     : 第 4 步——Docker 构建（镜像构建与容器运行验证，需 Docker 环境）
#   test_step4_module_health.py    : 第 4 步——模块健康检查（所有模块的导入和基础功能验证）
#   test_step4_multithreading.py   : 第 4 步——多线程安全（并发数据生成和文件写入的线程安全性验证）
#   test_step5_tui_backend.py      : 第 5 步——TUI 后端接口（DataAPI / CommandAPI / UserStore 单元测试）
#
# 运行方式：
#   cd C_end_Simulator
#   pytest                         # 运行所有非 Docker 测试
#   pytest -m docker               # 仅运行需要 Docker 环境的测试
#   pytest tests/test_step1_data_generation.py  # 运行单个测试文件
