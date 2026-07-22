from __future__ import annotations

import csv
import base64
from datetime import date, datetime, timedelta, timezone
from collections.abc import Generator
import io
import json
import os
from pathlib import Path
import secrets
from typing import Literal
from urllib.parse import quote

import segno
from PIL import Image
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text, and_
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    RECRUITMENT_BATCH_MAX_ACTIVE_SITES,
    AuditLog,
    EnrollmentCounter,
    GroupLabel,
    QRConfig,
    QRTargetDailyHit,
    QRTargetStreakState,
    RandomizationRecord,
    RandomizationSetting,
    RecruitmentBatch,
    RecruitmentBatchSite,
    Site,
    SiteDailyPassword,
)
from app.admin_ui import PageId, render_admin_page

from app.seed import ensure_preset_sites
from app.state import (
    DEFAULT_RANDOMIZATION_SEED,
    FailedAttemptWindow,
    app_state,
    hash_password,
    trial_group_at_index,
    utc_now,
)
from app.timeutil import (
    DEFAULT_RECRUITMENT_START_DATE,
    DEFAULT_WEEKLY_PLAN_PER_WEEK,
    DEFAULT_WEEKLY_PLAN_WEEKS,
    assert_same_hk_calendar_day,
    format_hk_datetime,
    hk_calendar_date,
    hk_date_stamp,
    hk_datetime_stamp,
    hk_today_password_window,
    recruitment_week_no,
    recruitment_week_bounds,
    recruitment_week_range_label,
    recruitment_plan_end_date,
    recruitment_plan_weeks_from_end_date,
    record_recruitment_week_for_stats,
    utc_iso,
)

try:
    import multipart as _multipart  # type: ignore

    _HAS_MULTIPART = True
except Exception:
    _HAS_MULTIPART = False


app = FastAPI(title="Randomization Product API")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads/qr"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR.parent)), name="uploads")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_SESSION_VALUE = "ok"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
TRIAL_STATUS_TRIAL = "trial"
TRIAL_STATUS_NONTrial = "nontrial"
H5_FORM_VERSION = "2026-07-17-dual-qr-v1"
ENROLLMENT_MODE_TRIAL = "trial"
ENROLLMENT_MODE_NONTrial = "nontrial"
QR_GROUP_TYPES = frozenset({"GENAI", "HUMAN"})
QR_MODES = frozenset({"dynamic", "static_url", "static_image"})
DYNAMIC_QR_TARGET_MAX = 5
DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT = 10  # 每條連結每日上限預設值（後台可改）
DYNAMIC_QR_TARGET_DAILY_MAX_LIMIT = 200  # 後台可設上限的硬頂
# 同一連結最多連續出現次數（後台可調）；達此數後下一次必須換其他連結
DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT = 3
DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_LIMIT = 20
QR_GROUP_COLORS: dict[str, dict[str, str]] = {
    "GENAI": {"dark": "#dc2626", "light": "#ffffff"},
    "HUMAN": {"dark": "#2563eb", "light": "#ffffff"},
}


def _is_admin_request(path: str) -> bool:
    return path.startswith("/admin")


def _build_basic_auth_challenge() -> Response:
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Admin Area"'},
        content="Unauthorized",
    )


def _verify_basic_auth_header(header_value: str | None) -> bool:
    if not header_value or not header_value.startswith("Basic "):
        return False
    encoded = header_value[6:].strip()
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return False
    if ":" not in decoded:
        return False
    username, password = decoded.split(":", 1)
    return secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD)


def _is_login_exempt_path(path: str) -> bool:
    return path in {"/admin/login"}


def _is_admin_cookie_authenticated(request: Request) -> bool:
    return request.cookies.get(ADMIN_SESSION_COOKIE) == ADMIN_SESSION_VALUE


