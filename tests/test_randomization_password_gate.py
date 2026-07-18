import base64
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app
from app.models import RECRUITMENT_BATCH_MAX_ACTIVE_SITES


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
    assert ov["total_randomized"] >= 1
    assert (
        ov["trial"]["total"] + ov["nontrial"]["total"] + ov["voided"]["total"]
        == ov["total_randomized"]
    )


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


def test_can_switch_from_static_image_back_to_dynamic():
    client = TestClient(app)
    file_content = b"\x89PNG\r\n\x1a\nfakepng"
    uploaded = admin_post(
        client,
        "/admin/qr-config/upload",
        data={"group": "GENAI", "changed_by": "admin", "reason": "upload image"},
        files={"file": ("qr.png", file_content, "image/png")},
    )
    assert uploaded.status_code == 200
    image_path = uploaded.json()["qr_value"]

    # 仍用旧图片路径作为 dynamic 目标时应被拒绝
    rejected = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": image_path,
            "changed_by": "admin",
            "reason": "bad switch",
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "dynamic_qr_target_must_be_url"

    switched = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/back_to_dynamic",
            "changed_by": "admin",
            "reason": "switch back to dynamic",
        },
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["qr_mode"] == "dynamic"
    assert switched.json()["stable_qr_path"] == "/r/GENAI"

    configs = admin_get(client, "/admin/qr-configs")
    genai = next(i for i in configs.json()["items"] if i["group_type"] == "GENAI")
    assert genai["qr_mode"] == "dynamic"
    assert genai["qr_value"] == "https://wa.me/back_to_dynamic"

    redirect = client.get("/r/GENAI", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://wa.me/back_to_dynamic"


def test_control_group_dual_qr_and_contact_channel_selection():
    client = TestClient(app)
    # HUMAN: WhatsApp 动态码 + 微信图片码
    admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "HUMAN",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/human_dual",
            "changed_by": "admin",
            "reason": "dual qr whatsapp",
        },
    )
    file_content = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\x0d\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    uploaded = admin_post(
        client,
        "/admin/qr-config/wechat",
        data={"group": "HUMAN", "changed_by": "admin"},
        files={"file": ("wechat.png", file_content, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    wechat_path = uploaded.json()["wechat_qr_path"]
    assert wechat_path.startswith("/uploads/qr/")

    assert uploaded.json()["qr_mode"] == "dynamic"
    assert uploaded.json()["qr_value"] == "https://wa.me/human_dual"

    configs = admin_get(client, "/admin/qr-configs").json()
    human = next(i for i in configs["items"] if i["group_type"] == "HUMAN")
    assert human["qr_mode"] == "dynamic"
    assert human["qr_value"] == "https://wa.me/human_dual"
    assert human["wechat_qr_path"] == wechat_path

    # 誤用主上傳（未確認）不得覆蓋動態跳轉連結
    blocked = admin_post(
        client,
        "/admin/qr-config/upload",
        data={"group": "HUMAN", "changed_by": "admin", "reason": "mistaken main upload"},
        files={"file": ("main.png", file_content, "image/png")},
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "dynamic_mode_use_wechat_upload"
    configs2 = admin_get(client, "/admin/qr-configs").json()
    human2 = next(i for i in configs2["items"] if i["group_type"] == "HUMAN")
    assert human2["qr_mode"] == "dynamic"
    assert human2["qr_value"] == "https://wa.me/human_dual"
    assert human2["wechat_qr_path"] == wechat_path

    # 强制下一条入 HUMAN：先给 GENAI 入一条，或用小 block；更稳妥是直接改记录分组后测渠道
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    # 配置 GENAI 动态码，确保随机可完成
    admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/genai_dual",
            "changed_by": "admin",
        },
    )

    # 多入几条直到出现 HUMAN
    human_body = None
    for i in range(12):
        r = client.post(
            "/randomization/trigger",
            json={
                "phone_number": f"+85261114{i:03d}",
                "recruiter_id": "r1",
                "site_id": "SITE_01",
                "recruiter_password": "123456",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if body["allocation_group"] == "HUMAN":
            human_body = body
            break
    assert human_body is not None
    assert human_body["show_dual_qr"] is True
    assert human_body["require_contact_channel"] is True
    assert human_body["whatsapp_qr"] == "/r/HUMAN"
    assert human_body["wechat_qr"] == wechat_path
    assert human_body["contact_channel"] is None

    enrollment_no = human_body["enrollment_no"]
    selected = client.post(
        "/randomization/contact-channel",
        json={
            "enrollment_no": enrollment_no,
            "contact_channel": "wechat",
            "changed_by": "r1",
        },
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["contact_channel"] == "wechat"

    listing = admin_get(client, "/admin/randomization-records").json()
    item = next(i for i in listing["items"] if i["enrollment_no"] == enrollment_no)
    assert item["contact_channel"] == "wechat"

    patched = admin_patch(
        client,
        "/admin/randomization-records/contact-channel",
        json={
            "enrollment_no": enrollment_no,
            "contact_channel": "whatsapp",
            "changed_by": "admin",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["contact_channel"] == "whatsapp"

    h5 = client.get("/h5/enroll")
    assert h5.status_code == 200
    assert "dual-qr" in h5.text
    assert "contactChannel" in h5.text


def test_admin_qr_panel_isolates_wechat_from_main_upload():
    """管理端文案/腳本須把微信上傳與主碼靜態圖替換分開，避免跳轉目標被蓋成圖片路徑。"""
    client = TestClient(app)
    page = admin_get(client, "/admin/web", params={"page": "qr"})
    assert page.status_code == 200
    html = page.text
    assert "2026-07-18-dynamic-pool-v1" in html
    assert "二維碼（WhatsApp/微信）" in html
    assert "上傳微信二維碼" in html
    assert "儲存主碼設定" in html
    assert "微信二維碼上傳" in html
    assert 'id="qrWechatSection"' in html
    assert 'id="qrDynamicTargets"' in html
    assert "qrTarget5" in html
    assert "confirm_replace_dynamic" in html
    assert "REPLACE" in html
    assert "已選擇微信圖片" in html
    # 微信上傳成功後應核對主碼未變
    assert "上傳微信後主碼跳轉目標被改動了" in html

    settings = admin_get(client, "/admin/web", params={"page": "settings"})
    assert settings.status_code == 200
    assert "前往二維碼頁（含微信上傳）" in settings.text
    assert "/admin/web?page=qr" in settings.text


def test_dynamic_qr_target_pool_random_redirect():
    client = TestClient(app)
    targets = [
        "https://wa.me/pool_a",
        "https://wa.me/pool_b",
        "https://wa.me/pool_c",
        "https://wa.me/pool_d",
        "https://wa.me/pool_e",
    ]
    saved = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_value": targets[0],
            "qr_targets": targets,
            "changed_by": "admin",
            "reason": "pool of 5",
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["qr_mode"] == "dynamic"
    assert body["qr_targets"] == targets

    configs = admin_get(client, "/admin/qr-configs").json()
    genai = next(i for i in configs["items"] if i["group_type"] == "GENAI")
    assert genai["qr_targets"] == targets
    assert genai["qr_targets_count"] == 5
    assert genai["qr_value"] == targets[0]

    too_many = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "GENAI",
            "qr_mode": "dynamic",
            "qr_targets": targets + ["https://wa.me/pool_f"],
            "changed_by": "admin",
        },
    )
    assert too_many.status_code == 400
    assert too_many.json()["detail"] == "dynamic_qr_targets_max_5"

    seen = set()
    for _ in range(80):
        r = client.get("/r/GENAI", follow_redirects=False)
        assert r.status_code == 302
        seen.add(r.headers["location"])
        if seen == set(targets):
            break
    assert seen == set(targets)

    # 單條仍相容
    single = admin_post(
        client,
        "/admin/qr-config",
        json={
            "group": "HUMAN",
            "qr_mode": "dynamic",
            "qr_value": "https://wa.me/only_one",
            "changed_by": "admin",
        },
    )
    assert single.status_code == 200
    assert single.json()["qr_targets"] == ["https://wa.me/only_one"]
    r = client.get("/r/HUMAN", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://wa.me/only_one"


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


def test_h5_randomize_page_has_participant_name_field():
    client = TestClient(app)
    for path in ("/h5/randomize", "/h5/enroll"):
        res = client.get(path)
        assert res.status_code == 200
        assert 'id="pname"' in res.text
        assert "參加者姓名" in res.text
        assert res.headers.get("cache-control") == "no-store, no-cache, must-revalidate, max-age=0"
    info = client.get("/h5/form-info").json()
    assert info["has_participant_name_field"] is True
    assert "/h5/enroll" in info["participant_pages"]


def test_participant_name_on_randomization_and_admin_update():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000071",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
            "participant_name": " 張三 ",
        },
    )
    assert randomized.status_code == 200
    enrollment_no = randomized.json()["enrollment_no"]
    listing = admin_get(client, "/admin/randomization-records").json()
    item = next(i for i in listing["items"] if i["enrollment_no"] == enrollment_no)
    assert item["participant_name"] == "張三"

    updated = admin_patch(
        client,
        "/admin/randomization-records/participant-name",
        json={
            "enrollment_no": enrollment_no,
            "participant_name": "李四",
            "changed_by": "admin",
            "reason": "fix name",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["participant_name"] == "李四"


def test_whatsapp_number_defaults_to_phone_and_can_be_updated():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000072",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert randomized.status_code == 200
    enrollment_no = randomized.json()["enrollment_no"]
    listing = admin_get(client, "/admin/randomization-records").json()
    item = next(i for i in listing["items"] if i["enrollment_no"] == enrollment_no)
    assert item["whatsapp_number"] == "+85260000072"

    updated = admin_patch(
        client,
        "/admin/randomization-records/whatsapp",
        json={
            "enrollment_no": enrollment_no,
            "whatsapp_number": "+85269998888",
            "changed_by": "admin",
            "reason": "different whatsapp",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["whatsapp_number"] == "+85269998888"

    phone_patch = admin_patch(
        client,
        "/admin/randomization-records/phone",
        json={
            "enrollment_no": enrollment_no,
            "new_phone_number": "+85260007777",
            "changed_by": "admin",
            "reason": "phone only",
        },
    )
    assert phone_patch.status_code == 200
    listing2 = admin_get(client, "/admin/randomization-records").json()
    item2 = next(i for i in listing2["items"] if i["enrollment_no"] == enrollment_no)
    assert item2["phone_number"] == "+85260007777"
    assert item2["whatsapp_number"] == "+85269998888"


def test_account_added_manual_check_toggle():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260000073",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert randomized.status_code == 200
    enrollment_no = randomized.json()["enrollment_no"]

    listing = admin_get(client, "/admin/randomization-records").json()
    item = next(i for i in listing["items"] if i["enrollment_no"] == enrollment_no)
    assert item["account_added"] is False

    checked = admin_patch(
        client,
        "/admin/randomization-records/account-added",
        json={
            "enrollment_no": enrollment_no,
            "account_added": True,
            "changed_by": "admin",
            "reason": "manual account check",
        },
    )
    assert checked.status_code == 200
    assert checked.json()["account_added"] is True

    listing2 = admin_get(client, "/admin/randomization-records").json()
    item2 = next(i for i in listing2["items"] if i["enrollment_no"] == enrollment_no)
    assert item2["account_added"] is True

    unchecked = admin_patch(
        client,
        "/admin/randomization-records/account-added",
        json={
            "enrollment_no": enrollment_no,
            "account_added": False,
            "changed_by": "admin",
        },
    )
    assert unchecked.status_code == 200
    assert unchecked.json()["account_added"] is False

    exported = admin_get(client, "/admin/randomization-records.csv")
    assert exported.status_code == 200
    assert "account_added" in exported.text


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
    assert current.json()["recruitment_start_date"] == "2026-06-15"


def test_settings_sync_weekly_plan_weeks_from_recruitment_dates():
    client = TestClient(app)
    updated = admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "recruitment_start_date": "2026-06-15",
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
            "recruitment_start_date": "2026-06-15",
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
    day_week1 = datetime(2026, 6, 18, 10, 0, tzinfo=hk).astimezone(timezone.utc)
    day_week2 = datetime(2026, 6, 25, 10, 0, tzinfo=hk).astimezone(timezone.utc)
    with SessionLocal() as db:
        records = db.scalars(select(RandomizationRecord).order_by(RandomizationRecord.id.asc())).all()
        assert len(records) >= 2
        records[0].randomized_at = day_week1
        records[1].randomized_at = day_week2
        db.commit()

    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["recruitment_start_date"] == "2026-06-15"
    assert overview["weekly_plan"] == {"weeks": 20, "per_week": 60, "total_target": 1200}
    weeks = overview["weekly_tracking"]
    w1 = next(item for item in weeks if item["week_no"] == 1)
    w2 = next(item for item in weeks if item["week_no"] == 2)
    w3 = next(item for item in weeks if item["week_no"] == 3)
    assert w1["week_label"] == "第1周"
    assert w1["range_start"] == "2026-06-15"
    assert w1["range_end"] == "2026-06-21"
    assert w1["valid_total"] == 1
    assert w1["valid_cumulative"] == 1
    assert w2["range_start"] == "2026-06-22"
    assert w2["range_end"] == "2026-06-28"
    assert w2["valid_total"] == 1
    assert w2["valid_cumulative"] == 2
    assert w3["valid_total"] == 0
    assert w3["valid_cumulative"] == 2
    assert len(weeks) >= 20
    assert weeks[19]["week_no"] == 20
    assert w2["nontrial_total"] == 0
    assert w2["voided_total"] == 0
    assert w2["week_total_all"] == 1


def test_overview_weekly_tracking_by_site_assigned_week():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import RandomizationRecord, Site

    client = TestClient(app)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "recruitment_start_date": "2026-06-15",
            "block_sizes": [4, 8, 12],
            "updated_by": "admin",
        },
    )
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    assigned = admin_patch(
        client,
        "/admin/sites/assigned-week",
        json={
            "site_id": "SITE_01",
            "assigned_recruitment_week": 2,
            "changed_by": "admin",
        },
    )
    assert assigned.status_code == 200

    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85261113001",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200

    hk = ZoneInfo("Asia/Hong_Kong")
    day_week1 = datetime(2026, 6, 18, 10, 0, tzinfo=hk).astimezone(timezone.utc)
    with SessionLocal() as db:
        record = db.scalar(
            select(RandomizationRecord).where(
                RandomizationRecord.phone_number == "+85261113001"
            )
        )
        assert record is not None
        record.randomized_at = day_week1
        db.commit()
        site = db.get(Site, "SITE_01")
        assert site is not None
        assert site.assigned_recruitment_week == 2
        assert record.assigned_recruitment_week == 2

    listing = admin_get(client, "/admin/randomization-records").json()
    item = next(i for i in listing["items"] if i["phone_number"] == "+85261113001")
    assert item["assigned_recruitment_week"] == 2
    assert item["site_assigned_recruitment_week"] == 2
    assert item["effective_recruitment_week"] == 2

    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    assert overview["weekly_tracking_mode"] == "site_assigned"
    w1 = next(item for item in overview["weekly_tracking"] if item["week_no"] == 1)
    w2 = next(item for item in overview["weekly_tracking"] if item["week_no"] == 2)
    assert w1["valid_total"] == 0
    assert w2["valid_total"] == 1
    assert w2["valid_cumulative"] == 1


def test_overview_weekly_tracking_includes_nontrial_and_voided():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import RandomizationRecord

    client = TestClient(app)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "recruitment_start_date": "2026-06-15",
            "block_sizes": [4, 8, 12],
            "updated_by": "admin",
        },
    )
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    phones = ("+85261112001", "+85261112002", "+85261112003")
    enrollment_nos = []
    for phone in phones:
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
        enrollment_nos.append(created.json()["enrollment_no"])

    admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": enrollment_nos[1],
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "weekly chart test",
        },
    )
    admin_post(
        client,
        "/admin/randomization-records/delete",
        json={
            "enrollment_no": enrollment_nos[2],
            "voided_by": "admin",
            "reason": "weekly chart test",
        },
    )

    hk = ZoneInfo("Asia/Hong_Kong")
    day_week2 = datetime(2026, 6, 25, 10, 0, tzinfo=hk).astimezone(timezone.utc)
    with SessionLocal() as db:
        records = db.scalars(select(RandomizationRecord).order_by(RandomizationRecord.id.asc())).all()
        targets = [r for r in records if r.enrollment_no in enrollment_nos]
        assert len(targets) == 3
        for record in targets:
            record.randomized_at = day_week2
        db.commit()

    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    w2 = next(item for item in overview["weekly_tracking"] if item["week_no"] == 2)
    assert w2["valid_total"] == 1
    assert w2["nontrial_total"] == 1
    assert w2["nontrial_intervention"] + w2["nontrial_control"] == 1
    assert w2["nontrial_cumulative"] == 1
    assert w2["voided_total"] == 1
    assert w2["week_total_all"] == 3


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
    assert overview["trial"]["total"] == 1
    assert overview["voided"]["total"] == 0
    assert overview["voided"]["intervention"] == 0
    assert overview["voided"]["control"] == 0
    assert overview["trial"]["intervention"] + overview["trial"]["control"] == 1
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
    assert overview["trial"]["total"] == 0
    assert overview["voided"]["total"] == 1
    assert overview["voided"]["intervention"] + overview["voided"]["control"] == 1


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


def test_site_table_window_iso_round_trips_hk_calendar_day():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    hk = ZoneInfo("Asia/Hong_Kong")
    start_hk = datetime(2026, 6, 28, 0, 0, 0, tzinfo=hk)
    end_hk = datetime(2026, 6, 28, 23, 59, 59, tzinfo=hk)
    ws = start_hk.astimezone(timezone.utc).isoformat()
    we = end_hk.astimezone(timezone.utc).isoformat()
    saved = admin_post(
        client,
        "/admin/site-passwords",
        json={
            "site_id": "SITE_01",
            "window_start": ws,
            "window_end": we,
            "raw_password": "654321",
            "changed_by": "admin",
        },
    )
    assert saved.status_code == 200, saved.text

    table = admin_get(client, "/admin/sites/table").json()
    row = next(item for item in table["items"] if item["site_id"] == "SITE_01")
    for key in ("window_start", "window_end"):
        val = row[key]
        assert val is not None
        assert val.endswith("+00:00") or val.endswith("Z"), val

    start_read = datetime.fromisoformat(row["window_start"].replace("Z", "+00:00")).astimezone(hk)
    end_read = datetime.fromisoformat(row["window_end"].replace("Z", "+00:00")).astimezone(hk)
    assert start_read.year == 2026 and start_read.month == 6 and start_read.day == 28
    assert start_read.hour == 0 and start_read.minute == 0
    assert end_read.year == 2026 and end_read.month == 6 and end_read.day == 28
    assert end_read.hour == 23 and end_read.minute == 59


def _assert_utc_iso(value: str | None) -> None:
    assert value is not None
    assert value.endswith("+00:00") or value.endswith("Z"), value


def test_api_datetime_fields_include_utc_timezone():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85261118877",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200, created.text
    _assert_utc_iso(created.json()["randomized_at"])

    records = admin_get(client, "/admin/randomization-records").json()
    assert records["items"]
    _assert_utc_iso(records["items"][0]["randomized_at"])

    settings = admin_get(client, "/admin/randomization-settings").json()
    _assert_utc_iso(settings["updated_at"])

    qr = admin_get(client, "/admin/qr-configs").json()
    assert qr["items"]
    _assert_utc_iso(qr["items"][0]["changed_at"])

    audit = admin_get(client, "/admin/audit-logs").json()
    assert audit["items"]
    _assert_utc_iso(audit["items"][0]["created_at"])

    batch = admin_get(client, "/admin/recruitment-batches/current").json()
    _assert_utc_iso(batch["batch"]["created_at"])


def test_randomization_audit_logs_include_trigger_input():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    phone = "+85261118899"
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": phone,
            "recruiter_id": "r_audit",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200, created.text
    enrollment_no = created.json()["enrollment_no"]

    audit = admin_get(client, "/admin/audit-logs").json()
    randomized = next(
        item for item in audit["items"] if item["event_type"] == "participant_randomized"
    )
    payload = json.loads(randomized["payload_json"])
    assert payload["phone_number"] == phone
    assert payload["site_id"] == "SITE_01"
    assert payload["recruiter_id"] == "r_audit"
    assert payload["enrollment_no"] == enrollment_no
    assert payload["allocation_group"] in ("GENAI", "HUMAN")
    assert payload["idempotent"] is False
    assert "recruiter_password" not in payload
    assert payload["at"].endswith("+00:00") or payload["at"].endswith("Z")

    again = client.post(
        "/randomization/trigger",
        json={
            "phone_number": phone,
            "recruiter_id": "r_audit",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert again.status_code == 200
    idem = next(
        item for item in admin_get(client, "/admin/audit-logs").json()["items"]
        if item["event_type"] == "participant_randomized_idempotent"
    )
    idem_payload = json.loads(idem["payload_json"])
    assert idem_payload["phone_number"] == phone
    assert idem_payload["enrollment_no"] == enrollment_no
    assert idem_payload["idempotent"] is True


def test_admin_record_change_audit_includes_snapshot():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85260007777",
            "recruiter_id": "recruiter_a",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200
    enrollment_no = created.json()["enrollment_no"]

    phone_patch = admin_patch(
        client,
        "/admin/randomization-records/phone",
        json={
            "enrollment_no": enrollment_no,
            "new_phone_number": "+85260008888",
            "changed_by": "admin_audit",
            "reason": "fix typo",
        },
    )
    assert phone_patch.status_code == 200

    trial_patch = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": enrollment_no,
            "trial_status": "nontrial",
            "changed_by": "admin_audit",
            "reason": "mark nontrial",
        },
    )
    assert trial_patch.status_code == 200

    voided = admin_post(
        client,
        "/admin/randomization-records/delete",
        json={"enrollment_no": enrollment_no, "voided_by": "admin_audit", "reason": "void test"},
    )
    assert voided.status_code == 200

    items = admin_get(client, "/admin/audit-logs").json()["items"]
    phone_audit = next(i for i in items if i["event_type"] == "admin_phone_corrected")
    phone_payload = json.loads(phone_audit["payload_json"])
    assert phone_payload["enrollment_no"] == enrollment_no
    assert phone_payload["site_id"] == "SITE_01"
    assert phone_payload["recruiter_id"] == "recruiter_a"
    assert phone_payload["old_phone_number"] == "+85260007777"
    assert phone_payload["new_phone_number"] == "+85260008888"
    assert phone_payload["changed_by"] == "admin_audit"
    assert phone_payload["reason"] == "fix typo"

    trial_audit = next(i for i in items if i["event_type"] == "admin_trial_status_updated")
    trial_payload = json.loads(trial_audit["payload_json"])
    assert trial_payload["old_trial_status"] == "trial"
    assert trial_payload["new_trial_status"] == "nontrial"
    assert trial_payload["phone_number"] == "+85260008888"

    void_audit = next(i for i in items if i["event_type"] == "admin_record_voided")
    void_payload = json.loads(void_audit["payload_json"])
    assert void_payload["old_activation_status"] != "voided"
    assert void_payload["new_activation_status"] == "voided"
    assert void_payload["phone_number"] == "+85260008888"
    assert void_payload["changed_by"] == "admin_audit"


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
    assert overview["trial"]["total"] == 0
    assert overview["nontrial"]["total"] == 1
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


def test_admin_can_update_nontrial_allocation_group_only():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    body = _trigger_randomization(client, "+85261115001")
    enrollment_no = body["enrollment_no"]
    original_group = body["allocation_group"]

    marked = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": enrollment_no,
            "trial_status": "nontrial",
            "changed_by": "admin",
            "reason": "test nontrial group edit",
        },
    )
    assert marked.status_code == 200

    new_group = "HUMAN" if original_group == "GENAI" else "GENAI"
    updated = admin_patch(
        client,
        "/admin/randomization-records/allocation-group",
        json={
            "enrollment_no": enrollment_no,
            "allocation_group": new_group,
            "changed_by": "admin",
            "reason": "manual nontrial group fix",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["allocation_group"] == new_group

    listing = admin_get(client, "/admin/randomization-records").json()
    item = next(i for i in listing["items"] if i["enrollment_no"] == enrollment_no)
    assert item["allocation_group"] == new_group

    back_trial = admin_patch(
        client,
        "/admin/randomization-records/trial-status",
        json={
            "enrollment_no": enrollment_no,
            "trial_status": "trial",
            "changed_by": "admin",
            "reason": "back to trial",
        },
    )
    assert back_trial.status_code == 200

    blocked = admin_patch(
        client,
        "/admin/randomization-records/allocation-group",
        json={
            "enrollment_no": enrollment_no,
            "allocation_group": original_group,
            "changed_by": "admin",
            "reason": "should fail on trial",
        },
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "only_nontrial_allocation_group_editable"


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


def test_site_password_window_can_update_without_new_password():
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01", "123456")

    hk = ZoneInfo("Asia/Hong_Kong")
    now_hk = datetime.now(hk)
    start_hk = now_hk.replace(hour=8, minute=0, second=0, microsecond=0)
    end_hk = now_hk.replace(hour=20, minute=0, second=0, microsecond=0)
    at_hk = start_hk + timedelta(hours=1)
    ws = start_hk.astimezone(timezone.utc).isoformat()
    we = end_hk.astimezone(timezone.utc).isoformat()
    at = at_hk.astimezone(timezone.utc).isoformat()

    updated = admin_post(
        client,
        "/admin/site-passwords",
        json={
            "site_id": "SITE_01",
            "window_start": ws,
            "window_end": we,
            "changed_by": "admin",
            "reason": "window only",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body.get("updated") is True

    table = admin_get(client, "/admin/sites/table").json()
    row = next(item for item in table["items"] if item["site_id"] == "SITE_01")
    assert row["window_start"] is not None
    assert row["window_end"] is not None
    assert row["password_plain"] == "123456"

    randomized = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85261119901",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
            "at": at,
        },
    )
    assert randomized.status_code == 200


def test_site_password_window_can_update_when_password_plain_missing():
    """旧数据可能只有 hash、无 password_plain；仍应允许仅更新生效窗。"""
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01", "123456")

    from app.db import SessionLocal
    from app.models import SiteDailyPassword

    with SessionLocal() as db:
        row = db.query(SiteDailyPassword).filter(SiteDailyPassword.site_id == "SITE_01").order_by(SiteDailyPassword.id.desc()).first()
        assert row is not None
        row.password_plain = None
        db.commit()

    table_before = admin_get(client, "/admin/sites/table").json()
    row_before = next(item for item in table_before["items"] if item["site_id"] == "SITE_01")
    assert row_before["password_plain"] is None
    assert row_before["window_end"] is not None

    hk = ZoneInfo("Asia/Hong_Kong")
    now_hk = datetime.now(hk)
    start_hk = now_hk.replace(hour=7, minute=0, second=0, microsecond=0)
    end_hk = now_hk.replace(hour=22, minute=30, second=0, microsecond=0)
    ws = start_hk.astimezone(timezone.utc).isoformat()
    we = end_hk.astimezone(timezone.utc).isoformat()

    updated = admin_post(
        client,
        "/admin/site-passwords",
        json={
            "site_id": "SITE_01",
            "window_start": ws,
            "window_end": we,
            "changed_by": "admin",
            "reason": "window only without plain",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json().get("updated") is True

    table_after = admin_get(client, "/admin/sites/table").json()
    row_after = next(item for item in table_after["items"] if item["site_id"] == "SITE_01")
    assert row_after["window_end"] == we
    assert row_after["window_start"] == ws


def test_site_password_window_same_hk_day_from_split_date_times():
    """模拟前端：同一香港日期 + 起止时间，应能通过校验。"""
    client = TestClient(app)
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01", "123456")

    hk = ZoneInfo("Asia/Hong_Kong")
    day = datetime.now(hk).date()
    start_hk = datetime(day.year, day.month, day.day, 8, 0, tzinfo=hk)
    end_hk = datetime(day.year, day.month, day.day, 20, 30, tzinfo=hk)
    ws = start_hk.astimezone(timezone.utc).isoformat()
    we = end_hk.astimezone(timezone.utc).isoformat()

    updated = admin_post(
        client,
        "/admin/site-passwords",
        json={
            "site_id": "SITE_01",
            "window_start": ws,
            "window_end": we,
            "changed_by": "admin",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json().get("updated") is True

    table = admin_get(client, "/admin/sites/table").json()
    row = next(item for item in table["items"] if item["site_id"] == "SITE_01")
    assert row["window_start"] == ws
    assert row["window_end"] == we


def test_site_password_required_when_no_existing_config():
    client = TestClient(app)
    ws, we = hk_full_day_window_iso()
    created = admin_post(
        client,
        "/admin/sites",
        json={"site_id": "SITE_NEW", "site_name": "新站點"},
    )
    assert created.status_code == 200
    rejected = admin_post(
        client,
        "/admin/site-passwords",
        json={
            "site_id": "SITE_NEW",
            "window_start": ws,
            "window_end": we,
            "changed_by": "admin",
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "password_required_for_new_site"


def set_site_enrollment_mode(client: TestClient, site_id: str, mode: str) -> None:
    r = admin_patch(
        client,
        "/admin/sites/enrollment-mode",
        json={
            "site_id": site_id,
            "enrollment_mode": mode,
            "changed_by": "admin",
            "reason": "test",
        },
    )
    assert r.status_code == 200, r.text


def _trigger_at_site(client: TestClient, phone: str, site_id: str) -> dict:
    r = client.post(
        "/randomization/trigger",
        json={
            "phone_number": phone,
            "recruiter_id": "r1",
            "site_id": site_id,
            "recruiter_password": "123456",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_nontrial_site_uses_independent_block_randomization():
    from app.state import trial_group_at_index

    client = TestClient(app)
    configure_deterministic_trial_sequence(client, seed=999)
    admin_post(client, "/admin/sites", json={"site_id": "SITE_NT", "site_name": "Non-trial站"})
    set_site_enrollment_mode(client, "SITE_NT", "nontrial")
    set_site_password(client, "SITE_01")
    set_site_password(client, "SITE_NT")
    open_batch(client, ["SITE_01", "SITE_NT"])

    expected_nontrial = [trial_group_at_index(i, (4,), 999) for i in range(3)]
    expected_trial = [trial_group_at_index(i, (4,), 999) for i in range(3)]

    nt1 = _trigger_at_site(client, "+85271000002", "SITE_NT")
    assert nt1["allocation_group"] == expected_nontrial[0]

    trial_body = _trigger_at_site(client, "+85271000001", "SITE_01")
    assert trial_body["allocation_group"] == expected_trial[0]

    nt2 = _trigger_at_site(client, "+85271000003", "SITE_NT")
    assert nt2["allocation_group"] == expected_nontrial[1]

    trial_body2 = _trigger_at_site(client, "+85271000004", "SITE_01")
    assert trial_body2["allocation_group"] == expected_trial[1]

    records = admin_get(client, "/admin/randomization-records").json()["items"]
    nt_record = next(r for r in records if r["enrollment_no"] == nt1["enrollment_no"])
    assert nt_record["trial_status"] == "nontrial"
    assert nt_record["allocation_group"] in {"GENAI", "HUMAN"}


def test_nontrial_site_allowed_when_trial_recruitment_closed():
    client = TestClient(app)
    admin_post(client, "/admin/sites", json={"site_id": "SITE_NT", "site_name": "Non-trial站"})
    set_site_enrollment_mode(client, "SITE_NT", "nontrial")
    set_site_password(client, "SITE_01")
    set_site_password(client, "SITE_NT")
    open_batch(client, ["SITE_01", "SITE_NT"])
    configure_deterministic_trial_sequence(client, seed=999)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={"min_per_group": 1, "block_sizes": [4], "updated_by": "super_admin"},
    )
    _trigger_at_site(client, "+85272000001", "SITE_01")
    _trigger_at_site(client, "+85272000002", "SITE_01")
    blocked = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85272000003",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert blocked.status_code == 409

    allowed = _trigger_at_site(client, "+85272000004", "SITE_NT")
    assert allowed["allocation_group"] in {"GENAI", "HUMAN"}
    records = admin_get(client, "/admin/randomization-records").json()["items"]
    nt_record = next(r for r in records if r["enrollment_no"] == allowed["enrollment_no"])
    assert nt_record["trial_status"] == "nontrial"


def test_overview_weekly_tracking_by_record_assigned_week():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import RandomizationRecord

    client = TestClient(app)
    admin_put(
        client,
        "/admin/randomization-settings",
        json={
            "recruitment_start_date": "2026-06-15",
            "block_sizes": [4, 8, 12],
            "updated_by": "admin",
        },
    )
    open_batch(client, ["SITE_01"])
    set_site_password(client, "SITE_01")
    created = client.post(
        "/randomization/trigger",
        json={
            "phone_number": "+85261113001",
            "recruiter_id": "r1",
            "site_id": "SITE_01",
            "recruiter_password": "123456",
        },
    )
    assert created.status_code == 200
    enrollment_no = created.json()["enrollment_no"]

    hk = ZoneInfo("Asia/Hong_Kong")
    day_week2 = datetime(2026, 6, 25, 10, 0, tzinfo=hk).astimezone(timezone.utc)
    with SessionLocal() as db:
        record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == enrollment_no))
        assert record is not None
        record.randomized_at = day_week2
        db.commit()

    before = admin_get(client, "/admin/randomization-records").json()
    item = next(i for i in before["items"] if i["enrollment_no"] == enrollment_no)
    assert item["effective_recruitment_week"] == 2

    patched = admin_patch(
        client,
        "/admin/randomization-records/assigned-week",
        json={
            "enrollment_no": enrollment_no,
            "assigned_recruitment_week": 4,
            "changed_by": "admin",
            "reason": "record week override",
        },
    )
    assert patched.status_code == 200

    overview = admin_get(client, "/admin/randomization-records").json()["overview"]
    w2 = next(item for item in overview["weekly_tracking"] if item["week_no"] == 2)
    w4 = next(item for item in overview["weekly_tracking"] if item["week_no"] == 4)
    assert w2["valid_total"] == 0
    assert w4["valid_total"] == 1

    after = admin_get(client, "/admin/randomization-records").json()
    item2 = next(i for i in after["items"] if i["enrollment_no"] == enrollment_no)
    assert item2["assigned_recruitment_week"] == 4
    assert item2["effective_recruitment_week"] == 4
