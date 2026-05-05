from __future__ import annotations

import csv
import base64
from datetime import date, datetime, timezone
from collections.abc import Generator
import io
import json
import os
from pathlib import Path
import secrets
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    PRESET_SITE_COUNT,
    RECRUITMENT_BATCH_MAX_ACTIVE_SITES,
    AuditLog,
    EnrollmentCounter,
    GroupLabel,
    QRConfig,
    RandomizationRecord,
    RandomizationSetting,
    RecruitmentBatch,
    RecruitmentBatchSite,
    Site,
    SiteDailyPassword,
)
from app.admin_ui import PageId, render_admin_page

from app.seed import ensure_preset_sites
from app.state import FailedAttemptWindow, app_state, hash_password, utc_now
from app.timeutil import assert_same_hk_calendar_day

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
        <h2>管理端登录</h2>
        {error_html}
        <input type="hidden" name="next" value="{next_path}" />
        <label>用户名</label>
        <input name="username" autocomplete="username" required />
        <label>密码</label>
        <input name="password" type="password" autocomplete="current-password" required />
        <button type="submit">登录</button>
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
        return HTMLResponse(_render_admin_login_page(error="用户名或密码错误", next_path=next), status_code=401)
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


def next_enrollment_no(db: Session) -> str:
    counter = db.get(EnrollmentCounter, 1)
    if counter is None:
        counter = EnrollmentCounter(id=1, seq=0)
        db.add(counter)
        db.flush()
    counter.seq += 1
    db.commit()
    db.refresh(counter)
    return f"R{utc_now().strftime('%Y%m%d')}-{counter.seq:06d}"


def ensure_schema_migrations() -> None:
    # 轻量 schema 自修复：老库补 recruiter_id 列，避免升级后查詢报错。
    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_records')")).fetchall()]
        if "recruiter_id" not in cols:
            conn.execute(text("ALTER TABLE randomization_records ADD COLUMN recruiter_id VARCHAR(64) DEFAULT ''"))
        rs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('randomization_settings')")).fetchall()]
        if rs_cols and "h5_show_allocation_group" not in rs_cols:
            conn.execute(
                text("ALTER TABLE randomization_settings ADD COLUMN h5_show_allocation_group BOOLEAN DEFAULT 1")
            )


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
                db.add(QRConfig(group_type=group, qr_value=value, version=1, changed_by="system", reason="seed"))
        for group, name in {"GENAI": "干预組", "HUMAN": "對照組"}.items():
            if db.get(GroupLabel, group) is None:
                db.add(GroupLabel(group_type=group, display_name=name, changed_by="system", reason="seed"))
        if db.get(EnrollmentCounter, 1) is None:
            db.add(EnrollmentCounter(id=1, seq=0))
        if db.get(RandomizationSetting, 1) is None:
            db.add(RandomizationSetting(id=1, max_enrollment=None, block_sizes_csv="4,8,12", updated_by="system"))
        ensure_preset_sites(db)
        db.commit()


class SiteUpsertRequest(BaseModel):
    site_id: str
    site_name: str


class SiteRenameIdRequest(BaseModel):
    old_site_id: str
    new_site_id: str
    site_name: str = ""


class DailyPasswordConfigRequest(BaseModel):
    site_id: str
    window_start: datetime
    window_end: datetime
    raw_password: str = Field(min_length=6, pattern=r"^\d{6,}$")
    changed_by: str
    reason: str = "password window"


class RandomizationTriggerRequest(BaseModel):
    phone_number: str = Field(min_length=6)
    site_id: str
    recruiter_id: str
    recruiter_password: str
    at: datetime | None = None


class RecruitmentBatchOpenRequest(BaseModel):
    site_ids: list[str]
    created_by: str
    label: str = ""
    max_active_sites: int = RECRUITMENT_BATCH_MAX_ACTIVE_SITES


class QRUpdateRequest(BaseModel):
    group: str
    qr_value: str
    changed_by: str
    reason: str = ""


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


class RecordDeleteRequest(BaseModel):
    enrollment_no: str
    deleted_by: str
    reason: str = ""


