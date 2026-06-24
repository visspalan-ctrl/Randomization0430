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


def admin_delete(client: TestClient, path: str, **kwargs):
    headers = {**_admin_headers(), **kwargs.pop("headers", {})}
    return client.delete(path, headers=headers, **kwargs)


def ensure_std_test_sites(client: TestClient) -> None:
    """reset 後預設 0 個站點，測試用例需先登記 SITE_01 / SITE_02。"""
    for sid, name in (("SITE_01", "站點01"), ("SITE_02", "站點02")):
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


def configure_deterministic_trial_sequence(client: TestClient, seed: int = 999) -> None:
    updated = admin_put(
        client,
        "/admin/randomization-settings",
        json={"block_sizes": [4], "updated_by": "admin"},
    )
    assert updated.status_code == 200, updated.text
    from app.db import SessionLocal
    from app.models import RandomizationSetting

    with SessionLocal() as db:
        setting = db.get(RandomizationSetting, 1)
        assert setting is not None
        setting.randomization_seed = seed
        db.commit()


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


def test_participant_active_sites_public_no_admin_session():
    """受試者設備未登入後台時須仍能載入當前批次站點（與 /h5/randomize 一致）。"""
    client = TestClient(app)
    assert client.get("/participant/active-sites").json() == {"items": []}
    open_batch(client, ["SITE_01", "SITE_02"])
    res = client.get("/participant/active-sites")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 2
    assert {x["site_id"] for x in items} == {"SITE_01", "SITE_02"}


def test_site_can_be_deleted_even_if_history_exists():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000008",
            "recruiter_id": "r8",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert randomized.status_code == 200

    deleted = admin_delete(client, "/admin/sites/SITE_01")
    assert deleted.status_code == 200
    sites = admin_get(client, "/admin/sites").json()["items"]
    assert {x["site_id"] for x in sites} == {"SITE_02"}


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
            "qr_mode": "static_url",
            "qr_value": "https://wa.me/new_genai",
            "changed_by": "admin",
            "reason": "rotation",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2


def test_dynamic_qr_redirect_and_update():
    client = TestClient(app)
    created = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/old_genai",
            "changed_by": "admin",
            "reason": "init dynamic",
        },
    )
    assert created.status_code == 200

    first = client.get("/r/GENAI", follow_redirects=False)
    assert first.status_code == 302
    assert first.headers["location"] == "https://wa.me/old_genai"

    updated = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/new_genai",
            "changed_by": "admin",
            "reason": "rotate target",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 3

    second = client.get("/r/GENAI", follow_redirects=False)
    assert second.status_code == 302
    assert second.headers["location"] == "https://wa.me/new_genai"


def test_dynamic_qr_png_endpoint():
    client = TestClient(app)
    admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/png_test",
            "changed_by": "admin",
            "reason": "png test",
        },
    )
    res = client.get("/r/GENAI/qr.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG")


def test_randomization_returns_stable_qr_for_dynamic_mode():
    client = TestClient(app)
    for group, target in (("GENAI", "https://wa.me/dyn_genai"), ("HUMAN", "https://wa.me/dyn_human")):
        admin_post(
            client,
            "/admin/qr-config",
            json={
                "group": group,
                "qr_mode": "dynamic",
                "qr_value": target,
                "changed_by": "admin",
                "reason": "dynamic for randomization",
            },
        )
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000123",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert randomized.status_code == 200
    body = randomized.json()
    group = body["allocation_group"]
    assert body["whatsapp_qr"] == f"/r/{group}"
    assert body["qr_display_mode"] == "dynamic"


def test_qr_configs_includes_qr_mode_and_stable_url():
    client = TestClient(app)
    admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/config_test",
            "changed_by": "admin",
            "reason": "config list",
        },
    )
    res = admin_get(client, "/admin/qr-configs")
    assert res.status_code == 200
    genai = next(i for i in res.json()["items"] if i["group_type"] == "GENAI")
    assert genai["qr_mode"] == "dynamic"
    assert genai["stable_qr_path"] == "/r/GENAI"
    assert genai["stable_qr_url"].endswith("/r/GENAI")


