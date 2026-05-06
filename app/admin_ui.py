"""管理員後台：左侧导航 + 分頁面内容（由 /admin/web?page= 驱动）。"""

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
#recordsScrollBox {
  max-height: none;
  height: 760px; /* roughly 20 rows visible before scrolling */
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
#qrPreview {
  max-width: 240px;
  max-height: 240px;
  border-radius: 10px;
  border: 1px solid var(--border);
  margin-top: 10px;
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
        <p>最多 {PRESET_SITE_COUNT} 站 · 首次预建 {PRESET_SITE_INITIAL_COUNT} 站 · 单批次 ≤{RECRUITMENT_BATCH_MAX_ACTIVE_SITES} 站 · 口令按香港同日時間窗</p>
      </div>
      <nav class="nav">
        {_nav_link("settings", active, base + "settings", "⚙", "隨機化設置")}
        {_nav_link("sites", active, base + "sites", "◎", "站點与口令")}
        {_nav_link("qr", active, base + "qr", "▣", "WhatsApp 二維碼")}
        {_nav_link("records", active, base + "records", "☰", "隨機化分組記錄")}
      </nav>
      <div class="sidebar-footer">
        <a href="/docs" target="_blank">API 文件 (Swagger)</a>
        · <a href="/h5/randomize" target="_blank">受試者页</a>
      </div>
    </aside>
    """


def panel_settings() -> str:
    return """
    <div class="page-header">
      <h2>隨機化設置</h2>
      <p class="lead">下方概覽展示服务端當前生效值；在「參數」中修改后儲存，将立即作用于后续隨機化。</p>
    </div>
    <div class="card">
      <h3>當前參數概覽</h3>
      <div id="settingsOverview" class="muted" style="margin-top:8px;">加載中…</div>
      <button type="button" class="secondary" style="margin-top:12px;" onclick="loadSettings()">重新整理概覽并同步表单</button>
    </div>
    <div class="card">
      <h3>參數</h3>
      <label>随机人数上限（留空表示不限制）</label>
      <input id="maxEnrollment" placeholder="例如 5000" />
      <label>区組大小（逗号分隔，须为偶数）</label>
      <input id="blockSizes" value="4,8,12" />
      <label>更新人</label>
      <input id="settingsUpdatedBy" value="admin" />
      <button type="button" onclick="saveSettings()">儲存設置</button>
      <button type="button" class="secondary" onclick="loadSettings()">重新加載</button>
    </div>
    """


def panel_sites() -> str:
    return f"""
    <div class="page-header">
      <h2>站點与口令</h2>
      <p class="lead">在站點一览中点击「啟用」加入待选列表（最多 <strong>{RECRUITMENT_BATCH_MAX_ACTIVE_SITES}</strong> 个），再点「開啟新批次」；或仍可通过 <a href="/docs" target="_blank">Swagger</a> 调用接口。口令须落在<strong>同一香港日历日</strong>内的起止時間（本地時間选择器）。</p>
    </div>
    <div class="card">
      <h4 class="subhead subhead-first">統計概覽</h4>
      <div id="siteOverview" class="muted" style="margin-bottom:10px;">加載中…</div>
      <button type="button" class="secondary" onclick="loadSiteOverview()">重新整理概覽</button>

      <h4 class="subhead">站點設置</h4>
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
          <select id="editSiteSelect" onchange="syncEditNameFromSelect(); document.getElementById('pwdSiteSelect').value = this.value;">
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
        <button type="button" class="btn-save-inline" onclick="saveSiteName()">保存修改</button>
      </div>
      <label for="pwdRaw">口令</label>
      <div class="password-field-wrap" id="pwdRawWrap">
        <input id="pwdRaw" type="password" autocomplete="new-password" />
        <button type="button" class="pwd-toggle" id="pwdToggle" onclick="togglePwdVisibility()" title="顯示口令" aria-label="顯示或隱藏口令">
          <span class="icon-eye" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg></span>
          <span class="icon-eye-off" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg></span>
        </button>
      </div>
      <p class="muted" style="margin:6px 0 0;font-size:12px;">要求：至少 6 位，且只能为数字（例如 123456）。</p>
      <div class="row">
        <div>
          <label>生效开始（本地）</label>
          <input id="pwdWinStart" type="datetime-local" />
        </div>
        <div>
          <label>生效结束（本地）</label>
          <input id="pwdWinEnd" type="datetime-local" />
        </div>
      </div>
      <div class="site-name-row" style="margin-top:10px;">
        <div class="field-name">
          <label>變更人</label>
          <input id="pwdBy" value="admin" />
        </div>
        <button type="button" class="btn-save-inline" onclick="savePassword()">儲存口令</button>
      </div>

      <h4 class="subhead">站點一览</h4>
      <button type="button" class="secondary" onclick="loadSitesAdminTable()">重新整理表格</button>
      <div class="scroll-box" style="margin-top:12px;">
        <table class="data" id="sitesAdminTable">
          <thead><tr><th>站點ID</th><th>名稱</th><th>當前狀態</th><th>口令</th><th>生效起(UTC)</th><th>生效止(UTC)</th><th>操作</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>

      <h4 style="margin-top:16px;margin-bottom:8px;font-size:12px;font-weight:600;color:#64748b;">已啟用站點</h4>
      <div id="batchPickList" class="batch-pick-zone"></div>
      <p class="muted" style="margin:8px 0 0;">点击表格中的「啟用/取消啟用」将立即同步到當前开放批次。</p>

    </div>
    """


def panel_qr() -> str:
    return """
    <div class="page-header">
      <h2>WhatsApp 二維碼</h2>
      <p class="lead">按干预組 / 對照組維護展示用二維碼。支援 URL 或上傳图片。</p>
    </div>
    <div class="card">
      <h3>組別与资源</h3>
      <label>組別与名稱</label>
      <div class="site-name-row">
        <div class="field-site">
          <select id="qrGroup" onchange="onQrGroupChange()">
            <option value="GENAI">干预組（干预組）</option>
            <option value="HUMAN">對照組（對照組）</option>
          </select>
        </div>
        <div class="field-name">
          <input id="groupNameCurrent" placeholder="請輸入組別名稱" />
        </div>
        <button type="button" class="btn-save-inline secondary" onclick="saveGroupLabels()">儲存</button>
      </div>
      <div class="participant-ui-card">
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
      <label>二維碼链接（URL）</label>
      <input id="qrValue" placeholder="https://wa.me/..." />
      <label>或上傳图片</label>
      <input id="qrFile" type="file" accept="image/png,image/jpeg,image/webp" />
      <label>變更人</label>
      <input id="qrBy" value="admin" />
      <label>原因</label>
      <input id="qrReason" value="manual update" />
      <button type="button" onclick="saveQr()">儲存</button>
      <button type="button" class="secondary" onclick="loadQrCurrent()">讀取當前</button>
      <div style="margin-top:14px;">
        <div class="muted">當前配置</div>
        <div id="qrCurrentText" class="muted" style="margin-top:4px;">—</div>
        <img id="qrPreview" alt="preview" style="display:none;" />
      </div>
    </div>
    """


def panel_records() -> str:
    return """
    <div class="page-header">
      <h2>隨機化分組記錄</h2>
      <p class="lead">查詢入組記錄；在列表中可直接修改手機號或作廢記錄（保留歷史，不影響後續隨機化序列）。審計以「admin」及預設原因記錄。</p>
    </div>
    <div class="card">
      <h3>入組概覽</h3>
      <div id="recordsOverview" class="muted" style="margin-top:8px;">加載中…</div>
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
          <label>日期</label>
          <input id="recordsFilterDate" type="date" />
        </div>
        <div style="flex:1 1 0;min-width:0;">
          <label>分組</label>
          <select id="recordsFilterGroup">
            <option value="">全部分組</option>
          </select>
        </div>
        <div style="flex:1 1 0;min-width:0;">
          <label>招募員ID</label>
          <input id="recordsFilterRecruiter" placeholder="輸入招募員ID關鍵字" />
        </div>
      </div>
      <div class="scroll-box" id="recordsScrollBox" style="margin-top:12px;">
        <table class="data" id="recordsTable">
          <thead><tr><th>编号</th><th>入組编号</th><th>手機號</th><th>站點</th><th>招募员ID</th><th>分組</th><th>狀態</th><th>時間</th><th>操作</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:8px;">
          <label for="recordsPageSize" style="margin:0;">每页</label>
          <select id="recordsPageSize" style="width:auto;max-width:none;padding:6px 8px;">
            <option value="20">20</option>
            <option value="50">50</option>
          </select>
          <span id="recordsPageMeta" class="muted">—</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <button type="button" class="secondary" id="recordsPrevBtn" style="margin:0;padding:6px 10px;font-size:12px;">上一页</button>
          <button type="button" class="secondary" id="recordsNextBtn" style="margin:0;padding:6px 10px;font-size:12px;">下一页</button>
        </div>
      </div>
    </div>
    <div class="card">
      <h3>審計日誌</h3>
      <button type="button" class="secondary" onclick="loadAudits()">重新整理日誌</button>
      <div class="scroll-box" style="margin-top:12px;">
        <table class="data" id="auditTable">
          <thead><tr><th>ID</th><th>事件</th><th>请求ID</th><th>時間</th></tr></thead>
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
    const options = { method: method || "GET", headers: { "Content-Type": "application/json" } };
    if (body) options.body = JSON.stringify(body);
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      resultBox.textContent = "[ERROR] " + path + "\\n" + JSON.stringify(data, null, 2);
      throw new Error(data.detail || "request_failed");
    }
    resultBox.textContent = "[OK] " + path + "\\n" + JSON.stringify(data, null, 2);
    return data;
  }

  function csvToInts(raw) {
    return raw.split(",").map(x => Number(x.trim())).filter(x => !Number.isNaN(x));
  }

  function renderSettingsOverview(data) {
    const el = document.getElementById("settingsOverview");
    if (!el) return;
    const maxE = data.max_enrollment;
    const maxLabel = maxE == null || maxE === "" ? "不限制" : String(maxE);
    const blocks = (data.block_sizes || []).length ? (data.block_sizes || []).join("、") : "—";
    const by = data.updated_by ? escapeHtml(String(data.updated_by)) : "—";
    const at = data.updated_at ? escapeHtml(String(data.updated_at)) : "—";
    el.innerHTML =
      "入組人数上限 <strong>" + escapeHtml(maxLabel) + "</strong>；区組大小 <strong>" + escapeHtml(blocks)
      + "</strong>。<br/>最近更新人 <strong>" + by + "</strong>；更新時間 <code style='font-size:12px'>" + at + "</code>。";
  }

  async function loadSettings() {
    if (!document.getElementById("maxEnrollment")) return;
    const data = await api("/admin/randomization-settings", "GET");
    renderSettingsOverview(data);
    document.getElementById("maxEnrollment").value = data.max_enrollment ?? "";
    document.getElementById("blockSizes").value = (data.block_sizes || []).join(",");
  }
  async function saveSettings() {
    const maxRaw = document.getElementById("maxEnrollment").value.trim();
    await api("/admin/randomization-settings", "PUT", {
      max_enrollment: maxRaw === "" ? null : Number(maxRaw),
      block_sizes: csvToInts(document.getElementById("blockSizes").value),
      updated_by: document.getElementById("settingsUpdatedBy").value
    });
    await loadSettings();
  }

  function localDatetimeToIso(elId) {
    const v = document.getElementById(elId);
    if (!v || !v.value) return null;
    return new Date(v.value).toISOString();
  }

  function ensurePasswordWindowDefaults() {
    const startEl = document.getElementById("pwdWinStart");
    const endEl = document.getElementById("pwdWinEnd");
    if (!startEl || !endEl) return;
    if (startEl.value && endEl.value) return;
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const y = now.getFullYear();
    const m = pad(now.getMonth() + 1);
    const d = pad(now.getDate());
    if (!startEl.value) startEl.value = y + "-" + m + "-" + d + "T00:00";
    if (!endEl.value) endEl.value = y + "-" + m + "-" + d + "T23:59";
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

  function syncEditNameFromSelect() {
    const sel = document.getElementById("editSiteSelect");
    const inp = document.getElementById("editSiteName");
    const idInp = document.getElementById("editSiteIdInput");
    if (!sel || !inp) return;
    const row = (window.__sitesList || []).find(s => s.site_id === sel.value);
    if (idInp) idInp.value = sel.value || "";
    inp.value = row ? row.site_name : "";
  }

  function syncEditSelectFromIdInput() {
    const idInp = document.getElementById("editSiteIdInput");
    const sel = document.getElementById("editSiteSelect");
    if (!idInp || !sel) return;
    const v = idInp.value.trim();
    if (!v) return;
    if ([...sel.options].some(o => o.value === v)) sel.value = v;
  }

  async function loadSiteOverview() {
    const el = document.getElementById("siteOverview");
    if (!el) return;
    const res = await fetch("/admin/site-recruitment-overview");
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { el.textContent = "概覽加載失败"; return; }
    const warnBatch = data.current_open_batch_site_count > data.max_parallel_sites_recommended
      ? " <span style='color:#b45309'>（批次站點数超建议）</span>" : "";
    const warnPwd = data.sites_with_active_password_at_ref > data.max_parallel_sites_recommended
      ? " <span style='color:#b45309'>（有效口令站點数超建议）</span>" : "";
    el.innerHTML = "预设 <strong>" + data.preset_site_capacity + "</strong>；已登记 <strong>" + data.registered_site_count
      + "</strong>。参考 UTC：<strong>" + data.reference_time_utc + "</strong>；口令有效站點 <strong>"
      + data.sites_with_active_password_at_ref + "</strong>" + warnPwd
      + "。开放批次 ID <strong>" + (data.current_open_batch_id ?? "无") + "</strong>，本批次站點数 <strong>"
      + data.current_open_batch_site_count + "</strong>" + warnBatch + "。";
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
      btn.title = "顯示口令";
      btn.setAttribute("aria-label", "顯示口令");
      return;
    }
    textEl.textContent = raw || "—";
    wrap.setAttribute("data-revealed", "1");
    btn.title = "隱藏口令";
    btn.setAttribute("aria-label", "隱藏口令");
  }

  function renderBatchPickList() {
    const el = document.getElementById("batchPickList");
    if (!el) return;
    const arr = window.__batchPickSiteIds || [];
    const meta = window.__sitesList || [];
    if (arr.length === 0) {
      el.innerHTML = '<p class="muted" style="margin:0">未选择站點。在上方表格「操作」列点击「啟用」加入，最多 ' + BATCH_MAX + ' 个。</p>';
      return;
    }
    let html = '<p class="muted" style="margin:0 0 8px">已选 <strong>' + arr.length + "</strong> / " + BATCH_MAX + '：</p><ul class="batch-pick-chips">';
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
        resultBox.textContent = "[ERROR] 最多可选 " + BATCH_MAX + " 个站點";
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
      resultBox.textContent = "[ERROR] 請先在表格中啟用至少一个站點";
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
        + "</span><button type='button' class='pwd-mini-toggle' title='顯示口令' aria-label='顯示口令' onclick='toggleSiteTablePassword(this)'>"
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
        (row.window_start || "—") +
        "</span></td><td><span class='table-time'>" +
        (row.window_end || "—") +
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
    if (!confirm("确认刪除站點 " + siteId + "？")) return;
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
    btn.title = revealed ? "隱藏口令" : "顯示口令";
    btn.setAttribute("aria-label", revealed ? "隱藏口令" : "顯示口令");
  }

  function resetPwdFieldVisibility() {
    const wrap = document.getElementById("pwdRawWrap");
    const inp = document.getElementById("pwdRaw");
    const btn = document.getElementById("pwdToggle");
    if (!wrap || !inp || !btn) return;
    wrap.classList.remove("is-revealed");
    inp.type = "password";
    btn.title = "顯示口令";
    btn.setAttribute("aria-label", "顯示或隱藏口令");
  }

  async function saveSiteName() {
    const idInp = document.getElementById("editSiteIdInput");
    const typed = idInp ? idInp.value.trim() : "";
    const selectedId = document.getElementById("editSiteSelect").value.trim();
    const sid = typed || selectedId;
    if (!selectedId) { resultBox.textContent = "[ERROR] 請先从下拉选择已有站點；新增请点「新增站點」按钮"; return; }
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
  }

  async function addSite() {
    const idInp = document.getElementById("addSiteIdInput");
    const nameInp = document.getElementById("addSiteNameInput");
    const sid = idInp ? idInp.value.trim() : "";
    const name = nameInp ? nameInp.value.trim() : "";
    if (!sid) { resultBox.textContent = "[ERROR] 新增站點需填写站點 ID"; return; }
    if (!name) { resultBox.textContent = "[ERROR] 新增站點需填写名稱"; return; }
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
    if (!sid) { resultBox.textContent = "[ERROR] 請先选择口令对应的站點"; return; }
    const ws = localDatetimeToIso("pwdWinStart");
    const we = localDatetimeToIso("pwdWinEnd");
    const pwd = document.getElementById("pwdRaw").value;
    if (!ws || !we) { resultBox.textContent = "[ERROR] 請填寫口令生效开始和结束時間"; return; }
    if (!/^\d{6,}$/.test(pwd || "")) { resultBox.textContent = "[ERROR] 口令要求：至少 6 位且只能为数字"; return; }
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

  async function loadQrCurrent() {
    const text = document.getElementById("qrCurrentText");
    const img = document.getElementById("qrPreview");
    if (!text) return;
    const group = document.getElementById("qrGroup").value;
    const data = await api("/admin/qr-configs", "GET");
    const current = (data.items || []).find(x => x.group_type === group);
    if (!current) { text.textContent = "無配置"; if (img) img.style.display = "none"; return; }
    document.getElementById("qrValue").value = current.qr_value || "";
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
      GENAI: data.intervention_name || "干预組",
      HUMAN: data.control_name || "對照組"
    };
    const optGen = sel.querySelector("option[value='GENAI']");
    const optHum = sel.querySelector("option[value='HUMAN']");
    if (optGen) optGen.textContent = (window.__groupLabels.GENAI || "干预組") + "（干预組）";
    if (optHum) optHum.textContent = (window.__groupLabels.HUMAN || "對照組") + "（對照組）";
    nameInp.value = window.__groupLabels[sel.value] || "";
  }

  function onQrGroupChange() {
    const sel = document.getElementById("qrGroup");
    const nameInp = document.getElementById("groupNameCurrent");
    if (sel && nameInp) {
      const labels = window.__groupLabels || { GENAI: "干预組", HUMAN: "對照組" };
      nameInp.value = labels[sel.value] || "";
      nameInp.placeholder = sel.value === "GENAI" ? "請輸入干预組名稱" : "請輸入對照組名稱";
    }
    loadQrCurrent();
  }

  async function saveGroupLabels() {
    const sel = document.getElementById("qrGroup");
    const nameInp = document.getElementById("groupNameCurrent");
    if (!sel || !nameInp) return;
    const labels = window.__groupLabels || { GENAI: "干预組", HUMAN: "對照組" };
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
      qr_value: document.getElementById("qrValue").value,
      changed_by: document.getElementById("qrBy").value,
      reason: document.getElementById("qrReason").value
    });
    await loadQrCurrent();
  }

  function renderRecordsOverview(ov) {
    const el = document.getElementById("recordsOverview");
    if (!el) return;
    if (!ov) {
      el.textContent = "暂无統計数据。";
      return;
    }
    const total = Number(ov.total_enrolled) || 0;
    const valid = Number(ov.valid_enrolled ?? total) || 0;
    const voided = Number(ov.voided_count) || 0;
    const inter = Number(ov.intervention_count) || 0;
    const ctrl = Number(ov.control_count) || 0;
    const other = Number(ov.other_group_count) || 0;
    let html =
      "總記錄 <strong>" + total + "</strong> 人（有效 <strong>" + valid + "</strong>，作廢 <strong>" + voided + "</strong>）；其中干预組（GENAI）<strong>" + inter
      + "</strong> 人，對照組（HUMAN）<strong>" + ctrl + "</strong> 人。";
    if (other > 0) {
      html += " <span class='muted'>另有其他分組記錄 " + other + " 條。</span>";
    }
    el.innerHTML = html;
  }

  function renderRecordsRows(items, startIndex) {
    const tbody = document.querySelector("#recordsTable tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    (items || []).forEach((row, idx) => {
      const tr = document.createElement("tr");
      const enc = JSON.stringify(row.enrollment_no);
      const phoneVal = escapeHtml(row.phone_number || "");
      const status = String(row.activation_status || "pending");
      const isVoided = status === "voided";
      const statusText = isVoided ? "作廢" : "有效";
      const actionText = isVoided ? "恢復" : "作廢";
      tr.innerHTML =
        "<td>" + String((startIndex || 0) + idx + 1) + "</td><td>" + escapeHtml(row.enrollment_no) + "</td><td><input type='text' class='rec-phone-input' value='" + phoneVal + "' /></td><td>"
        + escapeHtml(row.site_id) + "</td><td>"
        + escapeHtml(row.recruiter_id || "") + "</td><td>" + escapeHtml(row.allocation_group) + "</td><td>" + statusText + "</td><td>"
        + escapeHtml(String(row.randomized_at || "")) + "</td><td><div class='table-actions'>"
        + "<button type='button' class='secondary' style='margin:0;padding:6px 10px;font-size:12px' onclick='saveRecordPhone(" + enc + ", this)'>修改手機號</button>"
        + "<button type='button' class='danger' style='margin:0;padding:6px 10px;font-size:12px' onclick='voidRecordRow(" + enc + ", " + (isVoided ? "true" : "false") + ")'>" + actionText + "</button></div></td>";
      tbody.appendChild(tr);
    });
  }

  function renderRecordsPagination(totalItems, pageSize, currentPage) {
    const meta = document.getElementById("recordsPageMeta");
    const prevBtn = document.getElementById("recordsPrevBtn");
    const nextBtn = document.getElementById("recordsNextBtn");
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    if (meta) meta.textContent = "第 " + currentPage + "/" + totalPages + " 页，共 " + totalItems + " 条";
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
        const d = String(row.randomized_at || "").slice(0, 10);
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
    if (!tbody) return;
    const data = await api("/admin/randomization-records", "GET");
    renderRecordsOverview(data.overview);
    window.__recordsItems = data.items || [];
    refillRecordsFilterOptions(window.__recordsItems);
    applyRecordsFilter();
  }

  function exportRecordsCsv() {
    const url = "/admin/randomization-records.csv";
    window.open(url, "_blank");
  }

  async function saveRecordPhone(enrollmentNo, btn) {
    const tr = btn && btn.closest ? btn.closest("tr") : null;
    const inp = tr ? tr.querySelector("input.rec-phone-input") : null;
    if (!inp) { resultBox.textContent = "[ERROR] 未找到该行手機號输入框"; return; }
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

  async function voidRecordRow(enrollmentNo, isVoided) {
    const tip = isVoided
      ? "确认恢復入組编号 " + enrollmentNo + " 的記錄為有效狀態？"
      : "确认作廢入組编号 " + enrollmentNo + " 的記錄？作廢會保留歷史記錄並不影響後續隨機化。";
    if (!confirm(tip)) return;
    await api("/admin/randomization-records/delete", "POST", {
      enrollment_no: enrollmentNo,
      voided_by: "admin",
      reason: isVoided ? "manual restore (list)" : "manual void (list)"
    });
    await loadRecords();
  }

  async function loadAudits() {
    const tbody = document.querySelector("#auditTable tbody");
    if (!tbody) return;
    const data = await api("/admin/audit-logs", "GET");
    tbody.innerHTML = "";
    (data.items || []).forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + row.id + "</td><td>" + row.event_type + "</td><td>" + row.request_id + "</td><td>" + (row.created_at || "") + "</td>";
      tbody.appendChild(tr);
    });
  }

  document.addEventListener("DOMContentLoaded", function() {
    if (PAGE === "settings") loadSettings();
    if (PAGE === "sites") {
      window.__batchPickSiteIds = [];
      ensurePasswordWindowDefaults();
      loadSiteOverview();
      loadSitesAdminTable();
      renderBatchPickList();
    }
    if (PAGE === "qr") { loadGroupLabels(); loadParticipantPageUi(); loadQrCurrent(); }
    if (PAGE === "records") {
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
  });
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
      <h3 style="margin-top:28px;font-size:13px;color:#64748b;">接口反馈</h3>
      <pre id="result">ready</pre>
    </main>
  </div>
  {scripts}
</body>
</html>"""
