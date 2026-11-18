"""生产模型：工单与工序行项（状态机流转）。"""
from app import db
from app.utils.time_utils import now


class WorkOrder(db.Model):
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

    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(32), unique=True, nullable=False, comment='单号 WO+日期+序号')
    product_name = db.Column(db.String(128), nullable=False, comment='产品名称')
    quantity = db.Column(db.Integer, nullable=False, default=1, comment='数量')
    due_date = db.Column(db.Date, nullable=True, comment='交期')
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='负责人')
    related_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True,
                                      comment='归属部门（P1 数据权限，可空回退负责人部门）')
    status = db.Column(db.String(20), nullable=False, default='pending', comment='状态')
    remark = db.Column(db.String(500), nullable=False, default='', comment='备注')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='创建人')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    leader = db.relationship('User', foreign_keys=[leader_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    department = db.relationship('Department', foreign_keys=[related_department_id])
    steps = db.relationship('WorkOrderStep', backref='work_order',
                            order_by='WorkOrderStep.seq', cascade='all, delete-orphan')

    def next_status(self):
        """合法的下一状态，无可流转时返回 None。"""
        return self.STATUS_FLOW.get(self.status)

    def __repr__(self) -> str:
        return '<WorkOrder %s>' % self.order_no


class WorkOrderStep(db.Model):
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
    name = db.Column(db.String(128), nullable=False, comment='工序名')
    seq = db.Column(db.Integer, nullable=False, default=1, comment='顺序号')
    status = db.Column(db.String(20), nullable=False, default='pending', comment='状态')
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='操作人，可空')
    started_at = db.Column(db.DateTime, nullable=True, comment='开始时间')
    finished_at = db.Column(db.DateTime, nullable=True, comment='完成时间')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')

    operator = db.relationship('User', foreign_keys=[operator_id])

    def next_status(self):
        """合法的下一状态，无可流转时返回 None。"""
        return self.STATUS_FLOW.get(self.status)

    def __repr__(self) -> str:
        return '<WorkOrderStep %s>' % self.name