def _wants_html_response(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "*/*" in accept


@app.middleware("http")
async def require_admin_basic_auth(request: Request, call_next):
    if _is_admin_request(request.url.path):
        if _is_login_exempt_path(request.url.path):
            return await call_next(request)
        if _is_admin_cookie_authenticated(request):
            return await call_next(request)
        auth_header = request.headers.get("Authorization")
        if not _verify_basic_auth_header(auth_header):
            if _wants_html_response(request):
                next_path = quote(request.url.path, safe="/")
                return RedirectResponse(url=f"/admin/login?next={next_path}", status_code=302)
            return _build_basic_auth_challenge()
    return await call_next(request)


def _render_admin_login_page(error: str = "", next_path: str = "/admin/web?page=settings") -> str:
    error_html = f'<p style="color:#b91c1c;font-size:13px;">{error}</p>' if error else ""
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Admin Login</title>
      <style>
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f8fafc;
          margin: 0;
          min-height: 100vh;
          display: grid;
          place-items: center;
        }}
        .card {{
          width: min(360px, 92vw);
          background: #fff;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 20px;
          box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
        }}
        h2 {{ margin: 0 0 12px; font-size: 20px; }}
        label {{ display: block; margin-top: 10px; font-size: 13px; color: #334155; }}
        input {{
          width: 100%;
          box-sizing: border-box;
          margin-top: 6px;
          padding: 10px 12px;
          border: 1px solid #cbd5e1;
          border-radius: 8px;
          font-size: 14px;
        }}
        button {{
          width: 100%;
          margin-top: 14px;
          padding: 10px 12px;
          border: none;
          border-radius: 8px;
          background: #2563eb;
          color: #fff;
          font-weight: 600;
          cursor: pointer;
        }}
      </style>
    </head>
    <body>
      <form class="card" method="post" action="/admin/login">
        <h2>管理端登入</h2>
        {error_html}
        <input type="hidden" name="next" value="{next_path}" />
        <label>用戶名稱</label>
        <input name="username" autocomplete="username" required />
        <label>密碼</label>
        <input name="password" type="password" autocomplete="current-password" required />
        <button type="submit">登入</button>
      </form>
    </body>
    </html>
    """


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(next: str = "/admin/web?page=settings"):
    return HTMLResponse(_render_admin_login_page(next_path=next))


@app.post("/admin/login")
def admin_login_submit(
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/admin/web?page=settings"),
):
    if not (secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD)):
        return HTMLResponse(_render_admin_login_page(error="用戶名稱或密碼錯誤", next_path=next), status_code=401)
    response = RedirectResponse(url=next or "/admin/web?page=settings", status_code=302)
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=ADMIN_SESSION_VALUE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(ADMIN_SESSION_COOKIE)
    return response


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_audit(db: Session, event_type: str, payload: dict) -> None:
    db.add(
        AuditLog(
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            request_id=secrets.token_hex(8),
        )
    )
    db.commit()


def _randomization_trigger_audit_payload(
    payload: RandomizationTriggerRequest,
    at: datetime,
    **extra: object,
) -> dict:
    """入組請求審計欄位（不含招募員密碼）。"""
    out: dict[str, object] = {
        "phone_number": payload.phone_number,
        "site_id": payload.site_id,
        "recruiter_id": payload.recruiter_id,
        "participant_name": _normalize_participant_name(payload.participant_name),
        "at": utc_iso(at),
    }
    out.update(extra)
    return out


def next_enrollment_no(db: Session) -> str:
    counter = db.get(EnrollmentCounter, 1)
    if counter is None:
        counter = EnrollmentCounter(id=1, seq=0)
        db.add(counter)
        db.flush()
    counter.seq += 1
    db.commit()
    db.refresh(counter)
    return f"R{hk_date_stamp(utc_now())}-{counter.seq:06d}"


def ensure_schema_migrations() -> None:
    # 輕量 schema 自修復：舊庫補 recruiter_id 欄，避免升級後查詢報錯。
    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_records')")).fetchall()]
        if "recruiter_id" not in cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN recruiter_id VARCHAR(64) DEFAULT ''"))
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "h5_show_allocation_group" not in rs_cols:
            conn.execute(
                text("ALTER TABLE randomization_settings ADD COLUMN h5_show_allocation_group BOOLEAN DEFAULT 1")
            )
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "min_per_group" not in rs_cols:
            conn.execute(text("ALTER TABLE randomization_settings ADD COLUMN min_per_group INTEGER"))
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "recruitment_start_date" not in rs_cols:
            conn.execute(text("ALTER TABLE randomization_settings ADD COLUMN recruitment_start_date DATE"))
            conn.execute(
                text(
                    "UPDATE randomization_settings SET recruitment_start_date = '2026-06-15' "
                    "WHERE recruitment_start_date IS NULL"
                )
            )
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "recruitment_end_date" not in rs_cols:
            conn.execute(text("ALTER TABLE randomization_settings ADD COLUMN recruitment_end_date DATE"))
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "weekly_plan_weeks" not in rs_cols:
            conn.execute(text("ALTER TABLE randomization_settings ADD COLUMN weekly_plan_weeks INTEGER"))
            conn.execute(
                text(
                    f"UPDATE randomization_settings SET weekly_plan_weeks = {DEFAULT_WEEKLY_PLAN_WEEKS} "
                    "WHERE weekly_plan_weeks IS NULL"
                )
            )
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "weekly_plan_per_week" not in rs_cols:
            conn.execute(text("ALTER TABLE randomization_settings ADD COLUMN weekly_plan_per_week INTEGER"))
            conn.execute(
                text(
                    f"UPDATE randomization_settings SET weekly_plan_per_week = {DEFAULT_WEEKLY_PLAN_PER_WEEK} "
                    "WHERE weekly_plan_per_week IS NULL"
                )
            )
        qr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('qr_configs')")).fetchall()]
        if qr_cols and "qr_mode" not in qr_cols:
            conn.execute(text("ALTER TABLE qr_configs ADD COLUMN qr_mode VARCHAR(32) DEFAULT 'static_url'"))
            conn.execute(
                text("UPDATE qr_configs SET qr_mode = 'static_image' WHERE qr_value LIKE '/uploads/%'")
            )
        if qr_cols and "qr_logo_path" not in qr_cols:
            conn.execute(text("ALTER TABLE qr_configs ADD COLUMN qr_logo_path VARCHAR(512)"))
        qr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('qr_configs')")).fetchall()]
        if qr_cols and "wechat_qr_path" not in qr_cols:
            conn.execute(text("ALTER TABLE qr_configs ADD COLUMN wechat_qr_path VARCHAR(512)"))
        qr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('qr_configs')")).fetchall()]
        if qr_cols and "qr_targets_json" not in qr_cols:
            conn.execute(text("ALTER TABLE qr_configs ADD COLUMN qr_targets_json VARCHAR(4096)"))
        qr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('qr_configs')")).fetchall()]
        if qr_cols and "target_daily_cap" not in qr_cols:
            conn.execute(
                text(
                    f"ALTER TABLE qr_configs ADD COLUMN target_daily_cap INTEGER DEFAULT {DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT}"
                )
            )
            conn.execute(
                text(
                    f"UPDATE qr_configs SET target_daily_cap = {DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT} "
                    "WHERE target_daily_cap IS NULL"
                )
            )
        qr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('qr_configs')")).fetchall()]
        if qr_cols and "target_max_consecutive" not in qr_cols:
            conn.execute(
                text(
                    f"ALTER TABLE qr_configs ADD COLUMN target_max_consecutive INTEGER DEFAULT {DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT}"
                )
            )
            conn.execute(
                text(
                    f"UPDATE qr_configs SET target_max_consecutive = {DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT} "
                    "WHERE target_max_consecutive IS NULL"
                )
            )
        rr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_records')")).fetchall()]
        if rr_cols and "trial_status" not in rr_cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN trial_status VARCHAR(16) DEFAULT 'trial'"))
            conn.execute(text("UPDATE randomization_records SET trial_status = 'trial' WHERE trial_status IS NULL"))
        rr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_records')")).fetchall()]
        if rr_cols and "subject_code" not in rr_cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN subject_code VARCHAR(64)"))
        if rr_cols and "assigned_recruitment_week" not in rr_cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN assigned_recruitment_week INTEGER"))
        rr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_records')")).fetchall()]
        if rr_cols and "participant_name" not in rr_cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN participant_name VARCHAR(128)"))
        rr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_records')")).fetchall()]
        if rr_cols and "whatsapp_number" not in rr_cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN whatsapp_number VARCHAR(32)"))
        if rr_cols and "account_added" not in rr_cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN account_added BOOLEAN DEFAULT 0"))
            conn.execute(text("UPDATE randomization_records SET account_added = 0 WHERE account_added IS NULL"))
        rr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_records')")).fetchall()]
        if rr_cols and "contact_channel" not in rr_cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN contact_channel VARCHAR(16)"))
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "randomization_seed" not in rs_cols:
            conn.execute(text("ALTER TABLE randomization_settings ADD COLUMN randomization_seed INTEGER"))
            conn.execute(
                text(
                    f"UPDATE randomization_settings SET randomization_seed = {DEFAULT_RANDOMIZATION_SEED} "
                    "WHERE randomization_seed IS NULL"
                )
            )
        site_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('sites')")).fetchall()]
        if site_cols and "assigned_recruitment_week" not in site_cols:
            conn.execute(text("ALTER TABLE sites ADD COLUMN assigned_recruitment_week INTEGER"))
        if site_cols and "enrollment_mode" not in site_cols:
            conn.execute(text("ALTER TABLE sites ADD COLUMN enrollment_mode VARCHAR(16) DEFAULT 'trial'"))
            conn.execute(text("UPDATE sites SET enrollment_mode = 'trial' WHERE enrollment_mode IS NULL"))


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_migrations()
    with SessionLocal() as db:
        for group, value in {
            "GENAI": "https://wa.me/genai_default",
            "HUMAN": "https://wa.me/human_default",
        }.items():
            existing = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
            if not existing:
                db.add(
                    QRConfig(
                        group_type=group,
                        qr_mode="static_url",
                        qr_value=value,
                        version=1,
                        changed_by="system",
                        reason="seed",
                    )
                )
        for group, name in {"GENAI": "干預組", "HUMAN": "對照組"}.items():
            if db.get(GroupLabel, group) is None:
                db.add(GroupLabel(group_type=group, display_name=name, changed_by="system", reason="seed"))
        if db.get(EnrollmentCounter, 1) is None:
            db.add(EnrollmentCounter(id=1, seq=0))
        if db.get(RandomizationSetting, 1) is None:
            db.add(
                RandomizationSetting(
                    id=1,
                    min_per_group=499,
                    recruitment_start_date=DEFAULT_RECRUITMENT_START_DATE,
                    recruitment_end_date=recruitment_plan_end_date(
                        DEFAULT_RECRUITMENT_START_DATE, DEFAULT_WEEKLY_PLAN_WEEKS
                    ),
                    weekly_plan_weeks=DEFAULT_WEEKLY_PLAN_WEEKS,
                    weekly_plan_per_week=DEFAULT_WEEKLY_PLAN_PER_WEEK,
                    block_sizes_csv="4,8,12",
                    randomization_seed=DEFAULT_RANDOMIZATION_SEED,
                    updated_by="system",
                )
            )
        else:
            setting = db.get(RandomizationSetting, 1)
            if setting is not None and setting.randomization_seed is None:
                setting.randomization_seed = DEFAULT_RANDOMIZATION_SEED
        for record in db.scalars(select(RandomizationRecord)).all():
            if _stored_whatsapp_number(record) is None:
                record.whatsapp_number = _display_phone(record.phone_number, record.enrollment_no)
        ensure_preset_sites(db)
        db.commit()


class SiteUpsertRequest(BaseModel):
    site_id: str
    site_name: str


class SiteAssignedWeekRequest(BaseModel):
    site_id: str
    assigned_recruitment_week: int | None = None
    changed_by: str
    reason: str = ""


class SiteEnrollmentModeRequest(BaseModel):
    site_id: str
    enrollment_mode: Literal["trial", "nontrial"]
    changed_by: str
    reason: str = ""


class SiteRenameIdRequest(BaseModel):
    old_site_id: str
    new_site_id: str
    site_name: str = ""


class DailyPasswordConfigRequest(BaseModel):
    site_id: str
    window_start: datetime
    window_end: datetime
    raw_password: str | None = None
    changed_by: str
    reason: str = "password window"


class RandomizationTriggerRequest(BaseModel):
    phone_number: str = Field(min_length=6)
    site_id: str
    recruiter_id: str
    recruiter_password: str
    participant_name: str = ""
    at: datetime | None = None


class RecruitmentBatchOpenRequest(BaseModel):
    site_ids: list[str]
    created_by: str
    label: str = ""
    max_active_sites: int = RECRUITMENT_BATCH_MAX_ACTIVE_SITES


class QRTargetItem(BaseModel):
    url: str
    daily_cap: int | None = None


class QRUpdateRequest(BaseModel):
    group: str
    qr_mode: Literal["dynamic", "static_url", "static_image"] = "static_url"
    qr_value: str = ""
    # 兼容舊版：純 URL 列表；優先使用 qr_target_items（每條可帶獨立每日上限）
    qr_targets: list[str] | None = None
    qr_target_items: list[QRTargetItem] | None = None
    # 組級預設每日上限（當某條未單獨設定時回退）；仍保留兼容
    target_daily_cap: int | None = None
    # 同一連結連續出現幾次後必須換鏈（動態模式）
    target_max_consecutive: int | None = None
    changed_by: str
    reason: str = ""


def _infer_qr_mode(qr_value: str, qr_mode: str | None = None) -> str:
    if qr_mode and qr_mode in QR_MODES:
        return qr_mode
    if qr_value.startswith("/uploads/"):
        return "static_image"
    return "static_url"


def _is_http_url(value: str) -> bool:
    lower = (value or "").strip().lower()
    return lower.startswith("http://") or lower.startswith("https://")


def _is_upload_or_image_path(value: str) -> bool:
    lower = (value or "").strip().lower()
    return (
        lower.startswith("/uploads/")
        or "/uploads/qr/" in lower
        or lower.endswith((".png", ".jpg", ".jpeg", ".webp"))
    )


def _normalize_target_daily_cap(value: int | None, *, required: bool = False) -> int | None:
    if value is None:
        if required:
            return DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT
        return None
    try:
        cap = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid_target_daily_cap")
    if cap < 1 or cap > DYNAMIC_QR_TARGET_DAILY_MAX_LIMIT:
        raise HTTPException(status_code=400, detail="invalid_target_daily_cap")
    return cap


def _normalize_target_max_consecutive(value: int | None, *, required: bool = False) -> int | None:
    if value is None:
        if required:
            return DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid_target_max_consecutive")
    if n < 1 or n > DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_LIMIT:
        raise HTTPException(status_code=400, detail="invalid_target_max_consecutive")
    return n


def _daily_cap_from_config(cfg: QRConfig) -> int:
    """組級預設每日上限（單條未指定時回退）。"""
    raw = getattr(cfg, "target_daily_cap", None)
    try:
        cap = int(raw) if raw is not None else DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT
    except (TypeError, ValueError):
        cap = DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT
    if cap < 1:
        return 1
    if cap > DYNAMIC_QR_TARGET_DAILY_MAX_LIMIT:
        return DYNAMIC_QR_TARGET_DAILY_MAX_LIMIT
    return cap


def _max_consecutive_from_config(cfg: QRConfig) -> int:
    """同一連結連續出現上限（達此數後下一次必須換鏈）。"""
    raw = getattr(cfg, "target_max_consecutive", None)
    try:
        n = int(raw) if raw is not None else DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT
    except (TypeError, ValueError):
        n = DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT
    if n < 1:
        return 1
    if n > DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_LIMIT:
        return DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_LIMIT
    return n


def _parse_target_entry(item: object, default_cap: int) -> dict[str, object] | None:
    if isinstance(item, str):
        url = item.strip()
        if not url:
            return None
        return {"url": url, "daily_cap": default_cap}
    if isinstance(item, dict):
        url = str(item.get("url") or "").strip()
        if not url:
            return None
        cap_raw = item.get("daily_cap", default_cap)
        try:
            cap = int(cap_raw) if cap_raw is not None else default_cap
        except (TypeError, ValueError):
            cap = default_cap
        if cap < 1:
            cap = 1
        if cap > DYNAMIC_QR_TARGET_DAILY_MAX_LIMIT:
            cap = DYNAMIC_QR_TARGET_DAILY_MAX_LIMIT
        return {"url": url, "daily_cap": cap}
    return None


def _normalize_dynamic_target_entries(
    raw_items: list[object] | None,
    fallback_value: str = "",
    default_cap: int = DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT,
) -> list[dict[str, object]]:
    """整理動態跳轉池條目：{url, daily_cap}，去重保序，最多 DYNAMIC_QR_TARGET_MAX。"""
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    candidates: list[object] = []
    if raw_items:
        candidates.extend(raw_items)
    if fallback_value:
        candidates.append(fallback_value)
    for item in candidates:
        entry = _parse_target_entry(item, default_cap)
        if entry is None:
            continue
        url = str(entry["url"])
        if url in seen:
            continue
        seen.add(url)
        out.append(entry)
        if len(out) >= DYNAMIC_QR_TARGET_MAX:
            break
    return out


def _normalize_dynamic_targets(raw_targets: list[str] | None, fallback_value: str = "") -> list[str]:
    """兼容舊呼叫：僅回傳 URL 列表。"""
    return [
        str(e["url"])
        for e in _normalize_dynamic_target_entries(raw_targets, fallback_value)
    ]


def _validate_dynamic_target_url(url: str) -> None:
    if not url:
        raise HTTPException(status_code=400, detail="dynamic_qr_target_required")
    if _is_upload_or_image_path(url) or not _is_http_url(url):
        raise HTTPException(status_code=400, detail="dynamic_qr_target_must_be_url")


def _target_entries_from_config(cfg: QRConfig) -> list[dict[str, object]]:
    default_cap = _daily_cap_from_config(cfg)
    raw = getattr(cfg, "qr_targets_json", None)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                entries = _normalize_dynamic_target_entries(parsed, "", default_cap)
                if entries:
                    return entries
        except (TypeError, json.JSONDecodeError):
            pass
    value = (cfg.qr_value or "").strip()
    if value:
        return [{"url": value, "daily_cap": default_cap}]
    return []


def _targets_from_config(cfg: QRConfig) -> list[str]:
    return [str(e["url"]) for e in _target_entries_from_config(cfg)]


def _daily_hit_counts(db: Session, group: str, day_key: str, targets: list[str]) -> dict[str, int]:
    if not targets:
        return {}
    rows = db.scalars(
        select(QRTargetDailyHit).where(
            QRTargetDailyHit.group_type == group,
            QRTargetDailyHit.day_key == day_key,
            QRTargetDailyHit.target_url.in_(targets),
        )
    ).all()
    return {r.target_url: int(r.hit_count or 0) for r in rows}


def _increment_daily_hit(db: Session, group: str, day_key: str, target_url: str) -> int:
    row = db.scalar(
        select(QRTargetDailyHit).where(
            QRTargetDailyHit.group_type == group,
            QRTargetDailyHit.day_key == day_key,
            QRTargetDailyHit.target_url == target_url,
        )
    )
    if row is None:
        row = QRTargetDailyHit(
            group_type=group,
            day_key=day_key,
            target_url=target_url,
            hit_count=1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return 1
    row.hit_count = int(row.hit_count or 0) + 1
    db.commit()
    db.refresh(row)
    return int(row.hit_count)


def _get_streak_state(db: Session, group: str) -> QRTargetStreakState | None:
    return db.get(QRTargetStreakState, group)


def _update_streak_state(db: Session, group: str, chosen: str) -> int:
    state = db.get(QRTargetStreakState, group)
    if state is None:
        state = QRTargetStreakState(group_type=group, last_target_url=chosen, consecutive_count=1)
        db.add(state)
        db.commit()
        db.refresh(state)
        return 1
    if state.last_target_url == chosen:
        state.consecutive_count = int(state.consecutive_count or 0) + 1
    else:
        state.last_target_url = chosen
        state.consecutive_count = 1
    db.commit()
    db.refresh(state)
    return int(state.consecutive_count)


def _pick_dynamic_target(cfg: QRConfig, db: Session, day_key: str | None = None) -> str:
    """從連結池挑選目標：避開當日已滿額，且同一連結不可連續達上限後仍再出。"""
    entries = _target_entries_from_config(cfg)
    if not entries:
        raise HTTPException(status_code=404, detail="target_not_configured")
    day = day_key or hk_date_stamp()
    targets = [str(e["url"]) for e in entries]
    counts = _daily_hit_counts(db, cfg.group_type, day, targets)
    available = [
        str(e["url"])
        for e in entries
        if counts.get(str(e["url"]), 0) < int(e["daily_cap"])
    ]
    if not available:
        raise HTTPException(status_code=429, detail="dynamic_qr_daily_cap_reached")

    # 同一連結已連續出現達上限後，必須換其他仍可用的連結
    max_consecutive = _max_consecutive_from_config(cfg)
    state = _get_streak_state(db, cfg.group_type)
    streak_blocked = ""
    if (
        state is not None
        and state.last_target_url
        and int(state.consecutive_count or 0) >= max_consecutive
    ):
        streak_blocked = state.last_target_url
        switched = [u for u in available if u != streak_blocked]
        if switched:
            available = switched

    chosen = available[0] if len(available) == 1 else secrets.choice(available)
    _increment_daily_hit(db, cfg.group_type, day, chosen)
    _update_streak_state(db, cfg.group_type, chosen)
    return chosen


def _public_base_url(request: Request | None = None) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8000"


def _stable_qr_path(group: str) -> str:
    return f"/r/{group}"


def _stable_qr_url(group: str, request: Request | None = None) -> str:
    return f"{_public_base_url(request)}{_stable_qr_path(group)}"


def _upload_path_from_url(url: str | None) -> Path | None:
    if not url or not url.startswith("/uploads/"):
        return None
    rel = url.removeprefix("/uploads/")
    path = UPLOAD_DIR.parent / rel
    return path if path.is_file() else None


def _serialize_qr_config(
    cfg: QRConfig,
    request: Request | None = None,
    db: Session | None = None,
) -> dict:
    mode = _infer_qr_mode(cfg.qr_value, cfg.qr_mode)
    entries = _target_entries_from_config(cfg) if mode == "dynamic" else []
    targets = [str(e["url"]) for e in entries]
    default_cap = _daily_cap_from_config(cfg)
    item = {
        "group_type": cfg.group_type,
        "qr_mode": mode,
        "qr_value": cfg.qr_value,
        "qr_targets": targets,
        "qr_target_items": entries,
        "qr_logo_path": cfg.qr_logo_path,
        "wechat_qr_path": getattr(cfg, "wechat_qr_path", None),
        "version": cfg.version,
        "changed_by": cfg.changed_by,
        "reason": cfg.reason,
        "changed_at": utc_iso(cfg.changed_at),
    }
    if mode == "dynamic":
        item["stable_qr_url"] = _stable_qr_url(cfg.group_type, request)
        item["stable_qr_path"] = _stable_qr_path(cfg.group_type)
        item["qr_targets_count"] = len(targets)
        item["qr_target_daily_cap"] = default_cap
        item["target_daily_cap"] = default_cap
        max_consecutive = _max_consecutive_from_config(cfg)
        item["qr_target_max_consecutive"] = max_consecutive
        item["target_max_consecutive"] = max_consecutive
        day = hk_date_stamp()
        counts = _daily_hit_counts(db, cfg.group_type, day, targets) if db is not None else {}
        item["qr_targets_daily"] = [
            {
                "url": str(e["url"]),
                "daily_cap": int(e["daily_cap"]),
                "hits_today": int(counts.get(str(e["url"]), 0)),
                "remaining_today": max(0, int(e["daily_cap"]) - int(counts.get(str(e["url"]), 0))),
            }
            for e in entries
        ]
        item["qr_targets_daily_day"] = day
        if db is not None:
            streak = _get_streak_state(db, cfg.group_type)
            if streak is not None and streak.last_target_url:
                item["qr_target_streak"] = {
                    "last_url": streak.last_target_url,
                    "consecutive_count": int(streak.consecutive_count or 0),
                    "must_switch_next": int(streak.consecutive_count or 0) >= max_consecutive,
                }
    return item


def _participant_qr_fields(cfg: QRConfig | None, group: str) -> dict[str, object]:
    if cfg is None:
        return {
            "whatsapp_qr": "",
            "qr_display_mode": "none",
            "wechat_qr": "",
            "show_dual_qr": False,
            "require_contact_channel": False,
            "contact_channel_options": [],
        }
    mode = _infer_qr_mode(cfg.qr_value, cfg.qr_mode)
    if mode == "dynamic":
        whatsapp_qr: str = _stable_qr_path(group)
    else:
        whatsapp_qr = cfg.qr_value
    wechat_qr = (getattr(cfg, "wechat_qr_path", None) or "").strip()
    show_dual = bool(whatsapp_qr and wechat_qr)
    return {
        "whatsapp_qr": whatsapp_qr,
        "qr_display_mode": mode,
        "wechat_qr": wechat_qr,
        "show_dual_qr": show_dual,
        "require_contact_channel": show_dual,
        "contact_channel_options": ["whatsapp", "wechat"] if show_dual else [],
    }


def _make_qr_png(content: str, group: str | None = None, logo_path: Path | None = None) -> bytes:
    buf = io.BytesIO()
    save_kwargs: dict[str, object] = {"kind": "png", "scale": 8, "border": 2}
    colors = QR_GROUP_COLORS.get(group or "")
    if colors:
        save_kwargs["dark"] = colors["dark"]
        save_kwargs["light"] = colors["light"]
        save_kwargs["data_dark"] = colors["dark"]
        save_kwargs["finder_dark"] = colors["dark"]
        save_kwargs["alignment_dark"] = colors["dark"]
        save_kwargs["timing_dark"] = colors["dark"]
    segno.make(content, error="h").save(buf, **save_kwargs)
    qr_bytes = buf.getvalue()
    if logo_path is None or not logo_path.is_file():
        return qr_bytes
    qr_img = Image.open(io.BytesIO(qr_bytes)).convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")
    qr_w, qr_h = qr_img.size
    logo_max = int(min(qr_w, qr_h) * 0.22)
    logo.thumbnail((logo_max, logo_max), Image.Resampling.LANCZOS)
    pad = max(6, logo_max // 10)
    bg_size = (logo.width + pad * 2, logo.height + pad * 2)
    bg = Image.new("RGBA", bg_size, (255, 255, 255, 255))
    bg.paste(logo, (pad, pad), logo)
    pos = ((qr_w - bg_size[0]) // 2, (qr_h - bg_size[1]) // 2)
    qr_img.paste(bg, pos, bg)
    out = io.BytesIO()
    qr_img.save(out, format="PNG")
    return out.getvalue()


def _qr_logo_path_for_group(db: Session, group: str) -> Path | None:
    cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
    if cfg is None:
        return None
    return _upload_path_from_url(cfg.qr_logo_path)


class GroupLabelUpdateRequest(BaseModel):
    intervention_name: str = Field(min_length=1, max_length=64)
    control_name: str = Field(min_length=1, max_length=64)
    changed_by: str
    reason: str = ""


class PhoneCorrectionRequest(BaseModel):
    enrollment_no: str
    new_phone_number: str = Field(min_length=6)
    changed_by: str
    reason: str = ""


class SubjectCodeUpdateRequest(BaseModel):
    enrollment_no: str
    subject_code: str = ""
    changed_by: str
    reason: str = ""


class ParticipantNameUpdateRequest(BaseModel):
    enrollment_no: str
    participant_name: str = ""
    changed_by: str
    reason: str = ""


class WhatsappNumberUpdateRequest(BaseModel):
    enrollment_no: str
    whatsapp_number: str = Field(min_length=6)
    changed_by: str
    reason: str = ""


class AccountAddedUpdateRequest(BaseModel):
    enrollment_no: str
    account_added: bool
    changed_by: str
    reason: str = "manual account check"


class ContactChannelUpdateRequest(BaseModel):
    enrollment_no: str
    contact_channel: Literal["whatsapp", "wechat"]
    changed_by: str = "recruiter"
    reason: str = "participant contact channel"


class RecordAssignedWeekRequest(BaseModel):
    enrollment_no: str
    assigned_recruitment_week: int | None = None
    changed_by: str
    reason: str = ""


class TrialStatusUpdateRequest(BaseModel):
    enrollment_no: str
    trial_status: Literal["trial", "nontrial"]
    changed_by: str
    reason: str = ""


class AllocationGroupUpdateRequest(BaseModel):
    enrollment_no: str
    allocation_group: Literal["GENAI", "HUMAN"]
    changed_by: str
    reason: str = ""


class RecordVoidRequest(BaseModel):
    enrollment_no: str
    voided_by: str
    reason: str = ""


class RandomizationSettingUpdateRequest(BaseModel):
    max_enrollment: int | None = None
    min_per_group: int | None = None
    recruitment_start_date: date | None = None
    recruitment_end_date: date | None = None
    weekly_plan_weeks: int | None = None
    weekly_plan_per_week: int | None = None
    block_sizes: list[int]
    updated_by: str


def _void_phone_storage(enrollment_no: str, phone: str) -> str:
    return f"voided:{enrollment_no}:{phone}"


def _display_phone(stored: str, enrollment_no: str) -> str:
    prefix = f"voided:{enrollment_no}:"
    if stored.startswith(prefix):
        return stored[len(prefix) :]
    return stored


def _stored_whatsapp_number(record: RandomizationRecord) -> str | None:
    raw = getattr(record, "whatsapp_number", None)
    if raw is None:
        return None
    trimmed = str(raw).strip()
    return trimmed if trimmed else None


def _display_whatsapp_number(record: RandomizationRecord) -> str:
    stored = _stored_whatsapp_number(record)
    if stored:
        return stored
    return _display_phone(record.phone_number, record.enrollment_no)


def _record_audit_snapshot(record: RandomizationRecord) -> dict[str, object]:
    """管理端變更審計：記錄當前入組記錄快照（不含密碼）。"""
    return {
        "enrollment_no": record.enrollment_no,
        "phone_number": _display_phone(record.phone_number, record.enrollment_no),
        "site_id": record.site_id,
        "site_name": record.site_name,
        "recruiter_id": record.recruiter_id,
        "participant_name": getattr(record, "participant_name", None),
        "whatsapp_number": _display_whatsapp_number(record),
        "allocation_group": record.allocation_group,
        "activation_status": record.activation_status,
        "trial_status": getattr(record, "trial_status", TRIAL_STATUS_TRIAL) or TRIAL_STATUS_TRIAL,
        "subject_code": record.subject_code,
        "assigned_recruitment_week": getattr(record, "assigned_recruitment_week", None),
        "account_added": bool(getattr(record, "account_added", False)),
        "contact_channel": getattr(record, "contact_channel", None),
    }


def _active_record_filter():
    return RandomizationRecord.activation_status != "voided"


def _trial_record_filter():
    return and_(
        RandomizationRecord.activation_status != "voided",
        RandomizationRecord.trial_status == TRIAL_STATUS_TRIAL,
    )


def _nontrial_record_filter():
    return and_(
        RandomizationRecord.activation_status != "voided",
        RandomizationRecord.trial_status == TRIAL_STATUS_NONTrial,
    )


def _group_enrollment_counts(db: Session, record_filter) -> tuple[int, int, int]:
    total = db.scalar(select(func.count()).select_from(RandomizationRecord).where(record_filter)) or 0
    genai = (
        db.scalar(
            select(func.count())
            .select_from(RandomizationRecord)
            .where(record_filter, RandomizationRecord.allocation_group == "GENAI")
        )
        or 0
    )
    human = (
        db.scalar(
            select(func.count())
            .select_from(RandomizationRecord)
            .where(record_filter, RandomizationRecord.allocation_group == "HUMAN")
        )
        or 0
    )
    return total, genai, human


def _trial_enrollment_counts(db: Session) -> tuple[int, int, int]:
    return _group_enrollment_counts(db, _trial_record_filter())


def _nontrial_enrollment_counts(db: Session) -> tuple[int, int, int]:
    return _group_enrollment_counts(db, _nontrial_record_filter())


def _voided_enrollment_counts(db: Session) -> tuple[int, int, int]:
    voided_filter = RandomizationRecord.activation_status == "voided"
    return _group_enrollment_counts(db, voided_filter)


def _normalize_subject_code(raw: str) -> str | None:
    code = raw.strip()
    return code if code else None


def _normalize_participant_name(raw: str) -> str | None:
    name = (raw or "").strip()
    return name if name else None


def _normalize_whatsapp_number(raw: str) -> str:
    number = (raw or "").strip().replace(" ", "")
    return number


def _record_effective_recruitment_week(
    record: RandomizationRecord,
    start_date: date,
    site_week_map: dict[str, int | None],
) -> int | None:
    if record.randomized_at is None:
        return None
    event_date = hk_calendar_date(record.randomized_at)
    return record_recruitment_week_for_stats(
        start_date,
        event_date,
        site_week_map.get(record.site_id),
        getattr(record, "assigned_recruitment_week", None),
    )


def _is_recruitment_period_ended(setting: RandomizationSetting) -> bool:
    end = getattr(setting, "recruitment_end_date", None)
    if end is None:
        return False
    if isinstance(end, str):
        end = date.fromisoformat(end)
    today_hk = hk_calendar_date(datetime.now(timezone.utc))
    return today_hk > end


def _is_recruitment_closed(
    setting: RandomizationSetting,
    trial_total: int,
    trial_genai: int,
    trial_human: int,
) -> bool:
    if _is_recruitment_period_ended(setting):
        return True
    min_per = getattr(setting, "min_per_group", None)
    if min_per is None or min_per <= 0:
        return False
    return trial_genai >= min_per and trial_human >= min_per


def _recruitment_start_date(setting: RandomizationSetting) -> date:
    raw = getattr(setting, "recruitment_start_date", None)
    if raw is None:
        return DEFAULT_RECRUITMENT_START_DATE
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


def _recruitment_end_date(setting: RandomizationSetting) -> date | None:
    raw = getattr(setting, "recruitment_end_date", None)
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


def _weekly_plan_weeks(setting: RandomizationSetting) -> int:
    raw = getattr(setting, "weekly_plan_weeks", None)
    if raw is None or raw <= 0:
        return DEFAULT_WEEKLY_PLAN_WEEKS
    return int(raw)


def _weekly_plan_per_week(setting: RandomizationSetting) -> int:
    raw = getattr(setting, "weekly_plan_per_week", None)
    if raw is None or raw <= 0:
        return DEFAULT_WEEKLY_PLAN_PER_WEEK
    return int(raw)


def _empty_week_bucket() -> dict[str, int]:
    return {
        "valid_total": 0,
        "valid_intervention": 0,
        "valid_control": 0,
        "nontrial_total": 0,
        "nontrial_intervention": 0,
        "nontrial_control": 0,
        "voided_total": 0,
    }


def _weekly_recruitment_tracking(db: Session, start_date: date, plan_weeks: int) -> list[dict]:
    site_week_map = {
        s.site_id: getattr(s, "assigned_recruitment_week", None)
        for s in db.scalars(select(Site)).all()
    }
    records = db.scalars(select(RandomizationRecord)).all()
    buckets: dict[int, dict[str, int]] = {}
    max_data_week = 0
    for record in records:
        if record.randomized_at is None:
            continue
        event_date = hk_calendar_date(record.randomized_at)
        week_no = record_recruitment_week_for_stats(
            start_date,
            event_date,
            site_week_map.get(record.site_id),
            getattr(record, "assigned_recruitment_week", None),
        )
        if week_no is None:
            continue
        bucket = buckets.setdefault(week_no, _empty_week_bucket())
        if record.activation_status == "voided":
            bucket["voided_total"] += 1
        elif record.trial_status == TRIAL_STATUS_NONTrial:
            bucket["nontrial_total"] += 1
            if record.allocation_group == "GENAI":
                bucket["nontrial_intervention"] += 1
            elif record.allocation_group == "HUMAN":
                bucket["nontrial_control"] += 1
        elif record.trial_status == TRIAL_STATUS_TRIAL:
            bucket["valid_total"] += 1
            if record.allocation_group == "GENAI":
                bucket["valid_intervention"] += 1
            elif record.allocation_group == "HUMAN":
                bucket["valid_control"] += 1
        max_data_week = max(max_data_week, week_no)

    today_hk = hk_calendar_date(datetime.now(timezone.utc))
    current_week = recruitment_week_no(start_date, today_hk) or 0
    if current_week <= 0 and max_data_week <= 0:
        end_week = plan_weeks
    else:
        end_week = max(max_data_week, current_week, plan_weeks)

    items: list[dict] = []
    running_trial_total = 0
    running_nontrial_total = 0
    for week_no in range(1, end_week + 1):
        bucket = buckets.get(week_no, _empty_week_bucket())
        running_trial_total += bucket["valid_total"]
        running_nontrial_total += bucket["nontrial_total"]
        week_start, week_end = recruitment_week_bounds(start_date, week_no)
        inter = bucket["valid_intervention"]
        ctrl = bucket["valid_control"]
        trial_total = bucket["valid_total"]
        nontrial_total = bucket["nontrial_total"]
        nontrial_inter = bucket["nontrial_intervention"]
        nontrial_ctrl = bucket["nontrial_control"]
        voided_total = bucket["voided_total"]
        items.append(
            {
                "week_no": week_no,
                "week_label": f"第{week_no}周",
                "range_start": week_start.isoformat(),
                "range_end": week_end.isoformat(),
                "range_label": recruitment_week_range_label(start_date, week_no),
                "valid_total": trial_total,
                "valid_intervention": inter,
                "valid_control": ctrl,
                "valid_other": max(0, trial_total - inter - ctrl),
                "nontrial_total": nontrial_total,
                "nontrial_intervention": nontrial_inter,
                "nontrial_control": nontrial_ctrl,
                "nontrial_other": max(0, nontrial_total - nontrial_inter - nontrial_ctrl),
                "voided_total": voided_total,
                "week_total_all": trial_total + nontrial_total + voided_total,
                "valid_cumulative": running_trial_total,
                "nontrial_cumulative": running_nontrial_total,
            }
        )
    return items


def _overview_status_bucket(total: int, intervention: int, control: int) -> dict[str, int]:
    return {
        "total": total,
        "intervention": intervention,
        "control": control,
        "other": max(0, total - intervention - control),
    }


def _recruitment_overview(setting: RandomizationSetting, db: Session) -> dict:
    trial_total, trial_genai, trial_human = _trial_enrollment_counts(db)
    nontrial_total, nontrial_genai, nontrial_human = _nontrial_enrollment_counts(db)
    voided_total, voided_genai, voided_human = _voided_enrollment_counts(db)
    total = db.scalar(select(func.count()).select_from(RandomizationRecord)) or 0
    closed = _is_recruitment_closed(setting, trial_total, trial_genai, trial_human)
    start_date = _recruitment_start_date(setting)
    end_date = _recruitment_end_date(setting)
    plan_weeks = _weekly_plan_weeks(setting)
    plan_per_week = _weekly_plan_per_week(setting)
    return {
        "total_randomized": total,
        "trial": _overview_status_bucket(trial_total, trial_genai, trial_human),
        "nontrial": _overview_status_bucket(nontrial_total, nontrial_genai, nontrial_human),
        "voided": _overview_status_bucket(voided_total, voided_genai, voided_human),
        "max_enrollment": setting.max_enrollment,
        "min_per_group": getattr(setting, "min_per_group", None),
        "recruitment_open": not closed,
        "recruitment_start_date": start_date.isoformat(),
        "recruitment_end_date": end_date.isoformat() if end_date is not None else None,
        "weekly_tracking": _weekly_recruitment_tracking(db, start_date, plan_weeks),
        "weekly_tracking_mode": "site_assigned",
        "weekly_plan": {
            "weeks": plan_weeks,
            "per_week": plan_per_week,
            "total_target": plan_weeks * plan_per_week,
        },
    }


class ParticipantPageSettingsRequest(BaseModel):
    show_allocation_group: bool


def normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_open_batch(db: Session) -> RecruitmentBatch | None:
    return db.scalar(select(RecruitmentBatch).where(RecruitmentBatch.closed_at.is_(None)).order_by(RecruitmentBatch.id.desc()))


def site_in_open_batch(db: Session, site_id: str) -> bool:
    batch = get_open_batch(db)
    if batch is None:
        return False
    bid = db.scalar(
        select(RecruitmentBatchSite.batch_id).where(
            RecruitmentBatchSite.batch_id == batch.id,
            RecruitmentBatchSite.site_id == site_id,
        )
    )
    return bid is not None


def _randomization_seed(setting: RandomizationSetting) -> int:
    raw = getattr(setting, "randomization_seed", None)
    if raw is None:
        return DEFAULT_RANDOMIZATION_SEED
    return int(raw)


def _site_enrollment_mode(site: Site | None) -> str:
    if site is None:
        return ENROLLMENT_MODE_TRIAL
    mode = getattr(site, "enrollment_mode", None) or ENROLLMENT_MODE_TRIAL
    return ENROLLMENT_MODE_NONTrial if mode == ENROLLMENT_MODE_NONTrial else ENROLLMENT_MODE_TRIAL


def _is_nontrial_recruitment_site(site: Site | None) -> bool:
    return _site_enrollment_mode(site) == ENROLLMENT_MODE_NONTrial


def _next_trial_allocation_group(db: Session, setting: RandomizationSetting) -> str:
    trial_total, _, _ = _trial_enrollment_counts(db)
    block_sizes = parse_block_sizes(setting.block_sizes_csv)
    seed = _randomization_seed(setting)
    return trial_group_at_index(trial_total, block_sizes, seed)


def _next_nontrial_allocation_group(db: Session, setting: RandomizationSetting) -> str:
    nontrial_total, _, _ = _nontrial_enrollment_counts(db)
    block_sizes = parse_block_sizes(setting.block_sizes_csv)
    seed = _randomization_seed(setting)
    return trial_group_at_index(nontrial_total, block_sizes, seed)


def parse_block_sizes(block_sizes_csv: str) -> tuple[int, ...]:
    try:
        values = tuple(int(x.strip()) for x in block_sizes_csv.split(",") if x.strip())
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="invalid_block_size_config") from exc
    if not values or any(v <= 0 or v % 2 != 0 for v in values):
        raise HTTPException(status_code=500, detail="invalid_block_size_config")
    return values


@app.get("/r/{group}/qr.png")
def qr_group_png(group: str, request: Request, db: Session = Depends(get_db)):
    if group not in QR_GROUP_TYPES:
        raise HTTPException(status_code=404, detail="invalid_group")
    cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
    if cfg is None or _infer_qr_mode(cfg.qr_value, cfg.qr_mode) != "dynamic":
        raise HTTPException(status_code=404, detail="dynamic_qr_not_configured")
    png = _make_qr_png(_stable_qr_url(group, request), group, _qr_logo_path_for_group(db, group))
    return Response(content=png, media_type="image/png")


@app.get("/admin/qr-preview/{group}.png")
def admin_qr_preview_png(group: str, request: Request, db: Session = Depends(get_db)):
    """管理端預覽：無需先儲存，即可生成固定動態碼二維碼圖。"""
    if group not in QR_GROUP_TYPES:
        raise HTTPException(status_code=400, detail="invalid_group")
    png = _make_qr_png(_stable_qr_url(group, request), group, _qr_logo_path_for_group(db, group))
    return Response(content=png, media_type="image/png")


@app.get("/r/{group}")
def qr_group_redirect(group: str, db: Session = Depends(get_db)):
    if group not in QR_GROUP_TYPES:
        raise HTTPException(status_code=404, detail="invalid_group")
    cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
    if cfg is None or _infer_qr_mode(cfg.qr_value, cfg.qr_mode) != "dynamic":
        raise HTTPException(status_code=404, detail="dynamic_qr_not_configured")
    target = _pick_dynamic_target(cfg, db)
    return RedirectResponse(url=target, status_code=302)


@app.get("/", response_class=HTMLResponse)
def home_page():
    return f"""
    <html><body style="font-family:-apple-system,sans-serif;padding:20px;">
    <h2>Randomization Product</h2>
    <p><strong>表單版本：</strong>{H5_FORM_VERSION}</p>
    <p><a href="/h5/enroll">受試者入組頁（推薦，含參加者姓名）</a></p>
    <p><a href="/h5/randomize">受試者掃碼頁（舊連結）</a></p>
    <p><a href="/h5/form-info">表單版本 API</a></p>
    <p><a href="/admin/web?page=settings">管理員後台頁</a></p>
    </body></html>
    """


@app.get("/h5/form-info")
def h5_form_info():
    return {
        "form_version": H5_FORM_VERSION,
        "has_participant_name_field": True,
        "participant_pages": ["/h5/enroll", "/h5/randomize"],
        "recommended_page": "/h5/enroll",
    }


def _h5_randomize_html() -> str:
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
      <meta http-equiv="Pragma" content="no-cache" />
      <meta http-equiv="Expires" content="0" />
      <title>歡迎參加第十七屆「戒煙大贏家」</title>
      <style>
        :root {
          --bg: #f3f6fb;
          --card: #ffffff;
          --text: #0f172a;
          --muted: #64748b;
          --border: #e2e8f0;
          --brand: #2563eb;
          --brand-hover: #1d4ed8;
          --ok: #166534;
          --err: #b91c1c;
        }
        body {
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          margin: 0;
          background: radial-gradient(circle at top, #eaf1ff, var(--bg) 46%);
          color: var(--text);
          min-height: 100vh;
          padding: 24px 14px;
        }
        .wrap { max-width: 560px; margin: 0 auto; }
        .card {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 18px;
          box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        }
        .title { margin: 0 0 6px; font-size: 22px; }
        .lead { margin: 0 0 14px; font-size: 13px; color: var(--muted); line-height: 1.5; }
        label { display:block; margin-top:10px; font-size:13px; color:#334155; font-weight: 600; }
        input, select, button {
          width:100%;
          box-sizing:border-box;
          margin-top:6px;
          padding:10px 12px;
          border-radius: 10px;
          border: 1px solid var(--border);
          font-size: 14px;
          background: #fff;
        }
        input:focus, select:focus {
          border-color: #93c5fd;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, .15);
          outline: none;
        }
        button {
          margin-top:14px;
          cursor:pointer;
          background: var(--brand);
          color: #fff;
          border: none;
          font-weight: 600;
          transition: background .15s ease;
        }
        button:hover { background: var(--brand-hover); }
        .phone-row { display: grid; grid-template-columns: 110px 1fr; gap: 8px; }
        .result {
          margin-top:16px;
          border-top: 1px dashed var(--border);
          padding-top:12px;
        }
        .kv { margin:5px 0; font-size:14px; }
        .group {
          font-size: 24px;
          font-weight: 800;
          margin: 10px 0;
          color: #1e3a8a;
          letter-spacing: .2px;
        }
        .ok {
          color: var(--ok);
          background: #f0fdf4;
          border: 1px solid #bbf7d0;
          border-radius: 10px;
          padding: 8px 10px;
        }
        .err {
          color: var(--err);
          white-space: pre-wrap;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 10px;
          padding: 8px 10px;
        }
        #qrImage {
          max-width: 260px;
          max-height: 260px;
          border: 1px solid var(--border);
          border-radius: 10px;
          display: none;
          margin-top: 8px;
          background: #fff;
          padding: 4px;
        }
        .dual-qr {
          display: none;
          gap: 12px;
          margin-top: 10px;
          flex-wrap: wrap;
        }
        .dual-qr.show { display: flex; }
        .dual-qr-card {
          flex: 1 1 150px;
          min-width: 140px;
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 10px;
          background: #f8fafc;
          text-align: center;
        }
        .dual-qr-card h4 {
          margin: 0 0 8px;
          font-size: 14px;
          color: #334155;
        }
        .dual-qr-card img {
          max-width: 160px;
          width: 100%;
          margin: 0 auto;
          display: block;
          border-radius: 8px;
          border: 1px solid var(--border);
          background: #fff;
          padding: 4px;
        }
        .channel-pick {
          display: none;
          margin-top: 14px;
          padding: 12px;
          border: 1px solid #bfdbfe;
          border-radius: 12px;
          background: #eff6ff;
        }
        .channel-pick.show { display: block; }
        .channel-pick h4 { margin: 0 0 8px; font-size: 14px; color: #1e3a8a; }
        .channel-pick .opts {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .channel-pick label.opt {
          flex: 1 1 120px;
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 12px;
          border: 1px solid #93c5fd;
          border-radius: 10px;
          background: #fff;
          cursor: pointer;
          font-size: 14px;
          font-weight: 600;
        }
        .channel-pick label.opt input { width: auto; margin: 0; }
        .channel-pick button { margin-top: 10px; width: 100%; }
        .highlight-field {
          margin-top: 12px;
          padding: 12px;
          border-radius: 12px;
          background: #f0f9ff;
          border: 1px solid #7dd3fc;
        }
        .highlight-field label { margin-top: 0; color: #0c4a6e; }
        .form-version {
          margin-top: 14px;
          font-size: 11px;
          color: var(--muted);
          text-align: center;
        }
      </style>
    </head>
    <body>
      <div class="wrap">
      <div class="card">
        <h3 class="title">歡迎參加第十七屆「戒煙大贏家」</h3>
        <p class="lead">請按現場資訊填寫後提交。系統會按當前招募地點與密碼時間窗校驗後完成隨機化。</p>
        <form id="f">
          <div class="highlight-field">
            <label for="pname">參加者姓名</label>
            <input id="pname" name="participant_name" placeholder="請輸入参加者姓名" autocomplete="name" />
          </div>
          <label>手機號</label>
          <div class="phone-row">
            <select id="phoneCode">
              <option value="+852" selected>+852</option>
              <option value="+86">+86</option>
              <option value="+853">+853</option>
              <option value="+886">+886</option>
            </select>
            <input id="phone" placeholder="請輸入號碼（不含區號）" inputmode="numeric" />
          </div>
          <label>招募地點</label>
          <select id="site">
            <option value="">請選擇站點</option>
          </select>
          <label>招募員姓名</label><input id="rid" placeholder="請輸入姓名" />
          <label>密碼</label><input id="pwd" type="password" />
          <p class="muted" style="font-size:12px;margin-top:6px;">校驗時間以伺服器當前時間為準；站點須屬於當前已開啟的招募批次，且密碼在設定的時間窗內有效。</p>
          <button type="submit">提交隨機化</button>
        </form>
        <p class="form-version">表單版本 __H5_FORM_VERSION__</p>

        <div class="result">
          <div class="kv"><strong>入組編號：</strong><span id="enrollmentNo">-</span></div>
          <div class="kv"><strong>招募地點：</strong><span id="siteName">-</span></div>
          <div class="group" id="groupRow">分組結果：<span id="groupResult">-</span></div>
          <div class="kv"><strong>二維碼：</strong></div>
          <img id="qrImage" alt="whatsapp-qr" />
          <div id="dualQr" class="dual-qr">
            <div class="dual-qr-card">
              <h4>WhatsApp</h4>
              <img id="qrWaImage" alt="whatsapp-qr" />
            </div>
            <div class="dual-qr-card">
              <h4>微信 WeChat</h4>
              <img id="qrWechatImage" alt="wechat-qr" />
            </div>
          </div>
          <div class="kv" id="qrLinkText"></div>
          <div id="channelPick" class="channel-pick">
            <h4>請選擇參加者實際添加的帳號</h4>
            <div class="opts">
              <label class="opt"><input type="radio" name="contactChannel" value="whatsapp" /> WhatsApp</label>
              <label class="opt"><input type="radio" name="contactChannel" value="wechat" /> 微信 WeChat</label>
            </div>
            <button type="button" id="saveChannelBtn">確認添加渠道</button>
            <div class="kv" id="channelStatus" style="margin-top:8px;"></div>
          </div>
          <div class="kv ok" id="okText"></div>
          <div class="kv err" id="errText"></div>
        </div>
      </div>
      </div>

      <script>
        let showAllocationGroup = true;

        async function loadParticipantUiConfig() {
          try {
            const res = await fetch("/participant-ui/config");
            const d = await res.json().catch(() => ({}));
            showAllocationGroup = d.show_allocation_group !== false;
          } catch (e) {
            showAllocationGroup = true;
          }
          const row = document.getElementById("groupRow");
          if (row) row.style.display = showAllocationGroup ? "" : "none";
        }

        function toAbsoluteUrl(raw) {
          if (!raw) return "";
          if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
          return window.location.origin + raw;
        }

        function renderResult(data) {
          document.getElementById("errText").textContent = "";
          const dual = !!data.show_dual_qr && !!(data.wechat_qr);
          document.getElementById("okText").textContent = data.idempotent
            ? "該手機號已隨機化，展示過往結果。"
            : (dual
              ? "隨機化成功。請讓參加者掃碼加入 WhatsApp 或微信，並由招募員確認添加渠道。"
              : "隨機化成功，請掃碼加入對應 WhatsApp 帳號。");
          document.getElementById("enrollmentNo").textContent = data.enrollment_no || "-";
          document.getElementById("siteName").textContent = data.site_name || data.site_id || "-";
          const gr = document.getElementById("groupResult");
          if (gr) gr.textContent = showAllocationGroup ? (data.allocation_group || "-") : "-";

          const qrRaw = data.whatsapp_qr || "";
          const qrMode = data.qr_display_mode || "";
          const qrUrl = toAbsoluteUrl(qrRaw);
          const qrImg = document.getElementById("qrImage");
          const qrLinkText = document.getElementById("qrLinkText");
          const dualBox = document.getElementById("dualQr");
          const channelPick = document.getElementById("channelPick");
          const channelStatus = document.getElementById("channelStatus");
          const waImg = document.getElementById("qrWaImage");
          const wxImg = document.getElementById("qrWechatImage");
          qrLinkText.innerHTML = "";
          if (channelStatus) channelStatus.textContent = "";
          window.__lastEnrollmentNo = data.enrollment_no || "";

          if (dual) {
            qrImg.style.display = "none";
            dualBox.classList.add("show");
            if (qrMode === "dynamic") {
              waImg.src = window.location.origin + "/r/" + (data.allocation_group || "") + "/qr.png?t=" + Date.now();
            } else {
              waImg.src = qrUrl;
            }
            wxImg.src = toAbsoluteUrl(data.wechat_qr);
            channelPick.classList.add("show");
            // 干預組預設 WhatsApp；對照組雙碼時需招募員確認
            let existing = data.contact_channel || "";
            if (!existing && data.allocation_group === "GENAI") existing = "whatsapp";
            document.querySelectorAll('input[name="contactChannel"]').forEach(function(r) {
              r.checked = r.value === existing;
            });
            if (existing) {
              const presetHint = (data.allocation_group === "GENAI" && existing === "whatsapp")
                ? "（干預組預設）"
                : "";
              channelStatus.textContent = "已選擇：" + (existing === "wechat" ? "微信" : "WhatsApp") + presetHint;
              channelStatus.className = "kv ok";
            }
            return;
          }

          dualBox.classList.remove("show");
          channelPick.classList.remove("show");
          if (!qrRaw) {
            qrImg.style.display = "none";
            qrLinkText.textContent = "未配置二維碼";
            return;
          }
          if (qrMode === "dynamic") {
            const group = data.allocation_group || "";
            qrImg.src = window.location.origin + "/r/" + group + "/qr.png";
            qrImg.style.display = "block";
            qrLinkText.textContent = "請掃碼加入 WhatsApp";
            return;
          }
          const isImg = /\\.(png|jpg|jpeg|webp)(\\?.*)?$/i.test(qrUrl) || qrUrl.includes("/uploads/qr/");
          if (isImg) {
            qrImg.src = qrUrl;
            qrImg.style.display = "block";
          } else {
            qrImg.style.display = "none";
          }
          qrLinkText.innerHTML = '二維碼連結：<a href="' + qrUrl + '" target="_blank">' + qrRaw + '</a>';
        }

        async function saveContactChannel() {
          const enrollmentNo = window.__lastEnrollmentNo || document.getElementById("enrollmentNo").textContent;
          const picked = document.querySelector('input[name="contactChannel"]:checked');
          const status = document.getElementById("channelStatus");
          if (!enrollmentNo || enrollmentNo === "-") {
            status.textContent = "請先完成隨機化";
            status.className = "kv err";
            return;
          }
          if (!picked) {
            status.textContent = "請先選擇 WhatsApp 或微信";
            status.className = "kv err";
            return;
          }
          const rid = (document.getElementById("rid").value || "").trim() || "recruiter";
          const res = await fetch("/randomization/contact-channel", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              enrollment_no: enrollmentNo,
              contact_channel: picked.value,
              changed_by: rid,
              reason: "h5 channel selection"
            })
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            status.textContent = "保存失敗：" + (data.detail || "unknown_error");
            status.className = "kv err";
            return;
          }
          status.textContent = "已保存：參加者添加的是 " + (picked.value === "wechat" ? "微信" : "WhatsApp");
          status.className = "kv ok";
        }

        async function loadSiteOptions() {
          const sel = document.getElementById("site");
          if (!sel) return;
          const res = await fetch("/participant/active-sites");
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            document.getElementById("errText").textContent = "站點列表載入失敗";
            return;
          }
          const items = data.items || [];
          if (!items.length) {
            sel.innerHTML = '<option value="">暫無已啟用站點</option>';
            document.getElementById("errText").textContent = "當前沒有已啟用站點，請先在管理後台啟用站點。";
            return;
          }
          sel.innerHTML = '<option value="">請選擇已啟用站點</option>';
          items.forEach((row) => {
            const opt = document.createElement("option");
            opt.value = row.site_id;
            opt.textContent = row.site_id + " — " + row.site_name;
            sel.appendChild(opt);
          });
        }

        document.getElementById("f").addEventListener("submit", async (e) => {
          e.preventDefault();
          document.getElementById("okText").textContent = "";
          document.getElementById("errText").textContent = "";
          const code = document.getElementById("phoneCode").value || "+852";
          const localPhone = (document.getElementById("phone").value || "").trim().replace(/\\s+/g, "");
          if (!/^\\d{6,}$/.test(localPhone)) {
            document.getElementById("errText").textContent = "手機號格式應為：區號 + 號碼，號碼至少 6 位數字。";
            return;
          }
          const payload = {
            phone_number: code + localPhone,
            site_id: document.getElementById("site").value,
            recruiter_id: document.getElementById("rid").value,
            participant_name: (document.getElementById("pname").value || "").trim(),
            recruiter_password: document.getElementById("pwd").value,
            at: new Date().toISOString()
          };
          const res = await fetch("/randomization/trigger", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            document.getElementById("errText").textContent =
              "隨機化失敗：" + (data.detail || "unknown_error");
            return;
          }
          renderResult(data);
        });

        loadParticipantUiConfig();
        loadSiteOptions();
        const saveChannelBtn = document.getElementById("saveChannelBtn");
        if (saveChannelBtn) saveChannelBtn.addEventListener("click", saveContactChannel);
      </script>
    </body>
    </html>
    """
    html = html.replace("__H5_FORM_VERSION__", H5_FORM_VERSION)
    return html


def _h5_randomize_response() -> HTMLResponse:
    return HTMLResponse(
        content=_h5_randomize_html(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/h5/randomize", response_class=HTMLResponse)
def randomize_page():
    return _h5_randomize_response()


@app.get("/h5/enroll", response_class=HTMLResponse)
def enroll_page():
    return _h5_randomize_response()


@app.get("/admin/web", response_class=HTMLResponse)
def admin_page(page: PageId = Query("settings")):
    return HTMLResponse(
        render_admin_page(page),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.post("/admin/sites")
def upsert_site(payload: SiteUpsertRequest, db: Session = Depends(get_db)):
    site = db.get(Site, payload.site_id)
    if site is None:
        site = Site(site_id=payload.site_id, site_name=payload.site_name)
        db.add(site)
    else:
        site.site_name = payload.site_name
    db.commit()
    add_audit(db, "site_upserted", payload.model_dump())
    return {"ok": True}


@app.patch("/admin/sites/assigned-week")
def update_site_assigned_week(payload: SiteAssignedWeekRequest, db: Session = Depends(get_db)):
    site = db.get(Site, payload.site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="site_not_found")
    if payload.assigned_recruitment_week is not None and payload.assigned_recruitment_week < 1:
        raise HTTPException(status_code=400, detail="invalid_assigned_recruitment_week")
    old_week = getattr(site, "assigned_recruitment_week", None)
    site.assigned_recruitment_week = payload.assigned_recruitment_week
    db.commit()
    add_audit(
        db,
        "site_assigned_week_updated",
        {
            "site_id": payload.site_id,
            "site_name": site.site_name,
            "old_assigned_recruitment_week": old_week,
            "new_assigned_recruitment_week": payload.assigned_recruitment_week,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {
        "ok": True,
        "site_id": site.site_id,
        "assigned_recruitment_week": site.assigned_recruitment_week,
    }


@app.patch("/admin/sites/enrollment-mode")
def update_site_enrollment_mode(payload: SiteEnrollmentModeRequest, db: Session = Depends(get_db)):
    site = db.get(Site, payload.site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="site_not_found")
    if payload.enrollment_mode not in {ENROLLMENT_MODE_TRIAL, ENROLLMENT_MODE_NONTrial}:
        raise HTTPException(status_code=400, detail="invalid_enrollment_mode")
    old_mode = _site_enrollment_mode(site)
    site.enrollment_mode = payload.enrollment_mode
    db.commit()
    add_audit(
        db,
        "site_enrollment_mode_updated",
        {
            "site_id": payload.site_id,
            "site_name": site.site_name,
            "old_enrollment_mode": old_mode,
            "new_enrollment_mode": payload.enrollment_mode,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {
        "ok": True,
        "site_id": site.site_id,
        "enrollment_mode": _site_enrollment_mode(site),
    }


@app.post("/admin/sites/rename-id")
def rename_site_id(payload: SiteRenameIdRequest, db: Session = Depends(get_db)):
    old_id = payload.old_site_id.strip()
    new_id = payload.new_site_id.strip()
    if not old_id or not new_id:
        raise HTTPException(status_code=400, detail="invalid_site_id")
    if old_id == new_id:
        site = db.get(Site, old_id)
        if site is None:
            raise HTTPException(status_code=404, detail="site_not_found")
        if payload.site_name.strip():
            site.site_name = payload.site_name.strip()
            db.commit()
        add_audit(db, "site_rename_noop", {"site_id": old_id})
        return {"ok": True, "site_id": old_id}
    site = db.get(Site, old_id)
    if site is None:
        raise HTTPException(status_code=404, detail="site_not_found")
    if db.get(Site, new_id) is not None:
        raise HTTPException(status_code=409, detail="site_id_already_exists")

    site.site_id = new_id
    if payload.site_name.strip():
        site.site_name = payload.site_name.strip()
    db.query(SiteDailyPassword).where(SiteDailyPassword.site_id == old_id).update({SiteDailyPassword.site_id: new_id})
    db.query(RecruitmentBatchSite).where(RecruitmentBatchSite.site_id == old_id).update({RecruitmentBatchSite.site_id: new_id})
    db.query(RandomizationRecord).where(RandomizationRecord.site_id == old_id).update({RandomizationRecord.site_id: new_id})
    db.commit()
    add_audit(db, "site_id_renamed", {"old_site_id": old_id, "new_site_id": new_id})
    return {"ok": True, "site_id": new_id}


@app.delete("/admin/sites/{site_id}")
def delete_site(site_id: str, db: Session = Depends(get_db)):
    record_count = db.query(RandomizationRecord).where(RandomizationRecord.site_id == site_id).count()
    db.query(RecruitmentBatchSite).where(RecruitmentBatchSite.site_id == site_id).delete()
    db.query(SiteDailyPassword).where(SiteDailyPassword.site_id == site_id).delete()
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="site_not_found")
    db.delete(site)
    db.commit()
    add_audit(db, "site_deleted", {"site_id": site_id, "history_record_count": record_count})
    return {"ok": True}


@app.get("/admin/sites")
def list_sites(db: Session = Depends(get_db)):
    sites = db.scalars(select(Site).order_by(Site.site_id.asc())).all()
    return {
        "items": [
            {
                "site_id": s.site_id,
                "site_name": s.site_name,
                "assigned_recruitment_week": getattr(s, "assigned_recruitment_week", None),
                "enrollment_mode": _site_enrollment_mode(s),
            }
            for s in sites
        ]
    }


@app.get("/admin/site-recruitment-overview")
def site_recruitment_overview(at: datetime | None = None, db: Session = Depends(get_db)):
    """統計：預設站點容量、當前密碼視窗覆蓋的站點數、當前開放招募批次站點數等。"""
    max_parallel = RECRUITMENT_BATCH_MAX_ACTIVE_SITES
    ref = normalize_utc(at) if at else utc_now()
    sites = db.scalars(select(Site).order_by(Site.site_id.asc())).all()
    pwd_site_rows = db.scalars(
        select(SiteDailyPassword.site_id)
        .where(
            SiteDailyPassword.active.is_(True),
            SiteDailyPassword.window_start <= ref,
            SiteDailyPassword.window_end >= ref,
        )
        .distinct()
    ).all()
    pwd_site_ids = sorted(set(pwd_site_rows))
    batch = get_open_batch(db)
    batch_site_count = 0
    if batch is not None:
        batch_site_count = db.query(RecruitmentBatchSite).where(RecruitmentBatchSite.batch_id == batch.id).count()
    start_hk, end_hk = hk_today_password_window()
    return {
        "max_parallel_sites_recommended": max_parallel,
        "reference_time_utc": utc_iso(ref),
        "default_password_window_start": utc_iso(start_hk.astimezone(timezone.utc)),
        "default_password_window_end": utc_iso(end_hk.astimezone(timezone.utc)),
        "registered_site_count": len(sites),
        "sites_with_active_password_at_ref": len(pwd_site_ids),
        "sites_with_active_password_ids": pwd_site_ids,
        "current_open_batch_id": batch.id if batch else None,
        "current_open_batch_site_count": batch_site_count,
    }


@app.get("/admin/sites/table")
def sites_admin_table(db: Session = Depends(get_db)):
    """管理員表格：站點ID、名稱、密碼明文（若已儲存）、生效時段、是否在開放招募批次中等。"""
    sites = db.scalars(select(Site).order_by(Site.site_id.asc())).all()
    batch = get_open_batch(db)
    batch_site_ids: set[str] = set()
    if batch is not None:
        batch_site_ids = set(
            db.scalars(select(RecruitmentBatchSite.site_id).where(RecruitmentBatchSite.batch_id == batch.id)).all()
        )
    items = []
    for s in sites:
        pwd = _latest_site_password(db, s.site_id)
        items.append(
            {
                "site_id": s.site_id,
                "site_name": s.site_name,
                "assigned_recruitment_week": getattr(s, "assigned_recruitment_week", None),
                "enrollment_mode": _site_enrollment_mode(s),
                "password_plain": pwd.password_plain if pwd else None,
                "window_start": utc_iso(pwd.window_start) if pwd else None,
                "window_end": utc_iso(pwd.window_end) if pwd else None,
                "in_open_recruitment_batch": s.site_id in batch_site_ids,
            }
        )
    return {
        "current_open_batch": (
            {
                "id": batch.id,
                "label": batch.label,
                "created_by": batch.created_by,
                "created_at": utc_iso(batch.created_at),
                "site_ids": sorted(batch_site_ids),
            }
            if batch
            else None
        ),
        "items": items,
    }


@app.post("/admin/recruitment-batches/open")
def open_recruitment_batch(payload: RecruitmentBatchOpenRequest, db: Session = Depends(get_db)):
    if not payload.site_ids:
        raise HTTPException(status_code=400, detail="no_sites_selected")
    if len(payload.site_ids) > RECRUITMENT_BATCH_MAX_ACTIVE_SITES:
        raise HTTPException(status_code=400, detail="too_many_active_sites")
    if len(set(payload.site_ids)) != len(payload.site_ids):
        raise HTTPException(status_code=400, detail="duplicate_site_ids")
    for sid in payload.site_ids:
        if db.get(Site, sid) is None:
            raise HTTPException(status_code=400, detail=f"unknown_site:{sid}")
    now = utc_now()
    for b in db.scalars(select(RecruitmentBatch).where(RecruitmentBatch.closed_at.is_(None))).all():
        b.closed_at = now
    batch = RecruitmentBatch(label=payload.label, created_by=payload.created_by)
    db.add(batch)
    db.flush()
    for sid in payload.site_ids:
        db.add(RecruitmentBatchSite(batch_id=batch.id, site_id=sid))
    db.commit()
    add_audit(db, "recruitment_batch_opened", {"batch_id": batch.id, "site_ids": payload.site_ids})
    return {"ok": True, "batch_id": batch.id, "site_ids": payload.site_ids}


@app.post("/admin/recruitment-batches/close")
def close_recruitment_batches(db: Session = Depends(get_db)):
    now = utc_now()
    n = 0
    for b in db.scalars(select(RecruitmentBatch).where(RecruitmentBatch.closed_at.is_(None))).all():
        b.closed_at = now
        n += 1
    db.commit()
    add_audit(db, "recruitment_batches_closed", {"closed_count": n})
    return {"ok": True, "closed_count": n}


@app.get("/admin/recruitment-batches/current")
def recruitment_batch_current(db: Session = Depends(get_db)):
    batch = get_open_batch(db)
    if batch is None:
        return {"batch": None}
    site_ids = db.scalars(select(RecruitmentBatchSite.site_id).where(RecruitmentBatchSite.batch_id == batch.id)).all()
    return {
        "batch": {
            "id": batch.id,
            "label": batch.label,
            "created_by": batch.created_by,
            "created_at": utc_iso(batch.created_at),
            "site_ids": sorted(site_ids),
        }
    }


def _latest_site_password(db: Session, site_id: str) -> SiteDailyPassword | None:
    return db.scalar(
        select(SiteDailyPassword)
        .where(SiteDailyPassword.site_id == site_id)
        .order_by(SiteDailyPassword.id.desc())
        .limit(1)
    )


@app.post("/admin/site-passwords")
def configure_site_daily_password(payload: DailyPasswordConfigRequest, db: Session = Depends(get_db)):
    ws = normalize_utc(payload.window_start)
    we = normalize_utc(payload.window_end)
    if we <= ws:
        raise HTTPException(status_code=400, detail="invalid_password_window")
    try:
        assert_same_hk_calendar_day(ws, we)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="password_window_must_be_same_hk_calendar_day") from exc
    if db.get(Site, payload.site_id) is None:
        raise HTTPException(status_code=404, detail="site_not_found")

    pwd_raw = (payload.raw_password or "").strip() or None
    if pwd_raw is not None and (len(pwd_raw) < 6 or not pwd_raw.isdigit()):
        raise HTTPException(status_code=400, detail="invalid_password_format")

    latest = _latest_site_password(db, payload.site_id)
    if pwd_raw is None:
        if latest is None:
            raise HTTPException(status_code=400, detail="password_required_for_new_site")
        latest.window_start = ws
        latest.window_end = we
        latest.changed_by = payload.changed_by
        latest.reason = payload.reason or latest.reason
        db.commit()
        add_audit(
            db,
            "site_daily_password_window_updated",
            {
                "site_id": payload.site_id,
                "password_config_id": latest.id,
                "window_start": utc_iso(ws),
                "window_end": utc_iso(we),
            },
        )
        return {"ok": True, "updated": True, "password_config_id": latest.id, "version": latest.version}

    existing = db.scalars(
        select(SiteDailyPassword).where(
            SiteDailyPassword.site_id == payload.site_id,
            SiteDailyPassword.window_start == ws,
        )
    ).all()
    version = 1 if not existing else max(x.version for x in existing) + 1
    db.add(
        SiteDailyPassword(
            site_id=payload.site_id,
            window_start=ws,
            window_end=we,
            password_hash=hash_password(pwd_raw),
            password_plain=pwd_raw,
            changed_by=payload.changed_by,
            reason=payload.reason,
            version=version,
            active=True,
        )
    )
    db.commit()
    add_audit(
        db,
        "site_daily_password_configured",
        {"site_id": payload.site_id, "window_start": utc_iso(ws), "window_end": utc_iso(we)},
    )
    return {"ok": True, "updated": False, "version": version}


@app.post("/randomization/trigger")
def trigger_randomization(payload: RandomizationTriggerRequest, db: Session = Depends(get_db)):
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, max_enrollment=None, block_sizes_csv="4,8,12", updated_by="system")
        db.add(setting)
        db.commit()
        db.refresh(setting)
    at = normalize_utc(payload.at) if payload.at else utc_now()

    lock_key = (payload.site_id, payload.recruiter_id)
    window = app_state.failed_attempts.setdefault(lock_key, FailedAttemptWindow())
    if window.is_locked(utc_now()):
        add_audit(
            db,
            "randomization_blocked_locked",
            _randomization_trigger_audit_payload(payload, at),
        )
        raise HTTPException(status_code=429, detail="password_attempt_locked")

    if not site_in_open_batch(db, payload.site_id):
        add_audit(
            db,
            "randomization_blocked_site_not_in_batch",
            _randomization_trigger_audit_payload(payload, at),
        )
        raise HTTPException(status_code=403, detail="site_not_in_active_recruitment_batch")

    active_pwd = db.scalar(
        select(SiteDailyPassword)
        .where(
            SiteDailyPassword.site_id == payload.site_id,
            SiteDailyPassword.active.is_(True),
            SiteDailyPassword.window_start <= at,
            SiteDailyPassword.window_end >= at,
        )
        .order_by(SiteDailyPassword.version.desc())
    )
    if active_pwd is None:
        add_audit(
            db,
            "randomization_failed_no_password_config",
            _randomization_trigger_audit_payload(payload, at),
        )
        raise HTTPException(status_code=403, detail="password_not_configured")

    if active_pwd.password_hash != hash_password(payload.recruiter_password):
        window.register_failure(utc_now())
        add_audit(
            db,
            "randomization_failed_invalid_password",
            _randomization_trigger_audit_payload(payload, at),
        )
        if window.is_locked(utc_now()):
            raise HTTPException(status_code=429, detail="password_attempt_locked")
        raise HTTPException(status_code=403, detail="invalid_password")
    window.clear()

    existing = db.scalar(
        select(RandomizationRecord).where(
            RandomizationRecord.phone_number == payload.phone_number,
            _active_record_filter(),
        )
    )
    if existing:
        if existing.site_id != payload.site_id:
            add_audit(
                db,
                "randomization_failed_site_mismatch",
                _randomization_trigger_audit_payload(
                    payload,
                    at,
                    existing_enrollment_no=existing.enrollment_no,
                    existing_site_id=existing.site_id,
                ),
            )
            raise HTTPException(status_code=403, detail="site_mismatch")
        qr = db.scalar(select(QRConfig).where(QRConfig.group_type == existing.allocation_group))
        # 舊的干預組記錄若尚未填渠道，補預設 WhatsApp
        if (
            existing.allocation_group == "GENAI"
            and not (getattr(existing, "contact_channel", None) or "").strip()
        ):
            existing.contact_channel = "whatsapp"
            db.commit()
            db.refresh(existing)
        add_audit(
            db,
            "participant_randomized_idempotent",
            _randomization_trigger_audit_payload(
                payload,
                at,
                enrollment_no=existing.enrollment_no,
                allocation_group=existing.allocation_group,
                idempotent=True,
                contact_channel=getattr(existing, "contact_channel", None),
            ),
        )
        return {
            "enrollment_no": existing.enrollment_no,
            "phone_number": _display_phone(existing.phone_number, existing.enrollment_no),
            "site_id": existing.site_id,
            "site_name": existing.site_name,
            "allocation_group": existing.allocation_group,
            **_participant_qr_fields(qr, existing.allocation_group),
            "contact_channel": getattr(existing, "contact_channel", None),
            "randomized_at": utc_iso(existing.randomized_at),
            "idempotent": True,
        }

    site = db.get(Site, payload.site_id)
    site_name = site.site_name if site else payload.site_id
    site_week = getattr(site, "assigned_recruitment_week", None) if site is not None else None
    if site_week is not None and site_week < 1:
        site_week = None
    nontrial_site = _is_nontrial_recruitment_site(site)
    if nontrial_site:
        group = _next_nontrial_allocation_group(db, setting)
        trial_status = TRIAL_STATUS_NONTrial
    else:
        trial_total, trial_genai, trial_human = _trial_enrollment_counts(db)
        if _is_recruitment_closed(setting, trial_total, trial_genai, trial_human):
            add_audit(
                db,
                "randomization_blocked_recruitment_target_reached",
                _randomization_trigger_audit_payload(
                    payload,
                    at,
                    min_per_group=getattr(setting, "min_per_group", None),
                    trial_total=trial_total,
                    trial_genai=trial_genai,
                    trial_human=trial_human,
                ),
            )
            raise HTTPException(status_code=409, detail="recruitment_target_reached")
        group = _next_trial_allocation_group(db, setting)
        trial_status = TRIAL_STATUS_TRIAL
    record = RandomizationRecord(
        enrollment_no=next_enrollment_no(db),
        phone_number=payload.phone_number,
        recruiter_id=payload.recruiter_id,
        participant_name=_normalize_participant_name(payload.participant_name),
        whatsapp_number=payload.phone_number,
        site_id=payload.site_id,
        site_name=site_name,
        allocation_group=group,
        trial_status=trial_status,
        assigned_recruitment_week=site_week,
        # 干預組（GENAI）預設添加渠道為 WhatsApp；對照組仍由招募員在雙碼時選擇
        contact_channel="whatsapp" if group == "GENAI" else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    qr = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
    add_audit(
        db,
        "participant_randomized",
        _randomization_trigger_audit_payload(
            payload,
            at,
            enrollment_no=record.enrollment_no,
            allocation_group=group,
            idempotent=False,
            contact_channel=getattr(record, "contact_channel", None),
        ),
    )
    return {
        "enrollment_no": record.enrollment_no,
        "phone_number": record.phone_number,
        "site_id": record.site_id,
        "site_name": record.site_name,
        "allocation_group": group,
        **_participant_qr_fields(qr, group),
        "contact_channel": getattr(record, "contact_channel", None),
        "randomized_at": utc_iso(record.randomized_at),
        "idempotent": False,
    }


@app.post("/randomization/contact-channel")
def set_contact_channel(payload: ContactChannelUpdateRequest, db: Session = Depends(get_db)):
    """入組後由招募員選擇參加者實際添加的渠道（WhatsApp / 微信）。"""
    if payload.contact_channel not in {"whatsapp", "wechat"}:
        raise HTTPException(status_code=400, detail="invalid_contact_channel")
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    if record.activation_status == "voided":
        raise HTTPException(status_code=400, detail="record_voided")
    snapshot = _record_audit_snapshot(record)
    old_channel = getattr(record, "contact_channel", None)
    record.contact_channel = payload.contact_channel
    db.commit()
    add_audit(
        db,
        "contact_channel_selected",
        {
            **snapshot,
            "old_contact_channel": old_channel,
            "new_contact_channel": payload.contact_channel,
            "contact_channel": payload.contact_channel,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {
        "ok": True,
        "enrollment_no": record.enrollment_no,
        "contact_channel": record.contact_channel,
    }


@app.post("/admin/qr-config")
def update_qr_config(payload: QRUpdateRequest, db: Session = Depends(get_db)):
    if payload.group not in QR_GROUP_TYPES:
        raise HTTPException(status_code=400, detail="invalid_group")
    if payload.qr_mode not in QR_MODES:
        raise HTTPException(status_code=400, detail="invalid_qr_mode")
    qr_value = (payload.qr_value or "").strip()
    targets_json: str | None = None
    daily_cap_to_set: int | None = None
    max_consecutive_to_set: int | None = None
    if payload.qr_mode == "dynamic":
        daily_cap_to_set = None
        if payload.target_daily_cap is not None:
            daily_cap_to_set = _normalize_target_daily_cap(payload.target_daily_cap, required=True)
        if payload.target_max_consecutive is not None:
            max_consecutive_to_set = _normalize_target_max_consecutive(
                payload.target_max_consecutive, required=True
            )
        # 單條未帶 daily_cap 時的回退：組級傳入值 → 預設 10
        default_cap = (
            int(daily_cap_to_set)
            if daily_cap_to_set is not None
            else DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT
        )
        raw_items: list[object] = []
        if payload.qr_target_items:
            if len(payload.qr_target_items) > DYNAMIC_QR_TARGET_MAX:
                raise HTTPException(status_code=400, detail="dynamic_qr_targets_max_5")
            for it in payload.qr_target_items:
                if it.daily_cap is not None:
                    _normalize_target_daily_cap(it.daily_cap, required=True)
                raw_items.append({"url": it.url, "daily_cap": it.daily_cap})
        elif payload.qr_targets is not None:
            if len(payload.qr_targets) > DYNAMIC_QR_TARGET_MAX:
                raise HTTPException(status_code=400, detail="dynamic_qr_targets_max_5")
            raw_items.extend(payload.qr_targets)
        entries = _normalize_dynamic_target_entries(raw_items, qr_value, int(default_cap))
        if not entries:
            raise HTTPException(status_code=400, detail="dynamic_qr_target_required")
        for entry in entries:
            _validate_dynamic_target_url(str(entry["url"]))
        qr_value = str(entries[0]["url"])
        targets_json = json.dumps(entries, ensure_ascii=False)
    if payload.qr_mode == "static_url" and not qr_value:
        raise HTTPException(status_code=400, detail="static_url_required")
    if payload.qr_mode == "static_image" and not qr_value:
        raise HTTPException(status_code=400, detail="static_image_path_required")
    cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == payload.group))
    if cfg is None:
        cfg = QRConfig(
            group_type=payload.group,
            qr_mode=payload.qr_mode,
            qr_value=qr_value,
            qr_targets_json=targets_json,
            target_daily_cap=(
                daily_cap_to_set
                if daily_cap_to_set is not None
                else DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT
            ),
            target_max_consecutive=(
                max_consecutive_to_set
                if max_consecutive_to_set is not None
                else DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT
            ),
            changed_by=payload.changed_by,
            reason=payload.reason,
        )
        db.add(cfg)
    else:
        cfg.version += 1
        cfg.qr_mode = payload.qr_mode
        cfg.qr_value = qr_value
        cfg.qr_targets_json = targets_json
        if daily_cap_to_set is not None:
            cfg.target_daily_cap = daily_cap_to_set
        elif payload.qr_mode == "dynamic" and not getattr(cfg, "target_daily_cap", None):
            cfg.target_daily_cap = DYNAMIC_QR_TARGET_DAILY_MAX_DEFAULT
        if max_consecutive_to_set is not None:
            cfg.target_max_consecutive = max_consecutive_to_set
        elif payload.qr_mode == "dynamic" and not getattr(cfg, "target_max_consecutive", None):
            cfg.target_max_consecutive = DYNAMIC_QR_TARGET_MAX_CONSECUTIVE_DEFAULT
        cfg.changed_by = payload.changed_by
        cfg.reason = payload.reason
    db.commit()
    db.refresh(cfg)
    add_audit(
        db,
        "qr_config_updated",
        {
            "group": payload.group,
            "version": cfg.version,
            "qr_mode": cfg.qr_mode,
            "qr_targets_count": len(_targets_from_config(cfg)) if payload.qr_mode == "dynamic" else 0,
            "target_daily_cap": _daily_cap_from_config(cfg) if payload.qr_mode == "dynamic" else None,
            "target_max_consecutive": (
                _max_consecutive_from_config(cfg) if payload.qr_mode == "dynamic" else None
            ),
        },
    )
    result = {"ok": True, "group": payload.group, "version": cfg.version, "qr_mode": cfg.qr_mode}
    if payload.qr_mode == "dynamic":
        entries = _target_entries_from_config(cfg)
        result["stable_qr_path"] = _stable_qr_path(payload.group)
        result["qr_targets"] = [str(e["url"]) for e in entries]
        result["qr_target_items"] = entries
        result["target_daily_cap"] = _daily_cap_from_config(cfg)
        result["qr_target_daily_cap"] = result["target_daily_cap"]
        result["target_max_consecutive"] = _max_consecutive_from_config(cfg)
        result["qr_target_max_consecutive"] = result["target_max_consecutive"]
    return result


@app.get("/admin/qr-configs")
def get_qr_configs(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(QRConfig).order_by(QRConfig.group_type.asc())).all()
    return {"items": [_serialize_qr_config(i, request, db) for i in items]}


@app.get("/admin/group-labels")
def get_group_labels(db: Session = Depends(get_db)):
    result = {"GENAI": "干預組", "HUMAN": "對照組"}
    items = db.scalars(select(GroupLabel).where(GroupLabel.group_type.in_(["GENAI", "HUMAN"]))).all()
    for it in items:
        if it.display_name:
            result[it.group_type] = it.display_name
    return {"intervention_name": result["GENAI"], "control_name": result["HUMAN"]}


@app.put("/admin/group-labels")
def update_group_labels(payload: GroupLabelUpdateRequest, db: Session = Depends(get_db)):
    updates = {"GENAI": payload.intervention_name.strip(), "HUMAN": payload.control_name.strip()}
    for group, name in updates.items():
        rec = db.get(GroupLabel, group)
        if rec is None:
            rec = GroupLabel(group_type=group, display_name=name, changed_by=payload.changed_by, reason=payload.reason)
            db.add(rec)
        else:
            rec.display_name = name
            rec.changed_by = payload.changed_by
            rec.reason = payload.reason
    db.commit()
    add_audit(db, "group_labels_updated", updates | {"changed_by": payload.changed_by})
    return {"ok": True, "intervention_name": updates["GENAI"], "control_name": updates["HUMAN"]}


if _HAS_MULTIPART:

    @app.post("/admin/qr-config/upload")
    async def upload_qr_config(
        group: str = Form(...),
        changed_by: str = Form(...),
        reason: str = Form(""),
        file: UploadFile = File(...),
        confirm_replace_dynamic: str = Form("0"),
        db: Session = Depends(get_db),
    ):
        if group not in QR_GROUP_TYPES:
            raise HTTPException(status_code=400, detail="invalid_group")
        # 已是動態 WhatsApp 時，主上傳會覆蓋跳轉連結；需明確確認，否則請改走微信上傳
        cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
        replace_ok = str(confirm_replace_dynamic or "").strip().lower() in {"1", "true", "yes", "on"}
        if (
            cfg is not None
            and _infer_qr_mode(cfg.qr_value, cfg.qr_mode) == "dynamic"
            and not replace_ok
        ):
            raise HTTPException(
                status_code=400,
                detail="dynamic_mode_use_wechat_upload",
            )
        ext = Path(file.filename or "").suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=400, detail="invalid_file_type")
        saved_name = f"{group.lower()}_{secrets.token_hex(8)}{ext}"
        saved_path = UPLOAD_DIR / saved_name
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="empty_file")
        with open(saved_path, "wb") as f:
            f.write(content)
        qr_value = f"/uploads/qr/{saved_name}"
        if cfg is None:
            cfg = QRConfig(
                group_type=group,
                qr_mode="static_image",
                qr_value=qr_value,
                qr_targets_json=None,
                changed_by=changed_by,
                reason=reason,
            )
            db.add(cfg)
        else:
            cfg.version += 1
            cfg.qr_mode = "static_image"
            cfg.qr_value = qr_value
            cfg.qr_targets_json = None
            cfg.changed_by = changed_by
            cfg.reason = reason
        db.commit()
        add_audit(db, "qr_config_image_uploaded", {"group": group, "version": cfg.version, "path": qr_value})
        return {"ok": True, "group": group, "version": cfg.version, "qr_value": qr_value}

    @app.post("/admin/qr-config/wechat")
    async def upload_wechat_qr(
        group: str = Form(...),
        changed_by: str = Form(...),
        reason: str = Form("wechat qr upload"),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
    ):
        """上傳微信二維碼圖片（建議用於對照組，與 WhatsApp 動態碼並排展示）。"""
        if group not in QR_GROUP_TYPES:
            raise HTTPException(status_code=400, detail="invalid_group")
        ext = Path(file.filename or "").suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=400, detail="invalid_file_type")
        saved_name = f"{group.lower()}_wechat_{secrets.token_hex(8)}{ext}"
        saved_path = UPLOAD_DIR / saved_name
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="empty_file")
        with open(saved_path, "wb") as f:
            f.write(content)
        wechat_path = f"/uploads/qr/{saved_name}"
        cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
        if cfg is None:
            raise HTTPException(status_code=400, detail="configure_whatsapp_qr_first")
        # 僅寫入微信圖，絕不改動 WhatsApp/主碼的 qr_mode、qr_value
        kept_mode = cfg.qr_mode
        kept_value = cfg.qr_value
        cfg.wechat_qr_path = wechat_path
        cfg.changed_by = changed_by
        cfg.reason = reason
        cfg.version += 1
        db.commit()
        add_audit(db, "wechat_qr_uploaded", {"group": group, "path": wechat_path})
        return {
            "ok": True,
            "group": group,
            "wechat_qr_path": wechat_path,
            "qr_mode": kept_mode,
            "qr_value": kept_value,
            "version": cfg.version,
        }

    @app.delete("/admin/qr-config/wechat")
    def delete_wechat_qr(group: str = Query(...), db: Session = Depends(get_db)):
        if group not in QR_GROUP_TYPES:
            raise HTTPException(status_code=400, detail="invalid_group")
        cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
        if cfg is None or not getattr(cfg, "wechat_qr_path", None):
            raise HTTPException(status_code=404, detail="wechat_qr_not_configured")
        cfg.wechat_qr_path = None
        cfg.version += 1
        db.commit()
        add_audit(db, "wechat_qr_removed", {"group": group})
        return {"ok": True, "group": group}

    @app.post("/admin/qr-config/logo")
    async def upload_qr_logo(
        group: str = Form(...),
        changed_by: str = Form(...),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
    ):
        if group not in QR_GROUP_TYPES:
            raise HTTPException(status_code=400, detail="invalid_group")
        ext = Path(file.filename or "").suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=400, detail="invalid_file_type")
        saved_name = f"{group.lower()}_logo_{secrets.token_hex(8)}{ext}"
        saved_path = UPLOAD_DIR / saved_name
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="empty_file")
        with open(saved_path, "wb") as f:
            f.write(content)
        logo_path = f"/uploads/qr/{saved_name}"
        cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
        if cfg is None:
            cfg = QRConfig(
                group_type=group,
                qr_mode="dynamic",
                qr_value="",
                qr_logo_path=logo_path,
                changed_by=changed_by,
                reason="logo upload",
            )
            db.add(cfg)
        else:
            cfg.qr_logo_path = logo_path
            cfg.changed_by = changed_by
        db.commit()
        add_audit(db, "qr_logo_uploaded", {"group": group, "path": logo_path})
        return {"ok": True, "group": group, "qr_logo_path": logo_path}

    @app.delete("/admin/qr-config/logo")
    def delete_qr_logo(group: str = Query(...), db: Session = Depends(get_db)):
        if group not in QR_GROUP_TYPES:
            raise HTTPException(status_code=400, detail="invalid_group")
        cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
        if cfg is None or not cfg.qr_logo_path:
            raise HTTPException(status_code=404, detail="logo_not_configured")
        cfg.qr_logo_path = None
        db.commit()
        add_audit(db, "qr_logo_removed", {"group": group})
        return {"ok": True, "group": group}
else:

    @app.post("/admin/qr-config/upload")
    async def upload_qr_config_unavailable():
        raise HTTPException(status_code=503, detail="multipart_not_installed")


@app.get("/admin/audit-logs")
def get_audit_logs(db: Session = Depends(get_db)):
    items = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()
    return {
        "items": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "payload_json": item.payload_json,
                "request_id": item.request_id,
                "created_at": utc_iso(item.created_at),
            }
            for item in items
        ]
    }


