"""P1 系统通用模型：OperationLog（统一日志）、Notification（站内消息）、StockWarningState（预警去重）。"""
from app import db
from app.utils.time_utils import now


class OperationLog(db.Model):
    """统一操作日志：一表双用（全局日志 P1-15 + 工单日志 P1-06）。

    target_type/target_id 为多态描述（无 FK），覆盖工单/员工/单据/请假等目标。
    日志只读：全项目仅 log_service.log_operation() 追加，无编辑/删除路由。
    """
    __tablename__ = 'operation_logs'
    __table_args__ = (
        db.Index('ix_oplog_module_created', 'module', 'created_at'),
        db.Index('ix_oplog_operator_created', 'operator_id', 'created_at'),
        db.Index('ix_oplog_target', 'target_type', 'target_id', 'created_at'),
    )

    ACTION_LABELS = {
        'login': '登录', 'create': '创建', 'update': '更新',
        'transition': '状态流转', 'approve': '审批', 'issue': '领料',
        'export': '导出', 'import': '导入', 'delete': '删除', 'restore': '恢复',
        'purge': '彻底删除',
    }

    id = db.Column(db.Integer, primary_key=True)
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True,
                            comment='操作人，可空（系统操作）')
    module = db.Column(db.String(32), nullable=False, default='', comment='模块（蓝图名）')
    action = db.Column(db.String(32), nullable=False, default='', comment='动作类型')
    target_type = db.Column(db.String(32), nullable=True, comment='多态目标类型')
    target_id = db.Column(db.Integer, nullable=True, comment='多态目标ID，无FK')
    summary = db.Column(db.String(500), nullable=False, default='', comment='摘要')
    ip = db.Column(db.String(64), nullable=True, comment='操作IP，可空')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='操作时间')

    operator = db.relationship('User', foreign_keys=[operator_id])

    @property
    def action_label(self) -> str:
        return self.ACTION_LABELS.get(self.action, self.action or '-')

    @property
    def operator_name(self) -> str:
        return self.operator.display_name() if self.operator else '系统'

    def __repr__(self) -> str:
        return '<OperationLog %s/%s %s>' % (self.module, self.action, self.target_id)


class Notification(db.Model):
    """站内消息（与人对人 ChatMessage 分离）：当前承载库存预警 notif_type='stock_warning'。"""
    __tablename__ = 'notifications'
    __table_args__ = (
        db.Index('ix_notif_receiver_read', 'receiver_id', 'is_read', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False,
                            comment='接收人')
    notif_type = db.Column(db.String(32), nullable=False, default='stock_warning',
                           comment='消息类型')
    title = db.Column(db.String(128), nullable=False, default='', comment='标题')
    content = db.Column(db.String(500), nullable=False, default='', comment='内容')
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=True,
                            comment='关联物料，可空')
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True,
                             comment='关联仓库，可空')
    link_url = db.Column(db.String(255), nullable=False, default='', comment='跳转链接')
    is_read = db.Column(db.Boolean, nullable=False, default=False, comment='是否已读')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    receiver = db.relationship('User', foreign_keys=[receiver_id])

    def __repr__(self) -> str:
        return '<Notification %s -> %s>' % (self.notif_type, self.receiver_id)


class StockWarningState(db.Model):
    """库存预警去重状态：UNIQUE(warehouse_id, material_id)。

    低位只推一次；回升复位 is_low=False 后再次跌破可再推（A4）。
    """
    __tablename__ = 'stock_warning_states'
    __table_args__ = (
        db.UniqueConstraint('warehouse_id', 'material_id', name='uq_stock_warn_wh_mat'),
    )

    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False,
                             comment='仓库')
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False,
                            comment='物料')
    is_low = db.Column(db.Boolean, nullable=False, default=False, comment='当前是否处于低位')
    last_notified_at = db.Column(db.DateTime, nullable=True, comment='最近推送时间')

    def __repr__(self) -> str:
        return '<StockWarningState wh=%s mat=%s low=%s>' % (
            self.warehouse_id, self.material_id, self.is_low)
