"""库存事务服务：出入库单据提交与库存增减同一事务，保证原子一致。

出库前 with_for_update() 行锁校验余量（MySQL InnoDB 生效；SQLite 单写者天然串行），
不足则抛 InsufficientStockError 并整体回滚。
"""
from app import db
from app.models.material import Material
from app.models.warehouse import Inventory, StockDocument, Warehouse
from app.utils.time_utils import now


class InsufficientStockError(Exception):
    """出库余量不足。"""

    def __init__(self, available: int = 0):
        super().__init__('库存不足')
        self.available = available or 0


class InventoryServiceError(ValueError):
    """单据参数非法（物料/仓库无效、数量<=0 等）。"""


def _generate_doc_no(doc_type: str) -> str:
    """生成唯一单据号：IN/OUT + 日期 + 4 位当日序号。"""
    prefix = 'IN' if doc_type == 'in' else 'OUT'
    date_str = now().strftime('%Y%m%d')
    seq = 1
    while True:
        doc_no = '%s%s%04d' % (prefix, date_str, seq)
        if not StockDocument.query.filter_by(doc_no=doc_no).first():
            return doc_no
        seq += 1


def apply_stock_document(doc_type: str, warehouse_id: int, material_id: int, quantity: int,
                         handler_id: int, created_by: int,
                         related_order_id=None, remark: str = '') -> StockDocument:
    """提交出入库单并同事务更新库存。

    - 入库：无库存记录则新建，数量累加；
    - 出库：余量不足抛 InsufficientStockError（可用余量见 e.available），整体回滚；
    - 成功：提交事务并返回单据。
    """
    if doc_type not in ('in', 'out'):
        raise InventoryServiceError('单据类型非法')
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        raise InventoryServiceError('数量必须为正整数')
    if qty <= 0:
        raise InventoryServiceError('数量必须大于0')

    warehouse = Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()
    if warehouse is None:
        raise InventoryServiceError('仓库不存在或已停用')
    material = Material.query.filter_by(id=material_id, is_active=True).first()
    if material is None:
        raise InventoryServiceError('物料不存在或已停用')

    try:
        # 行锁（MySQL）；SQLite 忽略 FOR UPDATE，由单写者保证串行
        inv = (Inventory.query
               .filter_by(warehouse_id=warehouse.id, material_id=material.id)
               .with_for_update()
               .first())
        if doc_type == 'in':
            if inv is None:
                inv = Inventory(warehouse_id=warehouse.id, material_id=material.id,
                                quantity=0, warn_threshold=0)
                db.session.add(inv)
            inv.quantity = (inv.quantity or 0) + qty
        else:
            if inv is None or (inv.quantity or 0) < qty:
                available = inv.quantity if inv is not None else 0
                db.session.rollback()
                raise InsufficientStockError(available)
            inv.quantity = inv.quantity - qty

        doc = StockDocument(
            doc_no=_generate_doc_no(doc_type),
            doc_type=doc_type,
            warehouse_id=warehouse.id,
            material_id=material.id,
            quantity=qty,
            handler_id=handler_id,
            related_order_id=related_order_id,
            remark=remark or '',
            created_by=created_by,
        )
        db.session.add(doc)
        db.session.commit()
        return doc
    except InsufficientStockError:
        raise
    except Exception:
        db.session.rollback()
        raise
