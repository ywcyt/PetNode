#!/usr/bin/env python3
"""
test_hmac_auth.py —— 测试 Flask 服务器 HMAC 签名防篡改机制

测试场景：
  1. 正确签名              → 期望 200
  2. 错误签名              → 期望 403
  3. 缺少 X-Signature 头   → 期望 403
  4. 篡改数据后签名不匹配  → 期望 403
  5. 健康检查不需要签名    → GET /api/health 期望 200

用法：
  python scripts/test_hmac_auth.py                         # 默认测 47.109.200.132:5000
  python scripts/test_hmac_auth.py --host 127.0.0.1        # 测本地
  python scripts/test_hmac_auth.py --host 47.109.200.132 --port 5000
"""

import argparse
import hashlib
import hmac
import json
import sys
import time

try:
    import requests
except ImportError:
    print("❌ 缺少 requests 库: pip install requests")
    sys.exit(1)

# 默认使用的正确 API Key
_CORRECT_API_KEY = "petnode_secret_key_2026"

# 默认使用的正确 HMAC 密钥
_CORRECT_HMAC_KEY = "petnode_hmac_secret_2026"

# 测试用的最小合法请求体
_SAMPLE_PAYLOAD = {
    "user_id": "user_test_hmac",
    "device_id": "test_device_hmac",
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
    parser = argparse.ArgumentParser(description="PetNode HMAC 签名防篡改测试")
    parser.add_argument("--host", default="47.109.200.132", help="服务器地址（默认 47.109.200.132）")
    parser.add_argument("--port", type=int, default=5000, help="服务器端口（默认 5000）")
    parser.add_argument("--api-key", default=_CORRECT_API_KEY, help="正确的 API Key")
    parser.add_argument("--hmac-key", default=_CORRECT_HMAC_KEY, help="正确的 HMAC 密钥")
    return parser.parse_args()


def calc_sig(body_bytes: bytes, hmac_key: str) -> str:
    """用 HMAC-SHA256 计算签名（与 Engine 端保持完全一致的算法）"""
    return hmac.new(
        hmac_key.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()


def make_body(payload: dict) -> bytes:
    """将 dict 序列化为 JSON bytes（sort_keys=True 保证 key 排序一致）"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


def run_test(name: str, func) -> bool:
    """运行单个测试，返回是否通过"""
    print("=" * 60)
    print(f"🧪 {name}")
    print("=" * 60)
    try:
        passed, detail = func()
        print(f"   状态码: {detail.get('status_code', '?')}")
        print(f"   响应体: {detail.get('body', '')}")
        if passed:
            print(f"\n   ✅ 通过\n")
        else:
            print(f"\n   ❌ 异常: {detail.get('reason', '未知原因')}\n")
        return passed
    except Exception as exc:
        print(f"   ❌ 测试执行异常: {exc}\n")
        return False


def main():
    args = parse_args()
    base_url = f"http://{args.host}:{args.port}"
    api_key = args.api_key
    hmac_key = args.hmac_key

    print(f"🔏 PetNode HMAC 签名防篡改测试")
    print(f"   目标服务器: {base_url}\n")

    # ── 测试 1：正确签名 → 期望 200 ──
    def test_correct_sig():
        body = make_body(_SAMPLE_PAYLOAD)
        sig = calc_sig(body, hmac_key)
        resp = requests.post(
            f"{base_url}/api/data",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "X-Signature": sig,
            },
            timeout=10,
        )
        ok = resp.status_code == 200
        reason = f"期望 200，实际 {resp.status_code}" if not ok else ""
        return ok, {"status_code": resp.status_code, "body": resp.text, "reason": reason}

    # ── 测试 2：错误签名 → 期望 403 ──
    def test_wrong_sig():
        body = make_body(_SAMPLE_PAYLOAD)
        resp = requests.post(
            f"{base_url}/api/data",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "X-Signature": "fake_signature_12345",
            },
            timeout=10,
        )
        ok = resp.status_code == 403
        reason = f"期望 403，实际 {resp.status_code}" if not ok else ""
        return ok, {"status_code": resp.status_code, "body": resp.text, "reason": reason}

    # ── 测试 3：缺少 X-Signature 头 → 期望 403 ──
    def test_missing_sig():
        body = make_body(_SAMPLE_PAYLOAD)
        resp = requests.post(
            f"{base_url}/api/data",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                # 故意不发 X-Signature
            },
            timeout=10,
        )
        ok = resp.status_code == 403
        reason = f"期望 403，实际 {resp.status_code}" if not ok else ""
        return ok, {"status_code": resp.status_code, "body": resp.text, "reason": reason}

    # ── 测试 4：篡改数据后签名不匹配 → 期望 403 ──
    def test_tampered_data():
        # 对原始数据算签名
        original_payload = {"heart_rate": 80}
        original_body = make_body(original_payload)
        sig = calc_sig(original_body, hmac_key)

        # 发送时把 body 替换成篡改后的数据，签名保持不变
        tampered_payload = {"heart_rate": 200}
        tampered_body = make_body(tampered_payload)

        resp = requests.post(
            f"{base_url}/api/data",
            data=tampered_body,  # 篡改后的数据
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "X-Signature": sig,  # 原始数据的签名（与篡改后数据不匹配）
            },
            timeout=10,
        )
        ok = resp.status_code == 403
        reason = f"期望 403，实际 {resp.status_code}" if not ok else ""
        return ok, {"status_code": resp.status_code, "body": resp.text, "reason": reason}

    # ── 测试 5：健康检查不需要签名 → 期望 200 ──
    def test_health_no_sig():
        resp = requests.get(
            f"{base_url}/api/health",
            timeout=10,
        )
        ok = resp.status_code == 200
        reason = f"期望 200，实际 {resp.status_code}" if not ok else ""
        return ok, {"status_code": resp.status_code, "body": resp.text, "reason": reason}

    tests = [
        ("测试 1：正确签名 → 期望 200", test_correct_sig),
        ("测试 2：错误签名 → 期望 403", test_wrong_sig),
        ("测试 3：缺少签名头 → 期望 403", test_missing_sig),
        ("测试 4：篡改数据后签名不匹配 → 期望 403", test_tampered_data),
        ("测试 5：健康检查不需要签名 → 期望 200", test_health_no_sig),
    ]

    results = []
    for name, func in tests:
        passed = run_test(name, func)
        results.append((name, passed))
        time.sleep(0.5)  # 每个测试之间等 0.5 秒，避免 gunicorn worker 竞争

    # ── 打印汇总结果 ──
    print("=" * 60)
    print("📋 测试汇总")
    print("=" * 60)
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"   {icon} {name}")

    all_passed = all(p for _, p in results)
    print()
    if all_passed:
        print("🎉 全部通过！HMAC 签名防篡改机制运行正常！")
        sys.exit(0)
    else:
        print("⚠️  部分测试未通过，请检查服务器配置")
        sys.exit(1)


if __name__ == "__main__":
    main()