@app.get("/admin/password-configs")
def get_password_configs(db: Session = Depends(get_db)):
    items = db.scalars(select(SiteDailyPassword).order_by(SiteDailyPassword.id.desc())).all()
    return {
        "items": [
            {
                "site_id": c.site_id,
                "window_start": utc_iso(c.window_start),
                "window_end": utc_iso(c.window_end),
                "active": c.active,
                "version": c.version,
                "changed_by": c.changed_by,
            }
            for c in items
        ]
    }


@app.get("/admin/randomization-records")
def get_randomization_records(db: Session = Depends(get_db)):
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, min_per_group=499, block_sizes_csv="4,8,12", updated_by="system")
        db.add(setting)
        db.commit()
        db.refresh(setting)
    records = db.scalars(select(RandomizationRecord).order_by(RandomizationRecord.id.desc())).all()
    site_week_map = {
        s.site_id: getattr(s, "assigned_recruitment_week", None)
        for s in db.scalars(select(Site)).all()
    }
    start_date = _recruitment_start_date(setting)
    overview = _recruitment_overview(setting, db)
    return {
        "overview": overview,
        "items": [
            {
                "enrollment_no": r.enrollment_no,
                "phone_number": _display_phone(r.phone_number, r.enrollment_no),
                "recruiter_id": r.recruiter_id,
                "participant_name": getattr(r, "participant_name", None),
                "whatsapp_number": _display_whatsapp_number(r),
                "site_id": r.site_id,
                "site_name": r.site_name,
                "allocation_group": r.allocation_group,
                "randomized_at": utc_iso(r.randomized_at),
                "activation_status": r.activation_status,
                "trial_status": getattr(r, "trial_status", TRIAL_STATUS_TRIAL) or TRIAL_STATUS_TRIAL,
                "subject_code": r.subject_code,
                "assigned_recruitment_week": getattr(r, "assigned_recruitment_week", None),
                "site_assigned_recruitment_week": site_week_map.get(r.site_id),
                "effective_recruitment_week": _record_effective_recruitment_week(r, start_date, site_week_map),
                "account_added": bool(getattr(r, "account_added", False)),
                "contact_channel": getattr(r, "contact_channel", None),
            }
            for r in records
        ],
    }


