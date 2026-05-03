"""
test_internal_services.py —— 内部服务函数单元测试

使用 mongomock 模拟 MongoDB，无需真实数据库。

覆盖范围：
  services/identity.py
    - normalize_identity()
    - build_user_hash()
    - get_or_create_user_hash()

  services/binding.py
    - bind_user_to_wechat()
    - unbind_user_from_wechat()
    - bind_user_to_device()
    - unbind_user_from_device()
    - assert_user_owns_pet()

  services/telemetry.py
    - get_pet_summary()
    - get_latest_respiration()
    - get_respiration_series()
    - get_latest_heart_rate()
    - get_heart_rate_series()
    - list_pet_events()

  blueprints/wechat.py — POST /api/v1/wechat/unbind（新增接口）
"""

from __future__ import annotations

import json
import os

import mongomock
import pytest

os.environ.setdefault("STORAGE_BACKEND", "file")
os.environ.setdefault("DATA_DIR", "/tmp/petnode_test")
os.environ.setdefault("JWT_SECRET", "test_secret_key_for_tests_only")
os.environ.setdefault("HASH_SECRET", "test_hash_secret_for_tests_only")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "petnode_test")

import flask_server.db as _db_module  # noqa: E402

_mock_client = mongomock.MongoClient()


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch):
    """每个测试前重置并注入 mongomock 数据库。"""
    _db_module._client = _mock_client
    db = _mock_client[os.environ["MONGO_DB"]]
    for col in ["wechat_bindings", "users", "user_pets", "received_records"]:
        db[col].drop()
    yield db


# ────────────────── 辅助 ──────────────────

def _get_db():
    return _mock_client[os.environ["MONGO_DB"]]


def _seed_records(db, device_id: str, count: int = 3):
    docs = []
    for i in range(count):
        ts = f"2026-05-{i + 1:02d}T10:00:00"
        docs.append(
            {
                "device_id": device_id,
                "timestamp": ts,
                "behavior": "resting",
                "heart_rate": 80.0 + i,
                "resp_rate": 20.0 + i,
                "event": "fever" if i == 2 else None,
                "event_phase": "onset" if i == 2 else None,
            }
        )
    db["received_records"].insert_many(docs)


def _seed_pet(db, user_id: str, device_id: str):
    db["user_pets"].insert_one({"user_id": user_id, "device_id": device_id})


# ────────────────── services/identity ──────────────────


class TestNormalizeIdentity:
    def test_strips_and_lowercases(self):
        from flask_server.services.identity import normalize_identity
        assert normalize_identity("  Alice  ") == "alice"
        assert normalize_identity("BOB") == "bob"

    def test_empty_raises(self):
        from flask_server.services.identity import normalize_identity
        with pytest.raises(ValueError):
            normalize_identity("")

    def test_whitespace_only_raises(self):
        from flask_server.services.identity import normalize_identity
        with pytest.raises(ValueError):
            normalize_identity("   ")


class TestBuildUserHash:
    def test_returns_24_char_hex(self):
        from flask_server.services.identity import build_user_hash
        h = build_user_hash("user-123", secret="test_secret")
        assert len(h) == 24
        assert all(c in "0123456789abcdef" for c in h)

    def test_stable_same_input(self):
        from flask_server.services.identity import build_user_hash
        h1 = build_user_hash("user-abc", secret="s")
        h2 = build_user_hash("user-abc", secret="s")
        assert h1 == h2

    def test_different_user_different_hash(self):
        from flask_server.services.identity import build_user_hash
        h1 = build_user_hash("user-001", secret="s")
        h2 = build_user_hash("user-002", secret="s")
        assert h1 != h2

    def test_empty_user_id_raises(self):
        from flask_server.services.identity import build_user_hash
        with pytest.raises(ValueError):
            build_user_hash("", secret="s")

    def test_empty_secret_raises(self):
        from flask_server.services.identity import build_user_hash
        with pytest.raises(RuntimeError):
            build_user_hash("user-001", secret="")