def test_admin_qr_preview_png_before_save():
    client = TestClient(app)
    res = admin_get(client, "/admin/qr-preview/GENAI.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG")


def test_qr_logo_upload_and_preview():
    client = TestClient(app)
    file_content = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\x0d\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    uploaded = admin_post(
        client,
        "/admin/qr-config/logo",
        data={"group": "GENAI", "changed_by": "admin"},
        files={"file": ("logo.png", file_content, "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["qr_logo_path"].startswith("/uploads/qr/")

    admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/logo_test",
            "changed_by": "admin",
            "reason": "dynamic with logo",
        },
    )
    preview = admin_get(client, "/admin/qr-preview/GENAI.png")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content.startswith(b"\x89PNG")
    assert len(preview.content) > 500


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

    configs = admin_get(client, "/admin/qr-configs")
    genai = next(i for i in configs.json()["items"] if i["group_type"] == "GENAI")
    assert genai["qr_mode"] == "static_image"


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
            "min_per_group": 499,
            "recruitment_end_date": "2026-11-01",
            "block_sizes": [4, 8],
            "updated_by": "super_admin",
        },
    )
    assert updated.status_code == 200
    current = admin_get(client, "/admin/randomization-settings")
    assert current.status_code == 200
    assert current.json()["min_per_group"] == 499
    assert current.json()["recruitment_end_date"] == "2026-11-01"
    assert current.json()["block_sizes"] == [4, 8]
    assert current.json()["recruitment_start_date"] == "2026-06-20"


def test_settings_sync_weekly_plan_weeks_from_recruitment_dates():
    client = TestClient(app)
    updated = admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "recruitment_start_date": "2026-06-20",
            "recruitment_end_date": "2026-10-31",
            "block_sizes": [4, 8, 12],
            "updated_by": "admin",
        },
    )
    assert updated.status_code == 200
    settings = admin_get(client, "/admin/randomization-settings").json()
    assert settings["weekly_plan_weeks"] == 20
    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["weekly_plan"]["weeks"] == 20


def test_overview_weekly_tracking_by_recruitment_week():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import RandomizationRecord

    client = TestClient(app)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "recruitment_start_date": "2026-06-20",
            "block_sizes": [4, 8, 12],
            "updated_by": "admin",
        },
    )
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    for phone in ("+85261111001", "+85261111002"):
        created = client.post(
            "/randomization/trigger",
            json={
                "phone_number": phone,
                "recruiter_id": "r1",
                "site_id": "SITE_01",
                "recruiter_password": "123456",
            },
        )
        assert created.status_code == 200

    hk = ZoneInfo("Asia/Hong_Kong")
    day_week2 = datetime(2026, 6, 21, 10, 0, tzinfo=hk).astimezone(timezone.utc)
    day_week3 = datetime(2026, 6, 28, 10, 0, tzinfo=hk).astimezone(timezone.utc)
    with SessionLocal() as db:
        records = db.scalars(select(RandomizationRecord).order_by(RandomizationRecord.id.asc())).all()
        assert len(records) >= 2
        records[0].randomized_at = day_week2
        records[1].randomized_at = day_week3
        db.commit()

    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["recruitment_start_date"] == "2026-06-20"
    assert overview["weekly_plan"] == {"weeks": 20, "per_week": 60, "total_target": 1200}
    weeks = overview["weekly_tracking"]
    w1 = next(item for item in weeks if item["week_no"] == 1)
    w2 = next(item for item in weeks if item["week_no"] == 2)
    w3 = next(item for item in weeks if item["week_no"] == 3)
    assert w1["week_label"] == "第1周"
    assert w1["range_start"] == "2026-06-20"
    assert w1["range_end"] == "2026-06-20"
    assert w1["valid_total"] == 0
    assert w1["valid_cumulative"] == 0
    assert w2["range_start"] == "2026-06-21"
    assert w2["range_end"] == "2026-06-27"
    assert w2["valid_total"] == 1
    assert w2["valid_cumulative"] == 1
    assert w3["valid_total"] == 1
    assert w3["valid_cumulative"] == 2
    assert len(weeks) >= 20
    assert weeks[19]["week_no"] == 20