@app.get("/admin/randomization-records.csv")
def export_randomization_records_csv(db: Session = Depends(get_db)):
    records = db.scalars(select(RandomizationRecord).order_by(RandomizationRecord.id.desc())).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "enrollment_no",
            "phone_number",
            "site_id",
            "recruiter_id",
            "participant_name",
            "whatsapp_number",
            "site_name",
            "allocation_group",
            "randomized_at (HKT)",
            "trial_status",
            "activation_status",
            "subject_code",
            "assigned_recruitment_week",
            "effective_recruitment_week",
            "account_added",
            "contact_channel",
        ]
    )
    setting = db.get(RandomizationSetting, 1)
    start_date = _recruitment_start_date(setting) if setting is not None else DEFAULT_RECRUITMENT_START_DATE
    site_week_map = {
        s.site_id: getattr(s, "assigned_recruitment_week", None)
        for s in db.scalars(select(Site)).all()
    }
    for r in records:
        writer.writerow(
            [
                r.enrollment_no,
                _display_phone(r.phone_number, r.enrollment_no),
                r.site_id,
                r.recruiter_id,
                getattr(r, "participant_name", None) or "",
                _display_whatsapp_number(r),
                r.site_name,
                r.allocation_group,
                format_hk_datetime(r.randomized_at),
                getattr(r, "trial_status", TRIAL_STATUS_TRIAL) or TRIAL_STATUS_TRIAL,
                r.activation_status,
                r.subject_code or "",
                getattr(r, "assigned_recruitment_week", None) or "",
                _record_effective_recruitment_week(r, start_date, site_week_map) or "",
                "yes" if bool(getattr(r, "account_added", False)) else "no",
                getattr(r, "contact_channel", None) or "",
            ]
        )
    csv_text = buf.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=randomization_records_{hk_datetime_stamp()}.csv"},
    )


