import base64
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app
from app.models import PRESET_SITE_COUNT, RECRUITMENT_BATCH_MAX_ACTIVE_SITES


def _admin_headers() -> dict[str, str]:
    token = base64.b64encode(b"admin:admin").decode("ascii")
    return {"Authorization": f"Basic {token}"}


def admin_get(client: TestClient, path: str, **kwargs):
    headers = {**_admin_headers(), **kwargs.pop("headers", {})}
    return client.get(path, headers=headers, **kwargs)


def admin_post(client: TestClient, path: str, **kwargs):
    headers = {**_admin_headers(), **kwargs.pop("headers", {})}
    return client.post(path, headers=headers, **kwargs)


def admin_put(client: TestClient, path: str, **kwargs):
    headers = {**_admin_headers(), **kwargs.pop("headers", {})}
    return client.put(path, headers=headers, **kwargs)


def admin_patch(client: TestClient, path: str, **kwargs):
    headers = {**_admin_headers(), **kwargs.pop("headers", {})}
    return client.patch(path, headers=headers, **kwargs)


def ensure_std_test_sites(client: TestClient) -> None:
    """reset 后默认 0 个站点，测试用例需先登记 SITE_01 / SITE_02。"""
    for sid, name in (("SITE_01", "站点01"), ("SITE_02", "站点02")):
        r = admin_post(client, "/admin/sites", json={"site_id": sid, "site_name": name})
        assert r.status_code == 200, r.text


def setup_function():
    client = TestClient(app)
    admin_post(client, "/admin/dev/reset")
    ensure_std_test_sites(client)


def hk_full_day_window_iso() -> tuple[str, str]:
    hk = ZoneInfo("Asia/Hong_Kong")
    now_hk = datetime.now(hk)
    start_hk = now_hk.replace(hour=0, minute=0, second=0, microsecond=0)
    end_hk = now_hk.replace(hour=23, minute=59, second=59, microsecond=999000)
    start_utc = start_hk.astimezone(timezone.utc)
    end_utc = end_hk.astimezone(timezone.utc)
    return start_utc.isoformat(), end_utc.isoformat()


def open_batch(client: TestClient, site_ids: list[str]) -> None:
    r = admin_post(
        client,
        "/admin/recruitment-batches/open",
        json={"site_ids": site_ids, "created_by": "admin", "label": "test"},
    )
    assert r.status_code == 200, r.text


def set_site_password(client: TestClient, site_id: str, raw_password: str = "123456") -> None:
    ws, we = hk_full_day_window_iso()
    r = admin_post(
        client,
        "/admin/site-passwords",
        json={
            "site_id": site_id,
            "window_start": ws,
            "window_end": we,
            "raw_password": raw_password,
            "changed_by": "admin",
        },
    )
    assert r.status_code == 200, r.text


def test_phone_and_password_allows_randomization():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000001",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert randomized.status_code == 200
    assert randomized.json()["allocation_group"] in {"GENAI", "HUMAN"}
    assert randomized.json()["enrollment_no"].startswith("R")
    listing = admin_get(client, "/admin/randomization-records").json()
    ov = listing["overview"]
    assert ov["total_enrolled"] >= 1
    assert ov["intervention_count"] + ov["control_count"] + ov["other_group_count"] == ov["total_enrolled"]


def test_wrong_password_lockout():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    for _ in range(4):
        res = client.post(
            "/randomization/trigger",
            json={
                "phone_number": "+85260000002",
                "recruiter_id": "r2",
                "site_id": "SITE_01",
                "recruiter_password": "wrongpass",
            },
        )
        assert res.status_code == 403

    fifth = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000002",
            "recruiter_id": "r2",
            "site_id": "SITE_01",
            "recruiter_password": "wrongpass",
        },
    )
    assert fifth.status_code == 429


def test_cross_site_existing_phone_rejected():
    client = TestClient(app)
    open_batch(client, ["SITE_01", "SITE_02"])
    set_site_password(client, "SITE_01")
    set_site_password(client, "SITE_02")
    first = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000003",
            "recruiter_id": "r3",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert first.status_code == 200
    second = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000003",
            "recruiter_id": "r3",
            "site_id": "SITE_02",
            "recruiter_password": "123456",
        },
    )
    assert second.status_code == 403


