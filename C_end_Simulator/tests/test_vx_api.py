"""
test_vx_api.py —— vx API 接口单元测试

使用 Flask test client + mongomock 模拟 MongoDB，无需真实数据库。

覆盖范围：
  - POST /api/v1/wechat/auth   微信身份校验（mock 模式）
  - POST /api/v1/wechat/bind   绑定/重复绑定/冲突
  - GET  /api/v1/me            用户信息（需 token）
  - GET  /api/v1/pets/.../summary        宠物快照
  - GET  /api/v1/pets/.../respiration/latest  最新呼吸
  - GET  /api/v1/pets/.../respiration/series  呼吸序列
  - GET  /api/v1/pets/.../heart-rate/latest   最新心率
  - GET  /api/v1/pets/.../heart-rate/series   心率序列
  - GET  /api/v1/pets/.../events              事件列表
  - 鉴权失败场景（缺少 token / token 无效）
"""

from __future__ import annotations

import json
import os

import mongomock
import pytest

# ── 配置测试环境变量（必须在 flask_server 导入之前设置）──
os.environ.setdefault("STORAGE_BACKEND", "file")
os.environ.setdefault("DATA_DIR", "/tmp/petnode_test")
os.environ.setdefault("JWT_SECRET", "test_secret_key_for_tests_only")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "petnode_test")

import flask_server.db as _db_module  # noqa: E402  (after env setup)

# ── 用 mongomock 替换真实 MongoDB 连接 ──
_mock_client = mongomock.MongoClient()


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch):
    """每个测试前重置并注入 mongomock 数据库。"""
    # 清空并重新挂载
    _db_module._client = _mock_client
    db = _mock_client[os.environ["MONGO_DB"]]
    # 清空所有相关集合
    for col in ["wechat_bindings", "users", "user_pets", "received_records"]:
        db[col].drop()
    yield db
    # 测试后不需要特殊清理


@pytest.fixture()
def app():
    """创建 Flask test app，注册所有 vx Blueprint。"""
    from flask import Flask
    from flask_server.blueprints import (
        wechat_bp, users_bp, pets_bp, devices_bp, family_bp,
    )

    flask_app = Flask(__name__)
    flask_app.register_blueprint(wechat_bp)
    flask_app.register_blueprint(users_bp)
    flask_app.register_blueprint(pets_bp)
    flask_app.register_blueprint(devices_bp)
    flask_app.register_blueprint(family_bp)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


# ────────────────── 工具函数 ──────────────────


def _parse(resp) -> dict:
    return json.loads(resp.data.decode("utf-8"))


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_access_token(user_id: str) -> str:
    from flask_server.auth import create_access_token
    return create_access_token(user_id)


def _seed_pet(db, user_id: str, device_id: str, pet_name: str = "旺财") -> None:
    """向 user_pets 注册一个设备绑定关系。"""
    db["user_pets"].insert_one(
        {"user_id": user_id, "device_id": device_id, "pet_name": pet_name}
    )


def _seed_records(db, device_id: str, count: int = 3):
    """向 received_records 插入若干测试记录。"""
    docs = []
    for i in range(count):
        ts = f"2026-05-0{i + 1}T10:00:00"
        docs.append(
            {
                "device_id": device_id,
                "timestamp": ts,
                "behavior": "resting",
                "heart_rate": 80.0 + i,
                "resp_rate": 20.0 + i,
                "temperature": 38.5,
                "steps": i * 10,
                "battery": 90,
                "gps_lat": 29.57,
                "gps_lng": 106.45,
                "event": "fever" if i == 2 else None,
                "event_phase": "onset" if i == 2 else None,
            }
        )
    db["received_records"].insert_many(docs)


# ────────────────── wechat/auth 测试 ──────────────────


class TestWechatAuth:
    def test_auth_missing_code(self, client):
        resp = client.post("/api/v1/wechat/auth", json={})
        data = _parse(resp)
        assert resp.status_code == 422
        assert data["code"] == 42201

    def test_auth_empty_code(self, client):
        resp = client.post("/api/v1/wechat/auth", json={"code": "  "})
        data = _parse(resp)
        assert resp.status_code == 422
        assert data["code"] == 42201

    def test_auth_not_bound(self, client):
        """未绑定用户 → is_bound=false，返回 wx_identity_token"""
        resp = client.post("/api/v1/wechat/auth", json={"code": "testcode123"})
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["is_bound"] is False
        assert "wx_identity_token" in data["data"]
        assert "access_token" not in data["data"]

    def test_auth_already_bound(self, client, mock_mongo):
        """已绑定用户 → is_bound=true，同时返回 access_token"""
        # mock openid 格式是 mock_openid_{code[:8]}
        openid = "mock_openid_testcode"
        mock_mongo["wechat_bindings"].insert_one(
            {"openid": openid, "user_id": "existing_user", "bound_at": "2026-01-01T00:00:00"}
        )
        resp = client.post("/api/v1/wechat/auth", json={"code": "testcode_xxx"})
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["is_bound"] is True
        assert "access_token" in data["data"]
        assert data["data"]["user_id"] == "existing_user"