@app.get("/admin/randomization-settings")
def get_randomization_settings(db: Session = Depends(get_db)):
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, max_enrollment=None, block_sizes_csv="4,8,12", updated_by="system")
        db.add(setting)
        db.commit()
        db.refresh(setting)
    end_date = _recruitment_end_date(setting)
    out = {
        "max_enrollment": setting.max_enrollment,
        "min_per_group": getattr(setting, "min_per_group", None),
        "recruitment_start_date": _recruitment_start_date(setting).isoformat(),
        "recruitment_end_date": end_date.isoformat() if end_date is not None else None,
        "weekly_plan_weeks": _weekly_plan_weeks(setting),
        "weekly_plan_per_week": _weekly_plan_per_week(setting),
        "block_sizes": list(parse_block_sizes(setting.block_sizes_csv)),
        "h5_show_allocation_group": bool(getattr(setting, "h5_show_allocation_group", True)),
        "updated_by": setting.updated_by,
        "updated_at": utc_iso(setting.updated_at),
    }
    return out


@app.get("/participant-ui/config")
def get_participant_ui_config(db: Session = Depends(get_db)):
    """供受試者 H5 頁讀取展示選項（無敏感欄位）。"""
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        return {"show_allocation_group": True}
    return {"show_allocation_group": bool(getattr(setting, "h5_show_allocation_group", True))}


