#!/usr/bin/env python3
"""
demo_classroom.py —— PetNode 第二阶段课堂验收演示脚本

演示流程：
  第一部分：连通性验证
    1. 🔌 健康检查（GET /api/health），显示服务器状态，记录 initial_count

  第二部分：鉴权机制演示（给老师看安全性）
    2. 🔐 无 Authorization 头          → 期望 401
    3. 🔐 错误 API Key                  → 期望 401
    4. 🔐 有 API Key 但缺少 HMAC 签名   → 期望 403
    5. 🔐 数据被篡改（签名与 body 不匹配）→ 期望 403
    6. ✅ 正确 API Key + 正确 HMAC 签名  → 期望 200

  第三部分：数据上传演示
    7. 📤 单条上传：完整 12 字段项圈数据
    8. 📦 批量上传：20 条模拟数据，统计成功/失败/平均响应时间
    9. 📊 再次健康检查，显示 total_received 变化

  第四部分：清理说明
    10. 🧹 打印 MongoDB 清理命令（服务端无删除 API，需手动清理）

用法：
  python scripts/demo_classroom.py                    # 默认连 47.109.200.132:5000
  python scripts/demo_classroom.py --host 127.0.0.1  # 测本地
  python scripts/demo_classroom.py --batch 10        # 只批量上传 10 条
  python scripts/demo_classroom.py --help            # 查看所有参数
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
    print("❌ 缺少 requests 库，请执行：pip install requests")
    sys.exit(1)

# ────────────────── 终端彩色输出常量 ──────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_RED    = "\033[31m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_WHITE  = "\033[97m"

# ────────────────── 默认常量 ──────────────────

_DEFAULT_API_KEY  = "petnode_secret_key_2026"
_DEFAULT_HMAC_KEY = "petnode_hmac_secret_2026"

# 单条上传示例数据的 device_id
_DEMO_DEVICE_SINGLE = "demo_collar_001"


# ────────────────── 命令行参数 ──────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PetNode 第二阶段课堂验收演示脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host",     default="47.109.200.132",      help="服务器地址（默认 47.109.200.132）")
    parser.add_argument("--port",     type=int, default=5000,         help="服务器端口（默认 5000）")
    parser.add_argument("--api-key",  default=_DEFAULT_API_KEY,       help="API Key（默认 petnode_secret_key_2026）")
    parser.add_argument("--hmac-key", default=_DEFAULT_HMAC_KEY,      help="HMAC 密钥（默认 petnode_hmac_secret_2026）")
    parser.add_argument("--timeout",  type=int, default=5,            help="请求超时秒数（默认 5）")
    parser.add_argument("--batch",    type=int, default=20,           help="批量上传条数（默认 20）")
    return parser.parse_args()


# ────────────────── 工具函数 ──────────────────

def _print_sep(title: str = "") -> None:
    """打印带标题的分隔线"""
    line = "=" * 60
    if title:
        print(f"\n{_BOLD}{_CYAN}{line}{_RESET}")
        print(f"{_BOLD}{_CYAN}  {title}{_RESET}")
        print(f"{_BOLD}{_CYAN}{line}{_RESET}")
    else:
        print(f"{_CYAN}{line}{_RESET}")


def _ok(msg: str) -> None:
    print(f"   {_GREEN}✅ {msg}{_RESET}")


def _fail(msg: str) -> None:
    print(f"   {_RED}❌ {msg}{_RESET}")


def _info(msg: str) -> None:
    print(f"   {_WHITE}{msg}{_RESET}")


def _warn(msg: str) -> None:
    print(f"   {_YELLOW}⚠️  {msg}{_RESET}")


def _calc_sig(body_bytes: bytes, hmac_key: str) -> str:
    """使用 HMAC-SHA256 对请求体 bytes 计算签名（与服务端完全一致）"""
    return hmac.new(
        hmac_key.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()


def _send_authenticated(
    url: str,
    record: dict,
    api_key: str,
    hmac_key: str,
    timeout: int = 5,
) -> "requests.Response":
    """
    辅助函数：对单条记录做完整的"序列化 → HMAC 签名 → 发送"流程。

    关键点：
    - 手动 json.dumps（不排序、ensure_ascii=False），保证与服务端验签的字节流完全一致
    - 用 data=body_bytes 发送原始 bytes，而不是 json= 参数（避免 requests 内部重新序列化）
    - 手动设置 Content-Type: application/json
    """
    # 1. 序列化：不用 sort_keys，与服务端约定保持一致
    body_bytes: bytes = json.dumps(record, ensure_ascii=False).encode("utf-8")

    # 2. 计算 HMAC-SHA256 签名
    signature = _calc_sig(body_bytes, hmac_key)

    # 3. 构造 headers 并 POST
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Signature": signature,
    }
    return requests.post(url, data=body_bytes, headers=headers, timeout=timeout)


def _build_record(
    index: int,
    behavior: str = "walking",
    heart_rate: float = 80.0,
    timestamp: str | None = None,
) -> dict:
    """
    构造一条完整的 12 字段项圈数据记录。
    """
    if timestamp is None:
        timestamp = f"2026-04-17T{index % 24:02d}:{(index * 3) % 60:02d}:00"
    return {
        "device_id":    f"demo_device_{index:04d}",
        "timestamp":    timestamp,
        "behavior":     behavior,
        "heart_rate":   heart_rate,
        "resp_rate":    float(15 + index % 10),
        "temperature":  round(38.0 + (index % 20) * 0.05, 2),
        "steps":        index * 10,
        "battery":      max(10, 100 - index),
        "gps_lat":      round(29.57 + (index % 5) * 0.001, 6),
        "gps_lng":      round(106.45 + (index % 5) * 0.001, 6),
        "event":        None,
        "event_phase":  None,
    }


# ────────────────── 各演示步骤 ──────────────────

def step_health_check(base_url: str, timeout: int) -> int:
    """
    第一部分 步骤 1：健康检查
    返回当前 total_received 计数（作为 initial_count）。
    """
    _print_sep("🔌 第一部分：连通性验证")
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 1  GET /api/health{_RESET}")
    print(f"{'─'*40}")
    try:
        resp = requests.get(f"{base_url}/api/health", timeout=timeout)
        _info(f"HTTP {resp.status_code}")
        data = resp.json()
        _info(f"响应：{json.dumps(data, ensure_ascii=False)}")
        count = data.get("total_received", 0)
        _ok(f"服务器在线，当前已接收数据：{_YELLOW}{count}{_RESET}{_GREEN} 条")
        return count
    except Exception as exc:
        _fail(f"健康检查失败：{exc}")
        _warn("无法连接到服务器，请确认服务已启动")
        sys.exit(1)


def step_auth_demo(base_url: str, api_key: str, hmac_key: str, timeout: int) -> list[tuple[str, bool]]:
    """
    第二部分：鉴权机制演示
    返回各子步骤的 (名称, 是否通过) 列表。
    """
    _print_sep("🔐 第二部分：鉴权机制演示（安全性展示）")

    # 一条最小合法 payload（后面几个负面测试不需要合法字段）
    _minimal = {
        "device_id":   "demo_device_auth",
        "timestamp":   "2026-04-17T00:00:00",
        "behavior":    "resting",
        "heart_rate":  70.0,
        "resp_rate":   16.0,
        "temperature": 38.5,
        "steps":       0,
        "battery":     100,
        "gps_lat":     29.57,
        "gps_lng":     106.45,
        "event":       None,
        "event_phase": None,
    }
    body_bytes = json.dumps(_minimal, ensure_ascii=False).encode("utf-8")

    results: list[tuple[str, bool]] = []

    # ── 子步骤 2：无 Authorization 头 → 期望 401 ──
    time.sleep(0.3)
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 2  🔐 无 Authorization 头 → 期望 401{_RESET}")
    print(f"{'─'*40}")
    try:
        resp = requests.post(
            f"{base_url}/api/data",
            data=body_bytes,
            headers={"Content-Type": "application/json"},  # 故意不带 Authorization
            timeout=timeout,
        )
        passed = resp.status_code == 401
        _info(f"HTTP {resp.status_code}  |  {resp.text.strip()}")
        if passed:
            _ok("符合预期，服务器拒绝了无鉴权请求（401 Unauthorized）")
        else:
            _fail(f"期望 401，实际 {resp.status_code}")
    except Exception as exc:
        _fail(f"请求异常：{exc}")
        passed = False
    results.append(("步骤 2  无 Authorization → 401", passed))

    # ── 子步骤 3：错误 API Key → 期望 401 ──
    time.sleep(0.3)
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 3  🔐 错误 API Key → 期望 401{_RESET}")
    print(f"{'─'*40}")
    try:
        resp = requests.post(
            f"{base_url}/api/data",
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer wrong_key_12345",  # 错误的 API Key
            },
            timeout=timeout,
        )
        passed = resp.status_code == 401
        _info(f"HTTP {resp.status_code}  |  {resp.text.strip()}")
        if passed:
            _ok("符合预期，服务器拒绝了错误 API Key（401 Unauthorized）")
        else:
            _fail(f"期望 401，实际 {resp.status_code}")
    except Exception as exc:
        _fail(f"请求异常：{exc}")
        passed = False
    results.append(("步骤 3  错误 API Key → 401", passed))

    # ── 子步骤 4：有正确 API Key 但缺少 X-Signature → 期望 403 ──
    time.sleep(0.3)
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 4  🔐 有正确 API Key 但缺少 HMAC 签名 → 期望 403{_RESET}")
    print(f"{'─'*40}")
    try:
        resp = requests.post(
            f"{base_url}/api/data",
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                # 故意不带 X-Signature
            },
            timeout=timeout,
        )
        passed = resp.status_code == 403
        _info(f"HTTP {resp.status_code}  |  {resp.text.strip()}")
        if passed:
            _ok("符合预期，服务器拒绝了缺少签名的请求（403 Forbidden）")
        else:
            _fail(f"期望 403，实际 {resp.status_code}")
    except Exception as exc:
        _fail(f"请求异常：{exc}")
        passed = False
    results.append(("步骤 4  缺少 HMAC 签名 → 403", passed))

    # ── 子步骤 5：数据被篡改（签名与实际 body 不匹配）→ 期望 403 ──
    time.sleep(0.3)
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 5  🔐 数据被篡改（签名与 body 不匹配）→ 期望 403{_RESET}")
    print(f"{'─'*40}")
    try:
        # 先对原始数据计算签名
        original_body = json.dumps({"heart_rate": 80}, ensure_ascii=False).encode("utf-8")
        sig_original   = _calc_sig(original_body, hmac_key)

        # 发送时把 body 替换成篡改后的数据，签名保持原始签名
        tampered_body = json.dumps({"heart_rate": 999}, ensure_ascii=False).encode("utf-8")

        resp = requests.post(
            f"{base_url}/api/data",
            data=tampered_body,                          # ← 篡改后的数据
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "X-Signature": sig_original,             # ← 原始数据的签名（不匹配）
            },
            timeout=timeout,
        )
        passed = resp.status_code == 403
        _info(f"HTTP {resp.status_code}  |  {resp.text.strip()}")
        if passed:
            _ok("符合预期，服务器检测到数据篡改（403 Forbidden）")
        else:
            _fail(f"期望 403，实际 {resp.status_code}")
    except Exception as exc:
        _fail(f"请求异常：{exc}")
        passed = False
    results.append(("步骤 5  数据被篡改 → 403", passed))

    # ── 子步骤 6：正确 API Key + 正确 HMAC 签名 → 期望 200 ──
    time.sleep(0.3)
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 6  ✅ 正确 API Key + 正确 HMAC 签名 → 期望 200{_RESET}")
    print(f"{'─'*40}")
    try:
        resp = _send_authenticated(f"{base_url}/api/data", _minimal, api_key, hmac_key, timeout)
        passed = resp.status_code == 200
        _info(f"HTTP {resp.status_code}  |  {resp.text.strip()}")
        if passed:
            _ok("鉴权全部通过，数据上传成功（200 OK）")
        else:
            _fail(f"期望 200，实际 {resp.status_code}")
    except Exception as exc:
        _fail(f"请求异常：{exc}")
        passed = False
    results.append(("步骤 6  正确鉴权 → 200", passed))

    return results


def step_single_upload(base_url: str, api_key: str, hmac_key: str, timeout: int) -> bool:
    """
    第三部分 步骤 7：单条上传演示（完整 12 字段）
    """
    _print_sep("📤 第三部分：数据上传演示")
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 7  📤 单条上传（完整 12 字段项圈数据）{_RESET}")
    print(f"{'─'*40}")

    record = {
        "device_id":   _DEMO_DEVICE_SINGLE,
        "timestamp":   "2026-04-17T10:00:00",
        "behavior":    "running",
        "heart_rate":  135.5,
        "resp_rate":   28.0,
        "temperature": 39.1,
        "steps":       3500,
        "battery":     87,
        "gps_lat":     29.5720,
        "gps_lng":     106.4530,
        "event":       "exercise",
        "event_phase": "peak",
    }

    _info("上传数据：")
    for k, v in record.items():
        _info(f"  {k}: {v}")

    try:
        t0  = time.time()
        resp = _send_authenticated(f"{base_url}/api/data", record, api_key, hmac_key, timeout)
        elapsed = (time.time() - t0) * 1000

        _info(f"\nHTTP {resp.status_code}  |  耗时 {elapsed:.1f} ms  |  {resp.text.strip()}")
        if resp.status_code == 200:
            _ok("单条上传成功")
            return True
        else:
            _fail(f"单条上传失败，状态码 {resp.status_code}")
            return False
    except Exception as exc:
        _fail(f"请求异常：{exc}")
        return False


def step_batch_upload(
    base_url: str,
    api_key: str,
    hmac_key: str,
    timeout: int,
    batch: int,
) -> tuple[int, int, float]:
    """
    第三部分 步骤 8：批量上传演示
    返回 (success_count, fail_count, avg_ms)
    """
    time.sleep(0.3)
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 8  📦 批量上传（{batch} 条模拟数据）{_RESET}")
    print(f"{'─'*40}")

    _BEHAVIORS = ["sleeping", "resting", "walking", "running"]
    success = 0
    fail    = 0
    total_ms: float = 0.0

    for i in range(batch):
        behavior   = _BEHAVIORS[i % len(_BEHAVIORS)]
        heart_rate = round(60.0 + (i * 3.7) % 100, 1)
        device_tag = f"demo_device_{i:04d}"          # 与 _build_record 保持一致
        record     = _build_record(i, behavior=behavior, heart_rate=heart_rate)

        try:
            t0   = time.time()
            resp = _send_authenticated(f"{base_url}/api/data", record, api_key, hmac_key, timeout)
            elapsed = (time.time() - t0) * 1000
            total_ms += elapsed

            if resp.status_code == 200:
                success += 1
                status_icon = f"{_GREEN}✓{_RESET}"
            else:
                fail += 1
                status_icon = f"{_RED}✗{_RESET}"

            print(
                f"   [{i+1:>3}/{batch}] {status_icon}  "
                f"HTTP {resp.status_code}  {elapsed:6.1f}ms  "
                f"device={device_tag}  behavior={behavior}",
            )
        except Exception as exc:
            fail += 1
            print(f"   [{i+1:>3}/{batch}] {_RED}✗{_RESET}  异常：{exc}")

        time.sleep(0.3)  # 避免过于密集的请求给服务器造成压力

    avg_ms = total_ms / batch if batch > 0 else 0.0

    print()
    _info(f"批量上传完成：{_GREEN}成功 {success} 条{_RESET}  {_RED}失败 {fail} 条{_RESET}  平均耗时 {avg_ms:.1f} ms")
    if fail == 0:
        _ok("全部批量上传成功")
    else:
        _warn(f"有 {fail} 条上传失败，请检查网络或服务器日志")

    return success, fail, avg_ms


def step_final_health(base_url: str, timeout: int, initial_count: int, expected_delta: int) -> bool:
    """
    第三部分 步骤 9：最终健康检查，验证 total_received 增量
    """
    time.sleep(0.3)
    print(f"\n{'─'*40}")
    print(f"{_BOLD}步骤 9  📊 再次健康检查（验证数据条数变化）{_RESET}")
    print(f"{'─'*40}")
    try:
        resp = requests.get(f"{base_url}/api/health", timeout=timeout)
        data = resp.json()
        current_count = data.get("total_received", 0)
        delta = current_count - initial_count

        _info(f"HTTP {resp.status_code}  |  {json.dumps(data, ensure_ascii=False)}")
        _info(f"演示前：{initial_count} 条  →  演示后：{current_count} 条  （新增 {delta} 条）")
        _info(f"预期新增：约 {expected_delta} 条（第 6 步 1 条 + 第 7 步 1 条 + 第 8 步 {expected_delta-2} 条）")

        if delta >= expected_delta - 2:   # 允许 ±2 的偏差（并发/重试等情况）
            _ok(f"total_received 符合预期，本次演示共上传 {delta} 条数据")
            return True
        else:
            _warn(f"新增条数 {delta} 与预期 {expected_delta} 有偏差，可能有部分请求未到达服务器")
            return False
    except Exception as exc:
        _fail(f"健康检查失败：{exc}")
        return False


def step_cleanup_instruction(batch: int) -> None:
    """
    第四部分：清理演示数据的说明
    （服务端没有删除 API，需要在服务器上手动执行 MongoDB 命令）
    """
    _print_sep("🧹 第四部分：清理演示数据")

    print(f"""
{_YELLOW}本演示脚本无法通过 API 自动删除服务端数据（服务端未提供 DELETE 接口）。