class RandomizationSettingUpdateRequest(BaseModel):
    max_enrollment: int | None = None
    block_sizes: list[int]
    updated_by: str


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


def parse_block_sizes(block_sizes_csv: str) -> tuple[int, ...]:
    try:
        values = tuple(int(x.strip()) for x in block_sizes_csv.split(",") if x.strip())
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="invalid_block_size_config") from exc
    if not values or any(v <= 0 or v % 2 != 0 for v in values):
        raise HTTPException(status_code=500, detail="invalid_block_size_config")
    return values


@app.get("/", response_class=HTMLResponse)
def home_page():
    return """
    <html><body>
    <h2>Randomization Product</h2>
    <p><a href="/h5/randomize">受試者扫码页</a></p>
    <p><a href="/admin/web?page=settings">管理員後台页</a></p>
    </body></html>
    """


@app.get("/h5/randomize", response_class=HTMLResponse)
def randomize_page():
    return """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
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
      </style>
    </head>
    <body>
      <div class="wrap">
      <div class="card">
        <h3 class="title">歡迎參加第十七屆「戒煙大贏家」</h3>
        <p class="lead">请按现场信息填写后提交。系统会按當前站點批次与口令時間窗校验后完成隨機化。</p>
        <form id="f">
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
          <label>站點ID</label>
          <select id="site">
            <option value="">請選擇站點</option>
          </select>
          <label>招募员ID</label><input id="rid" placeholder="REC001" />
          <label>口令</label><input id="pwd" type="password" />
          <p class="muted" style="font-size:12px;margin-top:6px;">校验時間以服务器當前時間为准；站點须属于當前已開啟的招募批次，且口令在配置的時間窗内有效。</p>
          <button type="submit">提交隨機化</button>
        </form>

        <div class="result">
          <div class="kv"><strong>入組编号：</strong><span id="enrollmentNo">-</span></div>
          <div class="kv"><strong>招募地點：</strong><span id="siteName">-</span></div>
          <div class="group" id="groupRow">分組结果：<span id="groupResult">-</span></div>
          <div class="kv"><strong>二維碼：</strong></div>
          <img id="qrImage" alt="whatsapp-qr" />
          <div class="kv" id="qrLinkText"></div>
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
          document.getElementById("okText").textContent = data.idempotent
            ? "该手機號已隨機化，展示历史结果。"
            : "隨機化成功，请扫码添加对应 WhatsApp 账号。";
          document.getElementById("enrollmentNo").textContent = data.enrollment_no || "-";
          document.getElementById("siteName").textContent = data.site_name || data.site_id || "-";
          const gr = document.getElementById("groupResult");
          if (gr) gr.textContent = showAllocationGroup ? (data.allocation_group || "-") : "-";

          const qrRaw = data.whatsapp_qr || "";
          const qrUrl = toAbsoluteUrl(qrRaw);
          const qrImg = document.getElementById("qrImage");
          const qrLinkText = document.getElementById("qrLinkText");
          qrLinkText.innerHTML = "";

          if (!qrUrl) {
            qrImg.style.display = "none";
            qrLinkText.textContent = "未配置二維碼";
            return;
          }
          const isImg = /\\.(png|jpg|jpeg|webp)(\\?.*)?$/i.test(qrUrl) || qrUrl.includes("/uploads/qr/");
          if (isImg) {
            qrImg.src = qrUrl;
            qrImg.style.display = "block";
          } else {
            qrImg.style.display = "none";
          }
          qrLinkText.innerHTML = '二維碼地址：<a href="' + qrUrl + '" target="_blank">' + qrRaw + '</a>';
        }

        async function loadSiteOptions() {
          const sel = document.getElementById("site");
          if (!sel) return;
          const res = await fetch("/participant/active-sites");
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            document.getElementById("errText").textContent = "站點列表加載失败";
            return;
          }
          const items = data.items || [];
          if (!items.length) {
            sel.innerHTML = '<option value="">暂无已啟用站點</option>';
            document.getElementById("errText").textContent = "當前无已啟用站點，請先在管理後台啟用站點。";
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
            document.getElementById("errText").textContent = "手機號格式应为：區號 + 號碼，號碼至少 6 位数字。";
            return;
          }
          const payload = {
            phone_number: code + localPhone,
            site_id: document.getElementById("site").value,
            recruiter_id: document.getElementById("rid").value,
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
              "隨機化失败：" + (data.detail || "unknown_error");
            return;
          }
          renderResult(data);
        });

        loadParticipantUiConfig();
        loadSiteOptions();
      </script>
    </body>
    </html>
    """


