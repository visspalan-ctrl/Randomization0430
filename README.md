# Randomization0430
> 轻量随机化分组系统（FastAPI + SQLite）
> 用于研究项目中的受试者随机分配、站点管理与审计追踪。

![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.1+-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 项目亮点

- 受试者随机化分组（支持区组随机）
- 管理后台（站点、口令、分组设置、记录查询）
- 管理端登录保护（MVP：页面登录 + Basic Auth 兼容）
- 审计日志记录，便于追溯操作历史
- 本地可快速启动，适合小型研究项目验证

---

## 在线页面（本地）

- 受试者页：`/h5/randomize`
- 管理页：`/admin/web?page=settings`
- 登录页：`/admin/login`
- API 文档：`/docs`

---

## 快速开始

### 1) 进入项目目录
```bash
cd ~/Projects/Randomization0430
```

### 2) 安装依赖
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3) 启动服务
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4) 打开页面
- 首页：<http://127.0.0.1:8000/>
- 登录页：<http://127.0.0.1:8000/admin/login>
- 管理页（需先登录）：先打开 <http://127.0.0.1:8000/admin/login>，登录后进入 <http://127.0.0.1:8000/admin/web?page=settings>
- API 文档：<http://127.0.0.1:8000/docs>

默认管理员账号（仅本地开发）：
- 用户名：`admin`
- 密码：`admin`

---

## 管理端认证说明

- 浏览器访问 `/admin/*` 未登录时，会跳转到 `/admin/login`
- 登录成功后写入 HttpOnly Cookie
- API 调用仍兼容 HTTP Basic Auth
- 删除站点时仅删除站点配置与关联口令/批次，不会删除历史入组记录（用于审计追溯）
- 建议通过环境变量覆盖默认账号密码：

```bash
export ADMIN_USERNAME="your_admin_user"
export ADMIN_PASSWORD="your_admin_password"
```

---

## 项目结构

```text
Randomization0430/
├── app/                  # 核心应用代码
├── tests/                # 自动化测试
├── product_docs/         # 产品文档
├── uploads/qr/           # 二维码资源目录（运行时）
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 测试

```bash
python3 -m pytest -q tests/test_randomization_password_gate.py
```

---

## Roadmap

- [x] 基础随机化流程
- [x] 管理后台页面
- [x] 管理端登录保护（MVP）
- [ ] 密码哈希升级（bcrypt/argon2）
- [ ] 去除明文口令字段
- [ ] 拆分路由模块，提升维护性

---

## 贡献方式

欢迎提 Issue / PR。
如果你想参与改进，请先开一个 Issue 说明你的想法和目标。

---

## 免责声明

本项目用于教学与研究流程验证，请勿直接用于生产临床场景而不做安全与合规增强。