@app.get("/participant/active-sites")
def participant_active_sites(db: Session = Depends(get_db)):
    """當前開放招募批次內的站點（僅 ID/名稱）。無需管理員登入，供手機等設備單獨打開 /h5/randomize 時載入下拉框。"""
    batch = get_open_batch(db)
    if batch is None:
        return {"items": []}
    site_ids = db.scalars(
        select(RecruitmentBatchSite.site_id).where(RecruitmentBatchSite.batch_id == batch.id)
    ).all()
    if not site_ids:
        return {"items": []}
    sites = db.scalars(select(Site).where(Site.site_id.in_(site_ids)).order_by(Site.site_id.asc())).all()
    return {"items": [{"site_id": s.site_id, "site_name": s.site_name} for s in sites]}


@app.put("/admin/participant-page-settings")
def update_participant_page_settings(payload: ParticipantPageSettingsRequest, db: Session = Depends(get_db)):
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, max_enrollment=None, block_sizes_csv="4,8,12", updated_by="system")
        db.add(setting)
    setting.h5_show_allocation_group = payload.show_allocation_group
    db.commit()
    db.refresh(setting)
    add_audit(
        db,
        "participant_page_settings_updated",
        {"show_allocation_group": setting.h5_show_allocation_group},
    )
    return {"ok": True, "show_allocation_group": setting.h5_show_allocation_group}


