# L1 轻量排产（倒排 + 超期预警）系统设计

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0（系统设计 / 工程实现依据） |
| 上游输入 | `docs/PRD-L1-Scheduling.md` v1.0 |
| 技术栈 | Flask 2.2.5 + SQLAlchemy 3.0.5 + Jinja2 + Bootstrap5 + Flask-Migrate / MySQL 5.5 |
| 计算位置 | 服务端唯一口径：`app/services/scheduling_service.py` |

## 1. 设计目标与范围边界

**目标**：只算日期、只做提醒。给每个有交期且可估工期的工单倒推出「最晚开工日」，并在列表/看板提前暴露超期与开工预警，允许人工覆盖且不被自动重算冲掉。

**本期包含**：4 个计划字段 + 1 次迁移；`time_utils` 工作日工具；`scheduling_service` 倒排服务；新建/编辑/工序变更自动算；人工覆盖与「重新倒排」；列表/看板/详情展示与标红；单元测试。

**明确不含（Out of Scope）**：L2 有限产能排程（班组/产线/机台负荷、甘特图）、L3 APS 求解器、BOM/齐套、节假日与调休日历、批量重算、审批流、新通知、自动改交期、状态机变更。

**不新增权限点**：沿用 `production.view`（查看）与 `production.manage`（编辑/重新倒排）。

## 2. 数据模型增量（`work_orders`）

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `plan_start_date` | `db.Date` | 是 | NULL | 倒推的最晚开工日；无工期/无交期时留空 |
| `plan_end_date` | `db.Date` | 是 | NULL | 计划完工日，**保留 `due_date` 原值**（含落在周末的情况） |
| `priority` | `db.String(10)` | 否 | `'normal'` | 取值域 `high`/`normal`/`low`；本期仅展示/排序，**不参与倒排** |
| `plan_manual` | `db.Boolean` | 否 | `False` | 人工覆盖标记：`True` 时自动重算不得改写两个日期 |

**是否需要「人工覆盖标记」字段？——推荐新增 `plan_manual`（第 4 字段），随同一迁移落地。**
理由：自动模式同样会写入 `plan_start_date`，"日期是否为空"无法区分来源；一个显式布尔位即可精确表达"保留人工值 / 允许自动改写"，且让"重新倒排"有明确的清除目标。这与 PRD FR5 一致。若删掉该字段只能退化为"改过一次就永不自动重算"，无法解除覆盖。

配套常量：在 `WorkOrder` 增加 `PRIORITY_LABELS = {'high': '高', 'normal': '普通', 'low': '低'}` 供表单 choices 与模板渲染共用。不新增模型方法——所有计算留在 service，便于单测。

## 3. 倒排算法

### 3.1 口径（与 PRD FR3 一致）

```
H_total = (Σ 各未删除工序行的 Process.standard_hours) × order.quantity
D       = max(1, ceil(H_total / DAILY_CAPACITY_HOURS))
plan_end_date   = order.due_date                       # 原值，不因周末改写
plan_start_date = 从 plan_end_date 向前（含）取第 D 个工作日
```

- **工时汇总方式推荐：`Σ standard_hours × quantity`（先求和再乘数量）。** 理由：`Process.standard_hours` 语义是"单件单工序参考工时"，总量必须与产量成正比；`WorkOrderStep.labor_hours` 是完工后的实际消耗，**不可**作为计划输入。
- 无法关联工序（`process_id` 为空/工序已软删）或工时为空/0 的步骤按 0 计；只累加有效工时。
- **日产能**：`DAILY_CAPACITY_HOURS = 8`（小时/工作日），全局单值，支持环境变量覆盖；`<=0` 由 service 抛 `ValueError`，不静默。
- **工作日历**：周一~周五，**不引入节假日/调休**（沿用 `time_utils.workdays_in_month` 简化口径）。
- **取整**：`ceil`，不足 1 天按 1 个工作日，保证不低估工期。

### 3.2 兜底

| 场景 | 处理 |
|---|---|
| `due_date` 为空 | 直接返回 `(None, None)`，不标红、不参与剩余天数 |
| 无工序 或 `H_total <= 0` | 返回 `(None, None)`，**不伪造"1 天开工"**；详情页提示"未维护工序参考工时，无法倒排" |
| 交期已过 | 仍按公式倒排（计划日期可为过去），由超期规则标红；**不把开工日 clamp 到今天**（会破坏倒排锚点、掩盖真实延误） |
| 交期落在周末 | `plan_end_date` 保留周末原值；回退时周末不计工作日、不作为开工日（第 1 个工作日 = 最近的工作日 ≤ 交期） |
| 历史工单 | 迁移后计划字段为 NULL，不回填；用户编辑保存时按现有工序重算 |
| 已完工工单 | 保留计划日期供追溯；不参与自动重算与标红 |

