# P2 增量需求与实现说明（生产侧轻量化）

## 背景与设计原则

系统面向小型工厂，当前阶段目标是**线上留痕与信息化**，不追求复杂流程管控。本次 P2 需求基于用户 2026-11-18 提出的 4 点要求：

1. 工序是工厂相对固定的基础数据，必须独立维护，不允许工单里自由输入；
2. 工序步骤要记录消耗工时（不仅起止时间）；
3. 领料必须校验库存；
4. 生产侧不引入审批流，**人事行政（请假）审批保持不变**。

> 经确认：第 4 点中"审批"特指生产环节——生产工单维持既有状态流转（pending→in_progress→completed→accepted），不新增审批人/审批意见；请假审批（部门主管单级终态）保留原样。

---

## 需求与实现对照

| 编号 | 需求 | 实现 | 相关文件 |
|---|---|---|---|
| P2-01 | 工序独立维护页面，只能下拉选择 | 新增 `Process` 工序档案主数据（编码/名称/参考工时/排序/启用），独立 CRUD 页 `/production/processes`；工单添加工序改为 `process_id` 下拉（仅启用项），后端二次校验工序存在且启用；名称做**快照**写入步骤，工序日后改名不影响历史工单 | `app/models/production.py`、`app/routes/production.py`、`app/forms/production.py`、`app/templates/production/process_list.html`、`app/utils/menu.py`、`app/utils/permissions.py` |
| P2-02 | 记录消耗工时 | `WorkOrderStep.labor_hours`（小时）字段；工序流转到"完成"时按起止时间自动计算（保留 2 位），提供"修工时"弹窗按实际消耗修正（保存即生效并记操作日志，无审批）；工单详情展示单步工时与合计 | `app/models/production.py`（`auto_labor_hours()`）、`app/routes/production.py`（`step_labor`）、`app/templates/production/order_detail.html` |
| P2-03 | 领料库存校验 | 领料弹窗通过 `/production/api/stock` 联动显示所选仓库+物料当前可用余量，填写数量超过余量即时红字提示且禁用提交；服务端前置校验给出"仓库/物料/余量/缺口"清晰提示，库存事务内仍保留 `with_for_update()` 行锁强校验防并发超发，提示失败不扣减库存、不留出库单 | `app/routes/production.py`（`api_stock`、`order_issue`）、`app/templates/production/order_detail.html`、`app/services/inventory_service.py` |
| P2-04 | 生产不做审批流 | 生产侧仅状态流转与操作日志，无审批字段与审批路由；人事请假审批保留 | 设计约束（无新增代码），测试 `test_production_has_no_approval_flow` 固化 |

---

## 数据模型变更

| 变更 | 说明 |
|---|---|
| 新表 `processes` | `code`(唯一)、`name`(唯一)、`standard_hours`、`sort_order`、`is_active`、`remark`、`created_at` |
| `work_order_steps` 加列 | `process_id`（外键 → processes.id，历史数据可空）、`labor_hours`（默认 0） |
| 权限点 | 新增 `production.process.manage`（工序档案维护）；授予 superadmin / leader / producer |
| 菜单 | 生产管理 → 工序档案（沿用 `production.view` 可见） |

迁移脚本：`migrations/versions/b2c3d4e5f6a7_production_process.py`（upgrade 已应用于当前 MySQL 库）。

**历史数据处理**：迁移后历史 18 条工单步骤按名称匹配绑定对应工序（`process_id`），`name` 快照原样保留，`labor_hours` 默认 0，不回溯伪造工时。

---

## 关键决策

- **快照而非实时关联**：工单步骤冗余存 `name`，引用工序时写入，工序档案改名/停用不影响历史工单展示，符合"线上留痕"定位。
- **工时不强制等于时间差**：完成时自动算作为初值，允许有权限者直接修正（如中途停线不计入），修正写操作日志，无需审批。
- **前端提示 + 服务端强校验双保险**：余量展示提升体验，但真正的库存安全由库存事务的行锁校验保证；前置校验只为给出更可读的"缺多少"反馈。
- **不引入审批**：生产侧保持轻量；请假审批属人事行政范畴，维持原状。

---

## P2-2 追加需求（仓库自定义 + 物料库位）

