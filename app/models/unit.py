"""计量单位档案 + 物料单位换算。

口径：
- 单位档案（units）维护 个/盒/箱/千克 等计量单位，dimension 标记量纲，防止跨量纲换算；
- 换算关系（unit_conversions）挂在物料上：1 换算单位 = factor × 物料基本单位；
- 物料基本单位取 Material.unit 与单位档案 name 精确匹配的那条记录；
- 库存/流水始终以基本单位记账，单据另存录入数量、单位与系数快照。
"""
from app import db
from app.models.mixins import SoftDeleteMixin
from app.utils.time_utils import now


class Unit(SoftDeleteMixin, db.Model):
    """计量单位主数据。"""
    __tablename__ = 'units'

    DIMENSION_LABELS = {
        'quantity': '数量',
        'weight': '重量',
        'length': '长度',
        'volume': '体积',
    }

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), nullable=False, comment='单位编码，如 PCS/BOX')
    name = db.Column(db.String(32), nullable=False, comment='单位名称，如 个/盒')
    dimension = db.Column(db.String(16), nullable=False, default='quantity',
                          comment='量纲：quantity/weight/length/volume')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='是否启用')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    def __repr__(self) -> str:
        return '<Unit %s %s>' % (self.code, self.name)


class UnitConversion(SoftDeleteMixin, db.Model):
    """某物料的换算关系：1 单位 = factor × 物料基本单位（不做链式换算）。"""
    __tablename__ = 'unit_conversions'
    __table_args__ = (
        db.UniqueConstraint('material_id', 'unit_id', name='uq_unit_conversion_mat_unit'),
        db.Index('ix_unit_conversion_material', 'material_id'),
        db.Index('ix_unit_conversion_unit', 'unit_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False,
                            comment='物料')
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False,
                        comment='换算单位')
    factor = db.Column(db.Float, nullable=False, comment='1 换算单位 = factor 基本单位')
    remark = db.Column(db.String(255), nullable=False, default='', comment='备注')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    material = db.relationship('Material', backref='unit_conversions')
    unit = db.relationship('Unit', backref='conversions')

    def __repr__(self) -> str:
        return '<UnitConversion material=%s unit=%s factor=%s>' % (
            self.material_id, self.unit_id, self.factor)