所有演示数据的 device_id 均以 "demo_" 开头，
可在服务器上执行以下 MongoDB 命令清理：{_RESET}

{_BOLD}{_GREEN}# 方法 1：直接在服务器上执行（需要先 SSH 登录）{_RESET}
{_CYAN}docker exec petnode-mongodb mongosh petnode --eval \\
  
{_RESET}
{_BOLD}{_GREEN}# 方法 2：SSH 一行命令（替换 <SERVER_IP> 为实际服务器 IP）{_RESET}

{_RESET}
{_YELLOW}删除后可再次访问 GET /api/health 确认数据已清理。{_RESET}
""")


# ────────────────── main ──────────────────

def main() -> None:
    args     = parse_args()
    base_url = f"http://{args.host}:{args.port}"
    api_key  = args.api_key
    hmac_key = args.hmac_key
    timeout  = args.timeout
    batch    = args.batch

    # ── 欢迎 Banner ──
    print(f"\n{_BOLD}{_CYAN}{'=' * 60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  🐾 PetNode 第二阶段课堂验收演示{_RESET}")
    print(f"{_BOLD}{_CYAN}{'=' * 60}{_RESET}")
    print(f"  目标服务器: {_YELLOW}{base_url}{_RESET}")
    print(f"  批量上传量: {_YELLOW}{batch} 条{_RESET}")
    print(f"  当前时间  : {_YELLOW}{time.strftime('%Y-%m-%d %H:%M:%S')}{_RESET}")
    print()

    all_results: list[tuple[str, bool]] = []

    # ════════════════════════════════════════════
    # 第一部分：连通性验证
    # ════════════════════════════════════════════
    initial_count = step_health_check(base_url, timeout)
    all_results.append(("步骤 1  健康检查 → 200", True))

    # ════════════════════════════════════════════
    # 第二部分：鉴权机制演示
    # ════════════════════════════════════════════
    time.sleep(0.3)
    auth_results = step_auth_demo(base_url, api_key, hmac_key, timeout)
    all_results.extend(auth_results)

    # ════════════════════════════════════════════
    # 第三部分：数据上传演示
    # ════════════════════════════════════════════
    time.sleep(0.3)
    single_ok = step_single_upload(base_url, api_key, hmac_key, timeout)
    all_results.append(("步骤 7  单条上传 → 200", single_ok))

    time.sleep(0.3)
    success_cnt, fail_cnt, avg_ms = step_batch_upload(base_url, api_key, hmac_key, timeout, batch)
    all_results.append(("步骤 8  批量上传（全部成功）", fail_cnt == 0))

    # 预期新增：步骤 6（1 条）+ 步骤 7（1 条）+ 步骤 8（batch 条）= batch + 2
    expected_delta = batch + 2
    health_ok = step_final_health(base_url, timeout, initial_count, expected_delta)
    all_results.append(("步骤 9  数据条数验证", health_ok))

    # ════════════════════════════════════════════
    # 第四部分：清理说明
    # ════════════════════════════════════════════
    step_cleanup_instruction(batch)

    # ════════════════════════════════════════════
    # 汇总结果
    # ════════════════════════════════════════════
    _print_sep("📋 演示结果汇总")
    print()
    for name, passed in all_results:
        icon = f"{_GREEN}✅{_RESET}" if passed else f"{_RED}❌{_RESET}"
        print(f"   {icon}  {name}")

    all_passed = all(p for _, p in all_results)
    print()
    if all_passed:
        print(f"{_BOLD}{_GREEN}{'=' * 60}{_RESET}")
        print(f"{_BOLD}{_GREEN}  🎉 全部演示步骤通过！第二阶段验收功能运行正常！{_RESET}")
        print(f"{_BOLD}{_GREEN}{'=' * 60}{_RESET}\n")
        sys.exit(0)
    else:
        failed_names = [n for n, p in all_results if not p]
        print(f"{_BOLD}{_YELLOW}{'=' * 60}{_RESET}")
        print(f"{_BOLD}{_YELLOW}  ⚠️  部分步骤未通过：{_RESET}")
        for n in failed_names:
            print(f"     {_RED}• {n}{_RESET}")
        print(f"{_BOLD}{_YELLOW}{'=' * 60}{_RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