@app.put("/admin/randomization-settings")
def update_randomization_settings(payload: RandomizationSettingUpdateRequest, db: Session = Depends(get_db)):
    if not payload.block_sizes or any(v <= 0 or v % 2 != 0 for v in payload.block_sizes):
        raise HTTPException(status_code=400, detail="invalid_block_sizes")
    if payload.max_enrollment is not None and payload.max_enrollment <= 0:
        raise HTTPException(status_code=400, detail="invalid_max_enrollment")
    if payload.min_per_group is not None and payload.min_per_group <= 0:
        raise HTTPException(status_code=400, detail="invalid_min_per_group")
    if payload.weekly_plan_weeks is not None and payload.weekly_plan_weeks <= 0:
        raise HTTPException(status_code=400, detail="invalid_weekly_plan_weeks")
    if payload.weekly_plan_per_week is not None and payload.weekly_plan_per_week <= 0:
        raise HTTPException(status_code=400, detail="invalid_weekly_plan_per_week")

    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, updated_by=payload.updated_by)
        db.add(setting)
    if "max_enrollment" in payload.model_fields_set:
        setting.max_enrollment = payload.max_enrollment
    if "min_per_group" in payload.model_fields_set:
        setting.min_per_group = payload.min_per_group
    if "recruitment_start_date" in payload.model_fields_set:
        setting.recruitment_start_date = payload.recruitment_start_date
    if "recruitment_end_date" in payload.model_fields_set:
        setting.recruitment_end_date = payload.recruitment_end_date
    if "weekly_plan_weeks" in payload.model_fields_set:
        setting.weekly_plan_weeks = payload.weekly_plan_weeks
    if "weekly_plan_per_week" in payload.model_fields_set:
        setting.weekly_plan_per_week = payload.weekly_plan_per_week
    end_candidate = _recruitment_end_date(setting)
    if end_candidate is not None and end_candidate < _recruitment_start_date(setting):
        raise HTTPException(status_code=400, detail="invalid_recruitment_end_date")
    dates_updated = (
        "recruitment_start_date" in payload.model_fields_set
        or "recruitment_end_date" in payload.model_fields_set
    )
    if dates_updated and end_candidate is not None:
        synced_weeks = recruitment_plan_weeks_from_end_date(_recruitment_start_date(setting), end_candidate)
        if synced_weeks is not None and synced_weeks > 0:
            setting.weekly_plan_weeks = synced_weeks
    setting.block_sizes_csv = ",".join(str(x) for x in payload.block_sizes)
    setting.updated_by = payload.updated_by
    db.commit()
    db.refresh(setting)
    end_date = _recruitment_end_date(setting)
    add_audit(
        db,
        "randomization_settings_updated",
        {
            "max_enrollment": setting.max_enrollment,
            "min_per_group": getattr(setting, "min_per_group", None),
            "recruitment_start_date": _recruitment_start_date(setting).isoformat(),
            "recruitment_end_date": end_date.isoformat() if end_date is not None else None,
            "weekly_plan_weeks": _weekly_plan_weeks(setting),
            "weekly_plan_per_week": _weekly_plan_per_week(setting),
            "block_sizes": payload.block_sizes,
            "updated_by": payload.updated_by,
        },
    )
    return {
        "ok": True,
        "max_enrollment": setting.max_enrollment,
        "min_per_group": getattr(setting, "min_per_group", None),
        "recruitment_start_date": _recruitment_start_date(setting).isoformat(),
        "recruitment_end_date": end_date.isoformat() if end_date is not None else None,
        "weekly_plan_weeks": _weekly_plan_weeks(setting),
        "weekly_plan_per_week": _weekly_plan_per_week(setting),
        "block_sizes": payload.block_sizes,
    }