def test_overview_weekly_plan_is_configurable():
    client = TestClient(app)
    updated = admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "weekly_plan_weeks": 10,
            "weekly_plan_per_week": 50,
            "block_sizes": [4, 8, 12],
            "updated_by": "admin",
        },
    )
    assert updated.status_code == 200
    settings = admin_get(client, "/admin/randomization-settings").json()
    assert settings["weekly_plan_weeks"] == 10
    assert settings["weekly_plan_per_week"] == 50
    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["weekly_plan"] == {"weeks": 10, "per_week": 50, "total_target": 500}
    assert len(overview["weekly_tracking"]) == 10


def test_min_per_group_blocks_new_randomization():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    configure_deterministic_trial_sequence(client, seed=999)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "min_per_group": 1,
            "block_sizes": [4],
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
    third = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85263333333",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 409
    assert third.json()["detail"] == "recruitment_target_reached"


def test_recruitment_end_date_blocks_new_randomization():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "min_per_group": None,
            "recruitment_start_date": "2026-01-01",
            "recruitment_end_date": "2026-06-18",
            "block_sizes": [4, 8, 12],
            "updated_by": "super_admin",
        },
    )
    blocked = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85269999999",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "recruitment_target_reached"
    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["recruitment_open"] is False


def test_voided_record_does_not_block_min_per_group_and_allows_rerandomize():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    configure_deterministic_trial_sequence(client, seed=999)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "min_per_group": 1,
            "block_sizes": [4],
            "updated_by": "super_admin",
        },
    )
    phone = "+85264444444"
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": phone,
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200
    enrollment_no = created.json()["enrollment_no"]
    voided = admin_post(
        client,
        "/admin/randomization-records/delete",
        json={"enrollment_no": enrollment_no, "voided_by": "admin", "reason": "void cap test"},
    )
    assert voided.status_code == 200
    rerandom = client.post(
        "/randomization/trigger",
        json={
            "phone_number": phone,
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert rerandom.status_code == 200
    assert rerandom.json()["idempotent"] is False
    assert rerandom.json()["enrollment_no"] != enrollment_no


def test_records_overview_uses_valid_group_counts():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "min_per_group": 499,
            "block_sizes": [4, 8, 12],
            "updated_by": "super_admin",
        },
    )
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85265555555",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200
    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["valid_enrolled"] == 1
    assert overview["voided_count"] == 0
    assert overview["voided_intervention_count"] == 0
    assert overview["voided_control_count"] == 0
    assert overview["valid_intervention_count"] + overview["valid_control_count"] == 1
    assert overview["recruitment_open"] is True
    assert overview["min_per_group"] == 499


def test_admin_can_void_randomization_record():
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
    voided = admin_post(
        client,
        "/admin/randomization-records/delete",
        json={
            "enrollment_no": enrollment_no,
            "voided_by": "admin",
            "reason": "void test",
        },
    )
    assert voided.status_code == 200
    records = admin_get(client, "/admin/randomization-records").json()["items"]
    target = next((r for r in records if r["enrollment_no"] == enrollment_no), None)
    assert target is not None
    assert target["activation_status"] == "voided"
    assert target["phone_number"] == "+85263333333"
    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["valid_enrolled"] == 0
    assert overview["voided_count"] == 1
    assert overview["voided_intervention_count"] + overview["voided_control_count"] == 1


