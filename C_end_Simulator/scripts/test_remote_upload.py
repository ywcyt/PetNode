#!/usr/bin/env python3
"""
test_remote_upload.py —— 本地电脑 → 远程服务器上传测试脚本

测试内容：
  1. 网络连通性（能不能连上服务器）
  2. 健康检查（Flask 是否存活）
  3. 单条数据上传（模拟一条项圈数据）
  4. 批量数据上传（模拟 10 条连续数据，测响应时间）
  5. 异常处理（发送非法数据，确认服务器正确拒绝）

用法：
  python test_remote_upload.py                           # 默认测 47.109.200.132:5000
  python test_remote_upload.py --host pppetnode.com      # 用域名
  python test_remote_upload.py --host 192.168.1.100      # 用其他 IP
  python test_remote_upload.py --port 8080               # 用其他端口
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import pytest

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

# ────────────────── 配置 ──────────────────

_DEFAULT_HOST = os.environ.get("PETNODE_TEST_HOST", "47.109.200.132")
_DEFAULT_PORT = int(os.environ.get("PETNODE_TEST_PORT", "5000"))
_DEFAULT_TIMEOUT = int(os.environ.get("PETNODE_TEST_TIMEOUT", "5"))


def _requires_requests():
    if requests is None:
        pytest.skip("缺少 requests 库")


def _check_connectivity(base_url: str, timeout: int) -> bool:
    """快速检查服务器是否可达，不可达时 pytest.skip"""
    try:
        r = requests.get(f"{base_url}/api/health", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


# ────────────────── 测试用例 ──────────────────


def test_connectivity():
    """测试 1: 网络连通性"""
    _requires_requests()
    base_url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"
    try:
        r = requests.get(f"{base_url}/api/health", timeout=_DEFAULT_TIMEOUT)
        assert r.status_code == 200, f"服务器返回 {r.status_code}"
    except requests.ConnectionError:
        pytest.skip(f"无法连接到 {base_url}（服务器不可达）")
    except requests.Timeout:
        pytest.skip(f"连接 {base_url} 超时")


def test_single_upload():
    """测试 2: 单条数据上传"""
    _requires_requests()
    base_url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"
    if not _check_connectivity(base_url, _DEFAULT_TIMEOUT):
        pytest.skip(f"服务器 {base_url} 不可达")

    record = {
        "device_id": "local_test_001",
        "timestamp": "2025-06-01T12:00:00",
        "behavior": "walking",
        "heart_rate": 105.3,
        "resp_rate": 22.1,
        "temperature": 38.65,
        "steps": 1234,
        "battery": 95,
        "gps_lat": 29.5700,
        "gps_lng": 106.4500,
        "event": None,
        "event_phase": None,
    }

    try:
        r = requests.post(f"{base_url}/api/data", json=record, timeout=_DEFAULT_TIMEOUT)
        assert r.status_code == 200, f"上传失败: {r.status_code}"
    except requests.RequestException as e:
        pytest.fail(f"请求异常: {e}")


def test_batch_upload():
    """测试 3: 批量数据上传"""
    _requires_requests()
    base_url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"
    if not _check_connectivity(base_url, _DEFAULT_TIMEOUT):
        pytest.skip(f"服务器 {base_url} 不可达")

    count = 10
    for i in range(count):
        record = {
            "device_id": f"batch_device_{i:03d}",
            "timestamp": f"2025-06-01T12:{i:02d}:00",
            "behavior": ["sleeping", "resting", "walking", "running"][i % 4],
            "heart_rate": round(60 + i * 5.5, 1),
            "resp_rate": round(14 + i * 1.2, 1),
            "temperature": round(38.2 + i * 0.05, 2),
            "steps": i * 100,
            "battery": 100 - i,
            "gps_lat": round(29.57 + i * 0.0001, 6),
            "gps_lng": round(106.45 + i * 0.0001, 6),
            "event": None,
            "event_phase": None,
        }

        try:
            r = requests.post(f"{base_url}/api/data", json=record, timeout=_DEFAULT_TIMEOUT)
            assert r.status_code == 200, f"第 {i+1} 条失败: {r.status_code}"
        except requests.RequestException as e:
            pytest.fail(f"第 {i+1} 条异常: {e}")


def test_invalid_request():
    """测试 4: 异常请求（服务器应该正确拒绝）"""
    _requires_requests()
    base_url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"
    if not _check_connectivity(base_url, _DEFAULT_TIMEOUT):
        pytest.skip(f"服务器 {base_url} 不可达")

    # 4a: 发送空 body
    r = requests.post(
        f"{base_url}/api/data", data="", timeout=_DEFAULT_TIMEOUT,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400, f"空 body 预期 400，实际 {r.status_code}"

    # 4b: 发送非 JSON
    r = requests.post(f"{base_url}/api/data", data="this is not json", timeout=_DEFAULT_TIMEOUT)
    assert r.status_code == 400, f"非 JSON 预期 400，实际 {r.status_code}"

    # 4c: 发送 JSON 数组（非 dict）
    r = requests.post(f"{base_url}/api/data", json=[1, 2, 3], timeout=_DEFAULT_TIMEOUT)
    assert r.status_code == 400, f"数组 预期 400，实际 {r.status_code}"


def test_health_after():
    """测试 5: 最终健康检查"""
    _requires_requests()
    base_url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"
    if not _check_connectivity(base_url, _DEFAULT_TIMEOUT):
        pytest.skip(f"服务器 {base_url} 不可达")

    r = requests.get(f"{base_url}/api/health", timeout=_DEFAULT_TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") is not None


# ────────────────── 命令行入口 ──────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="PetNode 远程上传测试")
    parser.add_argument("--host", default="47.109.200.132", help="服务器地址（IP 或域名）")
    parser.add_argument("--port", type=int, default=5000, help="Flask 端口（默认 5000）")
    parser.add_argument("--timeout", type=int, default=5, help="请求超时秒数（默认 5）")
    return parser.parse_args()


def main():
    if requests is None:
        print("缺少 requests 库，请先安装: pip install requests")
        sys.exit(1)

    args = parse_args()
    base_url = f"http://{args.host}:{args.port}"

    print("PetNode 远程上传测试")
    print(f"   目标服务器: {base_url}")
    print(f"   超时设置: {args.timeout}s")

    # 连通性检查
    try:
        r = requests.get(f"{base_url}/api/health", timeout=args.timeout)
        if r.status_code != 200:
            print(f"服务器返回 {r.status_code}，跳过后续测试")
            sys.exit(1)
    except requests.ConnectionError:
        print(f"无法连接到 {base_url}（服务器不可达）")
        sys.exit(1)
    except requests.Timeout:
        print(f"连接 {base_url} 超时")
        sys.exit(1)

    # 运行 pytest
    sys.exit(pytest.main([__file__, "-v"]))


if __name__ == "__main__":
    main()