@app.get("/admin/web", response_class=HTMLResponse)
def admin_page(page: PageId = Query("settings")):
    return HTMLResponse(render_admin_page(page))


@app.post("/admin/sites")
def upsert_site(payload: SiteUpsertRequest, db: Session = Depends(get_db)):
    site = db.get(Site, payload.site_id)
    cnt = db.query(Site).count()
    if site is None:
        if cnt >= PRESET_SITE_COUNT:
            raise HTTPException(status_code=409, detail="max_preset_sites_reached")
        site = Site(site_id=payload.site_id, site_name=payload.site_name)
        db.add(site)
    else:
        site.site_name = payload.site_name
    db.commit()
    add_audit(db, "site_upserted", payload.model_dump())
    return {"ok": True}


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
    if db.scalar(select(RandomizationRecord).where(RandomizationRecord.site_id == site_id).limit(1)):
        raise HTTPException(status_code=409, detail="site_has_randomization_records")
    db.query(RecruitmentBatchSite).where(RecruitmentBatchSite.site_id == site_id).delete()
    db.query(SiteDailyPassword).where(SiteDailyPassword.site_id == site_id).delete()
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="site_not_found")
    db.delete(site)
    db.commit()
    add_audit(db, "site_deleted", {"site_id": site_id})
    return {"ok": True}


@app.get("/admin/sites")
def list_sites(db: Session = Depends(get_db)):
    sites = db.scalars(select(Site).order_by(Site.site_id.asc())).all()
    return {"items": [{"site_id": s.site_id, "site_name": s.site_name} for s in sites]}


@app.get("/admin/site-recruitment-overview")
def site_recruitment_overview(at: datetime | None = None, db: Session = Depends(get_db)):
    """統計：预设站點容量、當前口令窗口覆盖的站點数、當前开放招募批次站點数等。"""
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
    return {
        "max_parallel_sites_recommended": max_parallel,
        "preset_site_capacity": PRESET_SITE_COUNT,
        "reference_time_utc": ref.isoformat(),
        "registered_site_count": len(sites),
        "sites_with_active_password_at_ref": len(pwd_site_ids),
        "sites_with_active_password_ids": pwd_site_ids,
        "current_open_batch_id": batch.id if batch else None,
        "current_open_batch_site_count": batch_site_count,
    }


@app.get("/admin/sites/table")
def sites_admin_table(db: Session = Depends(get_db)):
    """管理員表格：站點ID、名稱、口令明文（若已儲存）、生效时段、是否在开放招募批次中等。"""
    sites = db.scalars(select(Site).order_by(Site.site_id.asc())).all()
    batch = get_open_batch(db)
    batch_site_ids: set[str] = set()
    if batch is not None:
        batch_site_ids = set(
            db.scalars(select(RecruitmentBatchSite.site_id).where(RecruitmentBatchSite.batch_id == batch.id)).all()
        )
    items = []
    for s in sites:
        pwd = db.scalar(
            select(SiteDailyPassword)
            .where(SiteDailyPassword.site_id == s.site_id)
            .order_by(SiteDailyPassword.id.desc())
            .limit(1)
        )
        items.append(
            {
                "site_id": s.site_id,
                "site_name": s.site_name,
                "password_plain": pwd.password_plain if pwd else None,
                "window_start": pwd.window_start.isoformat() if pwd else None,
                "window_end": pwd.window_end.isoformat() if pwd else None,
                "in_open_recruitment_batch": s.site_id in batch_site_ids,
            }
        )
    return {
        "preset_site_capacity": PRESET_SITE_COUNT,
        "current_open_batch": (
            {
                "id": batch.id,
                "label": batch.label,
                "created_by": batch.created_by,
                "created_at": batch.created_at.isoformat() if batch.created_at else None,
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
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "site_ids": sorted(site_ids),
        }
    }


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
            password_hash=hash_password(payload.raw_password),
            password_plain=payload.raw_password,
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
        {"site_id": payload.site_id, "window_start": ws.isoformat(), "window_end": we.isoformat()},
    )
    return {"ok": True, "version": version}