class TestGetOrCreateUserHash:
    def test_creates_and_stores(self, mock_mongo):
        from flask_server.services.identity import get_or_create_user_hash
        db = _get_db()
        db["users"].insert_one({"user_id": "u001"})
        h = get_or_create_user_hash(db, "u001")
        assert len(h) == 24
        # 已写入库
        doc = db["users"].find_one({"user_id": "u001"})
        assert doc["user_hash"] == h

    def test_idempotent(self, mock_mongo):
        from flask_server.services.identity import get_or_create_user_hash
        db = _get_db()
        db["users"].insert_one({"user_id": "u002"})
        h1 = get_or_create_user_hash(db, "u002")
        h2 = get_or_create_user_hash(db, "u002")
        assert h1 == h2

    def test_reads_existing_hash(self, mock_mongo):
        from flask_server.services.identity import get_or_create_user_hash
        db = _get_db()
        db["users"].insert_one({"user_id": "u003", "user_hash": "aabbccdd11223344aabb1122"})
        h = get_or_create_user_hash(db, "u003")
        assert h == "aabbccdd11223344aabb1122"

    def test_empty_user_id_raises(self, mock_mongo):
        from flask_server.services.identity import get_or_create_user_hash
        with pytest.raises(ValueError):
            get_or_create_user_hash(_get_db(), "")


# ────────────────── services/binding ──────────────────