# ────────────────── wechat/bind 测试 ──────────────────


class TestWechatBind:
    def _get_wx_token(self, client) -> str:
        resp = client.post("/api/v1/wechat/auth", json={"code": "bindcode1"})
        return _parse(resp)["data"]["wx_identity_token"]

    def test_bind_missing_token(self, client):
        resp = client.post("/api/v1/wechat/bind", json={})
        data = _parse(resp)
        assert resp.status_code == 422
        assert data["code"] == 42201

    def test_bind_invalid_wx_token(self, client):
        resp = client.post(
            "/api/v1/wechat/bind", json={"wx_identity_token": "not_a_jwt"}
        )
        data = _parse(resp)
        assert resp.status_code == 401
        assert data["code"] == 40103

    def test_bind_creates_new_user(self, client, mock_mongo):
        wx_token = self._get_wx_token(client)
        resp = client.post(
            "/api/v1/wechat/bind", json={"wx_identity_token": wx_token}
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["bind_status"] == "bound"
        assert "user_id" in data["data"]
        assert "access_token" in data["data"]
        # 确认 MongoDB 中已写入绑定记录
        assert mock_mongo["wechat_bindings"].count_documents({}) == 1

    def test_bind_already_bound(self, client, mock_mongo):
        """第二次 bind 同一微信身份 → already_bound"""
        wx_token = self._get_wx_token(client)
        client.post("/api/v1/wechat/bind", json={"wx_identity_token": wx_token})
        # 再次 bind（需要重新拿 wx_token，因为有 openid 是同一个）
        wx_token2 = self._get_wx_token(client)
        resp = client.post(
            "/api/v1/wechat/bind", json={"wx_identity_token": wx_token2}
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["data"]["bind_status"] == "already_bound"

    def test_bind_conflict_different_user(self, client, mock_mongo):
        """该微信身份已绑定 user A，user B 再绑定 → 409"""
        wx_token = self._get_wx_token(client)
        # 先以匿名方式绑定（创建 user A）
        client.post("/api/v1/wechat/bind", json={"wx_identity_token": wx_token})
        # user B 尝试绑定同一微信 → 需要新的 wx_token
        wx_token2 = self._get_wx_token(client)
        user_b_access = _create_access_token("user_b_999")
        resp = client.post(
            "/api/v1/wechat/bind",
            json={"wx_identity_token": wx_token2},
            headers=_auth_header(user_b_access),
        )
        data = _parse(resp)
        assert resp.status_code == 409
        assert data["code"] == 40901


# ────────────────── /me 测试 ──────────────────


class TestMe:
    def test_me_no_auth(self, client):
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client):
        resp = client.get("/api/v1/me", headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401

    def test_me_success(self, client, mock_mongo):
        user_id = "test_user_001"
        mock_mongo["users"].insert_one(
            {"user_id": user_id, "nickname": "旺财主人", "created_at": "2026-01-01T00:00:00"}
        )
        mock_mongo["user_pets"].insert_one(
            {"user_id": user_id, "device_id": "device_aabbcc", "pet_name": "旺财"}
        )
        token = _create_access_token(user_id)
        resp = client.get("/api/v1/me", headers=_auth_header(token))
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["user_id"] == user_id
        assert data["data"]["nickname"] == "旺财主人"
        assert len(data["data"]["pets"]) == 1
        assert data["data"]["pets"][0]["device_id"] == "device_aabbcc"


# ────────────────── 宠物遥测测试 ──────────────────


class TestPetSummary:
    def test_no_auth(self, client):
        resp = client.get("/api/v1/pets/device_001/summary")
        assert resp.status_code == 401

    def test_no_pet_access(self, client, mock_mongo):
        token = _create_access_token("user_no_pets")
        resp = client.get("/api/v1/pets/device_001/summary", headers=_auth_header(token))
        data = _parse(resp)
        assert resp.status_code == 403
        assert data["code"] == 40301

    def test_no_records(self, client, mock_mongo):
        user_id = "user_001"
        device_id = "device_001"
        _seed_pet(mock_mongo, user_id, device_id)
        token = _create_access_token(user_id)
        resp = client.get(f"/api/v1/pets/{device_id}/summary", headers=_auth_header(token))
        data = _parse(resp)
        assert resp.status_code == 404
        assert data["code"] == 40401

    def test_summary_ok(self, client, mock_mongo):
        user_id = "user_001"
        device_id = "device_001"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=3)
        token = _create_access_token(user_id)
        resp = client.get(f"/api/v1/pets/{device_id}/summary", headers=_auth_header(token))
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        d = data["data"]
        assert d["pet_id"] == device_id
        assert d["latest_respiration_bpm"] is not None
        assert d["latest_heart_rate_bpm"] is not None
        # 最新记录是第3条（idx=2），有 fever 事件
        assert d["current_event"] == "fever"


class TestRespirationLatest:
    def test_respiration_latest_ok(self, client, mock_mongo):
        user_id = "user_002"
        device_id = "device_002"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=2)
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/respiration/latest",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["unit"] == "bpm"
        assert isinstance(data["data"]["value_bpm"], float)


