# 工厂管理系统

基于 Flask 的内网单机小型工厂管理系统：人员/部门/权限(RBAC)/考勤/生产/物料/仓库/文件/站内聊天。

P0 为 9 大业务模块；P1 增量已交付：请假申请与审批、迟到早退判定、部门数据权限隔离、工单领料关联、库存变动流水与预警站内推送、文件部门级可见/检索/预览、聊天历史分页与精确未读、全局操作日志、CSV 导出。详见 `docs/PRD-P1.md` 与 `docs/ARCHITECTURE-P1.md`。
P2 增量已交付：工序档案独立维护（工单只能下拉引用）、工序消耗工时记录与修正、领料库存余量显示与强校验；仓库档案完整增删改查（可逆停用/软删除/搜索），物料档案记录仓位货位并在出入库带出提示；所有用户可新增的数据均支持软删除（页面隐藏、数据库保留，管理员可在「系统管理→回收站」恢复；出入库单删除反向冲销库存、恢复时重新入账）；文件管理支持图片/PDF 内联预览及 TXT/CSV/Word(docx)/Excel(xlsx/xls) 内容级在线预览（旧版 doc/ppt 提示下载或另存新版）；待开始工单锁定工序执行（只有进行中工单可流转工序/修工时），进行中/已完成工单可记录成品数量、良品/不良数量、良率、不良率与不良原因；不良原因独立主数据维护并支持软删除/回收站恢复；生产侧不引入审批流，人事请假审批保持。详见 `docs/PRD-P2.md`。

后续增量：L1 轻量排产（交期倒排与超期/开工预警）、工艺路线、产品档案与 BOM、客户/供应商独立档案、单位档案与换算（拆箱领用）、菜单搜索、操作日志中文化及前端查询文案统一。详见 `docs/PRD-L1-Scheduling.md`、`docs/ARCHITECTURE-L1-Scheduling.md` 与提交记录。

## 数据导入（CSV / Excel）

原来支持 CSV 导出的 3 个页面现在都支持导入：**人员管理**、**月度考勤**、**库存查询**。导入模板直接复用各自导出文件的字段（字段顺序可不同，必须包含全部列，多余列忽略），可从导入页面一键下载导出 CSV 作为模板。

| 页面 | 导入唯一键 | 处理口径 |
|---|---|---|
| 人员管理 | 工号 | 已存在更新，不存在新建；新建账号登录名=工号，初始密码取 `IMPORT_DEFAULT_PASSWORD`（默认 `123456`） |
| 月度考勤 | 部门 + 姓名 + 日期 | 已存在更新，不存在新建；按文件值落库，不重算迟到/早退 |
| 库存查询 | 仓库 + 物料编码 | 已存在更新，不存在新建；规格/存放位置同步回物料档案；状态须与数量/阈值一致；导入为库存快照覆盖，不生成出入库单据 |

支持 `.csv`（UTF-8/UTF-8 BOM/GBK）、`.xlsx`、`.xls`。导入先全量校验再单事务写库，任一行失败则整份文件不落库，页面一次性列出所有错误行。需要同时具备对应模块管理权限和 `system.import`（数据导入）权限；部门主管仍受部门数据权限限制。

**部署影响说明**：

- **依赖无新增**：Excel 导入所需的 `openpyxl`（读 `.xlsx`）、`xlrd`（读 `.xls`）已在 `requirements.txt`（P2 文件预览阶段引入），部署脚本安装依赖时一并装好，无需额外操作。
- **无新数据库迁移**：导入不新增表或字段，Alembic head 仍为 `e0f1a2b3c4d5`。新增的 `system.import` 权限点由 `scripts/seed.py` 幂等写入 `permissions` 表并绑定到内置角色；部署脚本（Windows `deploy_env.bat` / Linux `deploy.sh`）第 6 步已执行 `seed.py`，全新部署和已上线环境重新执行 seed 后均会自动获得该权限，无需手工改库。
- **可选配置**：新建账号初始密码可通过 `.env` 的 `IMPORT_DEFAULT_PASSWORD` 覆盖（默认 `123456`），未配置时不改变默认行为。

## 技术栈

- Flask 2.2+ 应用工厂 + Flask-SQLAlchemy + Flask-Login + Flask-WTF + Flask-Migrate
- Bootstrap5 CDN + Jinja2 服务端渲染，中文界面
- 数据库：MySQL（当前项目库 `FactoryManagementSystem`，见根目录 `.env`）/ SQLite（开发验证，`DB_ENGINE=sqlite`）

## 部署与运行（Windows / Linux / macOS）

项目把“部署”和“运行”拆开，同时保留一键入口。Windows 用 bat，Linux/macOS 用 shell 脚本：

