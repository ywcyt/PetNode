#!/usr/bin/env python3
"""
test_local_engine.py —— 在本地电脑运行 Engine，上传数据到远程服务器

测试内容：
  1. 检查服务器连通性
  2. 记录服务器当前已接收数据条数（作为基准）
  3. 本地启动 Engine，生成 20 条数据（2 只狗 × 10 ticks）上传到服务器
  4. 验证服务器新增接收条数 = 20
  5. 展示 Engine 运行统计（发送/缓存/补发）

用法：
  python scripts/test_local_engine.py                              # 默认测 47.109.200.132:5000
  python scripts/test_local_engine.py --host pppetnode.com         # 用域名
  python scripts/test_local_engine.py --dogs 3 --ticks 20         # 自定义狗数和 tick 数

注意：
  需要在 C_end_Simulator/ 目录下运行（因为 engine 模块的 import 路径）
"""

import argparse
import sys
import time
import os

# ── 确保 import 路径正确 ──
# 如果从 scripts/ 目录运行，需要把上级目录加到 sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)  # C_end_Simulator/
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import requests
except ImportError:
    print("❌ 缺少 requests 库: pip install requests")
    sys.exit(1)

try:
    import numpy
except ImportError:
    print("❌ 缺少 numpy 库: pip install numpy")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="PetNode 本地 Engine 上传测试")
    parser.add_argument("--host", default="47.109.200.132", help="服务器地址")
    parser.add_argument("--port", type=int, default=5000, help="Flask 端口")
    parser.add_argument("--dogs", type=int, default=2, help="模拟狗数量（默认 2）")
    parser.add_argument("--ticks", type=int, default=10, help="每只狗的 tick 数（默认 10）")
    parser.add_argument("--interval", type=float, default=0.5, help="每轮间隔秒数（默认 0.5）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认 42）")
    return parser.parse_args()


def get_server_count(base_url: str) -> int:
    """查询服务器当前已接收数据条数"""
    try:
        r = requests.get(f"{base_url}/api/health", timeout=5)
        if r.status_code == 200:
            return r.json().get("total_received", 0)
    except Exception:
        pass
    return -1