def test_same_phone_returns_idempotent_record():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    first = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000004",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    second = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000004",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert second.json()["enrollment_no"] == first.json()["enrollment_no"]


def test_qr_config_update_is_versioned():
    client = TestClient(app)
    updated = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_value": "https://wa.me/new_genai",
            "changed_by": "admin",
            "reason": "rotation",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2


def test_qr_config_image_upload_is_supported():
    client = TestClient(app)
    file_content = b"\x89PNG\r\n\x1a\nfakepng"
    uploaded = admin_post(
        client,
        "/admin/qr-config/upload",
        data={"group": "GENAI", "changed_by": "admin", "reason": "upload image"},
        files={"file": ("qr.png", file_content, "image/png")},
    )
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["qr_value"].startswith("/uploads/qr/")


def test_qr_configs_endpoint_returns_groups():
    client = TestClient(app)
    res = admin_get(client, "/admin/qr-configs")
    assert res.status_code == 200
    groups = {item["group_type"] for item in res.json()["items"]}
    assert {"GENAI", "HUMAN"}.issubset(groups)


def test_admin_can_maintain_record_phone():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000005",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    enrollment_no = randomized.json()["enrollment_no"]
    corrected = admin_patch(
        client,
        "/admin/randomization-records/phone",
        json={
            "enrollment_no": enrollment_no,
            "new_phone_number": "+85260000999",
            "changed_by": "admin_maintainer",
            "reason": "manual correction",
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["phone_number"] == "+85260000999"


def test_admin_can_update_randomization_settings():
    client = TestClient(app)
    updated = admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "max_enrollment": 5000,
            "block_sizes": [4, 8],
            "updated_by": "super_admin",
        },
    )
    assert updated.status_code == 200
    current = admin_get(client, "/admin/randomization-settings")
    assert current.status_code == 200
    assert current.json()["max_enrollment"] == 5000
    assert current.json()["block_sizes"] == [4, 8]


def test_max_enrollment_blocks_new_randomization():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "max_enrollment": 1,
            "block_sizes": [4, 8, 12],
            "updated_by": "super_admin",
        },
    )
    first = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85261111111",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    second = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85262222222",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_admin_can_delete_randomization_record():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85263333333",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    enrollment_no = created.json()["enrollment_no"]
    deleted = admin_post(
        client,
        "/admin/randomization-records/delete",
        json={
            "enrollment_no": enrollment_no,
            "deleted_by": "admin",
            "reason": "cleanup test",
        },
    )
    assert deleted.status_code == 200
    records = admin_get(client, "/admin/randomization-records").json()["items"]
    assert all(r["enrollment_no"] != enrollment_no for r in records)


def test_list_sites_and_recruitment_overview():
    client = TestClient(app)
    listed = admin_get(client, "/admin/sites")
    assert listed.status_code == 200
    ids = {x["site_id"] for x in listed.json()["items"]}
    assert "SITE_01" in ids
    assert "SITE_02" in ids
    assert len(ids) == 2
    now_iso = datetime.now(timezone.utc).isoformat()
    overview = admin_get(client, "/admin/site-recruitment-overview", params={"at": now_iso})
    assert overview.status_code == 200
    body = overview.json()
    assert body["max_parallel_sites_recommended"] == RECRUITMENT_BATCH_MAX_ACTIVE_SITES
    assert body["preset_site_capacity"] == PRESET_SITE_COUNT
    assert "registered_site_count" in body


def test_randomization_requires_active_batch():
    client = TestClient(app)
    set_site_password(client, "SITE_01")
    res = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85264444444",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "site_not_in_active_recruitment_batch"


def test_password_window_must_be_same_hk_day():
    client = TestClient(app)
    ws = "2026-06-01T16:00:00+08:00"
    we = "2026-06-02T10:00:00+08:00"
    r = admin_post(
        client,
        "/admin/site-passwords",
        json={
            "site_id": "SITE_01",
            "window_start": ws,
            "window_end": we,
            "raw_password": "123456",
            "changed_by": "admin",
        },
    )
    assert r.status_code == 400
