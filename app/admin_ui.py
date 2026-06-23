"""管理員後台：左側導航 + 分頁面內容（由 /admin/web?page= 驅動）。"""

from __future__ import annotations

from typing import Literal

from app.models import (
    PRESET_SITE_COUNT,
    PRESET_SITE_INITIAL_COUNT,
    RECRUITMENT_BATCH_MAX_ACTIVE_SITES,
)

PageId = Literal["settings", "sites", "qr", "records"]

ADMIN_CSS = """
:root {
  --bg: #f1f5f9;
  --surface: #ffffff;
  --sidebar: #0f172a;
  --sidebar-hover: #1e293b;
  --text: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --accent: #4f46e5;
  --accent-hover: #4338ca;
  --danger: #dc2626;
  --radius: 12px;
  --shadow: 0 1px 3px rgba(15,23,42,0.08), 0 4px 16px rgba(15,23,42,0.06);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
}
.app-shell {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--sidebar);
  color: #e2e8f0;
  padding: 24px 0;
  display: flex;
  flex-direction: column;
}
.sidebar-brand {
  padding: 0 20px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  margin-bottom: 12px;
}
.sidebar-brand h1 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #fff;
}
.sidebar-brand p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.4;
}
.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 10px;
  flex: 1;
}
.nav a {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  color: #cbd5e1;
  text-decoration: none;
  font-weight: 500;
  font-size: 13px;
  transition: background 0.15s, color 0.15s;
}
.nav a:hover {
  background: var(--sidebar-hover);
  color: #fff;
}
.nav a.active {
  background: rgba(79, 70, 229, 0.25);
  color: #fff;
  box-shadow: inset 3px 0 0 var(--accent);
}
.nav .nav-icon { width: 20px; text-align: center; opacity: 0.9; }
.sidebar-footer {
  padding: 16px 20px 0;
  margin-top: auto;
  border-top: 1px solid rgba(255,255,255,0.08);
  font-size: 12px;
}
.sidebar-footer a { color: #a5b4fc; }
.main {
  flex: 1;
  padding: 28px 32px 40px;
  overflow-x: auto;
  max-width: calc(100vw - 260px);
}
.page-header {
  margin-bottom: 24px;
}
.page-header h2 {
  margin: 0 0 6px;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.03em;
}
.page-header .lead {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  max-width: 720px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 22px 24px;
  margin-bottom: 20px;
  box-shadow: var(--shadow);
}
.card h3 {
  margin: 0 0 16px;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text);
}
.card h4 {
  margin: 20px 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}
label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: #475569;
  margin-top: 12px;
  margin-bottom: 4px;
}
input, select, textarea {
  width: 100%;
  max-width: 520px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  background: #fff;
}
input:focus, select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(79,70,229,0.15);
}
.row { display: flex; gap: 12px; flex-wrap: wrap; max-width: 720px; }
.row > * { flex: 1; min-width: 140px; }
button, .btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 18px;
  margin-top: 12px;
  margin-right: 10px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  background: var(--accent);
  color: #fff;
  transition: background 0.15s;
}
button:hover, .btn:hover { background: var(--accent-hover); }
button.secondary { background: #475569; }
button.secondary:hover { background: #334155; }
button.danger { background: var(--danger); }
button.danger:hover { background: #b91c1c; }
.muted { color: var(--muted); font-size: 12px; line-height: 1.5; }
.records-overview {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.overview-stat-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #f8fafc;
}
.overview-stat-row.overview-stat-trial { border-left: 4px solid #15803d; }
.overview-stat-row.overview-stat-nontrial { border-left: 4px solid #2563eb; }
.overview-stat-row.overview-stat-voided { border-left: 4px solid #dc2626; }
.overview-stat-label {
  flex: 0 0 88px;
  font-weight: 700;
  font-size: 14px;
  color: var(--text);
}
.overview-stat-metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 20px;
}
.overview-metric {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
}
.overview-metric-total { margin-left: 4px; }
.overview-metric-label {
  font-size: 13px;
  color: var(--muted);
  font-weight: 500;
}
.overview-num {
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.overview-num-md { font-size: 18px; }
.overview-num-lg { font-size: 26px; }
.overview-num.valid { color: #15803d; }
.overview-num.invalid { color: #dc2626; }
.overview-num.neutral { color: #2563eb; }
.overview-cap {
  font-size: 15px;
  color: var(--muted);
  font-weight: 500;
}
.overview-stat-footer {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
  line-height: 1.6;
}
pre#result {
  background: #1e293b;
  color: #e2e8f0;
  padding: 14px 16px;
  border-radius: 10px;
  font-size: 12px;
  overflow: auto;
  max-width: 900px;
  max-height: 200px;
  margin-top: 8px;
}
table.data {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 10px;
}
table.data th {
  text-align: left;
  padding: 10px 8px;
  background: #f8fafc;
  border-bottom: 2px solid var(--border);
  color: #475569;
  font-weight: 600;
}
table.data td {
  padding: 8px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
table.data tr:hover td { background: #fafafa; }
.scroll-box {
  max-height: 320px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.table-wrap {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow-x: auto;
}
.batch-pick-zone {
  margin-top: 18px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #f8fafc;
  max-width: 900px;
}
.batch-pick-chips {
  list-style: none;
  margin: 0;
  padding: 0;
}
.batch-pick-chips li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.batch-pick-chips li:last-child { border-bottom: none; }
.table-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
select.rec-status-select {
  width: 100%;
  min-width: 100px;
  max-width: 132px;
  padding: 6px 8px;
  font-size: 12px;
}
.card .subhead {
  margin: 22px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
}
.card .subhead-first { margin-top: 8px; }
.site-name-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px 16px;
  max-width: 900px;
}
.site-name-row .field-site { flex: 0 1 300px; min-width: 200px; }
.site-name-row .field-site select { max-width: 100%; width: 100%; }
.site-name-row .field-name { flex: 1 1 200px; min-width: 160px; }
.site-name-row .field-name input { max-width: none; width: 100%; }
.site-name-row .field-site-id { flex: 0 1 150px; min-width: 120px; }
.site-name-row .field-site-id input { max-width: none; width: 100%; }
.site-name-row .btn-save-inline {
  margin-top: 0;
  margin-bottom: 2px;
  flex-shrink: 0;
  align-self: flex-end;
}
.site-name-row label { margin-top: 0; }
.participant-ui-card {
  margin-top: 12px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #f8fafc;
  max-width: 900px;
}
.participant-ui-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
}
.participant-ui-toggle-label {
  font-size: 13px;
  color: #334155;
  font-weight: 600;
}
.switch {
  position: relative;
  display: inline-flex;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.switch-slider {
  position: absolute;
  inset: 0;
  cursor: pointer;
  background-color: #cbd5e1;
  border-radius: 999px;
  transition: background-color 0.2s ease;
}
.switch-slider:before {
  content: "";
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  top: 3px;
  background-color: #fff;
  border-radius: 50%;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.2);
  transition: transform 0.2s ease;
}
.switch input:checked + .switch-slider {
  background-color: #2563eb;
}
.switch input:checked + .switch-slider:before {
  transform: translateX(20px);
}
.pwd-site-select { max-width: 520px; }
.password-field-wrap {
  position: relative;
  max-width: 520px;
}
.password-field-wrap input {
  width: 100%;
  padding-right: 44px;
  box-sizing: border-box;
  max-width: 520px;
}
.pwd-toggle {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 40px;
  height: 36px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.pwd-toggle:hover { color: var(--accent); background: rgba(79, 70, 229, 0.08); }
.pwd-toggle .icon-eye-off { display: none; }
.password-field-wrap.is-revealed .icon-eye { display: none; }
.password-field-wrap.is-revealed .icon-eye-off { display: inline-flex; }
.table-pwd-cell {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  white-space: nowrap;
}
.table-pwd {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.4;
  color: #334155;
}
.table-status {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  line-height: 1.4;
  color: #334155;
}
.table-time {
  display: inline-block;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.pwd-mini-toggle {
  border: none;
  background: transparent;
  width: 16px;
  height: 16px;
  padding: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: baseline;
  justify-content: center;
  vertical-align: baseline;
  color: #64748b;
  margin-top: 0;
}
.pwd-mini-toggle:hover { color: var(--accent); }
.pwd-mini-toggle svg { display: block; width: 16px; height: 16px; }
.pwd-mini-toggle .icon-eye-off { display: none; }
.table-pwd-cell[data-revealed='1'] .pwd-mini-toggle .icon-eye { display: none; }
.table-pwd-cell[data-revealed='1'] .pwd-mini-toggle .icon-eye-off { display: inline-flex; }
#qrPreview, #qrLivePreview {
  max-width: 240px;
  max-height: 240px;
  border-radius: 10px;
  border: 1px solid var(--border);
  margin-top: 10px;
  background: #fff;
  padding: 8px;
}
.qr-mode-card {
  margin-top: 20px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
  overflow: hidden;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
}
.qr-mode-card-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 14px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.6);
}
.qr-mode-card-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.qr-mode-card-header p {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  text-align: right;
  max-width: 280px;
  line-height: 1.45;
}
.qr-mode-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 16px 18px 18px;
}
.qr-mode-option {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 148px;
  padding: 16px 16px 14px;
  border: 2px solid var(--border);
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.12s;
}
.qr-mode-option:hover {
  border-color: #c7d2fe;
  box-shadow: 0 4px 14px rgba(79, 70, 229, 0.08);
  transform: translateY(-1px);
}
.qr-mode-option:has(input:checked) {
  border-color: var(--accent);
  background: linear-gradient(180deg, rgba(79, 70, 229, 0.05) 0%, #fff 72%);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12);
}
.qr-mode-option input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}
.qr-mode-option-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}
.qr-mode-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  font-size: 17px;
  font-weight: 700;
  line-height: 1;
  color: var(--accent);
  background: rgba(79, 70, 229, 0.1);
}
.qr-mode-option:has(input:checked) .qr-mode-icon {
  color: #fff;
  background: var(--accent);
}
.qr-mode-check {
  width: 18px;
  height: 18px;
  border: 2px solid #cbd5e1;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 2px;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}
.qr-mode-option:has(input:checked) .qr-mode-check {
  border-color: var(--accent);
  background: var(--accent);
  box-shadow: inset 0 0 0 3px #fff;
}
.qr-mode-option strong {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.35;
}
.qr-mode-badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #4338ca;
  background: #e0e7ff;
}
.qr-mode-option span.qr-mode-desc {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-top: 8px;
  line-height: 1.55;
}
@media (max-width: 960px) {
  .qr-mode-options {
    grid-template-columns: 1fr;
  }
  .qr-mode-card-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .qr-mode-card-header p {
    text-align: left;
    max-width: none;
  }
}
.qr-preview-panel {
  margin-top: 14px;
  padding: 14px;
  border: 1px dashed var(--border);
  border-radius: 12px;
  background: #fff;
  text-align: center;
}
.qr-preview-panel #qrLivePreview {
  max-width: 220px;
  max-height: 220px;
  margin: 8px auto 0;
}
.qr-preview-hint {
  font-size: 12px;
  color: var(--muted);
  margin-top: 8px;
  line-height: 1.5;
}
@media (max-width: 900px) {
  .app-shell { flex-direction: column; }
  .sidebar { width: 100%; flex-direction: row; flex-wrap: wrap; padding: 16px; }
  .nav { flex-direction: row; flex-wrap: wrap; }
  .main { max-width: 100%; padding: 20px; }
}
"""