def main():
    args = parse_args()
    base_url = f"http://{args.host}:{args.port}"
    api_url = f"{base_url}/api/data"
    expected_records = args.dogs * args.ticks

    print("🐾 PetNode 本地 Engine 上传测试")
    print(f"   服务器: {base_url}")
    print(f"   模拟: {args.dogs} 只狗 × {args.ticks} ticks = {expected_records} 条数据")
    print(f"   间隔: {args.interval}s/轮, 种子: {args.seed}")

    # ══════════════════════════════════════════
    # Step 1: 检查服务器连通性
    # ══════════════════════════════════════════
    print("\n" + "=" * 60)
    print("🔌 Step 1: 检查服务器连通性")
    print("=" * 60)

    try:
        start = time.time()
        r = requests.get(f"{base_url}/api/health", timeout=5)
        elapsed = time.time() - start

        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ 服务器在线 (响应 {elapsed:.3f}s)")
            print(f"   📊 当前已接收: {data.get('total_received')} 条")
        else:
            print(f"   ❌ 服务器返回 {r.status_code}: {r.text[:100]}")
            sys.exit(1)
    except requests.ConnectionError:
        print("   ❌ 连接失败！请检查:")
        print(f"      1. 服务器上 Flask 容器是否运行")
        print(f"      2. 安全组是否放行 {args.port} 端口")
        sys.exit(1)
    except requests.Timeout:
        print("   ❌ 连接超时")
        sys.exit(1)

    # ══════════════════════════════════════════
    # Step 2: 记录基准数据
    # ══════════════════════════════════════════
    print("\n" + "=" * 60)
    print("📏 Step 2: 记录基准数据")
    print("=" * 60)

    before_count = get_server_count(base_url)
    print(f"   服务器当前累计: {before_count} 条")
    print(f"   预计新增: {expected_records} 条")

    # ══════════════════════════════════════════
    # Step 3: 启动本地 Engine
    # ══════════════════════════════════════════
    print("\n" + "=" * 60)
    print("🚀 Step 3: 启动本地 Engine")
    print("=" * 60)

    # 导入 Engine 模块
    try:
        from engine.models import SmartCollar
        from engine.exporters import HttpExporter
        from datetime import timedelta
        print("   ✅ Engine 模块导入成功")
    except ImportError as e:
        print(f"   ❌ 导入失败: {e}")
        print("   请确保在 C_end_Simulator/ 目录下运行此脚本")
        sys.exit(1)

    # 创建项圈
    collars = []
    for i in range(args.dogs):
        collar = SmartCollar(
            tick_interval=timedelta(minutes=1),
            seed=args.seed + i,
        )
        collars.append(collar)
        print(f"   🐕 项圈 #{i+1}: device={collar.profile.dog_id}, "
              f"breed={collar.profile.breed_size}, age={collar.profile.age_stage}")

    # 创建 HttpExporter（指向远程服务器）
    exporter = HttpExporter(api_url=api_url)
    print(f"   📡 HttpExporter → {api_url}")

    # 运行模拟
    print(f"\n   ⏳ 开始生成并上传数据...")
    total_sent = 0
    total_failed = 0
    all_times = []

    for tick in range(args.ticks):
        for collar in collars:
            record = collar.generate_one_record()

            tick_start = time.time()
            exporter.export(record)
            tick_elapsed = time.time() - tick_start
            all_times.append(tick_elapsed)

            total_sent += 1

        # 进度条
        progress = (tick + 1) / args.ticks * 100
        sys.stdout.write(
            f"\r   📈 进度: {tick+1}/{args.ticks} ticks "
            f"({total_sent} 条已发送) [{progress:.0f}%]"
        )
        sys.stdout.flush()

        if args.interval > 0 and tick < args.ticks - 1:
            time.sleep(args.interval)

    print()  # 换行

    # flush + close
    exporter.flush()
    exporter.close()

    # ══════════════════════════════════════════
    # Step 4: 验证服务器接收
    # ══════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✅ Step 4: 验证服务器接收情况")
    print("=" * 60)

    time.sleep(1)  # 等一秒让服务器处理完
    after_count = get_server_count(base_url)
    new_records = after_count - before_count if after_count >= 0 and before_count >= 0 else -1

    print(f"   发送前: {before_count} 条")
    print(f"   发送后: {after_count} 条")
    print(f"   新增: {new_records} 条")
    print(f"   预期: {expected_records} 条")

    if new_records == expected_records:
        print(f"   ✅ 完全匹配！所有 {expected_records} 条数据都成功上传")
    elif new_records > 0:
        print(f"   ⚠️  数据有差异 (可能有其他客户端同时在发)")
    else:
        print(f"   ❌ 数据未增长，上传可能失败")

    # ══════════════════════════════════════════
    # Step 5: 性能统计
    # ══════════════════════════════════════════
    print("\n" + "=" * 60)
    print("📊 Step 5: 性能统计")
    print("=" * 60)

    if all_times:
        avg_time = sum(all_times) / len(all_times)
        max_time = max(all_times)
        min_time = min(all_times)

        print(f"   总请求数: {len(all_times)}")
        print(f"   平均响应: {avg_time:.3f}s")
        print(f"   最快响应: {min_time:.3f}s")
        print(f"   最慢响应: {max_time:.3f}s")

        if max_time < 1.0:
            print(f"   ✅ 最慢 {max_time:.3f}s < 1s，满足响应时间要求")
        else:
            print(f"   ⚠️  最慢 {max_time:.3f}s >= 1s，部分请求超出要求")

    print(f"\n   Engine 统计: {exporter}")

    # ══════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════
    print("\n" + "=" * 60)
    print("📋 最终汇总")
    print("=" * 60)

    all_pass = True
    checks = {
        "服务器连通": after_count >= 0,
        "数据上传": new_records >= expected_records,
        "响应 < 1s": max(all_times) < 1.0 if all_times else False,
    }

    for name, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"   {icon} {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("🎉 全部通��！本地 Engine 可以正常上传数据到远程服务器！")
    else:
        print("⚠️  部分检查未通过，请查看上面的详细信息")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()