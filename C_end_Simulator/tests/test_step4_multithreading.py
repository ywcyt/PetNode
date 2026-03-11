"""
Step 4 测试 A：多线程测试

测试范围：
  - 多线程并行数据生成：验证线程池并行生成数据的正确性
  - 线程安全性：验证 FileExporter 在多线程环境下写入数据不丢失
  - 并发 SmartCollar：多个项圈在线程池中同时生成记录
  - 数据完整性：多线程环境下记录字段不丢失、不损坏
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from engine.models.dog_profile import DogProfile
from engine.models.smart_collar import SmartCollar
from engine.exporters.file_exporter import FileExporter
from engine.traits import CardiacRisk, OrthoRisk


# ────────── 多线程 SmartCollar 数据生成测试 ──────────


class TestMultithreadingDataGeneration:
    """验证多个 SmartCollar 实例在线程池中并行生成数据的正确性"""

    def test_parallel_collars_generate_correct_count(self):
        """4 个项圈各生成 50 条记录，线程池并行应产出 200 条"""
        num_dogs = 4
        num_ticks = 50
        collars = [
            SmartCollar(seed=i * 100)
            for i in range(num_dogs)
        ]

        all_records: list[dict] = []
        with ThreadPoolExecutor(max_workers=num_dogs) as executor:
            for _ in range(num_ticks):
                futures = [
                    executor.submit(collar.generate_one_record)
                    for collar in collars
                ]
                for future in as_completed(futures):
                    all_records.append(future.result())

        assert len(all_records) == num_dogs * num_ticks

    def test_parallel_records_have_valid_fields(self):
        """线程池并行生成的每条记录都应包含完整的 13 个必需字段"""
        expected_keys = {
            "user_id", "device_id", "timestamp", "behavior", "heart_rate",
            "resp_rate", "temperature", "steps", "battery",
            "gps_lat", "gps_lng", "event", "event_phase",
        }
        collars = [SmartCollar(seed=i) for i in range(3)]
        with ThreadPoolExecutor(max_workers=3) as executor:
            for _ in range(20):
                futures = [
                    executor.submit(collar.generate_one_record)
                    for collar in collars
                ]
                for future in as_completed(futures):
                    record = future.result()
                    assert set(record.keys()) == expected_keys

    def test_parallel_vital_ranges(self):
        """多线程生成的记录生理指标应全部在合法范围内"""
        collars = [SmartCollar(seed=i * 7) for i in range(4)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            for _ in range(30):
                futures = [
                    executor.submit(collar.generate_one_record)
                    for collar in collars
                ]
                for future in as_completed(futures):
                    r = future.result()
                    assert 30 <= r["heart_rate"] <= 250
                    assert 8 <= r["resp_rate"] <= 80
                    assert 36.0 <= r["temperature"] <= 42.0

    def test_parallel_different_device_ids(self):
        """并行的多个项圈应产生不同的 device_id"""
        collars = [SmartCollar(seed=i * 10) for i in range(5)]
        device_ids = set()
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(collar.generate_one_record)
                for collar in collars
            ]
            for future in as_completed(futures):
                device_ids.add(future.result()["device_id"])
        assert len(device_ids) == 5


# ────────── FileExporter 线程安全测试 ──────────


class TestMultithreadingFileExporter:
    """验证 FileExporter 在多线程写入环境下的线程安全性"""

    def test_concurrent_writes_no_data_loss(self, tmp_path: Path):
        """多线程同时 export()，最终文件行数应等于总记录数"""
        exporter = FileExporter(output_dir=tmp_path)
        num_threads = 4
        records_per_thread = 50

        def write_records(thread_id: int) -> int:
            for i in range(records_per_thread):
                exporter.export({
                    "thread_id": thread_id,
                    "index": i,
                    "device_id": f"dev_{thread_id}",
                })
            return records_per_thread

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(write_records, t)
                for t in range(num_threads)
            ]
            total = sum(f.result() for f in as_completed(futures))

        exporter.flush()
        exporter.close()

        lines = exporter.filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == total
        assert total == num_threads * records_per_thread

    def test_concurrent_writes_valid_json(self, tmp_path: Path):
        """多线程写入的每行应是合法的 JSON（无交错损坏）"""
        exporter = FileExporter(output_dir=tmp_path)

        def write_records(thread_id: int) -> None:
            collar = SmartCollar(seed=thread_id * 42)
            for _ in range(30):
                record = collar.generate_one_record()
                exporter.export(record)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(write_records, t) for t in range(4)]
            for f in as_completed(futures):
                f.result()

        exporter.flush()
        exporter.close()

        lines = exporter.filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 120  # 4 threads × 30 records
        for line in lines:
            parsed = json.loads(line)  # 不应抛 JSONDecodeError
            assert "device_id" in parsed

    def test_concurrent_collar_and_export_integration(self, tmp_path: Path):
        """模拟引擎实际工作模式：线程池并行生成 + 导出"""
        num_dogs = 3
        num_ticks = 40
        collars = [
            SmartCollar(
                profile=DogProfile(
                    dog_id=f"dog_{i}",
                    traits=[CardiacRisk()] if i % 2 == 0 else [],
                ),
                seed=i * 11,
            )
            for i in range(num_dogs)
        ]
        exporter = FileExporter(output_dir=tmp_path)

        with ThreadPoolExecutor(max_workers=num_dogs) as executor:
            for _ in range(num_ticks):
                futures = [
                    executor.submit(collar.generate_one_record)
                    for collar in collars
                ]
                for future in as_completed(futures):
                    exporter.export(future.result())

        exporter.flush()
        exporter.close()

        lines = exporter.filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == num_dogs * num_ticks

        # 验证 device_id 种类正确
        device_ids = set()
        for line in lines:
            parsed = json.loads(line)
            device_ids.add(parsed["device_id"])
        assert len(device_ids) == num_dogs


# ────────── run() 函数多线程集成测试 ──────────


class TestRunMultithreading:
    """验证 run() 调度器的多线程并行工作模式"""

    def test_run_multi_dog_parallel(self, tmp_path: Path):
        """run() 使用多线程时，多只狗应并行生成数据，记录数正确"""
        from engine.main import run
        records = run(
            num_dogs=4,
            num_ticks=25,
            seed=42,
            output_dir=tmp_path,
        )
        assert len(records) == 100  # 4 dogs × 25 ticks
        # 应有 4 个不同的 device_id
        device_ids = {r["device_id"] for r in records}
        assert len(device_ids) == 4

    def test_run_multi_user_multi_dog_parallel(self, tmp_path: Path):
        """多用户多狗并行模式应正确分配 user_id"""
        from engine.main import run
        records = run(
            num_dogs=6,
            num_ticks=10,
            seed=42,
            output_dir=tmp_path,
            num_users=3,
        )
        assert len(records) == 60  # 6 dogs × 10 ticks
        user_ids = {r["user_id"] for r in records}
        assert len(user_ids) == 3
        device_ids = {r["device_id"] for r in records}
        assert len(device_ids) == 6

    def test_run_large_scale_parallel(self, tmp_path: Path):
        """大规模并行：8 只狗 × 50 ticks = 400 条记录"""
        from engine.main import run
        records = run(
            num_dogs=8,
            num_ticks=50,
            seed=42,
            output_dir=tmp_path,
        )
        assert len(records) == 400
        # 验证 JSONL 输出
        jsonl = tmp_path / "realtime_stream.jsonl"
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 400