def _nav_link(page: PageId, current: PageId, href: str, icon: str, label: str) -> str:
    cls = "active" if page == current else ""
    return f'<a class="nav-item {cls}" href="{href}"><span class="nav-icon">{icon}</span>{label}</a>'


def render_sidebar(active: PageId) -> str:
    base = "/admin/web?page="
    return f"""
    <aside class="sidebar">
      <div class="sidebar-brand">
        <h1>隨機化管理台</h1>
        <p>最多 {PRESET_SITE_COUNT} 站 · 首次預建 {PRESET_SITE_INITIAL_COUNT} 站 · 單批次 ≤{RECRUITMENT_BATCH_MAX_ACTIVE_SITES} 站 · 密碼按香港同日時間窗</p>
      </div>
      <nav class="nav">
        {_nav_link("settings", active, base + "settings", "⚙", "隨機化設定")}
        {_nav_link("sites", active, base + "sites", "◎", "站點與密碼")}
        {_nav_link("qr", active, base + "qr", "▣", "WhatsApp 二維碼")}
        {_nav_link("records", active, base + "records", "☰", "隨機化分組記錄")}
      </nav>
      <div class="sidebar-footer">
        <a href="/docs" target="_blank">API 文件 (Swagger)</a>
        · <a href="/h5/randomize" target="_blank">受試者頁</a>
      </div>
    </aside>
    """


def panel_settings() -> str:
    return """
    <div class="page-header">
      <h2>隨機化設定</h2>
      <p class="lead">下方概覽展示服務端當前生效值；在「參數」中修改後儲存，將立即作用於後續隨機化。</p>
    </div>
    <div class="card">
      <h3>當前參數概覽</h3>
      <div id="settingsOverview" class="muted" style="margin-top:8px;">載入中…</div>
      <button type="button" class="secondary" style="margin-top:12px;" onclick="loadSettings()">重新整理概覽並同步表單</button>
    </div>
    <div class="card">
      <h3>參數</h3>
      <label>有效入組總人數上限（留空表示不限制；達標後停招）</label>
      <input id="maxEnrollment" placeholder="例如 998" />
      <label>招募起始日（香港時間，用於入組概覽每週跟踪）</label>
      <input id="recruitmentStartDate" type="date" />
      <h4 style="font-size:13px;margin:18px 0 8px;color:#64748b;">入組概覽與每週跟踪</h4>
      <label>計劃跟踪週數</label>
      <input id="weeklyPlanWeeks" type="number" min="1" placeholder="例如 20" />
      <label>每週預計入組人數</label>
      <input id="weeklyPlanPerWeek" type="number" min="1" placeholder="例如 60" />
      <p id="weeklyPlanTargetHint" class="muted" style="font-size:12px;margin-top:4px;">累計計劃目標 = 週數 × 每週人數</p>
      <label>區組大小（逗號分隔，須為偶數）</label>
      <input id="blockSizes" value="4,8,12" />
      <label>更新人</label>
      <input id="settingsUpdatedBy" value="admin" />
      <button type="button" onclick="saveSettings()">儲存設定</button>
      <button type="button" class="secondary" onclick="loadSettings()">重新載入</button>
    </div>
    """


def panel_sites() -> str:
    return f"""
    <div class="page-header">
      <h2>站點與密碼</h2>
      <p class="lead">在站點一覽中點擊「啟用」加入待選列表（最多 <strong>{RECRUITMENT_BATCH_MAX_ACTIVE_SITES}</strong> 個），再點「開啟新批次」；或仍可透過 <a href="/docs" target="_blank">Swagger</a> 調用介面。密碼須落在<strong>同一香港日曆日</strong>內的起止時間（以下按香港時間填寫）。</p>
    </div>
    <div class="card">
      <h4 class="subhead subhead-first">統計概覽</h4>
      <div id="siteOverview" class="muted" style="margin-bottom:10px;">載入中…</div>
      <button type="button" class="secondary" onclick="loadSiteOverview()">重新整理概覽</button>

      <h4 class="subhead">站點設定</h4>
      <div class="site-name-row" style="margin-top:0;">
        <div class="field-name">
          <label for="addSiteNameInput">新增站點名稱</label>
          <input id="addSiteNameInput" type="text" placeholder="顯示名稱" />
        </div>
        <div class="field-site-id">
          <label for="addSiteIdInput">新增站點 ID</label>
          <input id="addSiteIdInput" type="text" placeholder="SITE_04" autocomplete="off" />
        </div>
        <button type="button" class="btn-save-inline secondary" onclick="addSite()">新增站點</button>
      </div>
      <div class="site-name-row" style="margin-top:10px;">
        <div class="field-site">
          <label for="editSiteSelect">選擇站點</label>
          <select id="editSiteSelect" onchange="syncEditNameFromSelect()">
            <option value="">請選擇站點</option>
          </select>
          <select id="pwdSiteSelect" class="pwd-site-select" style="display:none;">
            <option value="">請選擇站點</option>
          </select>
        </div>
        <div class="field-name">
          <label for="editSiteName">名稱</label>
          <input id="editSiteName" type="text" placeholder="顯示名稱" />
        </div>
        <div class="field-site-id">
          <label for="editSiteIdInput">站點 ID</label>
          <input id="editSiteIdInput" type="text" placeholder="SITE_01" autocomplete="off" onblur="syncEditSelectFromIdInput()" />
        </div>
        <button type="button" class="btn-save-inline" onclick="saveSiteName()">儲存修改</button>
      </div>
      <label for="pwdRaw">密碼</label>
      <div class="password-field-wrap" id="pwdRawWrap">
        <input id="pwdRaw" type="password" autocomplete="new-password" />
        <button type="button" class="pwd-toggle" id="pwdToggle" onclick="togglePwdVisibility()" title="顯示密碼" aria-label="顯示或隱藏密碼">
          <span class="icon-eye" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg></span>
          <span class="icon-eye-off" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg></span>
        </button>
      </div>
      <p class="muted" style="margin:6px 0 0;font-size:12px;">要求：至少 6 位，且只能為數字（例如 123456）。</p>
      <div class="row">
        <div>
          <label>生效開始（香港時間）</label>
          <input id="pwdWinStart" type="datetime-local" />
        </div>
        <div>
          <label>生效結束（香港時間）</label>
          <input id="pwdWinEnd" type="datetime-local" />
        </div>
      </div>
      <div class="site-name-row" style="margin-top:10px;">
        <div class="field-name">
          <label>變更人</label>
          <input id="pwdBy" value="admin" />
        </div>
        <button type="button" class="btn-save-inline" onclick="savePassword()">儲存密碼</button>
      </div>

      <h4 class="subhead">站點一覽</h4>
      <button type="button" class="secondary" onclick="loadSitesAdminTable()">重新整理表格</button>
      <div class="scroll-box" style="margin-top:12px;">
        <table class="data" id="sitesAdminTable">
          <thead><tr><th>站點ID</th><th>名稱</th><th>當前狀態</th><th>密碼</th><th>生效起（香港時間）</th><th>生效止（香港時間）</th><th>操作</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>

      <h4 style="margin-top:16px;margin-bottom:8px;font-size:12px;font-weight:600;color:#64748b;">已啟用站點</h4>
      <div id="batchPickList" class="batch-pick-zone"></div>
      <p class="muted" style="margin:8px 0 0;">點擊表格中的「啟用/取消啟用」將立即同步到當前開放批次。</p>

    </div>
    """