@app.patch("/admin/randomization-records/phone")
def admin_correct_phone(payload: PhoneCorrectionRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    duplicate = db.scalar(
        select(RandomizationRecord).where(
            RandomizationRecord.phone_number == payload.new_phone_number,
            _active_record_filter(),
        )
    )
    if duplicate and duplicate.enrollment_no != payload.enrollment_no:
        raise HTTPException(status_code=409, detail="phone_already_exists")
    snapshot = _record_audit_snapshot(record)
    old_phone = snapshot["phone_number"]
    record.phone_number = payload.new_phone_number
    db.commit()
    add_audit(
        db,
        "admin_phone_corrected",
        {
            **snapshot,
            "old_phone_number": old_phone,
            "new_phone_number": payload.new_phone_number,
            "phone_number": payload.new_phone_number,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "phone_number": record.phone_number}


@app.patch("/admin/randomization-records/subject-code")
def admin_update_subject_code(payload: SubjectCodeUpdateRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    new_code = _normalize_subject_code(payload.subject_code)
    if new_code:
        duplicate = db.scalar(
            select(RandomizationRecord).where(
                RandomizationRecord.subject_code == new_code,
                RandomizationRecord.enrollment_no != payload.enrollment_no,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="subject_code_already_exists")
    snapshot = _record_audit_snapshot(record)
    old_code = record.subject_code
    record.subject_code = new_code
    db.commit()
    add_audit(
        db,
        "admin_subject_code_updated",
        {
            **snapshot,
            "old_subject_code": old_code,
            "new_subject_code": new_code,
            "subject_code": new_code,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "subject_code": record.subject_code}


@app.patch("/admin/randomization-records/participant-name")
def admin_update_participant_name(payload: ParticipantNameUpdateRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    new_name = _normalize_participant_name(payload.participant_name)
    snapshot = _record_audit_snapshot(record)
    old_name = getattr(record, "participant_name", None)
    record.participant_name = new_name
    db.commit()
    add_audit(
        db,
        "admin_participant_name_updated",
        {
            **snapshot,
            "old_participant_name": old_name,
            "new_participant_name": new_name,
            "participant_name": new_name,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "participant_name": record.participant_name}


@app.patch("/admin/randomization-records/whatsapp")
def admin_update_whatsapp_number(payload: WhatsappNumberUpdateRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    new_number = _normalize_whatsapp_number(payload.whatsapp_number)
    if len(new_number) < 6:
        raise HTTPException(status_code=400, detail="invalid_whatsapp_number")
    snapshot = _record_audit_snapshot(record)
    old_number = snapshot["whatsapp_number"]
    record.whatsapp_number = new_number
    db.commit()
    add_audit(
        db,
        "admin_whatsapp_number_updated",
        {
            **snapshot,
            "old_whatsapp_number": old_number,
            "new_whatsapp_number": new_number,
            "whatsapp_number": new_number,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {
        "ok": True,
        "enrollment_no": record.enrollment_no,
        "whatsapp_number": _display_whatsapp_number(record),
    }


@app.patch("/admin/randomization-records/account-added")
def admin_update_account_added(payload: AccountAddedUpdateRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    snapshot = _record_audit_snapshot(record)
    old_value = bool(getattr(record, "account_added", False))
    record.account_added = bool(payload.account_added)
    db.commit()
    add_audit(
        db,
        "admin_account_added_updated",
        {
            **snapshot,
            "old_account_added": old_value,
            "new_account_added": record.account_added,
            "account_added": record.account_added,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "account_added": record.account_added}


@app.patch("/admin/randomization-records/contact-channel")
def admin_update_contact_channel(payload: ContactChannelUpdateRequest, db: Session = Depends(get_db)):
    if payload.contact_channel not in {"whatsapp", "wechat"}:
        raise HTTPException(status_code=400, detail="invalid_contact_channel")
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    snapshot = _record_audit_snapshot(record)
    old_channel = getattr(record, "contact_channel", None)
    record.contact_channel = payload.contact_channel
    db.commit()
    add_audit(
        db,
        "admin_contact_channel_updated",
        {
            **snapshot,
            "old_contact_channel": old_channel,
            "new_contact_channel": payload.contact_channel,
            "contact_channel": payload.contact_channel,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "contact_channel": record.contact_channel}


@app.patch("/admin/randomization-records/assigned-week")
def admin_update_record_assigned_week(payload: RecordAssignedWeekRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    if payload.assigned_recruitment_week is not None and payload.assigned_recruitment_week < 1:
        raise HTTPException(status_code=400, detail="invalid_assigned_recruitment_week")
    snapshot = _record_audit_snapshot(record)
    old_week = getattr(record, "assigned_recruitment_week", None)
    record.assigned_recruitment_week = payload.assigned_recruitment_week
    db.commit()
    add_audit(
        db,
        "admin_record_assigned_week_updated",
        {
            **snapshot,
            "old_assigned_recruitment_week": old_week,
            "new_assigned_recruitment_week": payload.assigned_recruitment_week,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {
        "ok": True,
        "enrollment_no": record.enrollment_no,
        "assigned_recruitment_week": record.assigned_recruitment_week,
    }


@app.patch("/admin/randomization-records/trial-status")
def admin_update_trial_status(payload: TrialStatusUpdateRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    if record.activation_status == "voided":
        raise HTTPException(status_code=400, detail="voided_record_cannot_change_trial_status")
    if payload.trial_status not in {TRIAL_STATUS_TRIAL, TRIAL_STATUS_NONTrial}:
        raise HTTPException(status_code=400, detail="invalid_trial_status")
    if payload.trial_status == TRIAL_STATUS_TRIAL and record.trial_status != TRIAL_STATUS_TRIAL:
        setting = db.get(RandomizationSetting, 1)
        if setting is not None:
            trial_total, trial_genai, trial_human = _trial_enrollment_counts(db)
            if _is_recruitment_closed(setting, trial_total, trial_genai, trial_human):
                raise HTTPException(status_code=409, detail="recruitment_target_reached")
    snapshot = _record_audit_snapshot(record)
    old_status = record.trial_status
    record.trial_status = payload.trial_status
    db.commit()
    add_audit(
        db,
        "admin_trial_status_updated",
        {
            **snapshot,
            "old_trial_status": old_status,
            "new_trial_status": payload.trial_status,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "trial_status": record.trial_status}


@app.patch("/admin/randomization-records/allocation-group")
def admin_update_allocation_group(payload: AllocationGroupUpdateRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    if record.activation_status == "voided":
        raise HTTPException(status_code=400, detail="voided_record_cannot_change_allocation_group")
    if getattr(record, "trial_status", TRIAL_STATUS_TRIAL) != TRIAL_STATUS_NONTrial:
        raise HTTPException(status_code=400, detail="only_nontrial_allocation_group_editable")
    if payload.allocation_group not in QR_GROUP_TYPES:
        raise HTTPException(status_code=400, detail="invalid_allocation_group")
    snapshot = _record_audit_snapshot(record)
    old_group = record.allocation_group
    if old_group == payload.allocation_group:
        return {"ok": True, "enrollment_no": record.enrollment_no, "allocation_group": record.allocation_group}
    record.allocation_group = payload.allocation_group
    db.commit()
    add_audit(
        db,
        "admin_allocation_group_updated",
        {
            **snapshot,
            "old_allocation_group": old_group,
            "new_allocation_group": payload.allocation_group,
            "allocation_group": payload.allocation_group,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "allocation_group": record.allocation_group}


@app.post("/admin/randomization-records/delete")
def admin_delete_record(payload: RecordVoidRequest, db: Session = Depends(get_db)):
    """
    Backward-compatible endpoint:
    keep route name 'delete', but perform soft-void to preserve randomization history.
    """
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    now = utc_now()
    is_voided = record.activation_status == "voided"
    if is_voided:
        snapshot = _record_audit_snapshot(record)
        original_phone = _display_phone(record.phone_number, record.enrollment_no)
        duplicate = db.scalar(
            select(RandomizationRecord).where(
                RandomizationRecord.phone_number == original_phone,
                _active_record_filter(),
            )
        )
        if duplicate and duplicate.enrollment_no != record.enrollment_no:
            raise HTTPException(status_code=409, detail="phone_already_exists")
        if record.trial_status == TRIAL_STATUS_TRIAL:
            setting = db.get(RandomizationSetting, 1)
            if setting is not None:
                trial_total, trial_genai, trial_human = _trial_enrollment_counts(db)
                if _is_recruitment_closed(setting, trial_total, trial_genai, trial_human):
                    raise HTTPException(status_code=409, detail="recruitment_target_reached")
        record.activation_status = "pending"
        record.phone_number = original_phone
        record.activation_timestamp = now
        db.commit()
        restored = _record_audit_snapshot(record)
        add_audit(
            db,
            "admin_record_restored",
            {
                **restored,
                "old_activation_status": snapshot["activation_status"],
                "new_activation_status": record.activation_status,
                "old_phone_number": original_phone,
                "new_phone_number": restored["phone_number"],
                "changed_by": payload.voided_by,
                "reason": payload.reason,
            },
        )
        return {"ok": True, "restored_enrollment_no": payload.enrollment_no, "activation_status": record.activation_status}

    snapshot = _record_audit_snapshot(record)
    original_phone = _display_phone(record.phone_number, record.enrollment_no)
    record.activation_status = "voided"
    record.phone_number = _void_phone_storage(record.enrollment_no, original_phone)
    record.activation_timestamp = now
    db.commit()
    add_audit(
        db,
        "admin_record_voided",
        {
            **snapshot,
            "phone_number": original_phone,
            "old_activation_status": snapshot["activation_status"],
            "new_activation_status": "voided",
            "changed_by": payload.voided_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "voided_enrollment_no": payload.enrollment_no, "activation_status": record.activation_status}


@app.post("/admin/dev/reset")
def dev_reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add(
            QRConfig(
                group_type="GENAI",
                qr_mode="static_url",
                qr_value="https://wa.me/genai_default",
                version=1,
                changed_by="system",
                reason="reset",
            )
        )
        db.add(
            QRConfig(
                group_type="HUMAN",
                qr_mode="static_url",
                qr_value="https://wa.me/human_default",
                version=1,
                changed_by="system",
                reason="reset",
            )
        )
        db.add(EnrollmentCounter(id=1, seq=0))
        db.add(
            RandomizationSetting(
                id=1,
                min_per_group=499,
                recruitment_start_date=DEFAULT_RECRUITMENT_START_DATE,
                recruitment_end_date=recruitment_plan_end_date(
                    DEFAULT_RECRUITMENT_START_DATE, DEFAULT_WEEKLY_PLAN_WEEKS
                ),
                weekly_plan_weeks=DEFAULT_WEEKLY_PLAN_WEEKS,
                weekly_plan_per_week=DEFAULT_WEEKLY_PLAN_PER_WEEK,
                block_sizes_csv="4,8,12",
                randomization_seed=DEFAULT_RANDOMIZATION_SEED,
                updated_by="system",
            )
        )
        ensure_preset_sites(db)
        db.commit()
    app_state.failed_attempts = {}
    return {"ok": True}
