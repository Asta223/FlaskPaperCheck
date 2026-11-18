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

## 验证

- 自动化测试：新增 `tests/test_p2_production.py`（15 项），全量 **228 passed**（P0/P1/QA + P2）。
- 端到端实测（MySQL `FactoryManagementSystem` 库）：工序档案页 200、工单详情下拉渲染、18 条历史步骤绑定成功、余量 API 返回正确、工时修正落库、全链路无异常。