def panel_qr() -> str:
    return """
    <div class="page-header">
      <h2>WhatsApp 二維碼</h2>
      <p class="lead">按干預組 / 對照組維護展示用二維碼。推薦使用動態二維碼：固定碼不變，可隨時更換跳轉連結。</p>
    </div>
    <div class="card">
      <h3>組別與資源</h3>
      <label>組別與名稱</label>
      <div class="site-name-row">
        <div class="field-site">
          <select id="qrGroup" onchange="onQrGroupChange()">
            <option value="GENAI">干預組（干預組）</option>
            <option value="HUMAN">對照組（對照組）</option>
          </select>
        </div>
        <div class="field-name">
          <input id="groupNameCurrent" placeholder="請輸入組別名稱" />
        </div>
        <button type="button" class="btn-save-inline secondary" onclick="saveGroupLabels()">儲存</button>
      </div>

      <div class="qr-mode-card">
        <div class="qr-mode-card-header">
          <h4>二維碼模式</h4>
          <p>選擇一種模式；動態二維碼適合印刷後仍可更換連結。</p>
        </div>
        <div class="qr-mode-options" id="qrModeOptions">
          <label class="qr-mode-option">
            <input type="radio" name="qrModeRadio" value="dynamic" checked onchange="onQrModeRadioChange(this.value)" />
            <div class="qr-mode-option-top">
              <span class="qr-mode-icon" aria-hidden="true">⟳</span>
              <span class="qr-mode-check" aria-hidden="true"></span>
            </div>
            <strong>動態二維碼 <span class="qr-mode-badge">推薦</span></strong>
            <span class="qr-mode-desc">固定二維碼圖案不變，後台可隨時更換 wa.me 等跳轉連結，適合印刷海報。</span>
          </label>
          <label class="qr-mode-option">
            <input type="radio" name="qrModeRadio" value="static_url" onchange="onQrModeRadioChange(this.value)" />
            <div class="qr-mode-option-top">
              <span class="qr-mode-icon" aria-hidden="true">🔗</span>
              <span class="qr-mode-check" aria-hidden="true"></span>
            </div>
            <strong>靜態 URL</strong>
            <span class="qr-mode-desc">直接使用連結生成二維碼；更換連結後需重新生成並替換圖片。</span>
          </label>
          <label class="qr-mode-option">
            <input type="radio" name="qrModeRadio" value="static_image" onchange="onQrModeRadioChange(this.value)" />
            <div class="qr-mode-option-top">
              <span class="qr-mode-icon" aria-hidden="true">🖼</span>
              <span class="qr-mode-check" aria-hidden="true"></span>
            </div>
            <strong>靜態圖片（上傳）</strong>
            <span class="qr-mode-desc">上傳已製作好的二維碼圖片檔案，系統直接展示該圖片。</span>
          </label>
        </div>
        <select id="qrMode" style="display:none;" onchange="onQrModeChange()">
          <option value="dynamic" selected>dynamic</option>
          <option value="static_url">static_url</option>
          <option value="static_image">static_image</option>
        </select>
      </div>

      <div id="qrPreviewPanel" class="qr-preview-panel" style="display:none;">
        <div style="font-size:13px;font-weight:600;color:#334155;">二維碼預覽（儲存前即可查看固定碼）</div>
        <div id="qrColorHint" class="qr-preview-hint"></div>
        <img id="qrLivePreview" alt="qr-live-preview" />
        <div id="qrLivePreviewUrl" class="qr-preview-hint"></div>
        <div style="margin-top:10px;">
          <button type="button" class="secondary" onclick="downloadQrPng()">下載二維碼 PNG</button>
        </div>
      </div>

      <label id="qrValueLabel">跳轉目標（可隨時更換）</label>
      <input id="qrValue" placeholder="https://wa.me/..." oninput="onQrValueInput()" />
      <div id="qrDynamicExtras" style="display:none;margin-top:10px;">
        <label>固定二維碼連結（印刷用，不變）</label>
        <input id="qrStableUrl" readonly />
        <label id="qrLogoLabel" style="margin-top:12px;">中心 Logo（可選，PNG/JPG）</label>
        <input id="qrLogoFile" type="file" accept="image/png,image/jpeg,image/webp" />
        <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;">
          <button type="button" class="secondary" onclick="uploadQrLogo()">上傳 Logo</button>
          <button type="button" class="secondary" onclick="removeQrLogo()">移除 Logo</button>
        </div>
        <div id="qrLogoCurrent" class="muted" style="margin-top:6px;"></div>
      </div>
      <label id="qrFileLabel">或上傳圖片</label>
      <input id="qrFile" type="file" accept="image/png,image/jpeg,image/webp" />
      <label>變更人</label>
      <input id="qrBy" value="admin" />
      <label>原因</label>
      <input id="qrReason" value="manual update" />
      <button type="button" onclick="saveQr()">儲存</button>
      <button type="button" class="secondary" onclick="loadQrCurrent()">讀取當前</button>

      <div class="participant-ui-card" style="margin-top:18px;">
        <h4 style="margin-top:0;margin-bottom:8px;font-size:12px;font-weight:600;color:#64748b;">受試者互動頁（/h5/randomize）</h4>
        <div class="participant-ui-toggle-row">
          <span class="participant-ui-toggle-label">隨機化結果中顯示分組</span>
          <label class="switch" title="切換是否顯示分組">
            <input type="checkbox" id="h5ShowAllocationGroup" checked />
            <span class="switch-slider"></span>
          </label>
        </div>
        <button type="button" class="secondary" style="margin-top:10px;" onclick="saveParticipantPageUi()">儲存顯示設定</button>
      </div>

      <div style="margin-top:14px;">
        <div class="muted">當前已儲存設定</div>
        <div id="qrCurrentText" class="muted" style="margin-top:4px;">—</div>
        <img id="qrPreview" alt="preview" style="display:none;" />
      </div>
    </div>
    """


def panel_records() -> str:
    return """
    <div class="page-header">
      <h2>隨機化分組記錄</h2>
      <p class="lead">查詢入組記錄；可編輯受試者編碼、手機號與狀態（Trial / Non-trial / 作廢），修改後分別點「保存編碼」「修改手機號」「保存狀態」。新隨機默認為 Trial。</p>
    </div>
    <div class="card">
      <h3>入組概覽</h3>
      <div id="recordsOverview" class="records-overview">載入中…</div>
      <div id="recordsWeeklySection" style="margin-top:16px;">
        <h4 style="font-size:13px;margin:0 0 8px;color:#64748b;">每週招募跟踪（Trial 有效入組）</h4>
        <p id="recordsWeeklyCaption" class="muted" style="font-size:12px;margin-bottom:8px;">載入中…</p>
        <div style="max-width:560px;">
          <canvas id="recordsWeeklyChart" height="150"></canvas>
        </div>
      </div>
    </div>
    <div class="card">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
        <h3 style="margin:0;">記錄列表</h3>
        <div style="display:flex;gap:8px;">
          <button type="button" class="secondary" onclick="loadRecords()">重新整理</button>
          <button type="button" class="secondary" onclick="exportRecordsCsv()">匯出 CSV</button>
        </div>
      </div>
      <div class="row" style="margin-top:10px;max-width:none;flex-wrap:nowrap;">
        <div style="flex:1 1 0;min-width:0;">
          <label>站點</label>
          <select id="recordsFilterSite">
            <option value="">全部站點</option>
          </select>
        </div>
        <div style="flex:1 1 0;min-width:0;">
          <label>日期（香港時間）</label>
          <input id="recordsFilterDate" type="date" />
        </div>
        <div style="flex:1 1 0;min-width:0;">
          <label>分組</label>
          <select id="recordsFilterGroup">
            <option value="">全部分組</option>
          </select>
        </div>
        <div style="flex:1 1 0;min-width:0;">
          <label>招募員姓名</label>
          <input id="recordsFilterRecruiter" placeholder="輸入招募員姓名關鍵字" />
        </div>
      </div>
      <div class="table-wrap" style="margin-top:12px;">
        <table class="data" id="recordsTable">
          <thead><tr><th>頁內序號</th><th>入組編號</th><th>受試者編碼</th><th>手機號</th><th>站點</th><th>招募員姓名</th><th>分組</th><th>狀態</th><th>時間（香港時間）</th><th>操作</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:8px;">
          <label for="recordsPageSize" style="margin:0;">每頁</label>
          <select id="recordsPageSize" style="width:auto;max-width:none;padding:6px 8px;">
            <option value="20">20</option>
            <option value="50">50</option>
          </select>
          <span id="recordsPageMeta" class="muted">—</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <button type="button" class="secondary" id="recordsPrevBtn" style="margin:0;padding:6px 10px;font-size:12px;">上一頁</button>
          <button type="button" class="secondary" id="recordsNextBtn" style="margin:0;padding:6px 10px;font-size:12px;">下一頁</button>
        </div>
      </div>
    </div>
    <div class="card">
      <h3>審計日誌</h3>
      <button type="button" class="secondary" onclick="loadAudits()">重新整理日誌</button>
      <div class="scroll-box" style="margin-top:12px;">
        <table class="data" id="auditTable">
          <thead><tr><th>ID</th><th>事件</th><th>請求ID</th><th>時間（香港時間）</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
    """