### 3.3 伪代码

```
# 工作日工具（新增到 app/utils/time_utils.py，纯函数）
is_workday(d)            = d.weekday() < 5
prev_workday(d)          = 严格向前最近的工作日（不含 d）
prev_workday_incl(d)     = d if is_workday(d) else prev_workday(d)
next_workday(d)          = 严格向后最近的工作日（不含 d）
workdays_between(a, b)   = 闭区间 [a,b] 内工作日数（a>b 时返回负）
workday_diff(a, b)       = b 相对 a 的工作日差；周末 a 先按 prev_workday_incl 锚定；同日=0

calculate_plan(due_date, hours_total, capacity) -> (start, end):
    if due_date is None or hours_total <= 0: return (None, None)
    if capacity <= 0: raise ValueError('DAILY_CAPACITY_HOURS 必须大于 0')
    D = max(1, ceil(hours_total / capacity))
    end = due_date                       # 保留原值
    cur = prev_workday_incl(end)         # 第 1 个工作日
    repeat (D - 1) times: cur = prev_workday(cur)
    return (cur, end)                    # cur 必为工作日
```

## 4. 服务层接口（`app/services/scheduling_service.py`，新建）

全部为模块级函数，显式传参、`today` 可注入，**不 import models**（通过 duck typing 读 `order.steps`），保证零 app context 亦可单测。

| 函数签名 | 职责 |
|---|---|
| `sum_standard_hours(order) -> float` | ORM 适配：遍历未删除 steps，`step.process.standard_hours or 0` 求和，返回 `round(x,2)` |
| `calculate_plan(due_date, hours_total, capacity=None) -> tuple[date\|None, date\|None]` | 纯核心算法（§3.3），`capacity` 默认读 `current_app.config['DAILY_CAPACITY_HOURS']` |
| `apply_plan(order, manual_start=None, manual_end=None) -> str` | 唯一写库入口：自动/人工两种模式写入 4 字段（见 §5）；返回 `'auto'`/`'manual'`/`'unavailable'` 供 flash |
| `is_overdue(order, today=None) -> bool` | 未完工且 `due_date < today` → 已超期（PRD FR8） |
| `is_start_warning(order, today=None) -> bool` | 未完工且 `plan_start_date <= today <= due_date` → 开工预警 |
| `days_remaining(order, today=None) -> int\|None` | `workday_diff(today, plan_start_date)`；>0 还剩 N 个工作日，=0 今天最晚开工，<0 已过 N 个工作日；无日期返回 None |
| `plan_status(order, today=None) -> dict` | 聚合 `{overdue, warning, label, days, manual, priority}` 供模板一次取值，避免模板调用 Python 函数 |

> 判定优先级：`is_overdue` 命中时 label 固定为「已超期」，忽略开工预警；终态（`completed`/`accepted`）一律返回全 False/空 label。所有比较前先判空。

## 5. 触发与覆盖策略

**人工/自动的判定口径（推荐，消除歧义）**：表单两个计划日期**仅在 `plan_manual=True` 时回填原值**，自动工单的字段留空并显示占位提示"留空 = 按交期自动倒排（当前：X）"。保存时：

```
manual_requested = (plan_start_date submitted != None) or (plan_end_date submitted != None)
若 manual_requested:
    两个日期都必须填写，否则 flash 校验错误并中止保存；写入提交值；plan_manual = True
否则:
    (start, end) = calculate_plan(due_date, sum_standard_hours(order))
    若 (None,None): 两日期置 NULL、plan_manual = False，返回 'unavailable'
    否则写入 start/end；plan_manual = False
```

理由：相比"逐个与自动值比对"，非空即人工更稳健（无浮点/日期边界比较），且天然支持"清空两个框 = 解除覆盖"。