| 平台 | 文件 | 用途 |
|---|---|---|
| 通用 | `部署命令.txt` | 手工顺序执行的命令清单（含 Windows 与 Linux 两套） |
| Windows | `deploy_env.bat` | 双击部署，不启动服务 |
| Windows | `run_system.bat` | 双击运行并打开默认浏览器 |
| Windows | `启动系统.bat` | 双击先部署再运行 |
| Linux/macOS | `deploy.sh` | 部署，不启动服务 |
| Linux/macOS | `run_system.sh` | 运行并尝试打开默认浏览器 |
| Linux/macOS | `start.sh` | 先部署再运行 |

### 1. 部署环境（一次性）

双击 `deploy_env.bat`，或按 `部署命令.txt` 中的顺序手工执行。脚本会自动：

- 没有 `venv` 时创建虚拟环境；
- 安装/更新 `requirements.txt` 依赖（含 Waitress）；
- 没有 `.env` 时从 `.env.example` 复制；
- 调用 `scripts/ensure_database.py` 确保 MySQL 库存在（SQLite 配置自动跳过）；
- 执行 `flask db upgrade`；
- 执行 `scripts/seed.py` 写入权限点、角色和账号（幂等）。

部署成功后窗口提示 `Environment is ready`，**不会启动服务**。

### 2. 日常运行

双击 `run_system.bat`。它会打开一个命令行窗口，用 Waitress 启动服务，并自动用默认浏览器打开：

- 本机：`http://127.0.0.1:5000`
- 局域网其他电脑：`http://<命令行打印的本机IP>:5000`

停止服务：在该窗口按 `Ctrl+C`，或直接关闭窗口。

### 3. 一键入口

双击 `启动系统.bat` 等价于先运行 `deploy_env.bat`，再运行 `run_system.bat`。服务由 **Waitress** 提供，不是 Flask 调试服务器；`run.py` 仅用于开发调试。

### 4. Linux / macOS

先赋予脚本执行权限（一次即可）：

```bash
chmod +x deploy.sh run_system.sh start.sh
```

然后：

```bash
./start.sh        # 先部署再运行
# 或
./deploy.sh       # 只部署
./run_system.sh   # 只运行，按 Ctrl+C 停止
```

前置条件：已安装 Python 3（Debian/Ubuntu 可能还需 `sudo apt install python3-venv`）；若使用 MySQL，先启动数据库服务（例如 `sudo systemctl start mysql` 或 `mariadb`），并确认 `.env` 中的 `DB_*` 与实际一致。

手工命令清单见 `部署命令.txt` 第七节。纯服务器/SSH 无图形界面时，`run_system.sh` 会自动设置 `OPEN_BROWSER=0`，只在终端打印访问地址；有桌面的环境会打开默认浏览器。

### 5. 端口与浏览器配置

编辑根目录 `.env`：

```ini
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
SERVER_THREADS=8
OPEN_BROWSER=1
```

若只允许本机访问，把 `SERVER_HOST` 改成 `127.0.0.1`；把 `OPEN_BROWSER` 改成 `0` 则不自动打开浏览器。

## 环境准备与启动

以下命令均**在项目根目录执行**。已激活虚拟环境时可直接用 `python` / `flask`；未激活时统一用 `venv\Scripts\python.exe -m ...` 形式（下文给出两种写法）。

### 全新安装（最短顺序）

```bash
# Windows：创建虚拟环境
python -m venv venv

# 安装依赖
venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
venv\Scripts\python.exe -m pip install -r requirements.txt

# 复制配置并按需修改数据库类型（Git Bash / macOS / Linux；CMD 用 copy .env.example .env）
cp .env.example .env

# 确保数据库存在（SQLite 自动跳过）
venv\Scripts\python.exe scripts\ensure_database.py

# 执行数据库迁移（仓库已含全部迁移脚本，直接 upgrade）
venv\Scripts\python.exe -m flask db upgrade
venv\Scripts\python.exe -m flask db current

# 写入种子数据（幂等）
venv\Scripts\python.exe scripts\seed.py

# 启动服务（Waitress，与双击 run_system.bat 一致）
venv\Scripts\python.exe start_server.py
```

### 1. 创建并激活虚拟环境

Windows PowerShell：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

若 PowerShell 禁止运行脚本，可先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Windows CMD：

```bat
python -m venv venv
venv\Scripts\activate.bat
```

Git Bash：

```bash
python -m venv venv
source venv/Scripts/activate
```

macOS / Linux：

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. 安装 pip 依赖

已激活虚拟环境时：

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

未激活虚拟环境时（Windows，推荐）：

```bash
venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` 已包含 Flask、Flask-SQLAlchemy、Flask-Login、Flask-WTF、Flask-Migrate、PyMySQL、邮件校验，以及 `openpyxl` / `xlrd`（Word/Excel 在线预览与 CSV/Excel 数据导入共用）、`python-docx`（Word 预览）。其中 `xlwt` 仅用于测试生成 `.xls` 样本，不作为运行依赖。

可选依赖（不是启动必需）：

```bash
python -m pip install pytest
python -m pip install python-dotenv
```

说明：`config.py` 已用标准库自动读取 `.env`，Flask CLI 提示安装 `python-dotenv` 可以忽略；装了只是为了消除提示。