@app.post("/randomization/trigger")
def trigger_randomization(payload: RandomizationTriggerRequest, db: Session = Depends(get_db)):
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, max_enrollment=None, block_sizes_csv="4,8,12", updated_by="system")
        db.add(setting)
        db.commit()
        db.refresh(setting)
    app_state.randomizer.set_block_sizes(parse_block_sizes(setting.block_sizes_csv))

    at = normalize_utc(payload.at) if payload.at else utc_now()

    lock_key = (payload.site_id, payload.recruiter_id)
    window = app_state.failed_attempts.setdefault(lock_key, FailedAttemptWindow())
    if window.is_locked(utc_now()):
        add_audit(db, "randomization_blocked_locked", payload.model_dump(exclude={"recruiter_password"}))
        raise HTTPException(status_code=429, detail="password_attempt_locked")

    if not site_in_open_batch(db, payload.site_id):
        add_audit(db, "randomization_blocked_site_not_in_batch", {"site_id": payload.site_id})
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
        add_audit(db, "randomization_failed_no_password_config", payload.model_dump(exclude={"recruiter_password"}))
        raise HTTPException(status_code=403, detail="password_not_configured")

    if active_pwd.password_hash != hash_password(payload.recruiter_password):
        window.register_failure(utc_now())
        add_audit(db, "randomization_failed_invalid_password", payload.model_dump(exclude={"recruiter_password"}))
        if window.is_locked(utc_now()):
            raise HTTPException(status_code=429, detail="password_attempt_locked")
        raise HTTPException(status_code=403, detail="invalid_password")
    window.clear()

    existing = db.scalar(select(RandomizationRecord).where(RandomizationRecord.phone_number == payload.phone_number))
    if existing:
        if existing.site_id != payload.site_id:
            raise HTTPException(status_code=403, detail="site_mismatch")
        qr = db.scalar(select(QRConfig).where(QRConfig.group_type == existing.allocation_group))
        return {
            "enrollment_no": existing.enrollment_no,
            "phone_number": existing.phone_number,
            "site_id": existing.site_id,
            "site_name": existing.site_name,
            "allocation_group": existing.allocation_group,
            "whatsapp_qr": qr.qr_value if qr else "",
            "randomized_at": existing.randomized_at.isoformat(),
            "idempotent": True,
        }

    if setting.max_enrollment is not None:
        current_count = db.query(RandomizationRecord).count()
        if current_count >= setting.max_enrollment:
            add_audit(db, "randomization_blocked_max_enrollment", {"max_enrollment": setting.max_enrollment})
            raise HTTPException(status_code=409, detail="max_enrollment_reached")

    site = db.get(Site, payload.site_id)
    site_name = site.site_name if site else payload.site_id
    group = app_state.randomizer.next_group()
    record = RandomizationRecord(
        enrollment_no=next_enrollment_no(db),
        phone_number=payload.phone_number,
        recruiter_id=payload.recruiter_id,
        site_id=payload.site_id,
        site_name=site_name,
        allocation_group=group,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    qr = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
    add_audit(db, "participant_randomized", {"enrollment_no": record.enrollment_no, "group": group})
    return {
        "enrollment_no": record.enrollment_no,
        "phone_number": record.phone_number,
        "site_id": record.site_id,
        "site_name": record.site_name,
        "allocation_group": group,
        "whatsapp_qr": qr.qr_value if qr else "",
        "randomized_at": record.randomized_at.isoformat(),
        "idempotent": False,
    }


@app.post("/admin/qr-config")
def update_qr_config(payload: QRUpdateRequest, db: Session = Depends(get_db)):
    if payload.group not in {"GENAI", "HUMAN"}:
        raise HTTPException(status_code=400, detail="invalid_group")
    cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == payload.group))
    if cfg is None:
        cfg = QRConfig(group_type=payload.group, qr_value=payload.qr_value, changed_by=payload.changed_by, reason=payload.reason)
        db.add(cfg)
    else:
        cfg.version += 1
        cfg.qr_value = payload.qr_value
        cfg.changed_by = payload.changed_by
        cfg.reason = payload.reason
    db.commit()
    add_audit(db, "qr_config_updated", {"group": payload.group, "version": cfg.version})
    return {"ok": True, "group": payload.group, "version": cfg.version}