class TestBindUserToWechat:
    def test_new_bind(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_wechat
        db = _get_db()
        result = bind_user_to_wechat(db, "u1", "openid_abc")
        assert result["bind_status"] == "bound"
        assert result["user_id"] == "u1"
        assert db["wechat_bindings"].count_documents({}) == 1

    def test_already_bound_same_user(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_wechat
        db = _get_db()
        bind_user_to_wechat(db, "u1", "openid_abc")
        result = bind_user_to_wechat(db, "u1", "openid_abc")
        assert result["bind_status"] == "already_bound"
        assert db["wechat_bindings"].count_documents({}) == 1

    def test_conflict_different_user(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_wechat
        db = _get_db()
        bind_user_to_wechat(db, "u1", "openid_abc")
        with pytest.raises(PermissionError):
            bind_user_to_wechat(db, "u2", "openid_abc")

    def test_empty_args_raise(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_wechat
        with pytest.raises(ValueError):
            bind_user_to_wechat(_get_db(), "", "openid_x")
        with pytest.raises(ValueError):
            bind_user_to_wechat(_get_db(), "u1", "")


class TestUnbindUserFromWechat:
    def test_unbind_existing(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_wechat, unbind_user_from_wechat
        db = _get_db()
        bind_user_to_wechat(db, "u1", "openid_xyz")
        result = unbind_user_from_wechat(db, "u1")
        assert result["unbind_status"] == "unbound"
        assert result["unbound_at"] is not None
        assert db["wechat_bindings"].count_documents({}) == 0

    def test_unbind_not_bound(self, mock_mongo):
        from flask_server.services.binding import unbind_user_from_wechat
        result = unbind_user_from_wechat(_get_db(), "ghost_user")
        assert result["unbind_status"] == "not_bound"
        assert result["unbound_at"] is None

    def test_empty_user_id_raises(self, mock_mongo):
        from flask_server.services.binding import unbind_user_from_wechat
        with pytest.raises(ValueError):
            unbind_user_from_wechat(_get_db(), "")


class TestBindUserToDevice:
    def test_new_bind(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_device
        result = bind_user_to_device(_get_db(), "u1", "dev_001", "旺财")
        assert result["bind_status"] == "bound"
        assert result["device_id"] == "dev_001"

    def test_already_bound(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_device
        db = _get_db()
        bind_user_to_device(db, "u1", "dev_001")
        result = bind_user_to_device(db, "u1", "dev_001")
        assert result["bind_status"] == "already_bound"
        assert db["user_pets"].count_documents({}) == 1

    def test_empty_args_raise(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_device
        with pytest.raises(ValueError):
            bind_user_to_device(_get_db(), "", "dev_001")


class TestUnbindUserFromDevice:
    def test_unbind_existing(self, mock_mongo):
        from flask_server.services.binding import bind_user_to_device, unbind_user_from_device
        db = _get_db()
        bind_user_to_device(db, "u1", "dev_001")
        result = unbind_user_from_device(db, "u1", "dev_001")
        assert result["unbind_status"] == "unbound"
        assert db["user_pets"].count_documents({}) == 0

    def test_unbind_not_found(self, mock_mongo):
        from flask_server.services.binding import unbind_user_from_device
        result = unbind_user_from_device(_get_db(), "u1", "ghost_dev")
        assert result["unbind_status"] == "not_bound"


class TestAssertUserOwnsPet:
    def test_passes_when_owns(self, mock_mongo):
        from flask_server.services.binding import assert_user_owns_pet
        db = _get_db()
        _seed_pet(db, "u1", "dev_001")
        assert_user_owns_pet(db, "u1", "dev_001")  # should not raise

    def test_raises_when_no_access(self, mock_mongo):
        from flask_server.services.binding import assert_user_owns_pet
        with pytest.raises(PermissionError):
            assert_user_owns_pet(_get_db(), "u_nobody", "dev_001")


# ────────────────── services/telemetry ──────────────────


class TestGetPetSummary:
    def test_ok(self, mock_mongo):
        from flask_server.services.telemetry import get_pet_summary
        db = _get_db()
        _seed_pet(db, "u1", "dev_s1")
        _seed_records(db, "dev_s1", 3)
        result = get_pet_summary(db, "u1", "dev_s1")
        assert result["pet_id"] == "dev_s1"
        assert result["latest_respiration_bpm"] is not None
        assert result["latest_heart_rate_bpm"] is not None

    def test_no_access_raises(self, mock_mongo):
        from flask_server.services.telemetry import get_pet_summary
        with pytest.raises(PermissionError):
            get_pet_summary(_get_db(), "u_nobody", "dev_s1")

    def test_no_data_raises(self, mock_mongo):
        from flask_server.services.telemetry import get_pet_summary
        db = _get_db()
        _seed_pet(db, "u1", "dev_empty")
        with pytest.raises(LookupError):
            get_pet_summary(db, "u1", "dev_empty")


class TestGetLatestRespiration:
    def test_ok(self, mock_mongo):
        from flask_server.services.telemetry import get_latest_respiration
        db = _get_db()
        _seed_pet(db, "u1", "dev_r1")
        _seed_records(db, "dev_r1", 2)
        result = get_latest_respiration(db, "u1", "dev_r1")
        assert result["unit"] == "bpm"
        assert isinstance(result["value_bpm"], float)

    def test_no_data_raises(self, mock_mongo):
        from flask_server.services.telemetry import get_latest_respiration
        db = _get_db()
        _seed_pet(db, "u1", "dev_r_empty")
        with pytest.raises(LookupError):
            get_latest_respiration(db, "u1", "dev_r_empty")


class TestGetRespirationSeries:
    def test_series_default(self, mock_mongo):
        from flask_server.services.telemetry import get_respiration_series
        db = _get_db()
        _seed_pet(db, "u1", "dev_rs1")
        _seed_records(db, "dev_rs1", 5)
        result = get_respiration_series(db, "u1", "dev_rs1")
        assert result["unit"] == "bpm"
        assert result["count"] == 5
        assert len(result["points"]) == 5

    def test_series_with_limit(self, mock_mongo):
        from flask_server.services.telemetry import get_respiration_series
        db = _get_db()
        _seed_pet(db, "u1", "dev_rs2")
        _seed_records(db, "dev_rs2", 5)
        result = get_respiration_series(db, "u1", "dev_rs2", limit=2)
        assert result["count"] == 2

    def test_series_invalid_limit_raises(self, mock_mongo):
        from flask_server.services.telemetry import get_respiration_series
        db = _get_db()
        _seed_pet(db, "u1", "dev_rs3")
        with pytest.raises(ValueError):
            get_respiration_series(db, "u1", "dev_rs3", limit="abc")


class TestGetLatestHeartRate:
    def test_ok(self, mock_mongo):
        from flask_server.services.telemetry import get_latest_heart_rate
        db = _get_db()
        _seed_pet(db, "u1", "dev_h1")
        _seed_records(db, "dev_h1", 2)
        result = get_latest_heart_rate(db, "u1", "dev_h1")
        assert result["unit"] == "bpm"
        assert isinstance(result["value_bpm"], float)

    def test_no_data_raises(self, mock_mongo):
        from flask_server.services.telemetry import get_latest_heart_rate
        db = _get_db()
        _seed_pet(db, "u1", "dev_h_empty")
        with pytest.raises(LookupError):
            get_latest_heart_rate(db, "u1", "dev_h_empty")


class TestGetHeartRateSeries:
    def test_series_default(self, mock_mongo):
        from flask_server.services.telemetry import get_heart_rate_series
        db = _get_db()
        _seed_pet(db, "u1", "dev_hs1")
        _seed_records(db, "dev_hs1", 4)
        result = get_heart_rate_series(db, "u1", "dev_hs1")
        assert result["count"] == 4
        for pt in result["points"]:
            assert "ts" in pt and "value_bpm" in pt

    def test_series_time_range(self, mock_mongo):
        from flask_server.services.telemetry import get_heart_rate_series
        db = _get_db()
        _seed_pet(db, "u1", "dev_hs2")
        _seed_records(db, "dev_hs2", 5)
        # 只取 5月1日～5月3日（含3条）
        result = get_heart_rate_series(
            db, "u1", "dev_hs2",
            start="2026-05-01T00:00:00",
            end="2026-05-03T23:59:59",
        )
        assert result["count"] == 3


class TestListPetEvents:
    def test_no_events(self, mock_mongo):
        from flask_server.services.telemetry import list_pet_events
        db = _get_db()
        _seed_pet(db, "u1", "dev_e1")
        db["received_records"].insert_one(
            {"device_id": "dev_e1", "timestamp": "2026-05-01T10:00:00",
             "behavior": "sleeping", "event": None, "event_phase": None}
        )
        result = list_pet_events(db, "u1", "dev_e1")
        assert result["items"] == []
        assert result["next_cursor"] is None

    def test_with_events(self, mock_mongo):
        from flask_server.services.telemetry import list_pet_events
        db = _get_db()
        _seed_pet(db, "u1", "dev_e2")
        _seed_records(db, "dev_e2", 3)  # 第3条有 fever
        result = list_pet_events(db, "u1", "dev_e2")
        assert len(result["items"]) == 1
        assert result["items"][0]["type"] == "fever"

    def test_pagination(self, mock_mongo):
        from flask_server.services.telemetry import list_pet_events
        db = _get_db()
        _seed_pet(db, "u1", "dev_e3")
        for i in range(5):
            db["received_records"].insert_one(
                {"device_id": "dev_e3", "timestamp": f"2026-05-{i + 1:02d}T10:00:00",
                 "behavior": "resting", "event": "bark", "event_phase": "onset"}
            )
        result = list_pet_events(db, "u1", "dev_e3", limit=3)
        assert len(result["items"]) == 3
        assert result["next_cursor"] is not None

    def test_invalid_limit_raises(self, mock_mongo):
        from flask_server.services.telemetry import list_pet_events
        db = _get_db()
        _seed_pet(db, "u1", "dev_e4")
        with pytest.raises(ValueError):
            list_pet_events(db, "u1", "dev_e4", limit="xyz")


# ────────────────── POST /wechat/unbind (新接口) ──────────────────


@pytest.fixture()
def app_client():
    from flask import Flask
    from flask_server.blueprints import wechat_bp, users_bp, pets_bp
    flask_app = Flask(__name__)
    flask_app.register_blueprint(wechat_bp)
    flask_app.register_blueprint(users_bp)
    flask_app.register_blueprint(pets_bp)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _parse(resp) -> dict:
    return json.loads(resp.data.decode("utf-8"))


def _make_token(user_id: str) -> str:
    from flask_server.auth import create_access_token
    return create_access_token(user_id)


class TestWechatUnbind:
    def test_unbind_no_auth(self, app_client):
        resp = app_client.post("/api/v1/wechat/unbind")
        assert resp.status_code == 401

    def test_unbind_not_bound(self, app_client, mock_mongo):
        token = _make_token("user_unbind_001")
        resp = app_client.post(
            "/api/v1/wechat/unbind",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["unbind_status"] == "not_bound"

    def test_unbind_success(self, app_client, mock_mongo):
        db = _get_db()
        user_id = "user_unbind_002"
        # 先插入一条绑定记录
        db["wechat_bindings"].insert_one(
            {"user_id": user_id, "openid": "openid_test", "bound_at": "2026-01-01T00:00:00"}
        )
        token = _make_token(user_id)
        resp = app_client.post(
            "/api/v1/wechat/unbind",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["unbind_status"] == "unbound"
        assert data["data"]["unbound_at"] is not None
        # 绑定记录已删除
        assert db["wechat_bindings"].count_documents({}) == 0