ADMIN_SCRIPTS = """
<script>
  const PAGE = "__PAGE__";
  const BATCH_MAX = __BATCH_MAX__;
  window.__batchPickSiteIds = [];
  const resultBox = document.getElementById("result");

  async function api(path, method, body) {
    const options = {
      method: method || "GET",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
    };
    if (body) options.body = JSON.stringify(body);
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (resultBox) resultBox.textContent = "[ERROR] " + path + "\\n" + JSON.stringify(data, null, 2);
      throw new Error(data.detail || "request_failed");
    }
    if (resultBox) resultBox.textContent = "[OK] " + path + "\\n" + JSON.stringify(data, null, 2);
    return data;
  }

  const HK_TZ = "Asia/Hong_Kong";

  function formatHkTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    const parts = new Intl.DateTimeFormat("zh-HK", {
      timeZone: HK_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).formatToParts(d);
    const get = (t) => (parts.find(p => p.type === t) || {}).value || "";
    return get("year") + "-" + get("month") + "-" + get("day") + " "
      + get("hour") + ":" + get("minute") + ":" + get("second") + " HKT";
  }

  function hkDateFromIso(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: HK_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(d);
  }

  function isoToHkDatetimeLocal(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: HK_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(d);
    const get = (t) => (parts.find(p => p.type === t) || {}).value || "";
    return get("year") + "-" + get("month") + "-" + get("day") + "T" + get("hour") + ":" + get("minute");
  }

  function hkDatetimeLocalToIso(value) {
    if (!value) return null;
    const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return null;
    const y = Number(m[1]);
    const mo = Number(m[2]);
    const d = Number(m[3]);
    const h = Number(m[4]);
    const mi = Number(m[5]);
    return new Date(Date.UTC(y, mo - 1, d, h - 8, mi, 0)).toISOString();
  }

  function csvToInts(raw) {
    return raw.split(",").map(x => Number(x.trim())).filter(x => !Number.isNaN(x));
  }

  function updateWeeklyPlanTargetHint() {
    const hint = document.getElementById("weeklyPlanTargetHint");
    if (!hint) return;
    const weeks = Number(document.getElementById("weeklyPlanWeeks")?.value || 0);
    const perWeek = Number(document.getElementById("weeklyPlanPerWeek")?.value || 0);
    if (weeks > 0 && perWeek > 0) {
      hint.textContent = "累計計劃目標 = " + weeks + " 週 × " + perWeek + " 人/週 = " + (weeks * perWeek) + " 人";
    } else {
      hint.textContent = "累計計劃目標 = 週數 × 每週人數";
    }
  }

  function renderSettingsOverview(data) {
    const el = document.getElementById("settingsOverview");
    if (!el) return;
    const maxE = data.max_enrollment;
    const maxLabel = maxE == null || maxE === "" ? "不限制" : String(maxE);
    const blocks = (data.block_sizes || []).length ? (data.block_sizes || []).join("、") : "—";
    const startDate = data.recruitment_start_date ? escapeHtml(String(data.recruitment_start_date)) : "—";
    const planWeeks = Number(data.weekly_plan_weeks) || 20;
    const planPerWeek = Number(data.weekly_plan_per_week) || 60;
    const by = data.updated_by ? escapeHtml(String(data.updated_by)) : "—";
    const at = data.updated_at ? escapeHtml(formatHkTime(data.updated_at)) : "—";
    el.innerHTML =
      "有效入組總上限 <strong>" + escapeHtml(maxLabel)
      + "</strong>（達標後停招）；招募起始日 <strong>" + startDate
      + "</strong>；每週跟踪 <strong>" + planWeeks + " 週 × " + planPerWeek + " 人/週 = " + (planWeeks * planPerWeek) + " 人</strong>"
      + "；區組大小 <strong>" + escapeHtml(blocks)
      + "</strong>。<br/>最近更新人 <strong>" + by + "</strong>；更新時間 <code style='font-size:12px'>" + at + "</code>。";
  }

  async function loadSettings() {
    if (!document.getElementById("maxEnrollment")) return;
    const data = await api("/admin/randomization-settings", "GET");
    renderSettingsOverview(data);
    document.getElementById("maxEnrollment").value = data.max_enrollment ?? "";
    const startEl = document.getElementById("recruitmentStartDate");
    if (startEl) startEl.value = data.recruitment_start_date ?? "";
    const weeksEl = document.getElementById("weeklyPlanWeeks");
    if (weeksEl) weeksEl.value = data.weekly_plan_weeks ?? "";
    const perWeekEl = document.getElementById("weeklyPlanPerWeek");
    if (perWeekEl) perWeekEl.value = data.weekly_plan_per_week ?? "";
    updateWeeklyPlanTargetHint();
    document.getElementById("blockSizes").value = (data.block_sizes || []).join(",");
  }
  async function saveSettings() {
    const maxRaw = document.getElementById("maxEnrollment").value.trim();
    const startRaw = (document.getElementById("recruitmentStartDate")?.value || "").trim();
    const weeksRaw = (document.getElementById("weeklyPlanWeeks")?.value || "").trim();
    const perWeekRaw = (document.getElementById("weeklyPlanPerWeek")?.value || "").trim();
    await api("/admin/randomization-settings", "PUT", {
      max_enrollment: maxRaw === "" ? null : Number(maxRaw),
      recruitment_start_date: startRaw === "" ? null : startRaw,
      weekly_plan_weeks: weeksRaw === "" ? null : Number(weeksRaw),
      weekly_plan_per_week: perWeekRaw === "" ? null : Number(perWeekRaw),
      block_sizes: csvToInts(document.getElementById("blockSizes").value),
      updated_by: document.getElementById("settingsUpdatedBy").value
    });
    await loadSettings();
  }

  function applyPasswordWindowDefaults(data) {
    const startEl = document.getElementById("pwdWinStart");
    const endEl = document.getElementById("pwdWinEnd");
    if (!startEl || !endEl) return;
    if (startEl.value && endEl.value) return;
    const ws = data && data.default_password_window_start;
    const we = data && data.default_password_window_end;
    if (ws && we) {
      if (!startEl.value) startEl.value = isoToHkDatetimeLocal(ws);
      if (!endEl.value) endEl.value = isoToHkDatetimeLocal(we);
      return;
    }
    const today = hkDateFromIso(new Date().toISOString());
    if (!startEl.value) startEl.value = today + "T00:00";
    if (!endEl.value) endEl.value = today + "T23:59";
  }

  function fillSiteIdSelects(items) {
    window.__sitesList = items || [];
    const selEdit = document.getElementById("editSiteSelect");
    const selPwd = document.getElementById("pwdSiteSelect");
    if (!selEdit || !selPwd) return;
    const prevEdit = selEdit.value;
    const prevPwd = selPwd.value;
    selEdit.innerHTML = "";
    selPwd.innerHTML = "";
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "請選擇站點";
    selEdit.appendChild(ph.cloneNode(true));
    selPwd.appendChild(ph.cloneNode(true));
    (items || []).forEach(row => {
      const oe = document.createElement("option");
      oe.value = row.site_id;
      oe.textContent = row.site_id + " — " + row.site_name;
      selEdit.appendChild(oe);
      const op = document.createElement("option");
      op.value = row.site_id;
      op.textContent = row.site_id + " — " + row.site_name;
      selPwd.appendChild(op);
    });
    if (prevEdit && [...selEdit.options].some(o => o.value === prevEdit)) selEdit.value = prevEdit;
    if (prevPwd && [...selPwd.options].some(o => o.value === prevPwd)) selPwd.value = prevPwd;
    syncEditNameFromSelect();
  }

  function syncPwdSiteFromEdit() {
    const selEdit = document.getElementById("editSiteSelect");
    const selPwd = document.getElementById("pwdSiteSelect");
    if (!selEdit || !selPwd) return;
    selPwd.value = selEdit.value;
  }

  function syncEditNameFromSelect() {
    const sel = document.getElementById("editSiteSelect");
    const inp = document.getElementById("editSiteName");
    const idInp = document.getElementById("editSiteIdInput");
    if (!sel || !inp) return;
    const row = (window.__sitesList || []).find(s => s.site_id === sel.value);
    if (idInp) idInp.value = sel.value || "";
    inp.value = row ? row.site_name : "";
    syncPwdSiteFromEdit();
  }

  function syncEditSelectFromIdInput() {
    const idInp = document.getElementById("editSiteIdInput");
    const sel = document.getElementById("editSiteSelect");
    if (!idInp || !sel) return;
    const v = idInp.value.trim();
    if (!v) return;
    if ([...sel.options].some(o => o.value === v)) sel.value = v;
    syncEditNameFromSelect();
  }

  async function loadSiteOverview() {
    const el = document.getElementById("siteOverview");
    if (!el) return;
    const res = await fetch("/admin/site-recruitment-overview");
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { el.textContent = "概覽載入失敗"; return; }
    const warnBatch = data.current_open_batch_site_count > data.max_parallel_sites_recommended
      ? " <span style='color:#b45309'>（批次站點數超建議）</span>" : "";
    const warnPwd = data.sites_with_active_password_at_ref > data.max_parallel_sites_recommended
      ? " <span style='color:#b45309'>（有效密碼站點數超建議）</span>" : "";
    el.innerHTML = "預設 <strong>" + data.preset_site_capacity + "</strong>；已登記 <strong>" + data.registered_site_count
      + "</strong>。參考時間（香港時間）：<strong>" + escapeHtml(formatHkTime(data.reference_time_utc)) + "</strong>；密碼有效站點 <strong>"
      + data.sites_with_active_password_at_ref + "</strong>" + warnPwd
      + "。開放批次 ID <strong>" + (data.current_open_batch_id ?? "無") + "</strong>，本批次站點數 <strong>"
      + data.current_open_batch_site_count + "</strong>" + warnBatch + "。";
    applyPasswordWindowDefaults(data);
    await refreshSiteDropdownsOnly();
    await loadCurrentBatchJson();
  }

  async function refreshSiteDropdownsOnly() {
    const data = await fetch("/admin/sites").then(r => r.json());
    fillSiteIdSelects(data.items || []);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function maskPassword(raw) {
    const text = String(raw || "");
    if (!text) return "—";
    return "•".repeat(Math.max(6, text.length));
  }

  function toggleSiteTablePassword(btn) {
    const wrap = btn && btn.closest ? btn.closest(".table-pwd-cell") : null;
    const textEl = wrap ? wrap.querySelector(".table-pwd") : null;
    if (!wrap || !textEl) return;
    const raw = textEl.getAttribute("data-raw") || "";
    const revealed = wrap.getAttribute("data-revealed") === "1";
    if (revealed) {
      textEl.textContent = maskPassword(raw);
      wrap.setAttribute("data-revealed", "0");
      btn.title = "顯示密碼";
      btn.setAttribute("aria-label", "顯示密碼");
      return;
    }
    textEl.textContent = raw || "—";
    wrap.setAttribute("data-revealed", "1");
    btn.title = "隱藏密碼";
    btn.setAttribute("aria-label", "隱藏密碼");
  }

  function renderBatchPickList() {
    const el = document.getElementById("batchPickList");
    if (!el) return;
    const arr = window.__batchPickSiteIds || [];
    const meta = window.__sitesList || [];
    if (arr.length === 0) {
      el.innerHTML = '<p class="muted" style="margin:0">未選擇站點。在上方表格「操作」列點擊「啟用」加入，最多 ' + BATCH_MAX + ' 個。</p>';
      return;
    }
    let html = '<p class="muted" style="margin:0 0 8px">已選 <strong>' + arr.length + "</strong> / " + BATCH_MAX + '：</p><ul class="batch-pick-chips">';
    arr.forEach(function(id) {
      const row = meta.find(function(s) { return s.site_id === id; });
      const label = row ? (escapeHtml(row.site_id) + " — " + escapeHtml(row.site_name)) : escapeHtml(id);
      html += "<li><span>" + label + "</span><button type='button' class='secondary' style='margin:0;padding:4px 8px;font-size:12px' onclick='removeBatchPickSite(" + JSON.stringify(id) + ")'>移除</button></li>";
    });
    html += "</ul>";
    el.innerHTML = html;
  }

  async function applyBatchSelectionNow() {
    const selected = window.__batchPickSiteIds || [];
    if (!selected.length) {
      await api("/admin/recruitment-batches/close", "POST", {});
      return;
    }
    await api("/admin/recruitment-batches/open", "POST", {
      site_ids: selected,
      created_by: "admin",
      label: "",
      max_active_sites: BATCH_MAX
    });
  }

  async function toggleBatchPickSite(siteId) {
    window.__batchPickSiteIds = window.__batchPickSiteIds || [];
    const arr = window.__batchPickSiteIds;
    const i = arr.indexOf(siteId);
    if (i >= 0) {
      arr.splice(i, 1);
    } else {
      if (arr.length >= BATCH_MAX) {
        resultBox.textContent = "[ERROR] 最多可選 " + BATCH_MAX + " 個站點";
        return;
      }
      arr.push(siteId);
    }
    await applyBatchSelectionNow();
    renderBatchPickList();
    await loadSiteOverview();
    await loadSitesAdminTable();
  }

  async function removeBatchPickSite(siteId) {
    const sid = String(siteId);
    window.__batchPickSiteIds = (window.__batchPickSiteIds || []).filter(function(x) { return String(x) !== sid; });
    await applyBatchSelectionNow();
    renderBatchPickList();
    await loadSiteOverview();
    await loadSitesAdminTable();
  }

  async function openRecruitmentBatch() {
    const selected = window.__batchPickSiteIds || [];
    if (!selected.length) {
      resultBox.textContent = "[ERROR] 請先在表格中啟用至少一個站點";
      return;
    }
    await api("/admin/recruitment-batches/open", "POST", {
      site_ids: selected,
      created_by: "admin",
      label: "",
      max_active_sites: BATCH_MAX
    });
    window.__batchPickSiteIds = [];
    renderBatchPickList();
    await loadSiteOverview();
    await loadSitesAdminTable();
  }

  async function loadCurrentBatchJson() {
    const pre = document.getElementById("currentBatchJson");
    if (!pre) return;
    const data = await fetch("/admin/recruitment-batches/current").then(r => r.json());
    pre.textContent = JSON.stringify(data.batch, null, 2);
  }

  async function loadSitesAdminTable() {
    const tbody = document.querySelector("#sitesAdminTable tbody");
    if (!tbody) return;
    const data = await fetch("/admin/sites/table").then(r => r.json());
    tbody.innerHTML = "";
    const picked = window.__batchPickSiteIds || [];
    (data.items || []).forEach(row => {
      const tr = document.createElement("tr");
      const pwd = row.password_plain ? row.password_plain : "—";
      const pwdCell =
        "<div class='table-pwd-cell' data-revealed='0'><span class='table-pwd' data-raw='" + escapeHtml(pwd) + "'>"
        + maskPassword(pwd)
        + "</span><button type='button' class='pwd-mini-toggle' title='顯示密碼' aria-label='顯示密碼' onclick='toggleSiteTablePassword(this)'>"
        + "<span class='icon-eye' aria-hidden='true'><svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z'/><circle cx='12' cy='12' r='3'/></svg></span>"
        + "<span class='icon-eye-off' aria-hidden='true'><svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24'/><line x1='1' y1='1' x2='23' y2='23'/></svg></span>"
        + "</button></div>";
      const sid = JSON.stringify(row.site_id);
      const isPicked = picked.indexOf(row.site_id) >= 0;
      const actLabel = isPicked ? "取消啟用" : "啟用";
      const actCls = isPicked ? "secondary" : "";
      const statusText = isPicked ? "已啟用" : "未啟用";
      tr.innerHTML =
        "<td>" +
        row.site_id +
        "</td><td>" +
        row.site_name +
        "</td><td><span class='table-status'>" +
        statusText +
        "</span>" +
        "</td><td>" +
        pwdCell +
        "</td><td><span class='table-time'>" +
        formatHkTime(row.window_start) +
        "</span></td><td><span class='table-time'>" +
        formatHkTime(row.window_end) +
        "</td><td><div class=\\\"table-actions\\\"><button type=\\\"button\\\" class=\\\"" +
        actCls +
        "\\\" style=\\\"margin:0;padding:6px 10px;font-size:12px\\\" onclick='toggleBatchPickSite(" +
        sid +
        ")'>" +
        actLabel +
        "</button><button type=\\\"button\\\" class=\\\"danger\\\" style=\\\"margin:0;padding:6px 10px;font-size:12px\\\" onclick='deleteSiteRow(" +
        sid +
        ")'>刪除</button></div></td>";
      tbody.appendChild(tr);
    });
    const sitesRes = await fetch("/admin/sites");
    const sitesJson = await sitesRes.json().catch(() => ({}));
    fillSiteIdSelects(sitesJson.items || []);
  }

  async function deleteSiteRow(siteId) {
    if (!confirm("確認刪除站點 " + siteId + "？")) return;
    const res = await fetch("/admin/sites/" + encodeURIComponent(siteId), { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { resultBox.textContent = "[ERROR] DELETE\\n" + JSON.stringify(data, null, 2); return; }
    resultBox.textContent = "[OK] 已刪除站點";
    window.__batchPickSiteIds = (window.__batchPickSiteIds || []).filter(function(x) { return x !== siteId; });
    renderBatchPickList();
    await loadSitesAdminTable();
    await loadSiteOverview();
  }

  function togglePwdVisibility() {
    const wrap = document.getElementById("pwdRawWrap");
    const inp = document.getElementById("pwdRaw");
    const btn = document.getElementById("pwdToggle");
    if (!wrap || !inp || !btn) return;
    wrap.classList.toggle("is-revealed");
    const revealed = wrap.classList.contains("is-revealed");
    inp.type = revealed ? "text" : "password";
    btn.title = revealed ? "隱藏密碼" : "顯示密碼";
    btn.setAttribute("aria-label", revealed ? "隱藏密碼" : "顯示密碼");
  }

  function resetPwdFieldVisibility() {
    const wrap = document.getElementById("pwdRawWrap");
    const inp = document.getElementById("pwdRaw");
    const btn = document.getElementById("pwdToggle");
    if (!wrap || !inp || !btn) return;
    wrap.classList.remove("is-revealed");
    inp.type = "password";
    btn.title = "顯示密碼";
    btn.setAttribute("aria-label", "顯示或隱藏密碼");
  }

  async function saveSiteName() {
    const idInp = document.getElementById("editSiteIdInput");
    const typed = idInp ? idInp.value.trim() : "";
    const selectedId = document.getElementById("editSiteSelect").value.trim();
    const sid = typed || selectedId;
    if (!selectedId) { resultBox.textContent = "[ERROR] 請先從下拉選擇已有站點；新增請點「新增站點」按鈕"; return; }
    if (!sid) { resultBox.textContent = "[ERROR] 請填寫站點 ID"; return; }
    const name = document.getElementById("editSiteName").value;
    if (selectedId && typed && typed !== selectedId) {
      await api("/admin/sites/rename-id", "POST", {
        old_site_id: selectedId,
        new_site_id: typed,
        site_name: name
      });
    } else {
    await api("/admin/sites", "POST", {
      site_id: sid,
      site_name: name
    });
    }
    await loadSitesAdminTable();
    await loadSiteOverview();
    if (idInp) idInp.value = sid;
    const sel = document.getElementById("editSiteSelect");
    if (sel) sel.value = sid;
    syncEditNameFromSelect();
  }

  async function addSite() {
    const idInp = document.getElementById("addSiteIdInput");
    const nameInp = document.getElementById("addSiteNameInput");
    const sid = idInp ? idInp.value.trim() : "";
    const name = nameInp ? nameInp.value.trim() : "";
    if (!sid) { resultBox.textContent = "[ERROR] 新增站點需填寫站點 ID"; return; }
    if (!name) { resultBox.textContent = "[ERROR] 新增站點需填寫名稱"; return; }
    await api("/admin/sites", "POST", { site_id: sid, site_name: name });
    await loadSitesAdminTable();
    await loadSiteOverview();
    const sel = document.getElementById("editSiteSelect");
    if (sel) sel.value = sid;
    if (idInp) idInp.value = "";
    if (nameInp) nameInp.value = "";
    syncEditNameFromSelect();
  }

  async function savePassword() {
    const sid = document.getElementById("pwdSiteSelect").value;
    if (!sid) { resultBox.textContent = "[ERROR] 請先選擇密碼對應的站點"; return; }
    const ws = hkDatetimeLocalToIso(document.getElementById("pwdWinStart").value);
    const we = hkDatetimeLocalToIso(document.getElementById("pwdWinEnd").value);
    const pwd = document.getElementById("pwdRaw").value;
    if (!ws || !we) { resultBox.textContent = "[ERROR] 請填寫密碼生效開始和結束時間"; return; }
    if (!/^\d{6,}$/.test(pwd || "")) { resultBox.textContent = "[ERROR] 密碼要求：至少 6 位且只能為數字"; return; }
    await api("/admin/site-passwords", "POST", {
      site_id: sid,
      window_start: ws,
      window_end: we,
      raw_password: pwd,
      changed_by: document.getElementById("pwdBy").value
    });
    document.getElementById("pwdRaw").value = "";
    resetPwdFieldVisibility();
    await loadSiteOverview();
    await loadSitesAdminTable();
  }

  function toAbsoluteUrl(raw) {
    if (!raw) return "";
    if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
    return window.location.origin + raw;
  }

  function syncQrModeRadio(mode) {
    const sel = document.getElementById("qrMode");
    const val = mode || sel?.value || "static_url";
    if (sel) sel.value = val;
    document.querySelectorAll('input[name="qrModeRadio"]').forEach(r => {
      r.checked = r.value === val;
    });
  }

  function onQrModeRadioChange(mode) {
    syncQrModeRadio(mode);
    onQrModeChange();
  }

  function onQrValueInput() {
    updateQrLivePreview();
  }

  function updateQrLivePreview() {
    const mode = document.getElementById("qrMode")?.value || "static_url";
    const group = document.getElementById("qrGroup")?.value;
    const panel = document.getElementById("qrPreviewPanel");
    const img = document.getElementById("qrLivePreview");
    const hint = document.getElementById("qrLivePreviewUrl");
    const colorHint = document.getElementById("qrColorHint");
    if (!panel || !img) return;
    if (mode !== "dynamic" || !group) {
      panel.style.display = "none";
      img.removeAttribute("src");
      if (colorHint) colorHint.textContent = "";
      return;
    }
    const stableUrl = window.location.origin + "/r/" + group;
    const stableInp = document.getElementById("qrStableUrl");
    if (stableInp) stableInp.value = stableUrl;
    img.src = "/admin/qr-preview/" + group + ".png?t=" + Date.now();
    img.style.display = "block";
    panel.style.display = "block";
    if (colorHint) {
      colorHint.textContent = group === "GENAI"
        ? "干預組：紅色二維碼"
        : "對照組：藍色二維碼";
    }
    const target = (document.getElementById("qrValue")?.value || "").trim();
    if (hint) {
      hint.innerHTML = "固定碼連結：<strong>" + stableUrl + "</strong>"
        + (target ? ("<br>當前跳轉目標（儲存後生效）：" + target) : "<br>請填寫跳轉目標後點擊儲存");
    }
  }

  function onQrModeChange() {
    const mode = document.getElementById("qrMode")?.value || "static_url";
    syncQrModeRadio(mode);
    const dynamicExtras = document.getElementById("qrDynamicExtras");
    const valueLabel = document.getElementById("qrValueLabel");
    const fileLabel = document.getElementById("qrFileLabel");
    const fileInput = document.getElementById("qrFile");
    if (dynamicExtras) dynamicExtras.style.display = mode === "dynamic" ? "block" : "none";
    if (valueLabel) {
      valueLabel.textContent = mode === "dynamic"
        ? "跳轉目標（可隨時更換）"
        : (mode === "static_image" ? "當前圖片路徑（上傳後自動填入）" : "二維碼連結（URL）");
    }
    if (fileLabel && fileInput) {
      const showFile = mode === "static_image";
      fileLabel.style.display = showFile ? "" : "none";
      fileInput.style.display = showFile ? "" : "none";
    }
    updateQrLivePreview();
  }

  function downloadQrPng() {
    const group = document.getElementById("qrGroup")?.value;
    if (!group) return;
    const mode = document.getElementById("qrMode")?.value;
    const url = mode === "dynamic"
      ? "/admin/qr-preview/" + group + ".png?t=" + Date.now()
      : "/r/" + group + "/qr.png";
    window.open(url, "_blank");
  }

  async function uploadQrLogo() {
    const fileInput = document.getElementById("qrLogoFile");
    if (!fileInput || !fileInput.files || !fileInput.files.length) {
      resultBox.textContent = "[ERROR] 請選擇 Logo 圖片";
      return;
    }
    const fd = new FormData();
    fd.append("group", document.getElementById("qrGroup").value);
    fd.append("changed_by", document.getElementById("qrBy").value || "admin");
    fd.append("file", fileInput.files[0]);
    const res = await fetch("/admin/qr-config/logo", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { resultBox.textContent = "[ERROR] logo upload\\n" + JSON.stringify(data, null, 2); return; }
    resultBox.textContent = "[OK] Logo 已上傳";
    fileInput.value = "";
    await loadQrCurrent();
    updateQrLivePreview();
  }

  async function removeQrLogo() {
    const group = document.getElementById("qrGroup")?.value;
    if (!group) return;
    const res = await fetch("/admin/qr-config/logo?group=" + encodeURIComponent(group), { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { resultBox.textContent = "[ERROR] remove logo\\n" + JSON.stringify(data, null, 2); return; }
    resultBox.textContent = "[OK] Logo 已移除";
    await loadQrCurrent();
    updateQrLivePreview();
  }

  async function loadQrCurrent() {
    const text = document.getElementById("qrCurrentText");
    const img = document.getElementById("qrPreview");
    if (!text) return;
    const group = document.getElementById("qrGroup").value;
    const data = await api("/admin/qr-configs", "GET");
    const current = (data.items || []).find(x => x.group_type === group);
    if (!current) {
      text.textContent = "尚無已儲存設定，可選擇模式並預覽後點擊儲存";
      if (img) img.style.display = "none";
      const logoEl = document.getElementById("qrLogoCurrent");
      if (logoEl) logoEl.textContent = "尚未上傳中心 Logo";
      syncQrModeRadio("dynamic");
      onQrModeChange();
      return;
    }
    const modeSel = document.getElementById("qrMode");
    if (modeSel) modeSel.value = current.qr_mode || "static_url";
    syncQrModeRadio(current.qr_mode || "static_url");
    document.getElementById("qrValue").value = current.qr_value || "";
    const stableInp = document.getElementById("qrStableUrl");
    if (stableInp) stableInp.value = current.stable_qr_url || "";
    const logoEl = document.getElementById("qrLogoCurrent");
    if (logoEl) {
      logoEl.textContent = current.qr_logo_path
        ? "當前 Logo：" + current.qr_logo_path
        : "尚未上傳中心 Logo";
    }
    const mode = current.qr_mode || "static_url";
    onQrModeChange();
    if (mode === "dynamic") {
      text.textContent = "v" + current.version + " · 動態碼 → " + (current.qr_value || "");
      if (img) { img.style.display = "none"; }
      return;
    }
    text.textContent = "v" + current.version + " · " + (current.qr_value || "");
    const previewUrl = toAbsoluteUrl(current.qr_value || "");
    const isImg = /\\.(png|jpg|jpeg|webp)(\\?.*)?$/i.test(previewUrl) || previewUrl.includes("/uploads/qr/");
    if (img && previewUrl && isImg) { img.src = previewUrl; img.style.display = "block"; }
    else if (img) { img.style.display = "none"; }
  }

  async function loadParticipantPageUi() {
    const cb = document.getElementById("h5ShowAllocationGroup");
    if (!cb) return;
    const r = await fetch("/participant-ui/config");
    const d = await r.json().catch(() => ({}));
    cb.checked = d.show_allocation_group !== false;
  }

  async function saveParticipantPageUi() {
    const cb = document.getElementById("h5ShowAllocationGroup");
    if (!cb) return;
    await api("/admin/participant-page-settings", "PUT", { show_allocation_group: cb.checked });
    resultBox.textContent = "[OK] 受試者頁顯示設定已更新";
  }

  async function loadGroupLabels() {
    const nameInp = document.getElementById("groupNameCurrent");
    const sel = document.getElementById("qrGroup");
    if (!nameInp || !sel) return;
    const data = await api("/admin/group-labels", "GET");
    window.__groupLabels = {
      GENAI: data.intervention_name || "干預組",
      HUMAN: data.control_name || "對照組"
    };
    const optGen = sel.querySelector("option[value='GENAI']");
    const optHum = sel.querySelector("option[value='HUMAN']");
    if (optGen) optGen.textContent = (window.__groupLabels.GENAI || "干預組") + "（干預組）";
    if (optHum) optHum.textContent = (window.__groupLabels.HUMAN || "對照組") + "（對照組）";
    nameInp.value = window.__groupLabels[sel.value] || "";
  }

  function onQrGroupChange() {
    const sel = document.getElementById("qrGroup");
    const nameInp = document.getElementById("groupNameCurrent");
    if (sel && nameInp) {
      const labels = window.__groupLabels || { GENAI: "干預組", HUMAN: "對照組" };
      nameInp.value = labels[sel.value] || "";
      nameInp.placeholder = sel.value === "GENAI" ? "請輸入干預組名稱" : "請輸入對照組名稱";
    }
    loadQrCurrent().then(() => onQrModeChange());
  }

  async function saveGroupLabels() {
    const sel = document.getElementById("qrGroup");
    const nameInp = document.getElementById("groupNameCurrent");
    if (!sel || !nameInp) return;
    const labels = window.__groupLabels || { GENAI: "干預組", HUMAN: "對照組" };
    const next = nameInp.value.trim();
    if (!next) { resultBox.textContent = "[ERROR] 請輸入組別名稱"; return; }
    if (sel.value === "GENAI") labels.GENAI = next;
    if (sel.value === "HUMAN") labels.HUMAN = next;
    await api("/admin/group-labels", "PUT", {
      intervention_name: labels.GENAI,
      control_name: labels.HUMAN,
      changed_by: document.getElementById("qrBy").value || "admin",
      reason: "manual group label update"
    });
    await loadGroupLabels();
  }

  async function saveQr() {
    const fileInput = document.getElementById("qrFile");
    if (fileInput && fileInput.files && fileInput.files.length > 0) {
      const fd = new FormData();
      fd.append("group", document.getElementById("qrGroup").value);
      fd.append("changed_by", document.getElementById("qrBy").value);
      fd.append("reason", document.getElementById("qrReason").value);
      fd.append("file", fileInput.files[0]);
      const res = await fetch("/admin/qr-config/upload", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { resultBox.textContent = "[ERROR] upload\\n" + JSON.stringify(data, null, 2); return; }
      resultBox.textContent = "[OK] 已上傳";
      await loadQrCurrent();
      return;
    }
    await api("/admin/qr-config", "POST", {
      group: document.getElementById("qrGroup").value,
      qr_mode: document.getElementById("qrMode").value,
      qr_value: document.getElementById("qrValue").value,
      changed_by: document.getElementById("qrBy").value,
      reason: document.getElementById("qrReason").value
    });
    await loadQrCurrent();
  }

  function overviewStatNum(n, kind, size) {
    const colorClass = kind === "invalid" ? "invalid" : (kind === "neutral" ? "neutral" : "valid");
    const sizeClass = size === "lg" ? "overview-num-lg" : "overview-num-md";
    return "<span class='overview-num " + sizeClass + " " + colorClass + "'>" + (Number(n) || 0) + "</span>";
  }

  function overviewStatFraction(n, cap, kind, size) {
    const num = overviewStatNum(n, kind, size);
    if (cap == null || cap === "") return num;
    return num + "<span class='overview-cap'>/" + escapeHtml(String(cap)) + "</span>";
  }

  function overviewStatRow(label, rowClass, inter, ctrl, total, numKind, groupCap, totalCap) {
    return "<div class='overview-stat-row " + rowClass + "'>"
      + "<div class='overview-stat-label'>" + escapeHtml(label) + "</div>"
      + "<div class='overview-stat-metrics'>"
      + "<span class='overview-metric'><span class='overview-metric-label'>干預</span>" + overviewStatFraction(inter, groupCap, numKind, "md") + "</span>"
      + "<span class='overview-metric'><span class='overview-metric-label'>對照</span>" + overviewStatFraction(ctrl, groupCap, numKind, "md") + "</span>"
      + "<span class='overview-metric overview-metric-total'><span class='overview-metric-label'>小計</span>"
      + overviewStatFraction(total, totalCap, numKind, "lg") + "</span>"
      + "</div></div>";
  }

  let recordsWeeklyChartInstance = null;

  function weeklyChartValueLabelPlugin() {
    return {
      id: "weeklyChartValueLabels",
      afterDatasetsDraw: function(chart) {
        const ctx = chart.ctx;
        const datasets = chart.data.datasets || [];
        ctx.save();
        ctx.font = "600 11px system-ui, -apple-system, sans-serif";
        ctx.textAlign = "center";

        function drawBarLabels(datasetIndex, textColor) {
          const meta = chart.getDatasetMeta(datasetIndex);
          if (!meta || meta.hidden) return;
          const dataset = datasets[datasetIndex];
          meta.data.forEach(function(bar, index) {
            const value = Number(dataset.data[index]) || 0;
            if (value <= 0) return;
            const props = bar.getProps(["x", "y", "base"], true);
            const midY = (props.y + props.base) / 2;
            ctx.fillStyle = textColor;
            ctx.textBaseline = "middle";
            ctx.fillText(String(value), props.x, midY);
          });
        }

        drawBarLabels(0, "#ffffff");
        drawBarLabels(1, "#ffffff");

        const metaInter = chart.getDatasetMeta(0);
        const metaCtrl = chart.getDatasetMeta(1);
        if (metaInter && metaCtrl && !metaInter.hidden) {
          metaInter.data.forEach(function(bar, index) {
            const interVal = Number(datasets[0].data[index]) || 0;
            const ctrlVal = Number(datasets[1].data[index]) || 0;
            const total = interVal + ctrlVal;
            if (total <= 0) return;
            const topBar = ctrlVal > 0 ? metaCtrl.data[index] : bar;
            const props = topBar.getProps(["x", "y"], true);
            ctx.fillStyle = "#334155";
            ctx.textBaseline = "bottom";
            ctx.font = "700 11px system-ui, -apple-system, sans-serif";
            ctx.fillText(String(total), props.x, props.y - 4);
          });
        }

        const lineIndex = datasets.findIndex(function(ds) {
          return ds.label && String(ds.label).indexOf("累計實際") >= 0;
        });
        if (lineIndex >= 0) {
          const lineMeta = chart.getDatasetMeta(lineIndex);
          const lineData = datasets[lineIndex].data || [];
          if (lineMeta && !lineMeta.hidden) {
            lineMeta.data.forEach(function(point, index) {
              const value = Number(lineData[index]) || 0;
              const prev = index > 0 ? Number(lineData[index - 1]) || 0 : -1;
              const isLast = index === lineData.length - 1;
              if (value <= 0) return;
              if (!(index === 0 || value !== prev || isLast)) return;
              const props = point.getProps(["x", "y"], true);
              ctx.fillStyle = "#15803d";
              ctx.textBaseline = "bottom";
              ctx.font = "700 11px system-ui, -apple-system, sans-serif";
              ctx.fillText(String(value), props.x, props.y - 6);
            });
          }
        }

        const planIndex = datasets.findIndex(function(ds) {
          return ds.label && String(ds.label).indexOf("累計計劃") >= 0;
        });
        if (planIndex >= 0) {
          const planMeta = chart.getDatasetMeta(planIndex);
          const planData = datasets[planIndex].data || [];
          if (planMeta && !planMeta.hidden && planData.length > 0) {
            const lastIdx = planData.length - 1;
            const value = Number(planData[lastIdx]) || 0;
            if (value > 0) {
              const point = planMeta.data[lastIdx];
              const props = point.getProps(["x", "y"], true);
              ctx.fillStyle = "#b45309";
              ctx.textBaseline = "bottom";
              ctx.font = "700 11px system-ui, -apple-system, sans-serif";
              ctx.fillText(String(value), props.x, props.y - 6);
            }
          }
        }

        ctx.restore();
      },
    };
  }

  function renderWeeklyChart(ov) {
    const canvas = document.getElementById("recordsWeeklyChart");
    const caption = document.getElementById("recordsWeeklyCaption");
    if (!canvas) return;
    try {
    const weeks = (ov && ov.weekly_tracking) || [];
    const start = ov && ov.recruitment_start_date;
    const planWeeks = (ov && ov.weekly_plan && ov.weekly_plan.weeks) || 20;
    const planPerWeek = (ov && ov.weekly_plan && ov.weekly_plan.per_week) || 60;
    const planTotal = (ov && ov.weekly_plan && ov.weekly_plan.total_target) || (planWeeks * planPerWeek);
    if (caption) {
      caption.textContent = start
        ? "招募起始：" + start + "（香港時間）· 柱狀為每週 Trial 有效入組（柱頂數字=該週合計，段內數字=干預/對照）· 虛線為累計計劃（第"
          + planWeeks + "周達 " + planTotal + " 人，" + planPerWeek + " 人/周）· 實線為 Trial 累計實際（旁邊數字標註；右軸刻度含計劃目標，勿與左軸柱高直接比對）"
        : "請在隨機化設定中配置招募起始日";
    }
    if (typeof Chart === "undefined") {
      if (caption) caption.textContent += "（圖表庫載入中，請重新整理）";
      return;
    }
    if (recordsWeeklyChartInstance) {
      recordsWeeklyChartInstance.destroy();
      recordsWeeklyChartInstance = null;
    }
    const labels = weeks.map(function(w) { return String(w.week_no); });
    const inter = weeks.map(function(w) { return Number(w.valid_intervention) || 0; });
    const ctrl = weeks.map(function(w) { return Number(w.valid_control) || 0; });
    const actualCumulative = weeks.map(function(w) { return Number(w.valid_cumulative) || 0; });
    const planCumulative = weeks.map(function(w) {
      return w.week_no <= planWeeks ? w.week_no * planPerWeek : null;
    });
    const actualMax = actualCumulative.reduce(function(m, v) { return Math.max(m, Number(v) || 0); }, 0);
    const planMax = planCumulative.reduce(function(m, v) { return Math.max(m, Number(v) || 0); }, 0);
    const weeklyMax = weeks.reduce(function(m, w) {
      return Math.max(m, (Number(w.valid_intervention) || 0) + (Number(w.valid_control) || 0));
    }, 0);
    recordsWeeklyChartInstance = new Chart(canvas, {
      type: "bar",
      plugins: [weeklyChartValueLabelPlugin()],
      data: {
        labels: labels,
        datasets: [
          { label: "干預組（每週）", data: inter, backgroundColor: "#dc2626", stack: "recruitment", order: 3, yAxisID: "y" },
          { label: "對照組（每週）", data: ctrl, backgroundColor: "#2563eb", stack: "recruitment", order: 3, yAxisID: "y" },
          {
            type: "line",
            label: "累計計劃（第" + planWeeks + "周 " + planTotal + " 人）",
            data: planCumulative,
            borderColor: "#b45309",
            backgroundColor: "#b45309",
            borderDash: [6, 4],
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            fill: false,
            order: 1,
            spanGaps: false,
            yAxisID: "y1",
          },
          {
            type: "line",
            label: "累計實際（Trial）",
            data: actualCumulative,
            borderColor: "#15803d",
            backgroundColor: "#15803d",
            borderWidth: 2,
            pointRadius: 2,
            pointHoverRadius: 5,
            fill: false,
            order: 2,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { position: "top" },
          tooltip: {
            callbacks: {
              afterTitle: function(items) {
                const idx = items[0] && items[0].dataIndex;
                if (idx == null || !weeks[idx]) return "";
                return weeks[idx].range_label || "";
              },
              label: function(ctx) {
                const label = ctx.dataset.label || "";
                const value = Number(ctx.parsed.y) || 0;
                if (ctx.dataset.type === "line") {
                  return label + "：" + value;
                }
                return label + "：" + value;
              },
              footer: function(items) {
                const idx = items[0] && items[0].dataIndex;
                if (idx == null || !weeks[idx]) return "";
                const w = weeks[idx];
                const interN = Number(w.valid_intervention) || 0;
                const ctrlN = Number(w.valid_control) || 0;
                const totalN = Number(w.valid_total) || 0;
                const cumN = Number(w.valid_cumulative) || 0;
                const lines = ["本週合計 " + totalN + " 人（干預 " + interN + " + 對照 " + ctrlN + "）"];
                if (totalN !== interN + ctrlN) {
                  lines.push("另有 " + (totalN - interN - ctrlN) + " 人未歸入干預/對照");
                }
                lines.push("累計實際 " + cumN + " 人");
                return lines;
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            title: { display: true, text: "招募週次" },
          },
          y: {
            stacked: true,
            beginAtZero: true,
            suggestedMax: Math.max(weeklyMax * 1.25, 4),
            ticks: { precision: 0 },
            title: { display: true, text: "每週入組人數（左軸）" },
            position: "left",
          },
          y1: {
            beginAtZero: true,
            suggestedMax: Math.max(planMax, actualMax) * 1.08,
            ticks: { precision: 0 },
            title: { display: true, text: "累計入組人數（右軸）" },
            position: "right",
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
    } catch (err) {
      if (caption) caption.textContent = (caption.textContent || "") + "（圖表渲染失敗）";
      if (resultBox) resultBox.textContent = "[ERROR] weekly chart\\n" + String(err && err.message ? err.message : err);
    }
  }

  function recordEffectiveStatus(row) {
    if (String(row.activation_status || "") === "voided") return "voided";
    const ts = String(row.trial_status || "trial");
    return ts === "nontrial" ? "nontrial" : "trial";
  }

  function renderStatusSelect(row) {
    const current = recordEffectiveStatus(row);
    const options = [
      ["trial", "Trial"],
      ["nontrial", "Non-trial"],
      ["voided", "作廢"],
    ];
    return "<select class='rec-status-select'>"
      + options.map(function(pair) {
        const val = pair[0];
        const label = pair[1];
        const selected = current === val ? " selected" : "";
        return "<option value='" + val + "'" + selected + ">" + label + "</option>";
      }).join("")
      + "</select>";
  }

  function renderRecordsOverview(ov) {
    const el = document.getElementById("recordsOverview");
    if (!el) return;
    if (!ov) {
      el.textContent = "暫無統計數據。";
      return;
    }
    const trialTotal = Number(ov.trial_enrolled != null ? ov.trial_enrolled : ov.valid_enrolled) || 0;
    const nontrialTotal = Number(ov.nontrial_enrolled) || 0;
    const voided = Number(ov.voided_count) || 0;
    const totalAll = Number(ov.total_enrolled != null ? ov.total_enrolled : ov.total_randomized) || 0;
    const trialInter = Number(ov.trial_intervention_count != null ? ov.trial_intervention_count : ov.valid_intervention_count) || 0;
    const trialCtrl = Number(ov.trial_control_count != null ? ov.trial_control_count : ov.valid_control_count) || 0;
    const nontrialInter = Number(ov.nontrial_intervention_count) || 0;
    const nontrialCtrl = Number(ov.nontrial_control_count) || 0;
    const voidInter = Number(ov.voided_intervention_count) || 0;
    const voidCtrl = Number(ov.voided_control_count) || 0;
    const maxTotal = ov.max_enrollment;
    const maxNum = maxTotal == null || maxTotal === "" ? null : Number(maxTotal);
    const trialGroupCap = maxNum && maxNum > 0 ? Math.floor(maxNum / 2) : null;
    const trialTotalCap = maxNum && maxNum > 0 ? maxNum : null;
    const statusText = ov.recruitment_open === false
      ? "<span style='color:#b45309;font-weight:600;'>已停招</span>"
      : "<span style='color:#15803d;font-weight:600;'>招募中</span>";
    const planWeeks = Number(ov.weekly_plan && ov.weekly_plan.weeks) || 20;
    const planPerWeek = Number(ov.weekly_plan && ov.weekly_plan.per_week) || 60;
    const planTotal = Number(ov.weekly_plan && ov.weekly_plan.total_target) || (planWeeks * planPerWeek);
    const planText = "計劃 " + planWeeks + " 週 × " + planPerWeek + " 人/週 = " + planTotal + " 人";
    el.innerHTML =
      overviewStatRow("Trial", "overview-stat-trial", trialInter, trialCtrl, trialTotal, "valid", trialGroupCap, trialTotalCap)
      + overviewStatRow("Non-trial", "overview-stat-nontrial", nontrialInter, nontrialCtrl, nontrialTotal, "neutral", null, null)
      + overviewStatRow("作廢", "overview-stat-voided", voidInter, voidCtrl, voided, "invalid", null, null)
      + "<div class='overview-stat-footer'>"
      + "隨機總計 " + overviewStatNum(totalAll, "valid", "md")
      + " · " + escapeHtml(planText)
      + " · 停招狀態 " + statusText
      + "</div>";
    renderWeeklyChart(ov);
  }

  function renderRecordsRows(items, startIndex) {
    const tbody = document.querySelector("#recordsTable tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    (items || []).forEach((row, idx) => {
      const tr = document.createElement("tr");
      const enc = JSON.stringify(row.enrollment_no);
      const codeVal = escapeHtml(row.subject_code || "");
      const phoneVal = escapeHtml(row.phone_number || "");
      const status = String(row.activation_status || "pending");
      const isVoided = status === "voided";
      const trialStatus = String(row.trial_status || "trial");
      tr.dataset.voided = isVoided ? "1" : "0";
      tr.dataset.trialStatus = trialStatus;
      tr.innerHTML =
        "<td>" + String((startIndex || 0) + idx + 1) + "</td><td>" + escapeHtml(row.enrollment_no) + "</td>"
        + "<td><input type='text' class='rec-subject-code-input' value='" + codeVal + "' placeholder='可選' /></td>"
        + "<td><input type='text' class='rec-phone-input' value='" + phoneVal + "' /></td><td>"
        + escapeHtml(row.site_id) + "</td><td>"
        + escapeHtml(row.recruiter_id || "") + "</td><td>" + escapeHtml(row.allocation_group) + "</td><td>"
        + renderStatusSelect(row) + "</td><td>"
        + escapeHtml(formatHkTime(row.randomized_at)) + "</td><td><div class='table-actions'>"
        + "<button type='button' class='secondary' style='margin:0;padding:6px 10px;font-size:12px' onclick='saveRecordSubjectCode(" + enc + ", this)'>保存編碼</button>"
        + "<button type='button' class='secondary' style='margin:0;padding:6px 10px;font-size:12px' onclick='saveRecordPhone(" + enc + ", this)'>修改手機號</button>"
        + "<button type='button' class='secondary' style='margin:0;padding:6px 10px;font-size:12px' onclick='saveRecordStatus(" + enc + ", this)'>保存狀態</button></div></td>";
      tbody.appendChild(tr);
    });
  }

  function renderRecordsPagination(totalItems, pageSize, currentPage) {
    const meta = document.getElementById("recordsPageMeta");
    const prevBtn = document.getElementById("recordsPrevBtn");
    const nextBtn = document.getElementById("recordsNextBtn");
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    if (meta) meta.textContent = "第 " + currentPage + "/" + totalPages + " 頁，共 " + totalItems + " 條";
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
  }

  function refillRecordsFilterOptions(items) {
    const siteSel = document.getElementById("recordsFilterSite");
    const groupSel = document.getElementById("recordsFilterGroup");
    if (!siteSel || !groupSel) return;
    const prevSite = siteSel.value;
    const prevGroup = groupSel.value;
    const sites = [...new Set((items || []).map(x => String(x.site_id || "")).filter(Boolean))].sort();
    const groups = [...new Set((items || []).map(x => String(x.allocation_group || "")).filter(Boolean))].sort();
    siteSel.innerHTML = '<option value="">全部站點</option>';
    groupSel.innerHTML = '<option value="">全部分組</option>';
    sites.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      siteSel.appendChild(opt);
    });
    groups.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      groupSel.appendChild(opt);
    });
    if (prevSite && [...siteSel.options].some(o => o.value === prevSite)) siteSel.value = prevSite;
    if (prevGroup && [...groupSel.options].some(o => o.value === prevGroup)) groupSel.value = prevGroup;
  }

  function applyRecordsFilter() {
    const all = window.__recordsItems || [];
    const site = (document.getElementById("recordsFilterSite")?.value || "").trim();
    const date = (document.getElementById("recordsFilterDate")?.value || "").trim();
    const group = (document.getElementById("recordsFilterGroup")?.value || "").trim();
    const recruiter = (document.getElementById("recordsFilterRecruiter")?.value || "").trim().toLowerCase();
    const filtered = all.filter(row => {
      if (site && String(row.site_id || "") !== site) return false;
      if (group && String(row.allocation_group || "") !== group) return false;
      if (date) {
        const d = hkDateFromIso(row.randomized_at);
        if (d !== date) return false;
      }
      if (recruiter && !String(row.recruiter_id || "").toLowerCase().includes(recruiter)) return false;
      return true;
    });
    window.__recordsFilteredItems = filtered;
    const pageSize = Number(document.getElementById("recordsPageSize")?.value || 20);
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    const current = Math.min(Math.max(1, window.__recordsCurrentPage || 1), totalPages);
    window.__recordsCurrentPage = current;
    const start = (current - 1) * pageSize;
    const end = start + pageSize;
    renderRecordsRows(filtered.slice(start, end), start);
    renderRecordsPagination(filtered.length, pageSize, current);
  }

  function resetRecordsFilter() {
    const ids = ["recordsFilterSite", "recordsFilterDate", "recordsFilterGroup", "recordsFilterRecruiter"];
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.value = "";
    });
    window.__recordsCurrentPage = 1;
    applyRecordsFilter();
  }

  async function loadRecords() {
    const tbody = document.querySelector("#recordsTable tbody");
    const overviewEl = document.getElementById("recordsOverview");
    if (!tbody) return;
    try {
      const data = await api("/admin/randomization-records", "GET");
      if (!data || !data.overview) throw new Error("invalid_records_response");
      renderRecordsOverview(data.overview);
      window.__recordsItems = data.items || [];
      refillRecordsFilterOptions(window.__recordsItems);
      applyRecordsFilter();
    } catch (err) {
      const msg = err && err.message ? String(err.message) : String(err);
      if (overviewEl) overviewEl.textContent = "載入失敗：" + msg + "（請重新登入或點「重新整理」）";
      if (resultBox) resultBox.textContent = "[ERROR] loadRecords\\n" + msg;
    }
  }

  function exportRecordsCsv() {
    const url = "/admin/randomization-records.csv";
    window.open(url, "_blank");
  }

  async function saveRecordSubjectCode(enrollmentNo, btn) {
    const tr = btn && btn.closest ? btn.closest("tr") : null;
    const inp = tr ? tr.querySelector("input.rec-subject-code-input") : null;
    if (!inp) { resultBox.textContent = "[ERROR] 未找到該行受試者編碼輸入框"; return; }
    await api("/admin/randomization-records/subject-code", "PATCH", {
      enrollment_no: enrollmentNo,
      subject_code: inp.value.trim(),
      changed_by: "admin",
      reason: "manual subject code (list)"
    });
    await loadRecords();
  }

  async function saveRecordPhone(enrollmentNo, btn) {
    const tr = btn && btn.closest ? btn.closest("tr") : null;
    const inp = tr ? tr.querySelector("input.rec-phone-input") : null;
    if (!inp) { resultBox.textContent = "[ERROR] 未找到該行手機號輸入框"; return; }
    const newPhone = inp.value.trim();
    if (!newPhone) { resultBox.textContent = "[ERROR] 請輸入新手機號"; return; }
    await api("/admin/randomization-records/phone", "PATCH", {
      enrollment_no: enrollmentNo,
      new_phone_number: newPhone,
      changed_by: "admin",
      reason: "manual correction (list)"
    });
    await loadRecords();
  }

  async function saveRecordStatus(enrollmentNo, btn) {
    const tr = btn && btn.closest ? btn.closest("tr") : null;
    const sel = tr ? tr.querySelector("select.rec-status-select") : null;
    if (!sel) { resultBox.textContent = "[ERROR] 未找到該行狀態選擇框"; return; }
    const newStatus = sel.value;
    const wasVoided = tr.dataset.voided === "1";
    const wasTrial = tr.dataset.trialStatus || "trial";
    const currentStatus = wasVoided ? "voided" : wasTrial;
    if (newStatus === currentStatus) {
      resultBox.textContent = "[OK] 狀態未變更";
      return;
    }
    let statusLabel = newStatus === "voided" ? "作廢" : (newStatus === "trial" ? "Trial" : "Non-trial");
    let tip = "確認將入組編號 " + enrollmentNo + " 的狀態改為「" + statusLabel + "」？";
    if (newStatus === "trial") tip += "（計入 998 上限）";
    if (newStatus === "nontrial") tip += "（不計 998 上限，手機號仍不可重複隨機）";
    if (newStatus === "voided") tip += "（作廢會保留歷史記錄並釋放手機號）";
    if (!confirm(tip)) return;

    if (newStatus === "voided") {
      await api("/admin/randomization-records/delete", "POST", {
        enrollment_no: enrollmentNo,
        voided_by: "admin",
        reason: "manual void (list status)"
      });
      await loadRecords();
      return;
    }

    if (wasVoided) {
      await api("/admin/randomization-records/delete", "POST", {
        enrollment_no: enrollmentNo,
        voided_by: "admin",
        reason: "manual restore (list status)"
      });
    }
    if (!wasVoided || newStatus !== wasTrial) {
      await api("/admin/randomization-records/trial-status", "PATCH", {
        enrollment_no: enrollmentNo,
        trial_status: newStatus,
        changed_by: "admin",
        reason: "manual trial status (list status)"
      });
    }
    await loadRecords();
  }

  async function loadAudits() {
    const tbody = document.querySelector("#auditTable tbody");
    if (!tbody) return;
    const data = await api("/admin/audit-logs", "GET");
    tbody.innerHTML = "";
    (data.items || []).forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + row.id + "</td><td>" + row.event_type + "</td><td>" + row.request_id + "</td><td>" + escapeHtml(formatHkTime(row.created_at)) + "</td>";
      tbody.appendChild(tr);
    });
  }

  function initRecordsPage() {
    const siteSel = document.getElementById("recordsFilterSite");
    const dateInp = document.getElementById("recordsFilterDate");
    const groupSel = document.getElementById("recordsFilterGroup");
    const recruiterInp = document.getElementById("recordsFilterRecruiter");
    const pageSizeSel = document.getElementById("recordsPageSize");
    const prevBtn = document.getElementById("recordsPrevBtn");
    const nextBtn = document.getElementById("recordsNextBtn");
    window.__recordsCurrentPage = 1;
    [siteSel, dateInp, groupSel].forEach(el => {
      if (!el) return;
      el.addEventListener("change", function() {
        window.__recordsCurrentPage = 1;
        applyRecordsFilter();
      });
    });
    if (recruiterInp) recruiterInp.addEventListener("input", function() {
      window.__recordsCurrentPage = 1;
      applyRecordsFilter();
    });
    if (pageSizeSel) pageSizeSel.addEventListener("change", function() {
      window.__recordsCurrentPage = 1;
      applyRecordsFilter();
    });
    if (prevBtn) prevBtn.addEventListener("click", function() {
      window.__recordsCurrentPage = Math.max(1, (window.__recordsCurrentPage || 1) - 1);
      applyRecordsFilter();
    });
    if (nextBtn) nextBtn.addEventListener("click", function() {
      window.__recordsCurrentPage = (window.__recordsCurrentPage || 1) + 1;
      applyRecordsFilter();
    });
    loadRecords();
    loadAudits();
  }

  function bootAdminPage() {
    if (PAGE === "settings") {
      const weeksEl = document.getElementById("weeklyPlanWeeks");
      const perWeekEl = document.getElementById("weeklyPlanPerWeek");
      if (weeksEl) weeksEl.addEventListener("input", updateWeeklyPlanTargetHint);
      if (perWeekEl) perWeekEl.addEventListener("input", updateWeeklyPlanTargetHint);
      loadSettings();
    }
    if (PAGE === "sites") {
      window.__batchPickSiteIds = [];
      loadSiteOverview();
      loadSitesAdminTable();
      renderBatchPickList();
    }
    if (PAGE === "qr") {
      loadGroupLabels();
      loadParticipantPageUi();
      loadQrCurrent().then(() => onQrModeChange());
    }
    if (PAGE === "records") initRecordsPage();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootAdminPage);
  } else {
    bootAdminPage();
  }
</script>
"""


def render_admin_page(page: PageId) -> str:
    panels = {
        "settings": panel_settings(),
        "sites": panel_sites(),
        "qr": panel_qr(),
        "records": panel_records(),
    }
    inner = panels[page]
    scripts = (
        ADMIN_SCRIPTS.replace("__PAGE__", page).replace(
            "__BATCH_MAX__", str(RECRUITMENT_BATCH_MAX_ACTIVE_SITES)
        )
    )
    chart_js = (
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>'
        if page == "records"
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>管理台 · {page}</title>
  <style>{ADMIN_CSS}</style>
</head>
<body>
  <div class="app-shell">
    {render_sidebar(page)}
    <main class="main">
      {inner}
      <h3 style="margin-top:28px;font-size:13px;color:#64748b;">介面回饋</h3>
      <pre id="result">ready</pre>
    </main>
  </div>
  {chart_js}
  {scripts}
</body>
</html>"""