class TestRespirationSeries:
    def test_series_no_filter(self, client, mock_mongo):
        user_id = "user_003"
        device_id = "device_003"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=5)
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/respiration/series",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["count"] == 5
        assert len(data["data"]["points"]) == 5
        assert data["data"]["unit"] == "bpm"

    def test_series_with_limit(self, client, mock_mongo):
        user_id = "user_004"
        device_id = "device_004"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=5)
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/respiration/series?limit=2",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["data"]["count"] == 2

    def test_series_invalid_limit(self, client, mock_mongo):
        user_id = "user_005"
        device_id = "device_005"
        _seed_pet(mock_mongo, user_id, device_id)
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/respiration/series?limit=abc",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 422
        assert data["code"] == 42201


class TestHeartRateLatest:
    def test_heart_rate_latest_ok(self, client, mock_mongo):
        user_id = "user_006"
        device_id = "device_006"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=2)
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/heart-rate/latest",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["unit"] == "bpm"
        assert isinstance(data["data"]["value_bpm"], float)


class TestHeartRateSeries:
    def test_heart_rate_series_ok(self, client, mock_mongo):
        user_id = "user_007"
        device_id = "device_007"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=3)
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/heart-rate/series",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["count"] == 3
        for pt in data["data"]["points"]:
            assert "ts" in pt
            assert "value_bpm" in pt