**调用点**：
- `order_new` / `order_edit`：构造/赋值基础字段后调用 `apply_plan`，再 `log_operation`、commit。编辑时若原本 `plan_manual=True` 且用户未清空表单 → 保持人工值不被改写。
- **`step_new` / `step_delete` 成功后也必须调用 `apply_plan`**（理由：新建工单时还没有工序，若不在此重算，计划日期将永远为空——这是本增量最容易漏的坑）。
- `order_status` 流转到终态时不重算；保留快照。
- **重新倒排**：新增 `POST /production/orders/<int:order_id>/plan/recalculate`（`production.manage`），用 `base_order_query().filter_by(id=order_id).first_or_404()` 保证数据权限，仅未完结工单允许；强制 `apply_plan(auto)` 清除 `plan_manual`，写审计日志并 flash 结果后重定向详情。

## 6. 路由与模板改动清单（逐文件）

| 文件 | 位置 / 函数 | 改动点 |
|---|---|---|
| `app/models/production.py` | `WorkOrder` 字段区 | 新增 4 列 + `PRIORITY_LABELS` 常量 |
| `app/forms/production.py` | `WorkOrderForm` | 新增 `plan_start_date`/`plan_end_date`（`DateField, Optional`）、`priority`（`SelectField, coerce=str`，choices 由 `PRIORITY_LABELS` 派生，default `normal`） |
| `app/utils/time_utils.py` | 文件末尾 | 新增 §3.3 的 6 个纯函数（无节假日） |
| `config.py` | `Config` 类 | 新增 `DAILY_CAPACITY_HOURS = float(os.environ.get('DAILY_CAPACITY_HOURS', '8'))` |
| `app/services/scheduling_service.py` | 新建 | §4 全部函数 |
| `app/routes/production.py` | import 段 | 引入 `apply_plan`、`plan_status`、`is_overdue` 等函数（无新增类） |
| 同上 | `order_new` / `order_edit` | 赋值计划字段、调用 `apply_plan`、日志摘要追加计划结果；render 时传入 `priority_labels` |
| 同上 | `step_new` / `step_delete` | 成功后调用 `apply_plan`（漏此则计划不更新） |
| 同上 | `order_list` | 构造 `plan_status_map = {o.id: plan_status(o) for o in pagination.items}`，连同 `priority_labels` 传入模板 |
| 同上 | `board` | 同上，对 `orders` 构造 `plan_status_map` 传入 |
| 同上 | `order_detail` | 传入 `plan = plan_status(order)`、`priority_labels`、`plan_hint`（无工时时提示） |
| 同上 | 新增 `order_plan_recalculate` | 见 §5；`production.manage` + `base_order_query` + 终态拒绝 + 日志 |
| `app/templates/production/order_form.html` | 表单 `row g-3` 区 | 新增两个计划日期输入 + 优先级下拉；`plan_manual=False` 时显示当前自动值只读提示；错误渲染 |
| `app/templates/production/order_list.html` | `thead` / `tbody` | 新增「计划开工日」「倒排剩余天数」两列（`colspan 9→11`）；`plan_status_map[o.id].overdue` → `<tr class="table-danger">` + 「已超期」/「开工预警」badge；优先级 badge 与「人工」小标记；未完结行加「重新倒排」按钮 |
| `app/templates/production/board.html` | 卡片 `div.border.rounded` | 卡片内增加计划开工日 + 剩余天数文案（三种文案）；预警卡片 `border-danger` + badge |
| `app/templates/production/order_detail.html` | 工单信息 card / 顶部按钮区 | 展示计划起止日、优先级、剩余天数、人工标记与计划来源；无工时提示；未完结 + manage 权限显示「重新倒排」按钮 |
| `migrations/versions/f6a7b8c9d0e1_l1_scheduling.py` | 新建 | 见 §7 |
| `tests/test_l1_scheduling.py` | 新建 | 见 §8 |

## 7. 迁移脚本设计

`revision = 'f6a7b8c9d0e1'`，`down_revision = 'e5f6a7b8c9d0'`（现链末端，已核实），沿用 `batch_alter_table` 风格：

```python
with op.batch_alter_table('work_orders', schema=None) as batch_op:
    batch_op.add_column(sa.Column('plan_start_date', sa.Date(), nullable=True,
                                  comment='计划开工日（倒推的最晚开工日）'))
    batch_op.add_column(sa.Column('plan_end_date', sa.Date(), nullable=True,
                                  comment='计划完工日（=交期）'))
    batch_op.add_column(sa.Column('priority', sa.String(length=10), nullable=False,
                                  server_default='normal', comment='优先级 high/normal/low'))
    batch_op.add_column(sa.Column('plan_manual', sa.Boolean(), nullable=False,
                                  server_default=sa.text('0'), comment='人工覆盖标记'))
```

