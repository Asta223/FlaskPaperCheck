"""仓库管理表单：仓库档案、出入库单据、预警阈值。"""
from flask_wtf import FlaskForm
from wtforms import HiddenField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

ZERO_CHOICE = (0, '-- 无 --')


def fill_warehouse_doc_choices(form) -> None:
    """运行时填充：仓库/物料/关联工单下拉。"""
    from app.models.material import Material
    from app.models.production import WorkOrder
    from app.models.warehouse import Warehouse
    form.warehouse_id.choices = [
        (w.id, w.name) for w in Warehouse.query.filter_by(is_active=True).order_by(Warehouse.id).all()
    ]
    form.material_id.choices = [
        (m.id, '%s（%s）%s' % (m.name, m.code,
                              ('【库位：%s】' % m.storage_location) if m.storage_location else ''))
        for m in Material.query.filter_by(is_active=True).order_by(Material.code).all()
    ]
    open_orders = WorkOrder.query.filter(WorkOrder.status.in_(['pending', 'in_progress'])) \
        .order_by(WorkOrder.id.desc()).limit(100).all()
    form.related_order_id.choices = [ZERO_CHOICE] + [
        (o.id, '%s（%s）' % (o.order_no, o.product_name)) for o in open_orders
    ]


class WarehouseForm(FlaskForm):
    """仓库档案表单。"""
    name = StringField('仓库名称', validators=[DataRequired(message='请输入仓库名称'), Length(max=64)])
    location = StringField('位置', validators=[Optional(), Length(max=128)])
    submit = SubmitField('保存')


class StockDocForm(FlaskForm):
    """出入库单据表单（P0：单物料/单）。"""
    doc_type = SelectField('单据类型', choices=[('in', '入库'), ('out', '出库')],
                           validators=[DataRequired(message='请选择单据类型')])
    warehouse_id = SelectField('仓库', coerce=int,
                               validators=[DataRequired(message='请选择仓库')])
    material_id = SelectField('物料', coerce=int,
                              validators=[DataRequired(message='请选择物料')])
    quantity = IntegerField('数量', validators=[
        DataRequired(message='请输入数量'), NumberRange(min=1, message='数量必须大于0'),
    ])
    related_order_id = SelectField('关联工单', coerce=int, validators=[Optional()])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('提交单据')


class InventoryThresholdForm(FlaskForm):
    """库存预警阈值设置。"""
    inventory_id = HiddenField('库存ID', validators=[DataRequired()])
    warn_threshold = IntegerField('预警阈值', validators=[
        DataRequired(message='请输入阈值'), NumberRange(min=0, message='阈值不能为负'),
    ])
    submit = SubmitField('保存阈值')