@app.get("/admin/qr-configs")
def get_qr_configs(db: Session = Depends(get_db)):
    items = db.scalars(select(QRConfig).order_by(QRConfig.group_type.asc())).all()
    return {
        "items": [
            {
                "group_type": i.group_type,
                "qr_value": i.qr_value,
                "version": i.version,
                "changed_by": i.changed_by,
                "reason": i.reason,
                "changed_at": i.changed_at.isoformat() if i.changed_at else None,
            }
            for i in items
        ]
    }


@app.get("/admin/group-labels")
def get_group_labels(db: Session = Depends(get_db)):
    result = {"GENAI": "干预組", "HUMAN": "對照組"}
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
        db: Session = Depends(get_db),
    ):
        if group not in {"GENAI", "HUMAN"}:
            raise HTTPException(status_code=400, detail="invalid_group")
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
        cfg = db.scalar(select(QRConfig).where(QRConfig.group_type == group))
        if cfg is None:
            cfg = QRConfig(group_type=group, qr_value=qr_value, changed_by=changed_by, reason=reason)
            db.add(cfg)
        else:
            cfg.version += 1
            cfg.qr_value = qr_value
            cfg.changed_by = changed_by
            cfg.reason = reason
        db.commit()
        add_audit(db, "qr_config_image_uploaded", {"group": group, "version": cfg.version, "path": qr_value})
        return {"ok": True, "group": group, "version": cfg.version, "qr_value": qr_value}
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
                "created_at": item.created_at.isoformat() if item.created_at else None,
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
                "window_start": c.window_start.isoformat() if c.window_start else None,
                "window_end": c.window_end.isoformat() if c.window_end else None,
                "active": c.active,
                "version": c.version,
                "changed_by": c.changed_by,
            }
            for c in items
        ]
    }


@app.get("/admin/randomization-records")
def get_randomization_records(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(RandomizationRecord)) or 0
    intervention = (
        db.scalar(
            select(func.count())
            .select_from(RandomizationRecord)
            .where(RandomizationRecord.allocation_group == "GENAI")
        )
        or 0
    )
    control = (
        db.scalar(
            select(func.count())
            .select_from(RandomizationRecord)
            .where(RandomizationRecord.allocation_group == "HUMAN")
        )
        or 0
    )
    other = max(0, total - intervention - control)
    records = db.scalars(select(RandomizationRecord).order_by(RandomizationRecord.id.desc())).all()
    return {
        "overview": {
            "total_enrolled": total,
            "intervention_count": intervention,
            "control_count": control,
            "other_group_count": other,
        },
        "items": [
            {
                "enrollment_no": r.enrollment_no,
                "phone_number": r.phone_number,
                "recruiter_id": r.recruiter_id,
                "site_id": r.site_id,
                "site_name": r.site_name,
                "allocation_group": r.allocation_group,
                "randomized_at": r.randomized_at.isoformat() if r.randomized_at else None,
                "activation_status": r.activation_status,
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
            "site_name",
            "allocation_group",
            "randomized_at",
            "activation_status",
        ]
    )
    for r in records:
        writer.writerow(
            [
                r.enrollment_no,
                r.phone_number,
                r.site_id,
                r.recruiter_id,
                r.site_name,
                r.allocation_group,
                r.randomized_at.isoformat() if r.randomized_at else "",
                r.activation_status,
            ]
        )
    csv_text = buf.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=randomization_records_{utc_now().strftime('%Y%m%d_%H%M%S')}.csv"},
    )