- 两个日期列可空且**不加 server_default**（历史数据留 NULL，禁止回填伪造）；两个非 NULL 列给 `server_default` 兼容 MySQL 5.5 已有行。
- 取值域 `high/normal/low` **不在数据库加 CHECK**（MySQL 5.5 会忽略），由表单 choices + service 校验兜底。
- 不加新索引（L1 不按这些字段过滤，优先级基数极低）。`downgrade()` 按逆序 `drop_column`。

## 8. 测试策略

| 类别 | 必覆盖用例 |
|---|---|
| 纯算法 | D=1/2/5/10；跨周末起止；交期=周六；`hours=0`/`None` → `(None,None)`；`capacity<=0` 抛错；`ceil` 边界（恰好整除 / 多 0.01h）；`workday_diff` 正/负/0/周末锚定 |
| 服务集成 | 建 `Process(standard_hours)` + 多工序 → 汇总值正确；改 `quantity` 后重算；`plan_manual=True` 时编辑不改写；无工序行/孤立 `process_id` 按 0 |
| 路由 | 新建自动写入；编辑人工覆盖保留；清空日期解除覆盖；跨部门用户 `recalculate` 被 404/403；无 `production.manage` 不能重算；终态拒绝重算；CSRF 校验（`client`/`login`/`get_csrf` 夹具） |
| 展示 | 列表含两新列与三种剩余天数文案；超期行 `table-danger` + 「已超期」优先；开工预警；已完工不标红；看板卡片同口径；「人工」标记 |
| 边界 | 无交期 / 无工序 / 零工时 / 交期已过 / 交期周末 / `DAILY_CAPACITY_HOURS` 环境变量覆盖（monkeypatch config） |
| 迁移 | `upgrade`/`downgrade` 在 SQLite（batch）通过；历史行 `priority='normal'`、`plan_manual=0`、日期 NULL |
| 回归 | 现有约 280 项 pytest 全量通过 |

## 9. 风险与约束

- **漏触发**：`step_new`/`step_delete` 不调用 `apply_plan` 会导致建单后计划永远为空——必须在实现清单中逐项核对。
- **并发**：两名管理员同时保存/重算按最后提交生效；L1 接受此最终一致，不引入行锁（留 L2）。
- **数据权限**：新路由必须走 `base_order_query()`；`order_list`/`board` 已走；现有 `order_edit` 用 `db.get_or_404` 未收窄（既有行为，本增量不扩大也不修复，仅记录为已知缺口）。
- **NULL 传播**：`due_date`/计划日期均可能为空，所有比较前先判空，禁止 `None < date`。
- **时区**：一律 `time_utils.today()`（Asia/Shanghai，naive）；禁用 `datetime.utcnow()`；字段为 `Date` 无时区问题。
- **日历简化**：无节假日表，长假会高估产能、低估工期，属已知简化；`priority` 不参与计算，L2 再接入有限产能。
- **工时口径假设**：`standard_hours` 视作"单件单工序小时"；若现场按批次口径记录，需在上线前统一数据口径，否则 D 会整体偏大。

## 10. 关键决策速查（推荐方案 + 一句话理由）

| 决策点 | 推荐 | 一句话理由 |
|---|---|---|
| 人工覆盖标记 | 新增 `plan_manual` 第 4 字段 | 自动值也写 `plan_start_date`，仅靠空非空无法区分来源 |
| 工时汇总 | `Σ standard_hours × quantity` | 参考工时是单件口径，工期必须与产量成正比 |
| 计划输入源 | `Process.standard_hours` 而非 `labor_hours` | 后者是完工实耗，不是计划基准 |
| 无工时兜底 | 日期留 NULL + 提示，不伪造 1 天 | 宁可缺失也不给出误导性计划 |
| 交期周末 | `plan_end_date` 保留原值 | 交期是业务承诺日，不应被算法改写 |
| 交期已过 | 照常倒排、不过滤、只标红 | 保留真实延误天数供追溯 |
| 覆盖判定 | 表单非空即人工，清空即解除 | 避免与自动值逐字段比较的边界歧义 |
| 剩余天数 | 工作日差（today 周末按前一工作日锚定） | 与倒排工作日历口径一致 |
| 超期优先级 | 「已超期」优先于「开工预警」 | 确定性逾期比临期更需关注 |
| 重新倒排权限 | 复用 `production.manage` + 数据权限出口 | 不新增权限点，最小改动面 |
