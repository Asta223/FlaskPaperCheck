# 工厂管理系统（FlaskPaperCheck 改造）

基于 Flask 的内网单机小型工厂管理系统：人员/部门/权限(RBAC)/考勤/生产/物料/仓库/文件/站内聊天。

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

# 3. 初始化数据库
flask db init                 # 首次（已有 migrations/ 可跳过）
flask db migrate -m "factory_mgmt_init"
flask db upgrade

# 4. 写入种子数据
venv\Scripts\python.exe scripts\seed.py

# 5. 启动
venv\Scripts\python.exe run.py
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
  models/            # SQLAlchemy 模型（user/rbac/org/attendance/production/material/warehouse/file/chat）
  forms/             # Flask-WTF 表单
  routes/            # 蓝图（auth/main/hr/rbac/attendance/production/material/warehouse/files/chat）
  services/          # 业务事务（库存/考勤统计/聊天聚合）
  utils/             # 权限注册表/菜单注册表/时间工具
  templates/         # Jinja2 模板（全部继承 base.html）
scripts/seed.py      # 种子数据（幂等）
migrations/          # alembic 迁移
```