def test_admin_can_restore_voided_record():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85263333334",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    enrollment_no = created.json()["enrollment_no"]
    first = admin_post(
        client,
        "/admin/randomization-records/delete",
        json={
            "enrollment_no": enrollment_no,
            "voided_by": "admin",
            "reason": "void for test",
        },
    )
    assert first.status_code == 200
    second = admin_post(
        client,
        "/admin/randomization-records/delete",
        json={
            "enrollment_no": enrollment_no,
            "voided_by": "admin",
            "reason": "restore for test",
        },
    )
    assert second.status_code == 200
    records = admin_get(client, "/admin/randomization-records").json()["items"]
    target = next((r for r in records if r["enrollment_no"] == enrollment_no), None)
    assert target is not None
    assert target["activation_status"] != "voided"


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


def test_enrollment_no_uses_hk_calendar_date():
    from unittest.mock import patch

    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    with patch("app.main.hk_date_stamp", return_value="20260619"):
        created = client.post(
            "/randomization/trigger",
            json={
                "phone_number": "+85260000777",
                "recruiter_id": "r1",
                "site_id": "SITE_01",
                "recruiter_password": "123456",
            },
        )
    assert created.status_code == 200
    assert created.json()["enrollment_no"].startswith("R20260619-")


def test_csv_export_uses_hkt_for_randomized_at():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000888",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200
    exported = admin_get(client, "/admin/randomization-records.csv")
    assert exported.status_code == 200
    assert "randomized_at (HKT)" in exported.text
    assert " HKT" in exported.text


def test_site_overview_includes_hk_password_window_defaults():
    client = TestClient(app)
    overview = admin_get(client, "/admin/site-recruitment-overview")
    assert overview.status_code == 200
    data = overview.json()
    assert "default_password_window_start" in data
    assert "default_password_window_end" in data
    hk = ZoneInfo("Asia/Hong_Kong")
    start_hk = datetime.fromisoformat(data["default_password_window_start"]).astimezone(hk)
    end_hk = datetime.fromisoformat(data["default_password_window_end"]).astimezone(hk)
    assert start_hk.date() == end_hk.date()
    assert start_hk.hour == 0 and start_hk.minute == 0
    assert end_hk.hour == 23 and end_hk.minute == 59


def _trigger_randomization(client: TestClient, phone: str) -> dict:
    r = client.post(
        "/randomization/trigger",
        json={
            "phone_number": phone,
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_new_record_defaults_to_trial():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    body = _trigger_randomization(client, "+85261111001")
    records = admin_get(client, "/admin/randomization-records").json()["items"]
    target = next(r for r in records if r["enrollment_no"] == body["enrollment_no"])
    assert target["trial_status"] == "trial"
    assert target.get("subject_code") in (None, "")


def test_nontrial_does_not_count_toward_min_per_group():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    configure_deterministic_trial_sequence(client, seed=999)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={"min_per_group": 1, "block_sizes": [4], "updated_by": "super_admin"},
    )
    first = _trigger_randomization(client, "+85261111002")
    marked = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": first["enrollment_no"],
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "cap test",
        },
    )
    assert marked.status_code == 200
    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["trial_enrolled"] == 0
    assert overview["nontrial_enrolled"] == 1
    assert overview["recruitment_open"] is True
    second = _trigger_randomization(client, "+85261111003")
    assert second["enrollment_no"] != first["enrollment_no"]
    assert second["idempotent"] is False


def test_mark_trial_as_nontrial_frees_min_per_group_slot():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    configure_deterministic_trial_sequence(client, seed=999)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={"min_per_group": 1, "block_sizes": [4], "updated_by": "super_admin"},
    )
    first = _trigger_randomization(client, "+85261111004")
    _trigger_randomization(client, "+85261111005")
    blocked = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85261111006",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert blocked.status_code == 409
    marked = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": first["enrollment_no"],
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "free slot",
        },
    )
    assert marked.status_code == 200
    third = _trigger_randomization(client, "+85261111006")
    assert third["idempotent"] is False


