"""P1 库存流水模型：StockLedger（不可变审计流水）。"""
from app import db
from app.utils.time_utils import now


class StockLedger(db.Model):
    """库存变动流水：由出入库单据/领料在同事务内生成，含变动前后余额。

    不可变审计：无 update/delete 路由，无 is_active 字段。
    绕过单据直接改 Inventory 不产生流水（约定边界）。
    """
    __tablename__ = 'stock_ledgers'
    __table_args__ = (
        db.Index('ix_ledger_mat_created', 'material_id', 'created_at'),
        db.Index('ix_ledger_wh_type_created', 'warehouse_id', 'doc_type', 'created_at'),
        db.Index('ix_ledger_order', 'related_order_id'),
    )

    DOC_TYPE_LABELS = {'in': '入库', 'out': '出库'}

    id = db.Column(db.Integer, primary_key=True)
    doc_no = db.Column(db.String(32), nullable=False, comment='单据号')
    doc_type = db.Column(db.String(8), nullable=False, comment='in/out')
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False,
                             comment='仓库')
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False,
                            comment='物料')
    quantity = db.Column(db.Integer, nullable=False, comment='变动数量（正数，方向看 doc_type）')
    before_balance = db.Column(db.Integer, nullable=False, default=0, comment='变动前余额')
    after_balance = db.Column(db.Integer, nullable=False, default=0, comment='变动后余额')
    related_order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=True,
                                 comment='关联工单，可空')
    handler_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True,
                           comment='经手人，可空')
    remark = db.Column(db.String(255), nullable=False, default='', comment='摘要')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='变动时间')

    warehouse = db.relationship('Warehouse', backref='ledgers')
    material = db.relationship('Material', backref='ledgers')
    handler = db.relationship('User', foreign_keys=[handler_id])
    related_order = db.relationship('WorkOrder', foreign_keys=[related_order_id],
                                    backref='stock_ledgers')

    @property
    def doc_type_label(self) -> str:
        return self.DOC_TYPE_LABELS.get(self.doc_type, self.doc_type)

    def __repr__(self) -> str:
        return '<StockLedger %s %s %s>' % (self.doc_no, self.doc_type, self.material_id)
