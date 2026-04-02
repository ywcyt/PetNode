#!/usr/bin/env python3
"""
test_api_key_auth.py —— 测试 Flask 服务器 API Key 鉴权机制

测试场景：
  1. 无 Authorization 头          → 期望 401
  2. 错误的 API Key               → 期望 401
  3. 正确的 API Key               → 期望 200
  4. 健康检查不需要认证            → GET /api/health 期望 200
  5. 格式错误的 Authorization 头   → 缺少 Bearer 前缀，期望 401

用法：
  python scripts/test_api_key_auth.py                         # 默认测 47.109.200.132:5000
  python scripts/test_api_key_auth.py --host 127.0.0.1        # 测本地
  python scripts/test_api_key_auth.py --host 47.109.200.132 --port 5000
"""

import argparse
import sys

try:
    import requests
except ImportError:
    print("❌ 缺少 requests 库: pip install requests")
    sys.exit(1)

# 默认使用的正确 API Key
_CORRECT_API_KEY = "petnode_secret_key_2026"

# 测试用的最小合法请求体
_SAMPLE_PAYLOAD = {
    "user_id": "user_test_auth",
    "device_id": "test_device_auth",
    "timestamp": "2026-04-01T00:00:00",
    "behavior": "walking",
    "heart_rate": 80.0,
    "resp_rate": 20.0,
    "temperature": 38.5,
    "steps": 100,
    "battery": 100,
    "gps_lat": 29.57,
    "gps_lng": 106.45,
    "event": None,
    "event_phase": None,
}


def parse_args():
    parser = argparse.ArgumentParser(description="PetNode API Key 鉴权测试")
    parser.add_argument("--host", default="47.109.200.132", help="服务器地址（默认 47.109.200.132）")
    parser.add_argument("--port", type=int, default=5000, help="Flask 端口（默认 5000）")
    return parser.parse_args()


def run_test(name: str, func) -> bool:
    """执行单个测试，返回是否通过。"""
    print(f"\n{'='*60}")
    print(f"🧪 {name}")
    print("=" * 60)
    try:
        passed = func()
        if passed:
            print(f"   ✅ 通过")
        else:
            print(f"   ❌ 失败")
        return passed
    except Exception as exc:
        print(f"   ❌ 异常: {exc}")
        return False


def main():
    args = parse_args()
    base_url = f"http://{args.host}:{args.port}"
    data_url = f"{base_url}/api/data"
    health_url = f"{base_url}/api/health"

    print("🔐 PetNode API Key 鉴权测试")
    print(f"   目标服务器: {base_url}")

    results: list[tuple[str, bool]] = []

    # ── 测试 1：无 Authorization 头 ──
    def test_no_auth():
        resp = requests.post(data_url, json=_SAMPLE_PAYLOAD, timeout=5)
        print(f"   状态码: {resp.status_code}")
        print(f"   响应体: {resp.text}")
        assert resp.status_code == 401, f"期望 401，实际 {resp.status_code}"
        return True

    # ── 测试 2：错误的 API Key ──
    def test_wrong_key():
        headers = {"Authorization": "Bearer wrong_key"}
        resp = requests.post(data_url, json=_SAMPLE_PAYLOAD, headers=headers, timeout=5)
        print(f"   状态码: {resp.status_code}")
        print(f"   响应体: {resp.text}")
        assert resp.status_code == 401, f"期望 401，实际 {resp.status_code}"
        return True

    # ── 测试 3：正确的 API Key ──
    def test_correct_key():
        headers = {"Authorization": f"Bearer {_CORRECT_API_KEY}"}
        resp = requests.post(data_url, json=_SAMPLE_PAYLOAD, headers=headers, timeout=5)
        print(f"   状态码: {resp.status_code}")
        print(f"   响应体: {resp.text}")
        assert resp.status_code == 200, f"期望 200，实际 {resp.status_code}"
        return True

    # ── 测试 4：健康检查不需要认证 ──
    def test_health_no_auth():
        resp = requests.get(health_url, timeout=5)
        print(f"   状态码: {resp.status_code}")
        print(f"   响应体: {resp.text}")
        assert resp.status_code == 200, f"期望 200，实际 {resp.status_code}"
        return True

    # ── 测试 5：格式错误的 Authorization 头（缺少 Bearer 前缀）──
    def test_malformed_auth():
        # 直接把 key 放进头，不加 "Bearer " 前缀
        headers = {"Authorization": _CORRECT_API_KEY}
        resp = requests.post(data_url, json=_SAMPLE_PAYLOAD, headers=headers, timeout=5)
        print(f"   状态码: {resp.status_code}")
        print(f"   响应体: {resp.text}")
        assert resp.status_code == 401, f"期望 401，实际 {resp.status_code}"
        return True

    # 按顺序执行所有测试
    tests = [
        ("测试 1：无 Authorization 头 → 期望 401", test_no_auth),
        ("测试 2：错误的 API Key → 期望 401", test_wrong_key),
        ("测试 3：正确的 API Key → 期望 200", test_correct_key),
        ("测试 4：健康检查不需要认证 → 期望 200", test_health_no_auth),
        ("测试 5：格式错误的 Authorization 头 → 期望 401", test_malformed_auth),
    ]

    for name, func in tests:
        passed = run_test(name, func)
        results.append((name, passed))

    # ── 汇总结果 ──
    print(f"\n{'='*60}")
    print("📋 测试汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        icon = "✅" if passed else "❌"
        # 只显示测试名称的前半部分（去掉"期望 xxx"部分）
        short_name = name.split("→")[0].strip()
        print(f"   {icon} {short_name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("🎉 全部通过！API Key 鉴权机制运行正常！")
    else:
        print("⚠️  部分测试未通过，请检查服务器配置")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