| 编号 | 需求 | 实现 |
|---|---|---|
| P2-05 | 仓库档案允许增删查改（不同厂区仓库不同，用户自定义） | 仓库档案补**可逆停用/启用**（`warehouse_toggle`，有库存>0 禁止停用）、**严格条件下彻底删除**（无库存记录、无出入库单据、无流水才允许物理删）、**按名称/位置搜索**；新建/编辑/停用/删除全部记操作日志 |
| P2-06 | 物料档案记录存放仓位/货位，便于出入库 | `Material.storage_location`（String128）单字段记录「什么仓库的什么货位」；物料新建/编辑可录入，列表/筛选可见；**出入库单据与工单领料的物料下拉直接带出【库位：…】提示**；库存查询页与库存 CSV 导出增加库位列 |

设计取舍：库位采用物料档案上的单一文本字段（如「原材料仓 A区-03排-2层」），不建独立库位表、不做仓库×物料多维关联——符合小型工厂"线上留痕、不搞复杂"定位，避免与库存维度冗余。

相关文件：`app/models/material.py`、`app/forms/material.py`、`app/forms/warehouse.py`、`app/forms/production.py`、`app/routes/material.py`、`app/routes/warehouse.py`、`app/templates/material/*`、`app/templates/warehouse/*`、`migrations/versions/c3d4e5f6a7b8_material_storage_location.py`。

---

## P2-3 追加需求（全量硬删除）

用户诉求：**所有可新增的数据都应支持硬删除**——误操作建立的错误数据不存在"停用/复用"的价值，必须能彻底删掉。

| 范围 | 新增硬删除入口 | 拒绝条件（保护历史完整性） |
|---|---|---|
| 员工 | `hr.employee_delete` | 当前登录账号；仍被考勤/请假/工单/文件等引用 |
| 部门 | `hr.department_purge` | 仍有子部门、员工、请假、工单引用 |
| 角色 | `rbac.role_delete` | 内置角色；仍有用户持有 |
| 工序档案 | `production.process_delete` | 已被工单步骤引用 |
| 工单 | `production.order_delete` | 已有工序步骤或领料单据 |
| 物料 | `material.material_delete` | 有库存/单据/流水/预警引用 |
| 物料分类 | `material.category_purge` | 有子分类或物料引用 |
| 出入库单 | `warehouse.doc_delete` | 原入库货已被后续出库消耗（扣回会使库存为负） |
| 文件 | `files.file_purge` | 无（同时删除磁盘文件与可见范围关联） |
| 文件分类 | `files.category_purge` | 有子分类或文件引用 |
| 请假申请 | `attendance.leave_delete` | 非本人且非管辖范围审批人（403） |
| 打卡记录 | `attendance.record_delete` | 非本人且非管辖范围主管（403） |
| 聊天消息 | `chat.message_delete` | 非发送人（403） |

**实现机制**：新增 `app/utils/delete_guard.py` 统一守卫——物理删除前扫描全库外键，有引用则拒绝并列出具体来源（如"库存记录 3 条、出入库单据 6 条"）；多对多关联表（user_roles / role_permissions / file_*_visibility）作为附属关系自动清理，不算引用；操作日志作为审计留痕永不删除，删除员工时仅将 `operator_id` 置空（摘要仍含姓名）。

**单据删除的账实一致性**：`reverse_stock_document()` 在同一事务内反向冲销库存（原入库→扣回、原出库→加回），保留原流水并追加一条方向相反、单号带 `-R` 后缀的冲销流水，保证"账实一致 + 审计不断链"。

**明确不提供删除的数据**：操作日志、库存流水、通知、库存预警状态、权限点——这些是系统自动产生的审计/状态数据，不属于"用户可新增"，删除会破坏留痕定位。

相关文件：`app/utils/delete_guard.py`、`app/services/inventory_service.py`、各业务蓝图与列表模板、`tests/test_p2_hard_delete.py`（15 项）。

---

## 验证

- 自动化测试：P2-1 `tests/test_p2_production.py`（15 项）、P2-2 `tests/test_p2_warehouse_material.py`（10 项）、P2-3 `tests/test_p2_hard_delete.py`（15 项），全量 **253 passed**（P0/P1/QA/P2）。
- 端到端实测（MySQL `FactoryManagementSystem` 库）：所有列表页删除按钮渲染正常；守卫正确检出物料的库存/单据/流水引用；临时工序与临时角色创建后硬删成功；有数据的员工账号打卡/请假删除按钮正常渲染。
