"""往来单位模型：客户档案、供应商档案（两张独立主数据表）。

第一版只做主数据维护与被业务单据引用，不做应收应付/账期/信用额度。
- 客户挂在工单上（工单是哪个客户下的单），名称写快照；
- 供应商挂在入库单上（这批料是谁送来的）；
- 编码/名称唯一性只校验未删除记录，与产品/工序口径一致。
"""
from app import db
from app.models.mixins import SoftDeleteMixin
from app.utils.time_utils import now


class _PartnerBase(SoftDeleteMixin, db.Model):
    """客户/供应商共用字段（抽象基类，不单独建表）。"""
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), nullable=False, comment='档案编号')
    name = db.Column(db.String(128), nullable=False, comment='单位名称')
    contact = db.Column(db.String(64), nullable=False, default='', comment='联系人')
    phone = db.Column(db.String(64), nullable=False, default='', comment='联系电话')
    address = db.Column(db.String(255), nullable=False, default='', comment='地址')
    tax_no = db.Column(db.String(64), nullable=False, default='', comment='税号')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='是否启用')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    def __repr__(self) -> str:
        return '<%s %s %s>' % (self.__class__.__name__, self.code, self.name)


class Customer(_PartnerBase):
    """客户档案：工单的下单方。"""
    __tablename__ = 'customers'


class Supplier(_PartnerBase):
    """供应商档案：入库单的送货方。"""
    __tablename__ = 'suppliers'