class TestEvents:
    def test_events_no_events(self, client, mock_mongo):
        """无 event 记录时返回空列表"""
        user_id = "user_008"
        device_id = "device_008"
        _seed_pet(mock_mongo, user_id, device_id)
        # 插入没有 event 的记录
        mock_mongo["received_records"].insert_one(
            {
                "device_id": device_id,
                "timestamp": "2026-05-01T10:00:00",
                "behavior": "sleeping",
                "heart_rate": 70.0,
                "resp_rate": 15.0,
                "event": None,
                "event_phase": None,
            }
        )
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/events",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        assert data["data"]["items"] == []
        assert data["data"]["next_cursor"] is None

    def test_events_with_events(self, client, mock_mongo):
        user_id = "user_009"
        device_id = "device_009"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=3)  # 第3条有 fever
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/events",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["code"] == 0
        items = data["data"]["items"]
        assert len(items) == 1
        assert items[0]["type"] == "fever"
        assert items[0]["phase"] == "onset"

    def test_events_pagination(self, client, mock_mongo):
        """cursor 分页：next_cursor 应出现当结果数超过 limit 时"""
        user_id = "user_010"
        device_id = "device_010"
        _seed_pet(mock_mongo, user_id, device_id)
        # 插入 5 条有 event 的记录
        for i in range(5):
            mock_mongo["received_records"].insert_one(
                {
                    "device_id": device_id,
                    "timestamp": f"2026-05-{i + 1:02d}T10:00:00",
                    "behavior": "resting",
                    "heart_rate": 80.0,
                    "resp_rate": 20.0,
                    "event": "bark",
                    "event_phase": "onset",
                }
            )
        token = _create_access_token(user_id)
        resp = client.get(
            f"/api/v1/pets/{device_id}/events?limit=3",
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert len(data["data"]["items"]) == 3
        assert data["data"]["next_cursor"] is not None


class TestDevicesAndPetsExtra:
    def test_bind_and_unbind_device(self, client, mock_mongo):
        mock_mongo["received_records"].insert_one(
            {"device_id": "dev_bind_001", "timestamp": "2026-05-01T10:00:00"}
        )
        token = _create_access_token("user_bind_001")
        resp = client.post(
            "/api/v1/devices/bind",
            json={"device_id": "dev_bind_001", "pet_name": "阿黄", "breed": "柯基"},
            headers=_auth_header(token),
        )
        data = _parse(resp)
        assert resp.status_code == 200
        assert data["data"]["pet_id"] == "dev_bind_001"

        resp2 = client.post(
            "/api/v1/devices/dev_bind_001/unbind",
            headers=_auth_header(token),
        )
        data2 = _parse(resp2)
        assert resp2.status_code == 200
        assert data2["data"]["unbind_status"] == "unbound"

    def test_update_me_and_pet_profile(self, client, mock_mongo):
        user_id = "user_profile_001"
        device_id = "dev_profile_001"
        _seed_pet(mock_mongo, user_id, device_id, "旧名")
        token = _create_access_token(user_id)

        me_resp = client.put(
            "/api/v1/me",
            json={"nickname": "新昵称", "avatar_url": "https://img.example/me.png"},
            headers=_auth_header(token),
        )
        assert me_resp.status_code == 200

        pet_resp = client.put(
            f"/api/v1/pets/{device_id}",
            json={"pet_name": "新宠物名", "weight": 8.5},
            headers=_auth_header(token),
        )
        pet_data = _parse(pet_resp)
        assert pet_resp.status_code == 200
        assert pet_data["data"]["pet_name"] == "新宠物名"

    def test_temperature_location_and_event_read(self, client, mock_mongo):
        user_id = "user_data_001"
        device_id = "dev_data_001"
        _seed_pet(mock_mongo, user_id, device_id)
        _seed_records(mock_mongo, device_id, count=3)
        token = _create_access_token(user_id)

        t_resp = client.get(
            f"/api/v1/pets/{device_id}/temperature/series",
            headers=_auth_header(token),
        )
        t_data = _parse(t_resp)
        assert t_resp.status_code == 200
        assert "points" in t_data["data"]

        l_resp = client.get(
            f"/api/v1/pets/{device_id}/location/latest",
            headers=_auth_header(token),
        )
        l_data = _parse(l_resp)
        assert l_resp.status_code == 200
        assert "lat" in l_data["data"] and "lng" in l_data["data"]

        e_resp = client.get(
            f"/api/v1/pets/{device_id}/events",
            headers=_auth_header(token),
        )
        e_data = _parse(e_resp)
        assert e_resp.status_code == 200
        event_id = e_data["data"]["items"][0]["event_id"]

        read_resp = client.put(
            f"/api/v1/pets/{device_id}/events/{event_id}/read",
            headers=_auth_header(token),
        )
        read_data = _parse(read_resp)
        assert read_resp.status_code == 200
        assert read_data["data"]["status"] == "marked_read"


class TestFamily:
    def test_family_invite_join_and_shared_access(self, client, mock_mongo):
        owner_id = "family_owner_001"
        member_id = "family_member_001"
        device_id = "dev_family_001"
        _seed_pet(mock_mongo, owner_id, device_id, "旺财")
        _seed_records(mock_mongo, device_id, count=2)

        owner_token = _create_access_token(owner_id)
        member_token = _create_access_token(member_id)

        create_resp = client.post("/api/v1/family", headers=_auth_header(owner_token))
        assert create_resp.status_code == 200

        invite_resp = client.post("/api/v1/family/invite", headers=_auth_header(owner_token))
        invite_data = _parse(invite_resp)
        assert invite_resp.status_code == 200
        token = invite_data["data"]["invite_token"]

        join_resp = client.post(
            "/api/v1/family/join",
            json={"invite_token": token},
            headers=_auth_header(member_token),
        )
        assert join_resp.status_code == 200

        shared_resp = client.get(
            f"/api/v1/pets/{device_id}/summary",
            headers=_auth_header(member_token),
        )
        assert shared_resp.status_code == 200

        members_resp = client.get("/api/v1/family/members", headers=_auth_header(owner_token))
        members_data = _parse(members_resp)
        assert members_resp.status_code == 200
        assert len(members_data["data"]["members"]) == 2
