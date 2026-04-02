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

import argparse
import json
import time
import sys

try:
    import requests
except ImportError:
    print("❌ 缺少 requests 库，请先安装: pip install requests")
    sys.exit(1)


# ────────────────── 配置 ──────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="PetNode 远程上传测试")
    parser.add_argument("--host", default="47.109.200.132", help="服务器地址（IP 或域名）")
    parser.add_argument("--port", type=int, default=5000, help="Flask 端口（默认 5000）")
    parser.add_argument("--timeout", type=int, default=5, help="请求超时秒数（默认 5）")
    return parser.parse_args()


# ────────────────── 测试用例 ──────────────────

def test_connectivity(base_url: str, timeout: int) -> bool:
    """测试 1: 网络连通性"""
    print("\n" + "=" * 60)
    print("🔌 测试 1: 网络连通性")
    print("=" * 60)

    try:
        start = time.time()
        r = requests.get(f"{base_url}/api/health", timeout=timeout)
        elapsed = time.time() - start

        print(f"   状态码: {r.status_code}")
        print(f"   响应时间: {elapsed:.3f}s")
        print(f"   响应体: {r.text}")

        if r.status_code == 200:
            print("   ✅ 连接成功！服务器存活")
            data = r.json()
            print(f"   📊 服务器已接收数据: {data.get('total_received', '?')} 条")
            return True
        else:
            print(f"   ⚠️  服务器返回非 200 状态码: {r.status_code}")
            print(f"   响应内容: {r.text[:200]}")
            return False

    except requests.ConnectionError:
        print("   ❌ 连接失败！可能的原因:")
        print("      1. 服务器上 Flask 容器未运行")
        print("      2. 服务器防火墙/安全组未放行 5000 端口")
        print("      3. 服��器 IP 或域名不正确")
        return False
    except requests.Timeout:
        print(f"   ❌ 连接超时（{timeout}s）！服务器可能不可达")
        return False
    except Exception as e:
        print(f"   ❌ 未知错误: {e}")
        return False