def test_subject_code_must_be_unique():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    first = _trigger_randomization(client, "+85261111006")
    second = _trigger_randomization(client, "+85261111007")
    ok = admin_patch(
        client,
        "/admin/randomization-records/subject-code",
        json={
            "enrollment_no": first["enrollment_no"],
            "subject_code": "SUBJ-001",
            "changed_by": "admin",
            "reason": "assign code",
        },
    )
    assert ok.status_code == 200
    dup = admin_patch(
        client,
        "/admin/randomization-records/subject-code",
        json={
            "enrollment_no": second["enrollment_no"],
            "subject_code": "SUBJ-001",
            "changed_by": "admin",
            "reason": "duplicate code",
        },
    )
    assert dup.status_code == 409
    assert dup.json()["detail"] == "subject_code_already_exists"


def test_nontrial_phone_still_blocks_rerandomize():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    phone = "+85261111008"
    first = _trigger_randomization(client, phone)
    marked = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": first["enrollment_no"],
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "nontrial phone test",
        },
    )
    assert marked.status_code == 200
    again = _trigger_randomization(client, phone)
    assert again["idempotent"] is True
    assert again["enrollment_no"] == first["enrollment_no"]


def test_mark_nontrial_to_trial_respects_min_per_group():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    configure_deterministic_trial_sequence(client, seed=999)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={"min_per_group": 1, "block_sizes": [4], "updated_by": "super_admin"},
    )
    first = _trigger_randomization(client, "+85261111009")
    second = _trigger_randomization(client, "+85261111010")
    mark_second_nontrial = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": second["enrollment_no"],
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "free slot",
        },
    )
    assert mark_second_nontrial.status_code == 200
    third = _trigger_randomization(client, "+85261111011")
    blocked = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": second["enrollment_no"],
            "trial_status": "trial",
            "changed_by": "admin",
            "reason": "min per group reached",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "recruitment_target_reached"
    admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": third["enrollment_no"],
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "free slot",
        },
    )
    allowed = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": second["enrollment_no"],
            "trial_status": "trial",
            "changed_by": "admin",
            "reason": "now has slot",
        },
    )
    assert allowed.status_code == 200


def test_nontrial_does_not_advance_trial_sequence_slot():
    from app.state import trial_group_at_index

    client = TestClient(app)
    configure_deterministic_trial_sequence(client, seed=999)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")

    expected = [trial_group_at_index(i, (4,), 999) for i in range(4)]

    first = _trigger_randomization(client, "+85270000001")
    second = _trigger_randomization(client, "+85270000002")
    assert first["allocation_group"] == expected[0]
    assert second["allocation_group"] == expected[1]

    marked = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": second["enrollment_no"],
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "ineligible",
        },
    )
    assert marked.status_code == 200

    third = _trigger_randomization(client, "+85270000003")
    assert third["allocation_group"] == expected[1]

    fourth = _trigger_randomization(client, "+85270000004")
    assert fourth["allocation_group"] == expected[2]


def test_voided_record_does_not_advance_trial_sequence_slot():
    from app.state import trial_group_at_index

    client = TestClient(app)
    configure_deterministic_trial_sequence(client, seed=999)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")

    expected = [trial_group_at_index(i, (4,), 999) for i in range(4)]

    first = _trigger_randomization(client, "+85270000011")
    assert first["allocation_group"] == expected[0]

    voided = admin_post(
        client,
        "/admin/randomization-records/delete",
        json={"enrollment_no": first["enrollment_no"], "voided_by": "admin", "reason": "mistake"},
    )
    assert voided.status_code == 200

    second = _trigger_randomization(client, "+85270000012")
    assert second["allocation_group"] == expected[0]

    third = _trigger_randomization(client, "+85270000013")
    assert third["allocation_group"] == expected[1]
