"""生产模型：产品档案/BOM、工序档案、工艺路线、工单与工序行项（状态机流转）。"""
from datetime import datetime

from app import db
from app.models.mixins import SoftDeleteMixin
from app.utils.time_utils import now


class Product(SoftDeleteMixin, db.Model):
    """产品档案（主数据）：统一维护产品编号/名称/规格/单位，工单只引用不手输。

    历史工单的 product_name 是名称快照（与工序名快照同口径），产品改名不影响历史；
    编码/名称唯一性只在应用层校验未删除记录，软删后允许重建同编码产品。
    """
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), nullable=False, comment='产品编号，如 PRD001')
    name = db.Column(db.String(128), nullable=False, comment='产品名称，如 圣诞树')
    spec = db.Column(db.String(128), nullable=False, default='', comment='规格型号')
    unit = db.Column(db.String(16), nullable=False, default='个', comment='计量单位')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='是否启用')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    bom_items = db.relationship('BomItem', backref='product',
                                cascade='all, delete-orphan', lazy='selectin')

    def __repr__(self) -> str:
        return '<Product %s %s>' % (self.code, self.name)


class BomItem(SoftDeleteMixin, db.Model):
    """BOM 用料明细：产品→物料→单件用量（一层，不做多级 BOM）。

    unit 是建档时从物料档案复制的**单位快照**，物料后续改单位不会误读历史用量。
    第一版只作为标准用料参考视图：不自动生成领料单、不扣减库存、不做齐套检查。
    明细随产品整体物理替换；软删/恢复产品时同步标记，避免已删产品占用物料引用。
    """
    __tablename__ = 'bom_items'
    __table_args__ = (
        db.UniqueConstraint('product_id', 'material_id', name='uq_bom_product_material'),
        db.Index('ix_bom_item_material', 'material_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'),
                           nullable=False, comment='所属产品')
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'),
                            nullable=False, comment='引用的物料档案')
    quantity = db.Column(db.Float, nullable=False, default=1,
                         comment='单件标准用量（允许小数，如 0.5 米）')
    unit = db.Column(db.String(16), nullable=False, default='', comment='单位快照（取自物料档案）')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')

    material = db.relationship('Material')

    def __repr__(self) -> str:
        return '<BomItem product=%s material=%s qty=%s>' % (
            self.product_id, self.material_id, self.quantity)


class Process(SoftDeleteMixin, db.Model):
    """工序档案（主数据）：工厂工序相对固定，由管理员统一维护，工单只能引用。

    停用（is_active=False）与删除（is_deleted=True）是两个独立状态；
    已被引用的工序不允许删除，历史工单步骤通过 name/code 快照保留当时的信息。
    """
    __tablename__ = 'processes'

    id = db.Column(db.Integer, primary_key=True)
    # 唯一性只校验未删除记录，软删后允许新建同编码/名称的工序
    code = db.Column(db.String(32), nullable=False, comment='工序编码，如 OP01')
    name = db.Column(db.String(64), nullable=False, comment='工序名称')
    standard_hours = db.Column(db.Float, nullable=False, default=0,
                               comment='参考工时（小时），仅作录入参考')
    sort_order = db.Column(db.Integer, nullable=False, default=0, comment='排序号')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='是否启用')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    def __repr__(self) -> str:
        return '<Process %s %s>' % (self.code, self.name)


class DefectReason(SoftDeleteMixin, db.Model):
    """不良原因主数据：统一维护，工单质量记录只能下拉引用，避免用户乱写。

    停用/软删除后不再出现在下拉；已有过质量记录引用时拒绝删除，保留历史留痕。
    """
    __tablename__ = 'defect_reasons'

    id = db.Column(db.Integer, primary_key=True)
    # 唯一性由应用层只校验未删除记录（与工序/物料等软删主数据口径一致）
    code = db.Column(db.String(32), nullable=False, comment='原因编码，如 DR01')
    name = db.Column(db.String(64), nullable=False, comment='不良原因名称')
    category = db.Column(db.String(64), nullable=False, default='', comment='原因分类，如来料/工艺/设备')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='是否启用')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    def __repr__(self) -> str:
        return '<DefectReason %s %s>' % (self.code, self.name)


