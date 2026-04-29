"""
MySQLStorage —— 将接收到的数据按规范化结构保存到 MySQL

对接方式：
- `user` / `device` / `trait_type` / `event_type` 作为基础字典表自动补齐
- 每次上报的模拟数据拆成多条 `telemetry_record`
- `event` / `event_phase` 通过 `event_instance` 记录一次事件实例

说明：
- 当前引擎上报的是一条扁平 JSON；这里把它转换成 `crebas.sql` 风格的规范化模型。
- `device_id` 在引擎侧是字符串，这里会稳定映射为一个 BIGINT 主键，同时把原始字符串保存到 `device_sn`。
- `user_id` 使用默认用户（可通过环境变量覆盖）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Optional

import pymysql
from pymysql.cursors import DictCursor

from .base_storage import BaseStorage

logger = logging.getLogger("storage.mysql")


TRAIT_TYPES: list[tuple[int, str, str, Optional[str]]] = [
    (1, "heart_rate", "心率", "bpm"),
    (2, "resp_rate", "呼吸频率", "次/分钟"),
    (3, "temperature", "体温", "°C"),
    (4, "steps", "步数", "step"),
    (5, "battery", "电量", "%"),
    (6, "gps_lat", "GPS纬度", "deg"),
    (7, "gps_lng", "GPS经度", "deg"),
    (8, "behavior", "行为状态", None),
]

EVENT_TYPES: dict[str, tuple[int, str, int]] = {
    "fever": (1, "发烧", 2),
    "injury": (2, "受伤", 1),
}


class MySQLStorage(BaseStorage):
    """MySQL 规范化存储实现。"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        charset: Optional[str] = None,
    ) -> None:
        self.host = host or os.environ.get("MYSQL_HOST", "localhost")
        self.port = port or int(os.environ.get("MYSQL_PORT", "3306"))
        self.db = db or os.environ.get("MYSQL_DB", "petnode")
        self.user = user or os.environ.get("MYSQL_USER", "root")
        self.password = password or os.environ.get("MYSQL_PASSWORD", "")
        self.charset = charset or os.environ.get("MYSQL_CHARSET", "utf8mb4")

        self.default_user_id = int(os.environ.get("MYSQL_DEFAULT_USER_ID", "1"))
        self.default_username = os.environ.get("MYSQL_DEFAULT_USERNAME", "petnode")
        self.default_password_hash = os.environ.get("MYSQL_DEFAULT_PASSWORD_HASH", "")
        self.default_nick_name = os.environ.get("MYSQL_DEFAULT_NICK_NAME", "PetNode")
        self.default_device_name_prefix = os.environ.get("MYSQL_DEVICE_NAME_PREFIX", "PetNode Device")
        self.default_pet_name_prefix = os.environ.get("MYSQL_PET_NAME_PREFIX", "PetNode Pet")

        try:
            self._connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db,
                charset=self.charset,
                cursorclass=DictCursor,
                autocommit=False,
            )
        except pymysql.Error:
            logger.error(
                "MySQLStorage connection failed: %s:%d, db=%s",
                self.host,
                self.port,
                self.db,
                exc_info=True,
            )
            raise

        self._open_events: dict[int, dict[str, object]] = {}
        self._ensure_schema()
        self._seed_reference_data()

        logger.info(
            "MySQLStorage initialized: %s:%d db=%s charset=%s",
            self.host,
            self.port,
            self.db,
            self.charset,
        )

    def _ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS `user` (
                user_id BIGINT NOT NULL PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                phone VARCHAR(11),
                nick_name VARCHAR(30) NOT NULL,
                create_time DATETIME(3) NOT NULL,
                update_time DATETIME(3) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS device (
                device_id BIGINT NOT NULL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                device_sn VARCHAR(50) NOT NULL,
                device_name VARCHAR(50) NOT NULL,
                pet_name VARCHAR(30) NOT NULL,
                is_online TINYINT,
                activate_time DATETIME(3),
                create_time DATETIME(3) NOT NULL,
                update_time DATETIME(3) NOT NULL,
                UNIQUE KEY uk_device_sn (device_sn),
                CONSTRAINT fk_device_user FOREIGN KEY (user_id) REFERENCES `user` (user_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS trait_type (
                trait_type_id BIGINT NOT NULL PRIMARY KEY,
                trait_code VARCHAR(50) NOT NULL,
                trait_name VARCHAR(50) NOT NULL,
                trait_unit VARCHAR(20),
                create_time DATETIME(3) NOT NULL,
                UNIQUE KEY uk_trait_code (trait_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS device_trait (
                device_id BIGINT NOT NULL,
                trait_type_id BIGINT NOT NULL,
                is_enabled TINYINT NOT NULL,
                create_time DATETIME(3) NOT NULL,
                PRIMARY KEY (device_id, trait_type_id),
                CONSTRAINT fk_device_trait_device FOREIGN KEY (device_id) REFERENCES device (device_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT,
                CONSTRAINT fk_device_trait_trait FOREIGN KEY (trait_type_id) REFERENCES trait_type (trait_type_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS event_type (
                event_type_id BIGINT NOT NULL PRIMARY KEY,
                event_code VARCHAR(50) NOT NULL,
                event_name VARCHAR(50) NOT NULL,
                event_level TINYINT NOT NULL,
                create_time DATETIME(3) NOT NULL,
                UNIQUE KEY uk_event_code (event_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS event_instance (
                event_instance_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                device_id BIGINT NOT NULL,
                event_type_id BIGINT NOT NULL,
                status TINYINT NOT NULL,
                event_content VARCHAR(500),
                start_time DATETIME(3) NOT NULL,
                end_time DATETIME(3),
                KEY idx_device_status_time (device_id, status, start_time),
                CONSTRAINT fk_event_instance_device FOREIGN KEY (device_id) REFERENCES device (device_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT,
                CONSTRAINT fk_event_instance_type FOREIGN KEY (event_type_id) REFERENCES event_type (event_type_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS telemetry_record (
                record_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                device_id BIGINT NOT NULL,
                event_instance_id BIGINT,
                trait_type_id BIGINT NOT NULL,
                trait_value VARCHAR(100) NOT NULL,
                timestamp DATETIME(3) NOT NULL,
                KEY idx_device_timestamp (device_id, timestamp),
                KEY idx_user_timestamp (user_id, timestamp),
                KEY idx_timestamp (timestamp),
                CONSTRAINT fk_telemetry_user FOREIGN KEY (user_id) REFERENCES `user` (user_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT,
                CONSTRAINT fk_telemetry_device FOREIGN KEY (device_id) REFERENCES device (device_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT,
                CONSTRAINT fk_telemetry_event FOREIGN KEY (event_instance_id) REFERENCES event_instance (event_instance_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT,
                CONSTRAINT fk_telemetry_trait FOREIGN KEY (trait_type_id) REFERENCES trait_type (trait_type_id)
                    ON DELETE RESTRICT ON UPDATE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
        ]

        try:
            with self._connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to initialize MySQL schema", exc_info=True)
            raise

    def _seed_reference_data(self) -> None:
        now = datetime.utcnow()
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT IGNORE INTO `user` (
                        user_id, username, password_hash, phone, nick_name, create_time, update_time
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        self.default_user_id,
                        self.default_username,
                        self.default_password_hash,
                        None,
                        self.default_nick_name,
                        now,
                        now,
                    ),
                )

                for trait_type_id, trait_code, trait_name, trait_unit in TRAIT_TYPES:
                    cursor.execute(
                        """
                        INSERT IGNORE INTO trait_type (
                            trait_type_id, trait_code, trait_name, trait_unit, create_time
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (trait_type_id, trait_code, trait_name, trait_unit, now),
                    )

                for event_code, (event_type_id, event_name, event_level) in EVENT_TYPES.items():
                    cursor.execute(
                        """
                        INSERT IGNORE INTO event_type (
                            event_type_id, event_code, event_name, event_level, create_time
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (event_type_id, event_code, event_name, event_level, now),
                    )

            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to seed MySQL reference data", exc_info=True)
            raise

    @staticmethod
    def _normalize_timestamp(raw_timestamp: object) -> datetime:
        if isinstance(raw_timestamp, datetime):
            return raw_timestamp.replace(tzinfo=None)

        if raw_timestamp is None:
            return datetime.utcnow()

        text = str(raw_timestamp).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            return parsed.replace(tzinfo=None)
        except ValueError:
            return datetime.utcnow()

    @staticmethod
    def _stable_device_id(device_sn: str) -> int:
        digest = hashlib.sha1(device_sn.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        value &= 0x7FFFFFFFFFFFFFFF
        return value or 1

    def _ensure_device(self, device_sn: str, timestamp: datetime) -> int:
        device_id = self._stable_device_id(device_sn)
        device_name = os.environ.get("MYSQL_DEVICE_NAME", f"{self.default_device_name_prefix}-{device_sn[:8]}")
        pet_name = os.environ.get("MYSQL_PET_NAME", f"{self.default_pet_name_prefix}-{device_sn[:6]}")

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT device_id FROM device WHERE device_id = %s OR device_sn = %s",
                    (device_id, device_sn),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """
                        INSERT INTO device (
                            device_id, user_id, device_sn, device_name, pet_name,
                            is_online, activate_time, create_time, update_time
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            device_id,
                            self.default_user_id,
                            device_sn,
                            device_name,
                            pet_name,
                            1,
                            timestamp,
                            timestamp,
                            timestamp,
                        ),
                    )

                    for trait_type_id, _, _, _ in TRAIT_TYPES:
                        cursor.execute(
                            """
                            INSERT IGNORE INTO device_trait (
                                device_id, trait_type_id, is_enabled, create_time
                            ) VALUES (%s, %s, %s, %s)
                            """,
                            (device_id, trait_type_id, 1, timestamp),
                        )

                    self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to ensure device row for device_sn=%s", device_sn, exc_info=True)
            raise

        return device_id

    def _ensure_event_type(self, event_name: str, timestamp: datetime) -> int:
        if event_name not in EVENT_TYPES:
            event_type_id = int.from_bytes(hashlib.sha1(event_name.encode("utf-8")).digest()[:6], "big")
            event_type_id &= 0x7FFFFFFFFFFFFFFF
            event_type_id = event_type_id or 1
            event_level = 1
            event_code = event_name
            event_display_name = event_name
        else:
            event_type_id, event_display_name, event_level = EVENT_TYPES[event_name]
            event_code = event_name

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event_type_id FROM event_type WHERE event_type_id = %s OR event_code = %s",
                    (event_type_id, event_code),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        """
                        INSERT INTO event_type (
                            event_type_id, event_code, event_name, event_level, create_time
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (event_type_id, event_code, event_display_name, event_level, timestamp),
                    )
                    self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to ensure event type for event_name=%s", event_name, exc_info=True)
            raise

        return event_type_id

    def _close_open_event(self, device_id: int, timestamp: datetime) -> None:
        cached = self._open_events.pop(device_id, None)
        if cached is None:
            return

        event_instance_id = int(cached["event_instance_id"])
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE event_instance
                    SET status = 0, end_time = %s, event_content = %s
                    WHERE event_instance_id = %s
                    """,
                    (
                        timestamp,
                        cached.get("event_content"),
                        event_instance_id,
                    ),
                )
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error(
                "Failed to close event instance: device_id=%s event_instance_id=%s",
                device_id,
                event_instance_id,
                exc_info=True,
            )
            raise

    def _ensure_open_event(
        self,
        device_id: int,
        event_name: str,
        event_phase: Optional[str],
        timestamp: datetime,
    ) -> int:
        event_type_id = self._ensure_event_type(event_name, timestamp)
        cached = self._open_events.get(device_id)

        event_content = json.dumps(
            {
                "event": event_name,
                "event_phase": event_phase,
                "timestamp": timestamp.isoformat(timespec="milliseconds"),
            },
            ensure_ascii=False,
        )

        if cached is not None and cached.get("event_name") == event_name:
            event_instance_id = int(cached["event_instance_id"])
            try:
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE event_instance
                        SET event_content = %s
                        WHERE event_instance_id = %s
                        """,
                        (event_content, event_instance_id),
                    )
                self._connection.commit()
            except pymysql.Error:
                self._connection.rollback()
                logger.error(
                    "Failed to update open event instance: device_id=%s event_instance_id=%s",
                    device_id,
                    event_instance_id,
                    exc_info=True,
                )
                raise
            cached["event_content"] = event_content
            return event_instance_id

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO event_instance (
                        device_id, event_type_id, status, event_content, start_time, end_time
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (device_id, event_type_id, 1, event_content, timestamp, None),
                )
                event_instance_id = int(cursor.lastrowid)
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error(
                "Failed to create event instance: device_id=%s event_name=%s",
                device_id,
                event_name,
                exc_info=True,
            )
            raise

        self._open_events[device_id] = {
            "event_name": event_name,
            "event_instance_id": event_instance_id,
            "event_content": event_content,
        }
        return event_instance_id

    def _insert_telemetry_rows(
        self,
        user_id: int,
        device_id: int,
        event_instance_id: Optional[int],
        timestamp: datetime,
        record: dict,
    ) -> None:
        rows = [
            (user_id, device_id, event_instance_id, 1, str(record.get("heart_rate")), timestamp),
            (user_id, device_id, event_instance_id, 2, str(record.get("resp_rate")), timestamp),
            (user_id, device_id, event_instance_id, 3, str(record.get("temperature")), timestamp),
            (user_id, device_id, event_instance_id, 4, str(record.get("steps")), timestamp),
            (user_id, device_id, event_instance_id, 5, str(record.get("battery")), timestamp),
            (user_id, device_id, event_instance_id, 6, str(record.get("gps_lat")), timestamp),
            (user_id, device_id, event_instance_id, 7, str(record.get("gps_lng")), timestamp),
            (user_id, device_id, event_instance_id, 8, str(record.get("behavior")), timestamp),
        ]

        try:
            with self._connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO telemetry_record (
                        user_id, device_id, event_instance_id, trait_type_id, trait_value, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error(
                "Failed to insert telemetry rows: device_id=%s event_instance_id=%s",
                device_id,
                event_instance_id,
                exc_info=True,
            )
            raise

    def save(self, record: dict) -> None:
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        device_sn = str(record.get("device_id") or "unknown-device")
        timestamp = self._normalize_timestamp(record.get("timestamp"))
        event_name = record.get("event")
        event_phase = record.get("event_phase")

        device_id = self._ensure_device(device_sn, timestamp)
        user_id = self.default_user_id

        if event_name:
            event_instance_id = self._ensure_open_event(device_id, str(event_name), str(event_phase) if event_phase is not None else None, timestamp)
        else:
            self._close_open_event(device_id, timestamp)
            event_instance_id = None

        self._insert_telemetry_rows(
            user_id=user_id,
            device_id=device_id,
            event_instance_id=event_instance_id,
            timestamp=timestamp,
            record=record,
        )

    def close(self) -> None:
        try:
            self._connection.close()
        except Exception:
            logger.warning("Error closing MySQLStorage connection", exc_info=True)
"""
MySQLStorage —— 将接收到的数据保存到 MySQL 规范化表结构

对接方式：
- 复用 crebas.sql 的实体划分：user / device / trait_type / event_type / event_instance / telemetry_record
- Engine 每次上报的一条 JSON 记录，会被拆成多条 telemetry_record
- 若记录中带有 event，则会自动维护 event_instance 的开启与关闭

设计原则：
- app.py 仍然只依赖 BaseStorage.save()/close()，不需要知道底层表结构
- 支持自动建表和默认字典数据，避免人工预置主数据
- device_id 仍保留为 Engine 的字符串 device_id 的稳定映射值，device_sn 保存原始字符串
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Optional

import pymysql
from pymysql.cursors import DictCursor

from .base_storage import BaseStorage

logger = logging.getLogger("storage.mysql")


class MySQLStorage(BaseStorage):
    """MySQL 规范化存储实现。"""

    _TRAIT_TYPES: list[tuple[int, str, str, Optional[str]]] = [
        (1, "heart_rate", "心率", "bpm"),
        (2, "resp_rate", "呼吸频率", "次/分钟"),
        (3, "temperature", "体温", "°C"),
        (4, "steps", "步数", "step"),
        (5, "battery", "电量", "%"),
        (6, "gps_lat", "GPS纬度", "deg"),
        (7, "gps_lng", "GPS经度", "deg"),
        (8, "behavior", "行为状态", None),
    ]

    _EVENT_TYPES: dict[str, tuple[int, str, int]] = {
        "fever": (1, "发烧", 2),
        "injury": (2, "受伤", 1),
    }

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        charset: Optional[str] = None,
    ) -> None:
        self.host = host or os.environ.get("MYSQL_HOST", "localhost")
        self.port = port or int(os.environ.get("MYSQL_PORT", "3306"))
        self.db = db or os.environ.get("MYSQL_DB", "petnode")
        self.user = user or os.environ.get("MYSQL_USER", "root")
        self.password = password or os.environ.get("MYSQL_PASSWORD", "")
        self.charset = charset or os.environ.get("MYSQL_CHARSET", "utf8mb4")
        self.default_user_id = int(os.environ.get("MYSQL_DEFAULT_USER_ID", "1"))
        self.default_username = os.environ.get("MYSQL_DEFAULT_USERNAME", "petnode")
        self.default_nick_name = os.environ.get("MYSQL_DEFAULT_NICK_NAME", "PetNode")
        self.default_device_name_prefix = os.environ.get("MYSQL_DEVICE_NAME_PREFIX", "PetNode-")

        try:
            self._connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db,
                charset=self.charset,
                cursorclass=DictCursor,
                autocommit=False,
            )
        except pymysql.Error as exc:
            logger.error(
                "MySQLStorage connection failed: %s:%d, db=%s, error=%s",
                self.host,
                self.port,
                self.db,
                exc,
            )
            raise

        self._open_event_cache: dict[int, tuple[int, str]] = {}
        self._ensure_schema()
        self._seed_lookup_tables()
        logger.info(
            "MySQLStorage initialized: host=%s port=%s db=%s user=%s",
            self.host,
            self.port,
            self.db,
            self.user,
        )

    # ------------------------------------------------------------------
    # Schema / seed data
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """创建与 crebas.sql 对齐的基础表结构。"""
        statements = [
            """
            CREATE TABLE IF NOT EXISTS `user` (
                user_id BIGINT NOT NULL,
                username VARCHAR(50) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                phone VARCHAR(11),
                nick_name VARCHAR(30) NOT NULL,
                create_time DATETIME(3) NOT NULL,
                update_time DATETIME(3) NOT NULL,
                PRIMARY KEY (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS device (
                device_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                device_sn VARCHAR(50) NOT NULL,
                device_name VARCHAR(50) NOT NULL,
                pet_name VARCHAR(30) NOT NULL,
                is_online TINYINT,
                activate_time DATETIME(3),
                create_time DATETIME(3) NOT NULL,
                update_time DATETIME(3) NOT NULL,
                PRIMARY KEY (device_id),
                UNIQUE KEY uk_device_sn (device_sn),
                KEY idx_device_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS device_trait (
                device_id BIGINT NOT NULL,
                trait_type_id BIGINT NOT NULL,
                is_enabled TINYINT NOT NULL,
                create_time DATETIME(3) NOT NULL,
                PRIMARY KEY (device_id, trait_type_id),
                KEY idx_trait_type (trait_type_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS event_type (
                event_type_id BIGINT NOT NULL,
                event_code VARCHAR(50) NOT NULL,
                event_name VARCHAR(50) NOT NULL,
                event_level TINYINT NOT NULL,
                create_time DATETIME(3) NOT NULL,
                PRIMARY KEY (event_type_id),
                UNIQUE KEY uk_event_code (event_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS event_instance (
                event_instance_id BIGINT NOT NULL AUTO_INCREMENT,
                device_id BIGINT NOT NULL,
                event_type_id BIGINT NOT NULL,
                status TINYINT NOT NULL,
                event_content VARCHAR(500),
                start_time DATETIME(3) NOT NULL,
                end_time DATETIME(3),
                PRIMARY KEY (event_instance_id),
                KEY idx_device_status_time (device_id, status, start_time),
                KEY idx_event_type (event_type_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS trait_type (
                trait_type_id BIGINT NOT NULL,
                trait_code VARCHAR(50) NOT NULL,
                trait_name VARCHAR(50) NOT NULL,
                trait_unit VARCHAR(20),
                create_time DATETIME(3) NOT NULL,
                PRIMARY KEY (trait_type_id),
                UNIQUE KEY uk_trait_code (trait_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS telemetry_record (
                record_id BIGINT NOT NULL AUTO_INCREMENT,
                user_id BIGINT NOT NULL,
                device_id BIGINT NOT NULL,
                event_instance_id BIGINT,
                trait_type_id BIGINT NOT NULL,
                trait_value VARCHAR(100) NOT NULL,
                timestamp DATETIME(3) NOT NULL,
                PRIMARY KEY (record_id),
                KEY idx_device_timestamp (device_id, timestamp),
                KEY idx_user_timestamp (user_id, timestamp),
                KEY idx_timestamp (timestamp),
                KEY idx_trait_type (trait_type_id),
                KEY idx_event_instance (event_instance_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
        ]

        try:
            with self._connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to initialize MySQL schema", exc_info=True)
            raise

    def _seed_lookup_tables(self) -> None:
        """插入默认用户、trait_type 和 event_type 字典数据。"""
        now = self._utc_now()

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO `user` (user_id, username, password_hash, phone, nick_name, create_time, update_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        username = VALUES(username),
                        nick_name = VALUES(nick_name),
                        update_time = VALUES(update_time)
                    """,
                    (
                        self.default_user_id,
                        self.default_username,
                        "",
                        None,
                        self.default_nick_name,
                        now,
                        now,
                    ),
                )

                for trait_type_id, trait_code, trait_name, trait_unit in self._TRAIT_TYPES:
                    cursor.execute(
                        """
                        INSERT INTO trait_type (trait_type_id, trait_code, trait_name, trait_unit, create_time)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            trait_name = VALUES(trait_name),
                            trait_unit = VALUES(trait_unit)
                        """,
                        (trait_type_id, trait_code, trait_name, trait_unit, now),
                    )

                for event_code, (event_type_id, event_name, event_level) in self._EVENT_TYPES.items():
                    cursor.execute(
                        """
                        INSERT INTO event_type (event_type_id, event_code, event_name, event_level, create_time)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            event_name = VALUES(event_name),
                            event_level = VALUES(event_level)
                        """,
                        (event_type_id, event_code, event_name, event_level, now),
                    )

            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to seed MySQL lookup tables", exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.utcnow().replace(microsecond=0)

    @staticmethod
    def _parse_timestamp(value: object) -> datetime:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None, microsecond=(value.microsecond // 1000) * 1000)

        if not isinstance(value, str) or not value.strip():
            return MySQLStorage._utc_now()

        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return MySQLStorage._utc_now()

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed.replace(microsecond=(parsed.microsecond // 1000) * 1000)

    @staticmethod
    def _stable_device_id(device_sn: str) -> int:
        digest = hashlib.sha1(device_sn.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF
        return value or 1

    def _ensure_device(self, device_sn: str, now: datetime) -> int:
        device_id = self._stable_device_id(device_sn)
        device_name = f"{self.default_device_name_prefix}{device_sn[:8]}"
        pet_name = device_sn[:30]

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO device (device_id, user_id, device_sn, device_name, pet_name, is_online, activate_time, create_time, update_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        device_sn = VALUES(device_sn),
                        device_name = VALUES(device_name),
                        pet_name = VALUES(pet_name),
                        is_online = VALUES(is_online),
                        update_time = VALUES(update_time)
                    """,
                    (
                        device_id,
                        self.default_user_id,
                        device_sn,
                        device_name,
                        pet_name,
                        1,
                        now,
                        now,
                        now,
                    ),
                )

                for trait_type_id, _, _, _ in self._TRAIT_TYPES:
                    cursor.execute(
                        """
                        INSERT INTO device_trait (device_id, trait_type_id, is_enabled, create_time)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            is_enabled = VALUES(is_enabled)
                        """,
                        (device_id, trait_type_id, 1, now),
                    )

            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to upsert device: device_sn=%s", device_sn, exc_info=True)
            raise

        return device_id

    def _ensure_event_type(self, event_name: str, now: datetime) -> int:
        event_code = event_name.strip().lower()
        event_type_id, event_label, event_level = self._EVENT_TYPES.get(
            event_code,
            (self._stable_device_id(f"event:{event_code}"), event_name, 1),
        )

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO event_type (event_type_id, event_code, event_name, event_level, create_time)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        event_name = VALUES(event_name),
                        event_level = VALUES(event_level)
                    """,
                    (event_type_id, event_code, event_label, event_level, now),
                )
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to upsert event type: %s", event_name, exc_info=True)
            raise

        return event_type_id

    def _ensure_active_event(
        self,
        device_id: int,
        event_name: Optional[str],
        event_phase: Optional[str],
        record_timestamp: datetime,
        now: datetime,
    ) -> Optional[int]:
        """确保事件实例状态与当前上报一致。"""
        if not event_name:
            cached = self._open_event_cache.pop(device_id, None)
            if cached is not None:
                event_instance_id, _ = cached
                try:
                    with self._connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE event_instance
                            SET status = %s, end_time = %s
                            WHERE event_instance_id = %s
                            """,
                            (0, now, event_instance_id),
                        )
                    self._connection.commit()
                except pymysql.Error:
                    self._connection.rollback()
                    logger.warning("Failed to close event instance %s", event_instance_id, exc_info=True)
            return None

        event_type_id = self._ensure_event_type(event_name, now)
        cached = self._open_event_cache.get(device_id)

        if cached is None or cached[1] != event_name:
            event_content = json.dumps(
                {
                    "event": event_name,
                    "phase": event_phase,
                    "opened_at": record_timestamp.isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
            )
            try:
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO event_instance (device_id, event_type_id, status, event_content, start_time, end_time)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (device_id, event_type_id, 1, event_content, record_timestamp, None),
                    )
                    event_instance_id = int(cursor.lastrowid)
                self._connection.commit()
            except pymysql.Error:
                self._connection.rollback()
                logger.error("Failed to open event instance: %s", event_name, exc_info=True)
                raise

            self._open_event_cache[device_id] = (event_instance_id, event_name)
            return event_instance_id

        event_instance_id = cached[0]
        event_content = json.dumps(
            {
                "event": event_name,
                "phase": event_phase,
                "updated_at": record_timestamp.isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
        )

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE event_instance
                    SET status = %s, event_content = %s
                    WHERE event_instance_id = %s
                    """,
                    (1, event_content, event_instance_id),
                )
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.warning("Failed to refresh event instance %s", event_instance_id, exc_info=True)
            raise

        return event_instance_id

    def _insert_telemetry_rows(
        self,
        user_id: int,
        device_id: int,
        event_instance_id: Optional[int],
        record_timestamp: datetime,
        record: dict,
    ) -> None:
        telemetry_values = [
            (1, record.get("heart_rate")),
            (2, record.get("resp_rate")),
            (3, record.get("temperature")),
            (4, record.get("steps")),
            (5, record.get("battery")),
            (6, record.get("gps_lat")),
            (7, record.get("gps_lng")),
            (8, record.get("behavior")),
        ]

        try:
            with self._connection.cursor() as cursor:
                for trait_type_id, trait_value in telemetry_values:
                    cursor.execute(
                        """
                        INSERT INTO telemetry_record (
                            user_id, device_id, event_instance_id, trait_type_id, trait_value, timestamp
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            user_id,
                            device_id,
                            event_instance_id,
                            trait_type_id,
                            str(trait_value),
                            record_timestamp,
                        ),
                    )
            self._connection.commit()
        except pymysql.Error:
            self._connection.rollback()
            logger.error("Failed to insert telemetry rows", exc_info=True)
            raise

    # ------------------------------------------------------------------
    # BaseStorage API
    # ------------------------------------------------------------------

    def save(self, record: dict) -> None:
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        device_sn = str(record.get("device_id") or "").strip()
        if not device_sn:
            raise ValueError("record.device_id is required")

        record_timestamp = self._parse_timestamp(record.get("timestamp"))
        now = self._utc_now()

        device_id = self._ensure_device(device_sn, now)
        event_name = record.get("event")
        event_phase = record.get("event_phase")
        event_instance_id = self._ensure_active_event(
            device_id=device_id,
            event_name=str(event_name).strip() if event_name not in (None, "") else None,
            event_phase=str(event_phase).strip() if event_phase not in (None, "") else None,
            record_timestamp=record_timestamp,
            now=now,
        )

        self._insert_telemetry_rows(
            user_id=self.default_user_id,
            device_id=device_id,
            event_instance_id=event_instance_id,
            record_timestamp=record_timestamp,
            record=record,
        )

    def close(self) -> None:
        try:
            self._connection.close()
            logger.info("MySQLStorage connection closed")
        except Exception:
            logger.warning("Error closing MySQLStorage connection", exc_info=True)