@app.get("/admin/randomization-settings")
def get_randomization_settings(db: Session = Depends(get_db)):
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, max_enrollment=None, block_sizes_csv="4,8,12", updated_by="system")
        db.add(setting)
        db.commit()
        db.refresh(setting)
    out = {
        "max_enrollment": setting.max_enrollment,
        "block_sizes": list(parse_block_sizes(setting.block_sizes_csv)),
        "h5_show_allocation_group": bool(getattr(setting, "h5_show_allocation_group", True)),
        "updated_by": setting.updated_by,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
    }
    return out


@app.get("/participant-ui/config")
def get_participant_ui_config(db: Session = Depends(get_db)):
    """供受試者 H5 頁讀取展示選項（無敏感字段）。"""
    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        return {"show_allocation_group": True}
    return {"show_allocation_group": bool(getattr(setting, "h5_show_allocation_group", True))}


@app.get("/participant/active-sites")
def participant_active_sites(db: Session = Depends(get_db)):
    """當前開放招募批次內的站點（僅 ID/名稱）。無需管理員登入，供手機等設備單獨打開 /h5/randomize 時加載下拉框。"""
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

    setting = db.get(RandomizationSetting, 1)
    if setting is None:
        setting = RandomizationSetting(id=1, updated_by=payload.updated_by)
        db.add(setting)
    setting.max_enrollment = payload.max_enrollment
    setting.block_sizes_csv = ",".join(str(x) for x in payload.block_sizes)
    setting.updated_by = payload.updated_by
    db.commit()
    db.refresh(setting)
    app_state.randomizer.set_block_sizes(tuple(payload.block_sizes))
    add_audit(
        db,
        "randomization_settings_updated",
        {
            "max_enrollment": setting.max_enrollment,
            "block_sizes": payload.block_sizes,
            "updated_by": payload.updated_by,
        },
    )
    return {
        "ok": True,
        "max_enrollment": setting.max_enrollment,
        "block_sizes": payload.block_sizes,
    }


@app.patch("/admin/randomization-records/phone")
def admin_correct_phone(payload: PhoneCorrectionRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    duplicate = db.scalar(select(RandomizationRecord).where(RandomizationRecord.phone_number == payload.new_phone_number))
    if duplicate and duplicate.enrollment_no != payload.enrollment_no:
        raise HTTPException(status_code=409, detail="phone_already_exists")
    old_phone = record.phone_number
    record.phone_number = payload.new_phone_number
    db.commit()
    add_audit(
        db,
        "admin_phone_corrected",
        {
            "enrollment_no": payload.enrollment_no,
            "old_phone": old_phone,
            "new_phone": payload.new_phone_number,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        },
    )
    return {"ok": True, "enrollment_no": record.enrollment_no, "phone_number": record.phone_number}


@app.post("/admin/randomization-records/delete")
def admin_delete_record(payload: RecordDeleteRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(RandomizationRecord).where(RandomizationRecord.enrollment_no == payload.enrollment_no))
    if record is None:
        raise HTTPException(status_code=404, detail="record_not_found")
    snapshot = {
        "enrollment_no": record.enrollment_no,
        "phone_number": record.phone_number,
        "site_id": record.site_id,
        "allocation_group": record.allocation_group,
    }
    db.delete(record)
    db.commit()
    add_audit(
        db,
        "admin_record_deleted",
        {
            "deleted_by": payload.deleted_by,
            "reason": payload.reason,
            "record": snapshot,
        },
    )
    return {"ok": True, "deleted_enrollment_no": payload.enrollment_no}


@app.post("/admin/dev/reset")
def dev_reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add(QRConfig(group_type="GENAI", qr_value="https://wa.me/genai_default", version=1, changed_by="system", reason="reset"))
        db.add(QRConfig(group_type="HUMAN", qr_value="https://wa.me/human_default", version=1, changed_by="system", reason="reset"))
        db.add(EnrollmentCounter(id=1, seq=0))
        db.add(RandomizationSetting(id=1, max_enrollment=None, block_sizes_csv="4,8,12", updated_by="system"))
        ensure_preset_sites(db)
        db.commit()
    app_state.failed_attempts = {}
    app_state.randomizer.current_block = []
    app_state.randomizer.assigned = {"GENAI": 0, "HUMAN": 0}
    return {"ok": True}
