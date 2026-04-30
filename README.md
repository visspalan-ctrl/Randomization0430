# Randomization0430

轻量随机化分组系统（FastAPI + SQLite）。

## 目录说明

- `app/`: 核心应用代码（API、管理页、模型、状态逻辑）
- `tests/`: 自动化测试
- `product_docs/`: 产品与功能文档
- `uploads/qr/`: 二维码上传目录（运行时文件）

## 快速启动

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 管理端登录（MVP）

- 所有 `/admin/*` 接口与页面使用 HTTP Basic Auth 保护。
- 默认账号密码（仅本地开发）：`admin` / `admin`
- 页面登录入口：`/admin/login`
- 登录成功后会写入 HttpOnly Cookie，可直接访问 `/admin/web?page=settings`
- 建议通过环境变量覆盖：

```bash
export ADMIN_USERNAME="your_admin_user"
export ADMIN_PASSWORD="your_admin_password"
```

## 代码规范（当前项目）

- Python 命名使用 `snake_case`
- 函数声明使用类型提示
- 关键复杂逻辑建议使用中英双语注释
- 时间字段统一为 `created_at` / `updated_at`

## 备注

- `randomization.db` 与 `uploads/qr/*` 属于本地运行数据，不建议直接纳入版本控制。