class ProcessRoute(SoftDeleteMixin, db.Model):
    """工艺路线（工序组）：把固定工序按顺序预先组合，工单新建时可一键批量生成工序步骤。

    典型例子：产品「圣诞树」= 下料→机加工→组装→质检→包装，维护为一条路线。
    路线本身可软删/停用；明细随路线整体替换，不单独暴露在回收站。
    """
    __tablename__ = 'process_routes'

    id = db.Column(db.Integer, primary_key=True)
    # 唯一性只校验未删除记录（与工序/不良原因口径一致）
    code = db.Column(db.String(32), nullable=False, comment='路线编码，如 RT01')
    name = db.Column(db.String(64), nullable=False, comment='路线名称，如 圣诞树工艺路线')
    product_name = db.Column(db.String(128), nullable=False, default='',
                             comment='适用产品名称快照（关联产品时自动带出，历史数据保留文本）')
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True,
                           comment='关联产品档案（可空，历史路线保留）')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='是否启用')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    items = db.relationship('ProcessRouteItem', backref='route',
                            order_by='ProcessRouteItem.seq',
                            cascade='all, delete-orphan', lazy='selectin')
    product = db.relationship('Product', foreign_keys=[product_id])

    def step_names(self) -> list:
        """按顺序列出工序名（列表/下拉提示复用）。"""
        return [item.process.name if item.process else '#' + str(item.process_id)
                for item in self.items]

    def __repr__(self) -> str:
        return '<ProcessRoute %s %s>' % (self.code, self.name)


class ProcessRouteItem(SoftDeleteMixin, db.Model):
    """工艺路线明细：引用工序档案 + 顺序号；同一路线内顺序号唯一。

    随路线一起软删/恢复，避免已删除路线继续占用工序引用；编辑路线时物理替换明细。
    """
    __tablename__ = 'process_route_items'
    __table_args__ = (
        db.UniqueConstraint('route_id', 'seq', name='uq_process_route_item_route_seq'),
        db.Index('ix_process_route_item_process', 'process_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('process_routes.id', ondelete='CASCADE'),
                         nullable=False, comment='所属工艺路线')
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id'),
                           nullable=False, comment='引用的工序档案')
    seq = db.Column(db.Integer, nullable=False, comment='工序顺序号，从1开始')

    process = db.relationship('Process')

    def __repr__(self) -> str:
        return '<ProcessRouteItem route=%s process=%s seq=%s>' % (
            self.route_id, self.process_id, self.seq)


