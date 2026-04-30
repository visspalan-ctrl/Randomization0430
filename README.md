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

### 1) 环境准备
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