### 3. 配置数据库

项目启动时自动读取根目录 `.env`；真实环境变量优先级高于 `.env`。

```bash
cp .env.example .env
```

MySQL 模式（当前项目正式库）：

```ini
DB_ENGINE=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123
DB_NAME=FactoryManagementSystem
```

首次部署 MySQL 时，先创建空库（进入 `mysql -uroot -p` 后执行）：

```sql
CREATE DATABASE IF NOT EXISTS FactoryManagementSystem
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

SQLite 模式（开发/验证）：把 `.env` 改为：

```ini
DB_ENGINE=sqlite
```

SQLite 文件为项目根目录 `factory_mgmt.db`。完全不配置任何 `DB_*` 时也会回退到 SQLite。也可使用完整连接串 `DATABASE_URL`，其优先级最高：

```ini
DATABASE_URL=mysql+pymysql://root:123@127.0.0.1:3306/FactoryManagementSystem?charset=utf8mb4
```

### 4. 数据库迁移

迁移脚本已全部入库，仓库中是**一条线性迁移链**，当前 head 为 `e0f1a2b3c4d5`。日常部署只需 `upgrade`，**不要重复执行 `flask db migrate` 生成新脚本**。

已激活虚拟环境时：

```bash
flask db upgrade
flask db current
flask db heads
flask db history
```

未激活虚拟环境时：

```bash
venv\Scripts\python.exe -m flask db upgrade
venv\Scripts\python.exe -m flask db current
venv\Scripts\python.exe -m flask db heads
venv\Scripts\python.exe -m flask db history
```

版本链（从旧到新）：

```text
<base>
  → d220c1496af3  factory_mgmt_init
  → a1b2c3d4e5f6  P1 增量
  → b2c3d4e5f6a7  P2 物料库位
  → c3d4e5f6a7b8  软删除
  → d4e5f6a7b8c9  工单质量与不良原因
  → e5f6a7b8c9d0  L1 轻量排产
  → f6a7b8c9d0e1  聊天会话隐藏
  → a7b8c9d0e1f2  工艺路线
  → b7c8d9e0f1a3  工艺路线明细软删
  → b8c9d0e1f2a4  产品档案与 BOM
  → c9d0e1f2a4b5  客户/供应商档案
  → d0e1f2a4b5c6  单位档案与换算
  → e0f1a2b3c4d5  head
```

回滚（仅排障时使用，先备份数据库）：

```bash
flask db downgrade <目标 revision>
```

注意：已有数据库的 `alembic_version` 与表结构一致时，直接 `upgrade` 即可；不要手动修改 `alembic_version`，也不要对已应用的 revision 重新生成/替换脚本。

### 5. 启动服务

日常使用：Windows 双击 `run_system.bat`（只启动）或 `启动系统.bat`（先部署再启动）；Linux/macOS 执行 `./run_system.sh` 或 `./start.sh`。详见上方“部署与运行”。

开发调试时也可以手动启动：

```bash
# Waitress（与双击脚本一致，推荐长期运行）
venv\Scripts\python.exe start_server.py

# Flask 自带开发服务器（仅调试，带热重载，不要用于正式使用）
venv\Scripts\python.exe run.py

# 已激活虚拟环境时
python start_server.py
python run.py
```

## 测试

```bash
# 全量 pytest（当前 406 项，约 1 分钟；未安装 pytest 时先执行 python -m pip install pytest）
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
  models/            # SQLAlchemy 模型（含 user/rbac/org/attendance/production/material/warehouse/partner/unit/file/chat/system 等）
  forms/             # Flask-WTF 表单
  routes/            # 蓝图（auth/main/hr/rbac/attendance/production/material/warehouse/files/chat/system/data_import）
  services/          # 业务事务（库存/考勤/聊天/日志/通知/导出/CSV-Excel 导入）
  utils/             # 权限与菜单注册表/时间工具/数据权限范围
  templates/         # Jinja2 模板（全部继承 base.html）
部署命令.txt        # 手工部署命令清单（Windows + Linux 两套，按顺序复制执行）
deploy_env.bat      # Windows 双击部署：venv/依赖/.env/建库/迁移/种子，不启动服务
run_system.bat      # Windows 双击运行：启动 Waitress 并打开默认浏览器
启动系统.bat        # Windows 双击一键：先部署再运行
deploy.sh           # Linux/macOS 部署，不启动服务
run_system.sh       # Linux/macOS 运行并尝试打开浏览器
start.sh            # Linux/macOS 一键：先部署再运行
start_server.py     # Waitress 服务入口（端口等参数见 .env）
scripts/ensure_database.py  # 按 .env 确保数据库存在（SQLite 跳过）
scripts/seed.py      # 种子数据（幂等）
migrations/          # 单一线性 Alembic 迁移链，head=e0f1a2b3c4d5
tests/               # pytest 套件（当前 406 项）
docs/                # PRD / 架构设计 / 类图与时序图
```
