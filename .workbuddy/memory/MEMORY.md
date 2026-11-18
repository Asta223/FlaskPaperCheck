# 项目长期记忆：小型工厂管理系统（原 FlaskPaperCheck 查重系统改造）

## 项目现状（2026-10-23 改造完成）
- 原"论文查重系统"业务已**全量拆除**（paper/history 蓝图、similarity/doc2vec/爬虫/语料库、旧模型 Paper/CheckRecord/AlgorithmConfig/ReferencePaper 全删）。
- 现为**小型工厂管理系统**：单体 Flask + Jinja2 + Bootstrap5（CDN），服务端渲染，中文界面，内网部署。
- 交付基线：git commit `c9c27e5`。SOP 全流程（PRD→架构→实现→QA 2 轮）闭环，测试 137 项全过。

## 架构要点
- Flask 2.2.5 + Flask-SQLAlchemy 3.0.5 + Flask-Login + Flask-WTF(CSRFProtect) + Flask-Migrate。requirements 仅 7 个依赖（无任何 ML 重依赖）。
- 10 个蓝图：auth(/auth)、main(/ 工作台)、hr(/hr 人员+部门)、rbac(/rbac)、attendance、production、material、warehouse、files、chat。
- 模型/forms 拆包：`app/models/`（10 文件，18 张业务表）、`app/forms/`；服务层 `app/services/`（inventory_service 出入库同事务+行锁回滚、attendance_service、chat_service）；`app/utils/`（permissions/menu/time_utils）。
- RBAC：权限点 `模块.动作` 两级，PERMISSION_REGISTRY 唯一声明，@permission_required + superadmin 硬放行；菜单经 MENU_REGISTRY + context_processor 按权限过滤。6 内置角色，用户单部门、可多角色。
- 时间约定：全部存本地时间 Asia/Shanghai（naive），统一走 `app/utils/time_utils.now()`。
- 迁移：单一初始迁移 `factory_mgmt_init`（旧 6 个迁移已删除重建）。
- 聊天：一对一消息 + AJAX 轮询（13s 未读角标，/chat/api/unread、/chat/api/messages?after_id 增量、/chat/api/read 已豁免 CSRF——QA 已评估接受）。

## P1 增量（2026-11-17 完成，git 4e2e83b）
- 16 条 P1 需求全部交付：请假审批/迟到早退、部门数据权限、领料关联、库存流水与预警、文件部门可见/检索/预览、聊天分页与精确未读、全局操作日志、CSV 导出（人员/考勤/库存）。
- 新增 7 张表（18→25）：LeaveRequest/StockLedger/OperationLog/Notification/StockWarningState/ConversationRead/file_department_visibility；新增 7 权限点（14→21）；新增 system 第 11 蓝图。
- 关键约定：数据权限收窄集中在 utils/data_scope.py + 各蓝图 base_query 出口，superadmin 豁免；文件部门可见以 models/file.py 的 can_view() 为准（父部门授权→子部门可见）；未读按 id>位点计数；day_status 逗号短码、统计按分钟字段。
- 重要事故已修复：.gitignore 曾误伤 app/models/ 导致模型从未入库，现已改为 `/models/` 并纳入 13 个模型文件；后续任何交付务必用 git archive 干净检出验证。
- 文档：docs/PRD-P1.md、docs/ARCHITECTURE-P1.md（配套 -P1 mermaid 图）；测试 212 用例（P0 98 + P1 65 + QA 独立 49）。

## 数据库：MySQL 5.5 + FactoryManagementSystem 库（2026-11-18）
- 应用当前正式跑在本机 MySQL 5.5 的 `FactoryManagementSystem` 库（utf8mb4_unicode_ci），root/123。Windows 下 MySQL 5.5 会把库名内部存储为小写 `factorymanagementsystem`，用驼峰名连接完全正常。`.env` 已设 `DB_ENGINE=mysql` + DB_HOST=127.0.0.1 + DB_NAME=FactoryManagementSystem；切回 sqlite 只需把 DB_ENGINE 改回 sqlite（SQLite 原库备份为 `factory_mgmt.db.bak_sqlite_20261118_0200`）。
- 2026-11-18 晚按用户要求把原带空格库 `factory manager` 改名为 `FactoryManagementSystem`：先 mysqldump 完整备份到 `backups/factory_manager_before_rename_20261118.sql`（backups/ 已被 gitignore），再用单条 `RENAME TABLE` 移动 26 张表（实测 MySQL 5.5 跨库 rename 会自动把 44 个 InnoDB 外键引用更新到新库），逐表核对 574 行数据后 DROP 旧库。`.env`、`scripts/seed_test_data.py`、`.env.example` 中库名已同步更新。
- MySQL 5.5 装在 `C:\Program Files (x86)\MySQL\MySQL Server 5.5`，服务名 MySQL(Auto)，曾因 datadir 缺 mysql 系统库报 1067，已修复（备份+复制系统库）。迁移脚本 `scripts/migrate_sqlite_to_mysql.py` 保留可复用（目标仍是旧 factory_mgmt 库）。
- 启动服务/改服务配置需管理员权限（主理人执行环境非管理员，需用户在管理员终端操作）。

