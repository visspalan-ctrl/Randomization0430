# Randomization0430
> 輕量隨機化分組系統（FastAPI + SQLite）
> 用於研究專案中的受試者隨機分配、站點管理與審計追蹤。

![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.1+-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 專案亮點

- 受試者隨機化分組（支援區組隨機）
- 管理後台（站點、密碼、分組設定、記錄查詢）
- 管理端登入保護（MVP：頁面登入 + Basic Auth 相容）
- 審計日誌記錄，便於追溯操作歷史
- 本地可快速啟動，適合小型研究專案驗證

---

## 線上頁面（本地）

- 受試者頁：`/h5/randomize`
- 管理頁：`/admin/web?page=settings`
- 登入頁：`/admin/login`
- API 文件：`/docs`

---

## 快速開始

### 1) 進入專案目錄
```bash
cd ~/Projects/Randomization0430
```

### 2) 安裝依賴
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3) 啟動服務
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4) 開啟頁面
- 首頁：<http://127.0.0.1:8000/>
- 登入頁：<http://127.0.0.1:8000/admin/login>
- 管理頁（需先登入）：先開啟 <http://127.0.0.1:8000/admin/login>，登入後進入 <http://127.0.0.1:8000/admin/web?page=settings>
- API 文件：<http://127.0.0.1:8000/docs>

預設管理員帳號（僅本地開發）：
- 用戶名稱：`admin`
- 密碼：`admin`

---

## 管理端認證說明

- 瀏覽器存取 `/admin/*` 未登入時，會跳轉到 `/admin/login`
- 登入成功後寫入 HttpOnly Cookie
- API 呼叫仍相容 HTTP Basic Auth
- 刪除站點時僅刪除站點設定與關聯密碼／批次，不會刪除歷史入組記錄（用於審計追溯）
- 建議透過環境變數覆蓋預設帳號密碼：

```bash
export ADMIN_USERNAME="your_admin_user"
export ADMIN_PASSWORD="your_admin_password"
```

---

## 專案結構

```text
Randomization0430/
├── app/                  # 核心應用程式碼
├── tests/                # 自動化測試
├── product_docs/         # 產品文件
├── uploads/qr/           # 二維碼資源目錄（執行時）
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 測試

```bash
python3 -m pytest -q tests/test_randomization_password_gate.py
```

---

## Roadmap

- [x] 基礎隨機化流程
- [x] 管理後台頁面
- [x] 管理端登入保護（MVP）
- [ ] 密碼雜湊升級（bcrypt/argon2）
- [ ] 去除明文密碼欄位
- [ ] 拆分路由模組，提升維護性

---

## 貢獻方式

歡迎提 Issue／PR。
如果你想參與改進，請先開一個 Issue 說明你的想法和目標。

---

## 免責聲明

本專案用於教學與研究流程驗證，請勿直接用於生產臨床場景而不做安全與合規增強。
