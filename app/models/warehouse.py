"""仓库模型：仓库档案、库存、出入库单据。"""
from app import db
from app.utils.time_utils import now


class Warehouse(db.Model):
    """仓库档案。"""
    __tablename__ = 'warehouses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, comment='仓库名称')
    location = db.Column(db.String(128), nullable=False, default='', comment='位置')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='停用=软删')

    def __repr__(self) -> str:
        return '<Warehouse %s>' % self.name


class Inventory(db.Model):
    """库存：(warehouse_id, material_id) 唯一；quantity 约定 >=0（出库校验保证）。"""
    __tablename__ = 'inventories'
    __table_args__ = (
        db.UniqueConstraint('warehouse_id', 'material_id', name='uq_inventory_wh_mat'),
    )

    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False,
                             comment='仓库')
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False,
                            comment='物料')
    quantity = db.Column(db.Integer, nullable=False, default=0, comment='当前数量 >=0')
    warn_threshold = db.Column(db.Integer, nullable=False, default=0, comment='预警阈值')

    warehouse = db.relationship('Warehouse', backref='inventories')
    material = db.relationship('Material', backref='inventories')

    @property
    def is_warning(self) -> bool:
        """库存是否低于等于预警阈值（页面标红）。"""
        return (self.quantity or 0) <= (self.warn_threshold or 0)

    def __repr__(self) -> str:
        return '<Inventory wh=%s mat=%s qty=%s>' % (self.warehouse_id, self.material_id, self.quantity)


class StockDocument(db.Model):
    """出入库单据（P0：单物料/单）。doc_type ∈ {'in','out'}。"""
    __tablename__ = 'stock_documents'

    DOC_TYPE_LABELS = {'in': '入库', 'out': '出库'}

    id = db.Column(db.Integer, primary_key=True)
    doc_no = db.Column(db.String(32), unique=True, nullable=False, comment='单据号 IN/OUT 前缀')
    doc_type = db.Column(db.String(8), nullable=False, comment='in=入库 out=出库')
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False,
                             comment='仓库')
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False,
                            comment='物料（P0 单物料/单）')
    quantity = db.Column(db.Integer, nullable=False, comment='数量 >0')
    handler_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='经手人')
    related_order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=True,
                                 comment='关联工单，可空（P1 领料用）')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='创建人')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    warehouse = db.relationship('Warehouse', backref='documents')
    material = db.relationship('Material', backref='documents')
    handler = db.relationship('User', foreign_keys=[handler_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    related_order = db.relationship('WorkOrder', backref='stock_documents')

    def __repr__(self) -> str:
        return '<StockDocument %s>' % self.doc_no