## 配置加载（2026-11-18 BugFix，git f3b36be）
- `config.py` 顶部纯标准库 `_load_dotenv()` 自动读取项目根 `.env`（零新增依赖，env 变量优先于 .env）；本地 `.env` 设 DB_ENGINE=sqlite 且已 gitignore 不入库。
- 无任何 DB_* 配置且无 .env 时回退 sqlite（原默认 MySQL）；显式 DATABASE_URL / DB_ENGINE=mysql / 任意 DB_* 分项均照常走 MySQL。VS Code Flask 扩展启动无需手动 set 环境变量。
- Flask CLI 会提示安装 python-dotenv，可忽略（config.py 自行加载）。

## P2 增量（2026-11-18 完成，git ca89bf9 起）
- 工序主数据/消耗工时/领料余量强校验；仓库档案 CRUD + 物料库位；全量软删除 + 管理员回收站（用户最终口径：删除=页面隐藏、数据库保留，不物理删）。
- 软删除统一在 `app/models/mixins.py`（16 表 is_deleted + Session 级 with_loader_criteria 全局过滤），恢复走 `app/services/soft_delete_service.py`；回收站 `system.recycle` 仅 superadmin（/system/recycle）。
- 关键坑：MySQL 5.5 复合唯一索引被外键借用，删前必须补普通索引；业务唯一性改为应用层只校验未删除记录；单测中 `db.session.get()` 因身份映射会返回已软删对象，应断言 `.is_deleted` 而非 `is None`。
- 迁移 d4e5f6a7b8c9 已应用 MySQL（15 表 + 回收站权限）；全量测试 **274 passed**。
- P2-5 多格式预览：`app/services/file_preview_service.py`（图片/PDF 内联；txt/csv/docx/xlsx/xls 内容级解析；doc/ppt 提示页），Jinja2 自动转义 + 大小/行列上限；依赖 python-docx/openpyxl/xlrd（xlwt 仅测试）。
- P2-6 工单质量：`WorkOrder.can_run_steps` 只认 in_progress，待开始/终态锁定工序流转与工时；质量数量/良率/不良率由 `record_quality()` 服务端计算；不良原因独立表 `defect_reasons` + `production.defect_reason.manage` 权限，引用守卫 + 回收站。迁移 e5f6a7b8c9d0 已应用 MySQL。

## 验证命令
- 全量：`DB_ENGINE=sqlite venv/Scripts/python.exe -m pytest tests -q`（274 passed）
- 冒烟：`venv/Scripts/python.exe scripts/smoke_test.py`（39 项，**须先删库重建再跑**，非幂等）

## 约定
- DB 环境变量驱动（DATABASE_URL 或 DB_* 分项），`DB_ENGINE=sqlite` 时用根目录 `factory_mgmt.db`；生产建议 MySQL。
- 种子：`scripts/seed.py`——admin/admin123（超管，首登改密），示例账号 leader1/keeper1/producer1/staff1/arch1 密码 123456。
- 测试：`tests/`（conftest 提供 client/login/get_csrf 夹具 + 7 模块 98 用例）+ `scripts/smoke_test.py`（39 项）。venv 已含 pytest。跑法：`venv/Scripts/python.exe -m pytest tests -q`。
- 文档：`docs/PRD.md`、`docs/ARCHITECTURE.md`（含类图/时序图 mermaid 文件）。
- 已知决策：无自助注册（管理员建号）；P0 出入库单物料/单；请假审批/群聊/BOM/节假日考勤规则均留 P1/P2。
