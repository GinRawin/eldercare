# eldercare-api

老年人饮食与健康管理后端 API，基于 FastAPI + PostgreSQL，供 Dify 调用。

## 快速启动（推荐 Docker）

```bash
cp .env.example .env
docker compose up --build
```

启动后访问：
- API 文档：http://localhost:8000/docs
- OpenAPI JSON（供 Dify 导入）：http://localhost:8000/openapi.json
- 健康检查：http://localhost:8000/health

## 本地开发（不用 Docker）

### 前置条件

- Python 3.12+
- uv
- PostgreSQL 16（或用 `docker compose up db` 单独跑数据库）

### 安装依赖

```bash
uv sync
```

### 配置环境变量

```bash
cp .env.example .env
# 修改 .env 中的 DATABASE_URL 指向你的 PostgreSQL
```

### 跑数据库迁移

```bash
uv run alembic upgrade head
```

### 启动服务

```bash
uv run uvicorn app.main:app --reload
```

## 分工约定（后端组）

| 成员 | 负责模块 |
|------|----------|
| 成员 1 | FastAPI 框架、profiles 接口、reminders 接口、OpenAPI 对接 Dify |
| 成员 2 | DDInter 数据导入、risk/check 接口、数据库 schema 细化 |

## 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/profiles/{elder_id} | 查询老人档案 |
| POST | /api/v1/profiles | 创建老人档案 |
| PATCH | /api/v1/profiles/{elder_id} | 更新老人档案 |
| POST | /api/v1/risk/check | 药物食物风险检查 |
| POST | /api/v1/intake-logs | 保存饮食用药日志 |
| GET | /api/v1/intake-logs | 查询近期日志 |
| GET | /api/v1/reminders/due | 查询待处理提醒 |
| POST | /api/v1/reminders/rules | 创建提醒规则 |
| POST | /api/v1/reminders/{id}/complete | 标记已完成 |
| POST | /api/v1/reminders/{id}/snooze | 标记稍后 |
| POST | /api/v1/reminders/{id}/skip | 标记跳过 |

## 数据库迁移（新增表或字段时）

```bash
uv run alembic revision --autogenerate -m "描述改动"
uv run alembic upgrade head
```

## DDInter 数据导入

见 `scripts/import_ddinter.py`（由后端成员 2 完善）。DDInter 2.0 仅用于非商业研究演示，商用前需确认授权。

## 运行测试

```bash
uv run pytest
```

## 代码规范

```bash
uv run ruff check .
uv run ruff format .
```

## 部署（华为云 ECS）

`eldercare-api` 不直接暴露公网，通过 Docker 内网供 Dify 访问：`http://eldercare-api:8000`

生产部署时 `DATABASE_URL` 等敏感信息通过环境变量注入，不要写入代码。
