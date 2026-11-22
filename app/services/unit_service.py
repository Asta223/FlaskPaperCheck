"""单位换算服务：把用户录入数量折算为库存基本单位数量。

口径：
- 物料基本单位 = Material.unit 与 Unit.name 精确匹配的主数据；
- 换算关系 1 单位 = factor × 基本单位，不做链式换算；
- 跨量纲拒绝；折算结果不是整数拒绝（库存 quantity 为整数）。
"""
from decimal import Decimal, InvalidOperation

from app import db
from app.models.material import Material
from app.models.unit import Unit, UnitConversion


class UnitConversionError(ValueError):
    """单位/换算关系非法。"""


def base_unit_of(material: Material):
    """取物料基本单位；物料单位未建档案时返回 None（仍允许按基本单位直接收发）。"""
    if material is None or not material.unit:
        return None
    return Unit.query.filter_by(name=material.unit, is_active=True).first()


def get_conversion(material_id: int, unit_id: int):
    """取物料指定换算单位的有效关系，无关系抛错。"""
    unit = db.session.get(Unit, unit_id)
    if unit is None or not unit.is_active:
        raise UnitConversionError('所选单位不存在或已停用')
    conv = UnitConversion.query.filter_by(material_id=material_id, unit_id=unit_id).first()
    if conv is None:
        raise UnitConversionError('物料未维护单位「%s」的换算关系' % unit.name)
    return conv


def resolve_base_quantity(material: Material, unit_id, input_qty):
    """折算录入数量到基本单位数量。

    Returns:
        (base_qty, conv, unit) —— conv/unit 为 None 表示按物料基本单位直接收发。
    """
    try:
        entered = Decimal(str(input_qty))
    except (InvalidOperation, TypeError, ValueError):
        raise UnitConversionError('录入数量非法')
    if entered <= 0:
        raise UnitConversionError('录入数量必须大于0')

    if not unit_id:
        return int(entered), None, None

    conv = get_conversion(material.id, int(unit_id))
    base = base_unit_of(material)
    if base is not None and base.dimension != conv.unit.dimension:
        raise UnitConversionError('单位「%s」与物料基本单位「%s」量纲不同，不能换算' % (
            conv.unit.name, base.name))

    total = entered * Decimal(str(conv.factor))
    if total != total.to_integral_value():
        raise UnitConversionError('按换算系数折算后不是整数，请调整录入数量')
    return int(total), conv, conv.unit


def available_in_unit(available_base: int, conv) -> float:
    """把基本单位余量换算为所选单位可领数量（仅用于前端提示）。"""
    if conv is None:
        return available_base
    factor = Decimal(str(conv.factor))
    return float(Decimal(str(available_base)) / factor)


def display_quantity(base_qty: int, material: Material, conv, unit) -> str:
    """生成可读数量文本：录入单位 + 折合基本单位。"""
    base_name = material.unit if material and material.unit else '基本单位'
    if conv is None:
        return '%s %s' % (base_qty, base_name)
    return '%s%s（折合 %s %s）' % (
        _fmt(Decimal(str(base_qty)) / Decimal(str(conv.factor))), unit.name, base_qty, base_name)


def _fmt(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), 'f')
