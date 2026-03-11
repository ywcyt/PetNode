"""
Step 4 测试 C：Docker 打包测试

测试范围：
  - Dockerfile 语法和文件存在性验证
  - docker-compose.yml 语法和结构验证
  - requirements.txt 文件存在性和格式验证
  - Docker 镜像构建测试（需要 Docker 环境）
  - Engine 容器启动和数据生成测试（需要 Docker 环境）

标记说明：
  - 无标记的测试：文件层面的静态验证（不需要 Docker）
  - @pytest.mark.docker 标记的测试：需要 Docker daemon 才能运行
"""

from __future__ import annotations

import json
import subprocess
import shutil
from pathlib import Path

import pytest

# ────────── 项目路径常量 ──────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # C_end_Simulator/


# ────────── 文件存在性测试 ──────────


class TestDockerFilesExist:
    """验证 Docker 相关文件是否存在且非空"""

    def test_engine_dockerfile_exists(self):
        """engine/Dockerfile 应存在且非空"""
        dockerfile = _PROJECT_ROOT / "engine" / "Dockerfile"
        assert dockerfile.exists(), f"缺少 {dockerfile}"
        assert dockerfile.stat().st_size > 0, f"{dockerfile} 为空文件"

    def test_tui_dockerfile_exists(self):
        """ui_tui/Dockerfile 应存在且非空"""
        dockerfile = _PROJECT_ROOT / "ui_tui" / "Dockerfile"
        assert dockerfile.exists(), f"缺少 {dockerfile}"
        assert dockerfile.stat().st_size > 0, f"{dockerfile} 为空文件"

    def test_docker_compose_exists(self):
        """docker-compose.yml 应存在且非空"""
        compose = _PROJECT_ROOT / "docker-compose.yml"
        assert compose.exists(), f"缺少 {compose}"
        assert compose.stat().st_size > 0, f"{compose} 为空文件"


# ────────── requirements.txt 测试 ──────────


class TestRequirementsFiles:
    """验证每个模块的 requirements.txt 文件"""

    @pytest.mark.parametrize("module_dir,expected_dep", [
        ("engine", "numpy"),
        ("ui_gui", "PyQt6"),
        ("ui_tui", "textual"),
        ("tests", "pytest"),
    ])
    def test_requirements_exists_and_has_dep(self, module_dir: str, expected_dep: str):
        """每个模块的 requirements.txt 应存在且包含核心依赖"""
        req_file = _PROJECT_ROOT / module_dir / "requirements.txt"
        assert req_file.exists(), f"缺少 {req_file}"
        content = req_file.read_text(encoding="utf-8")
        assert expected_dep.lower() in content.lower(), (
            f"{req_file} 中缺少依赖 {expected_dep}"
        )

    @pytest.mark.parametrize("module_dir", [
        "engine", "ui_gui", "ui_tui", "tests",
    ])
    def test_requirements_valid_format(self, module_dir: str):
        """requirements.txt 每行应符合 pip 格式（非空行应包含包名）"""
        req_file = _PROJECT_ROOT / module_dir / "requirements.txt"
        if not req_file.exists():
            pytest.skip(f"{req_file} 不存在")
        for line_num, line in enumerate(
            req_file.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # 简单验证：非注释行应包含至少一个字母
            assert any(c.isalpha() for c in stripped), (
                f"{req_file}:{line_num} 格式无效: {stripped!r}"
            )


# ────────── Dockerfile 内容验证 ──────────


class TestDockerfileContent:
    """验证 Dockerfile 内容结构"""

    def test_engine_dockerfile_has_from(self):
        """engine/Dockerfile 应包含 FROM 指令"""
        content = (_PROJECT_ROOT / "engine" / "Dockerfile").read_text()
        assert "FROM" in content

    def test_engine_dockerfile_has_pip_install(self):
        """engine/Dockerfile 应包含 pip install"""
        content = (_PROJECT_ROOT / "engine" / "Dockerfile").read_text()
        assert "pip install" in content

    def test_engine_dockerfile_has_entrypoint(self):
        """engine/Dockerfile 应包含入口点"""
        content = (_PROJECT_ROOT / "engine" / "Dockerfile").read_text()
        assert "ENTRYPOINT" in content or "CMD" in content


# ────────── docker-compose.yml 内容验证 ──────────


class TestDockerComposeContent:
    """验证 docker-compose.yml 内容结构"""

    def test_compose_has_engine_service(self):
        """docker-compose.yml 应定义 engine 服务"""
        content = (_PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "engine:" in content

    def test_compose_has_volumes(self):
        """docker-compose.yml 应挂载 output_data 卷"""
        content = (_PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "output_data" in content

    def test_compose_valid_yaml(self):
        """docker-compose.yml 应是合法的 YAML（使用 docker compose config 验证）"""
        compose_file = _PROJECT_ROOT / "docker-compose.yml"
        if not shutil.which("docker"):
            pytest.skip("Docker 未安装，跳过 YAML 验证")
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "config", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"docker-compose.yml 语法错误:\n{result.stderr}"
        )


# ────────── Docker 构建测试（需要 Docker 环境）──────────


@pytest.mark.docker
class TestDockerBuild:
    """
    Docker 镜像构建和容器运行测试。

    这些测试需要 Docker daemon 运行，使用 pytest -m docker 运行。
    """

    def test_engine_image_builds(self):
        """engine 镜像应能成功构建"""
        if not shutil.which("docker"):
            pytest.skip("Docker 未安装")
        result = subprocess.run(
            [
                "docker", "build",
                "-f", str(_PROJECT_ROOT / "engine" / "Dockerfile"),
                "-t", "petnode-engine-test:latest",
                str(_PROJECT_ROOT),
            ],
            capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0, (
            f"Engine 镜像构建失败:\n{result.stderr}"
        )

    def test_engine_container_runs_and_generates_data(self, tmp_path: Path):
        """engine 容器应能启动并生成数据"""
        if not shutil.which("docker"):
            pytest.skip("Docker 未安装")

        output_dir = tmp_path / "output_data"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 运行容器：少量 ticks，快速完成
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{output_dir}:/app/output_data",
                "petnode-engine-test:latest",
                "--dogs", "1",
                "--ticks", "10",
                "--interval", "0",
                "--seed", "42",
                "--output-dir", "/app/output_data",
            ],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, (
            f"Engine 容器运行失败:\n{result.stderr}"
        )

        # 验证输出文件
        jsonl = output_dir / "realtime_stream.jsonl"
        assert jsonl.exists(), "容器未生成 realtime_stream.jsonl"
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 10, f"预期 10 条记录，实际 {len(lines)} 条"

        # 验证每行 JSON 合法
        for line in lines:
            parsed = json.loads(line)
            assert "device_id" in parsed

        # 验证 engine_status.json
        status_path = output_dir / "engine_status.json"
        assert status_path.exists(), "容器未生成 engine_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["running"] is False

    def test_docker_compose_config_valid(self):
        """docker compose config 应通过验证"""
        if not shutil.which("docker"):
            pytest.skip("Docker 未安装")
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", str(_PROJECT_ROOT / "docker-compose.yml"),
                "config", "--quiet",
            ],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"docker-compose.yml 配置无效:\n{result.stderr}"
        )
