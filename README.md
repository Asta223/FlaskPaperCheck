# 工厂管理系统（FlaskPaperCheck 改造）

基于 Flask 的内网单机小型工厂管理系统：人员/部门/权限(RBAC)/考勤/生产/物料/仓库/文件/站内聊天。

P0 为 9 大业务模块；P1 增量已交付：请假申请与审批、迟到早退判定、部门数据权限隔离、工单领料关联、库存变动流水与预警站内推送、文件部门级可见/检索/预览、聊天历史分页与精确未读、全局操作日志、CSV 导出。详见 `docs/PRD-P1.md` 与 `docs/ARCHITECTURE-P1.md`。

## 技术栈

- Flask 2.2+ 应用工厂 + Flask-SQLAlchemy + Flask-Login + Flask-WTF + Flask-Migrate
- Bootstrap5 CDN + Jinja2 服务端渲染，中文界面
- 数据库：MySQL（生产）/ SQLite（开发验证，`DB_ENGINE=sqlite`）

## 快速开始（开发验证）

```bash
# 1. 安装依赖（venv）
venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 配置环境变量（或复制 .env.example 为 .env）
set DB_ENGINE=sqlite          # bash: export DB_ENGINE=sqlite

# 3. 初始化数据库（仓库已含迁移脚本，直接 upgrade，勿重复运行 flask db migrate）
flask db upgrade

# 4. 写入种子数据
venv\Scripts\python.exe scripts\seed.py

# 5. 启动
venv\Scripts\python.exe run.py
```

## 测试

```bash
# 全量 pytest（P0 + P1 + QA 独立用例，约 8 秒）
venv\Scripts\python.exe -m pytest tests -q

# 端到端冒烟（39 项）：脚本按"单次/新库"设计，运行前须从零建库，
# 否则第二次运行会因数据累积（签到已存在、库存累计、消息重复）出现失败。
# 从零建库：删除根目录 factory_mgmt.db → flask db upgrade → scripts\seed.py
venv\Scripts\python.exe scripts\smoke_test.py
```

## 种子账号

| 登录名 | 密码 | 角色 | 说明 |
|---|---|---|---|
| admin | admin123 | 超级管理员 | **首次登录后请立即修改密码！** |
| leader1 | 123456 | 部门主管 | 示例账号，上线前修改 |
| keeper1 | 123456 | 仓管员 | 示例账号 |
| producer1 | 123456 | 生产管理员 | 示例账号 |
| staff1 | 123456 | 普通员工 | 示例账号 |
| arch1 | 123456 | 档案管理员 | 示例账号 |

## 时间约定

所有时间字段统一存本地时间（Asia/Shanghai，naive datetime），
统一走 `app/utils/time_utils.py` 的 `now()`。

## 目录结构

```
app/
  __init__.py        # 应用工厂：蓝图注册、上下文注入、错误页
  models/            # SQLAlchemy 模型（user/rbac/org/attendance/leave/ledger/production/material/warehouse/file/chat/system）
  forms/             # Flask-WTF 表单
  routes/            # 蓝图（auth/main/hr/rbac/attendance/production/material/warehouse/files/chat/system）
  services/          # 业务事务（库存/考勤/聊天/日志/通知/导出）
  utils/             # 权限与菜单注册表/时间工具/数据权限范围
  templates/         # Jinja2 模板（全部继承 base.html）
scripts/seed.py      # 种子数据（幂等）
migrations/          # alembic 迁移（factory_mgmt_init + p1_increment）
tests/               # pytest 套件（P0 98 + P1 65 + QA 独立 49）
docs/                # PRD / 架构设计 / 类图与时序图
```