class WorkOrder(SoftDeleteMixin, db.Model):
    """生产工单。状态机：pending→in_progress→completed→accepted（仅允许相邻流转）。"""
    __tablename__ = 'work_orders'

    # 状态常量与标签（模板直接引用字典渲染）
    STATUS_LABELS = {
        'pending': '待开始',
        'in_progress': '进行中',
        'completed': '已完成',
        'accepted': '已验收',
    }
    # 合法流转：当前状态 → 下一状态
    STATUS_FLOW = {
        'pending': 'in_progress',
        'in_progress': 'completed',
        'completed': 'accepted',
    }
    # L1 优先级标签：表单 choices 与模板渲染共用（本期仅展示/排序，不参与倒排）
    PRIORITY_LABELS = {'high': '高', 'normal': '普通', 'low': '低'}

    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(32), unique=True, nullable=False, comment='单号 WO+日期+序号')
    product_name = db.Column(db.String(128), nullable=False, comment='产品名称快照（引用产品时自动带出）')
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True,
                           comment='关联产品档案（可空，历史工单保留自由文本）')
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True,
                            comment='关联客户档案（可空，历史工单可为空）')
    customer_name = db.Column(db.String(128), nullable=False, default='',
                              comment='客户名称快照（引用客户时自动带出）')
    quantity = db.Column(db.Integer, nullable=False, default=1, comment='数量')
    due_date = db.Column(db.Date, nullable=True, comment='交期')
    # L1 轻量排产：倒排计划字段（计算全部留在 scheduling_service）
    plan_start_date = db.Column(db.Date, nullable=True, comment='计划开工日（倒推的最晚开工日）')
    plan_end_date = db.Column(db.Date, nullable=True, comment='计划完工日（=交期，保留原值）')
    priority = db.Column(db.String(10), nullable=False, default='normal',
                         comment='优先级 high/normal/low（L1 仅展示/排序）')
    plan_manual = db.Column(db.Boolean, nullable=False, default=False,
                            comment='人工覆盖标记：True 时自动重算不改写计划日期')
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='负责人')
    related_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True,
                                      comment='归属部门（P1 数据权限，可空回退负责人部门）')
    status = db.Column(db.String(20), nullable=False, default='pending', comment='状态')
    remark = db.Column(db.String(500), nullable=False, default='', comment='备注')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='创建人')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    # P2-6 质量记录：进行中/已完成工单回填；成品数量=良品+不良，良率/不良率入库保存
    output_qty = db.Column(db.Integer, nullable=False, default=0,
                           comment='成品数量（实际产出，良品+不良）')
    good_qty = db.Column(db.Integer, nullable=False, default=0, comment='合格数量')
    defect_qty = db.Column(db.Integer, nullable=False, default=0, comment='不良数量')
    yield_rate = db.Column(db.Float, nullable=False, default=0, comment='良率(%)')
    defect_rate = db.Column(db.Float, nullable=False, default=0, comment='不良率(%)')
    defect_reason_id = db.Column(db.Integer, db.ForeignKey('defect_reasons.id'), nullable=True,
                                 comment='不良原因（引用主数据）')
    quality_remark = db.Column(db.String(500), nullable=False, default='', comment='质量备注')
    quality_recorded_at = db.Column(db.DateTime, nullable=True, comment='质量记录时间')
    quality_recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True,
                                    comment='质量记录人')

    leader = db.relationship('User', foreign_keys=[leader_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    product = db.relationship('Product', foreign_keys=[product_id])
    customer = db.relationship('Customer', foreign_keys=[customer_id])
    department = db.relationship('Department', foreign_keys=[related_department_id])
    defect_reason = db.relationship('DefectReason', foreign_keys=[defect_reason_id])
    quality_recorder = db.relationship('User', foreign_keys=[quality_recorded_by])
    steps = db.relationship('WorkOrderStep', backref='work_order',
                            order_by='WorkOrderStep.seq', cascade='all, delete-orphan')

    def next_status(self):
        """合法的下一状态，无可流转时返回 None。"""
        return self.STATUS_FLOW.get(self.status)

    @property
    def can_run_steps(self) -> bool:
        """只有「进行中」工单才能执行工序流转/工时修正。

        待开始是计划态（只允许排布工序、领料），已完成/已验收是终态，均不可操作。
        """
        return self.status == 'in_progress'

    def record_quality(self, output_qty: int, good_qty: int, defect_qty: int,
                       reason_id=None, remark: str = '', operator_id=None) -> None:
        """写入质量记录并同步计算良率/不良率（服务端唯一计算口径）。"""
        if output_qty < 0 or good_qty < 0 or defect_qty < 0:
            raise ValueError('数量不能为负数')
        if good_qty + defect_qty != output_qty:
            raise ValueError('良品数量 + 不良数量必须等于成品数量')
        # 仅不良数量非 0 时要求原因；全良品（不良=0）时原因必须允许为空
        if defect_qty > 0 and not reason_id:
            raise ValueError('存在不良品时必须选择不良原因')
        self.output_qty = output_qty
        self.good_qty = good_qty
        self.defect_qty = defect_qty
        self.yield_rate = round(good_qty * 100.0 / output_qty, 2) if output_qty else 0.0
        self.defect_rate = round(defect_qty * 100.0 / output_qty, 2) if output_qty else 0.0
        self.defect_reason_id = reason_id or None
        self.quality_remark = remark or ''
        self.quality_recorded_at = now()
        self.quality_recorded_by = operator_id

    def __repr__(self) -> str:
        return '<WorkOrder %s>' % self.order_no


# 模块级别名：供路由/表单直接 import，与 WorkOrder.PRIORITY_LABELS 同源
PRIORITY_LABELS = WorkOrder.PRIORITY_LABELS


class WorkOrderStep(SoftDeleteMixin, db.Model):
    """工序行项：pending→in_progress→completed。"""
    __tablename__ = 'work_order_steps'

    STATUS_LABELS = {
        'pending': '待开始',
        'in_progress': '进行中',
        'completed': '已完成',
    }
    STATUS_FLOW = {
        'pending': 'in_progress',
        'in_progress': 'completed',
    }

    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=False,
                              comment='所属工单')
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id'), nullable=True,
                           comment='引用的工序档案（历史数据可空）')
    name = db.Column(db.String(128), nullable=False, comment='工序名快照（引用时带出，允许历史留痕）')
    seq = db.Column(db.Integer, nullable=False, default=1, comment='顺序号')
    status = db.Column(db.String(20), nullable=False, default='pending', comment='状态')
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='操作人，可空')
    started_at = db.Column(db.DateTime, nullable=True, comment='开始时间')
    finished_at = db.Column(db.DateTime, nullable=True, comment='完成时间')
    labor_hours = db.Column(db.Float, nullable=False, default=0,
                            comment='消耗工时（小时）：完成时按起止算，允许手动修正')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')

    operator = db.relationship('User', foreign_keys=[operator_id])
    process = db.relationship('Process', foreign_keys=[process_id])

    def auto_labor_hours(self) -> float:
        """按起止时间计算消耗工时（小时，保留 2 位）；缺任一时间返回 0。"""
        if not self.started_at or not self.finished_at:
            return 0.0
        seconds = (self.finished_at - self.started_at).total_seconds()
        return round(max(seconds, 0) / 3600.0, 2) if seconds >= 0 else 0.0

    @property
    def total_hours_display(self) -> str:
        """工时展示（保留两位）。"""
        return '%.2f' % (self.labor_hours or 0)

    def next_status(self):
        """合法的下一状态，无可流转时返回 None。"""
        return self.STATUS_FLOW.get(self.status)

    def __repr__(self) -> str:
        return '<WorkOrderStep %s>' % self.name