def test_single_upload(base_url: str, timeout: int) -> bool:
    """测试 2: 单条数据上传"""
    print("\n" + "=" * 60)
    print("📤 测试 2: 单条数据上传")
    print("=" * 60)

    # 构造一条完整的模拟数据（与 SmartCollar 输出格式完全一致）
    record = {
        "user_id": "user_test_local",
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

    print(f"   发送数据: device_id={record['device_id']}, behavior={record['behavior']}")

    try:
        start = time.time()
        r = requests.post(
            f"{base_url}/api/data",
            json=record,
            timeout=timeout,
        )
        elapsed = time.time() - start

        print(f"   状态码: {r.status_code}")
        print(f"   响应时间: {elapsed:.3f}s")
        print(f"   响应体: {r.text}")

        if r.status_code == 200:
            print("   ✅ 上传成功！")
            if elapsed < 1.0:
                print(f"   ✅ 响应时间 {elapsed:.3f}s < 1s，满足要求")
            else:
                print(f"   ⚠️  响应时间 {elapsed:.3f}s >= 1s，超出要求")
            return True
        else:
            print(f"   ❌ 上传失败: {r.status_code}")
            return False

    except Exception as e:
        print(f"   ❌ 请求异常: {e}")
        return False


def test_batch_upload(base_url: str, timeout: int, count: int = 10) -> bool:
    """测试 3: 批量数据上传（模拟连续发送）"""
    print("\n" + "=" * 60)
    print(f"📦 测试 3: 批量上传 {count} 条数据")
    print("=" * 60)

    success = 0
    fail = 0
    total_time = 0.0
    max_time = 0.0

    for i in range(count):
        record = {
            "user_id": "user_test_batch",
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
            start = time.time()
            r = requests.post(f"{base_url}/api/data", json=record, timeout=timeout)
            elapsed = time.time() - start

            total_time += elapsed
            max_time = max(max_time, elapsed)

            if r.status_code == 200:
                success += 1
            else:
                fail += 1
                print(f"   ⚠️  第 {i+1} 条失败: {r.status_code} {r.text[:100]}")

        except Exception as e:
            fail += 1
            print(f"   ❌ 第 {i+1} 条异常: {e}")

    avg_time = total_time / count if count > 0 else 0

    print(f"\n   📊 结果统计:")
    print(f"      成功: {success}/{count}")
    print(f"      失败: {fail}/{count}")
    print(f"      平均响应时间: {avg_time:.3f}s")
    print(f"      最大响应时间: {max_time:.3f}s")
    print(f"      总耗时: {total_time:.3f}s")

    if success == count:
        print("   ✅ 全部上传成功！")
        if max_time < 1.0:
            print(f"   ✅ 最大响应时间 {max_time:.3f}s < 1s，满足要求")
        return True
    else:
        print(f"   ❌ 有 {fail} 条失败")
        return False


def test_invalid_request(base_url: str, timeout: int) -> bool:
    """测试 4: 异常请求（服务器应该正确拒绝）"""
    print("\n" + "=" * 60)
    print("🚫 测试 4: 异常请求处理")
    print("=" * 60)

    all_pass = True

    # 4a: 发送空 body
    print("\n   4a: 发送空请求体...")
    try:
        r = requests.post(f"{base_url}/api/data", data="", timeout=timeout,
                          headers={"Content-Type": "application/json"})
        if r.status_code == 400:
            print(f"      ✅ 正确拒绝 (400): {r.json().get('message', '')}")
        else:
            print(f"      ⚠️  预期 400，实际 {r.status_code}")
            all_pass = False
    except Exception as e:
        print(f"      ❌ 异常: {e}")
        all_pass = False

    # 4b: 发送非 JSON
    print("   4b: 发送非 JSON 数据...")
    try:
        r = requests.post(f"{base_url}/api/data", data="this is not json", timeout=timeout)
        if r.status_code == 400:
            print(f"      ✅ 正确拒绝 (400)")
        else:
            print(f"      ⚠️  预期 400，实际 {r.status_code}")
            all_pass = False
    except Exception as e:
        print(f"      ❌ 异常: {e}")
        all_pass = False

    # 4c: 发送 JSON 数组（非 dict）
    print("   4c: 发送 JSON 数组（非 dict）...")
    try:
        r = requests.post(f"{base_url}/api/data", json=[1, 2, 3], timeout=timeout)
        if r.status_code == 400:
            print(f"      ✅ 正确拒绝 (400)")
        else:
            print(f"      ⚠️  预期 400，实际 {r.status_code}")
            all_pass = False
    except Exception as e:
        print(f"      ❌ 异常: {e}")
        all_pass = False

    if all_pass:
        print("\n   ✅ 异常处理全部正确！")
    return all_pass


def test_health_after(base_url: str, timeout: int) -> None:
    """测试 5: 最终健康检查（确认数据都收到了）"""
    print("\n" + "=" * 60)
    print("📊 测试 5: 最终数据统计")
    print("=" * 60)

    try:
        r = requests.get(f"{base_url}/api/health", timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            print(f"   服务器状态: {data.get('status')}")
            print(f"   累计接收: {data.get('total_received')} 条")
            print(f"   服务器时间: {data.get('timestamp')}")
        else:
            print(f"   ⚠️  健康检查返回: {r.status_code}")
    except Exception as e:
        print(f"   ❌ 健康检查失败: {e}")


# ────────────────── 主入口 ──────────────────

def main():
    args = parse_args()
    base_url = f"http://{args.host}:{args.port}"

    print("🐾 PetNode 远程上传测试")
    print(f"   目标服务器: {base_url}")
    print(f"   超时设置: {args.timeout}s")

    results = {}

    # 测试 1: 连通性（如果连不上，后续测试直接跳过）
    results["连通性"] = test_connectivity(base_url, args.timeout)
    if not results["连通性"]:
        print("\n" + "=" * 60)
        print("💀 服务器不可达，后续测试跳过")
        print("请检查:")
        print(f"  1. 服务器上 Flask 容器是否运行: docker ps | grep flask")
        print(f"  2. 安全组是否放行端口 {args.port}: 阿里云控制台 → ECS → 安全组")
        print(f"  3. 地址是否正确: {base_url}")
        print("=" * 60)
        sys.exit(1)

    # 测试 2~5
    results["单条上传"] = test_single_upload(base_url, args.timeout)
    results["批量上传"] = test_batch_upload(base_url, args.timeout)
    results["异常处理"] = test_invalid_request(base_url, args.timeout)
    test_health_after(base_url, args.timeout)

    # 汇总
    print("\n" + "=" * 60)
    print("📋 测试汇总")
    print("=" * 60)
    all_pass = True
    for name, passed in results.items():
        icon = "✅" if passed else "❌"
        print(f"   {icon} {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("🎉 全部通过！本地电脑可以正常上传数据到服务器！")
    else:
        print("⚠️  部分测试未通过，请检查上面的错误信息")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()