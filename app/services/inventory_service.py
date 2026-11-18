"""库存事务服务：出入库单据提交与库存增减同一事务，保证原子一致。

出库前 with_for_update() 行锁校验余量（MySQL InnoDB 生效；SQLite 单写者天然串行），
不足则抛 InsufficientStockError 并整体回滚。

P1 增量（零回归约束）：
- 事务内同 commit 追加 StockLedger 流水（库存/单据/流水三者原子）；
- commit 成功后触发库存预警推送（try/except 隔离，失败不回滚单据）；
- 领料场景可经 work_order_log 参数在同事务内追加工单 OperationLog（三步原子）。
  以上均为新增可选参数/内部行为，P0 既有调用签名与返回值语义完全不变。
"""
from app import db
from app.models.ledger import StockLedger
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
        exists = (StockDocument.query.execution_options(include_deleted=True)
                  .filter_by(doc_no=doc_no).first())
        if not exists:
            return doc_no
        seq += 1


def reverse_stock_document(doc: StockDocument, operator_id: int) -> int:
    """软删除单据时反向冲销库存，并追加一条冲销流水（同事务）。

    - 原入库单 → 从库存扣回数量；库存已被后续出库消耗则拒绝删除；
    - 原出库单 → 把数量加回库存；
    - 原流水作为不可变审计保留，新增方向相反的冲销流水（单号后缀 -R）。

    Returns:
        冲销后的库存数量。

    Raises:
        InsufficientStockError: 原入库单对应的库存不足以扣回。
    """
    inv = (Inventory.query
           .filter_by(warehouse_id=doc.warehouse_id, material_id=doc.material_id)
           .with_for_update().first())
    before = (inv.quantity or 0) if inv is not None else 0
    if doc.doc_type == 'in':
        if before < doc.quantity:
            db.session.rollback()
            raise InsufficientStockError(before)
        after = before - doc.quantity
    else:  # out：加回
        after = before + doc.quantity
    if inv is None:
        inv = Inventory(warehouse_id=doc.warehouse_id, material_id=doc.material_id,
                        quantity=0, warn_threshold=0)
        db.session.add(inv)
    inv.quantity = after

    reverse_type = 'out' if doc.doc_type == 'in' else 'in'
    db.session.add(StockLedger(
        doc_no='%s-R' % doc.doc_no,
        doc_type=reverse_type,
        warehouse_id=doc.warehouse_id,
        material_id=doc.material_id,
        quantity=doc.quantity,
        before_balance=before,
        after_balance=after,
        related_order_id=doc.related_order_id,
        handler_id=operator_id,
        remark='冲销单据 %s（删除%s单，回收站可恢复）' % (
            doc.doc_no, '入' if doc.doc_type == 'in' else '出'),
        created_at=now(),
    ))
    return after


def restore_stock_document(doc: StockDocument, operator_id: int) -> int:
    """回收站恢复单据时重新入账：按原方向调整库存并追加恢复流水（同事务）。

    - 原入库单：库存加回（删除时已扣回）；
    - 原出库单：库存再次扣减（删除时已加回），余量不足则拒绝恢复；
    - 原单据不新建、单号不变，流水以 -RS 后缀区分（审计可追溯）。
    """
    inv = (Inventory.query
           .filter_by(warehouse_id=doc.warehouse_id, material_id=doc.material_id)
           .with_for_update().first())
    before = (inv.quantity or 0) if inv is not None else 0
    if doc.doc_type == 'out':
        if before < doc.quantity:
            db.session.rollback()
            raise InsufficientStockError(before)
        after = before - doc.quantity
    else:  # in：加回
        after = before + doc.quantity
    if inv is None:
        inv = Inventory(warehouse_id=doc.warehouse_id, material_id=doc.material_id,
                        quantity=0, warn_threshold=0)
        db.session.add(inv)
    inv.quantity = after

    db.session.add(StockLedger(
        doc_no='%s-RS' % doc.doc_no,
        doc_type=doc.doc_type,
        warehouse_id=doc.warehouse_id,
        material_id=doc.material_id,
        quantity=doc.quantity,
        before_balance=before,
        after_balance=after,
        related_order_id=doc.related_order_id,
        handler_id=operator_id,
        remark='恢复单据 %s（回收站恢复重新入账）' % doc.doc_no,
        created_at=now(),
    ))
    return after


def apply_stock_document(doc_type: str, warehouse_id: int, material_id: int, quantity: int,
                         handler_id: int, created_by: int,
                         related_order_id=None, remark: str = '',
                         work_order_log: dict = None) -> StockDocument:
    """提交出入库单并同事务更新库存 + 追加流水。

    - 入库：无库存记录则新建，数量累加；
    - 出库：余量不足抛 InsufficientStockError（可用余量见 e.available），整体回滚；
    - 成功：提交事务，写入流水，触发预警（失败隔离），返回单据。

    Args:
        work_order_log: 可选，领料场景的同事务工单日志配置
            {'order_id': int, 'summary': str, 'operator_id': int}。P0 调用方无需传。
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
        before = inv.quantity or 0 if inv is not None else 0
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
        after = inv.quantity or 0

        doc = StockDocument(
            doc_no=_generate_doc_no(doc_type),
            doc_type=doc_type,
            warehouse_id=warehouse.id,
            material_id=material.id,
            quantity=qty,
            handler_id=handler_id,
            related_order_id=related_order_id or None,  # 规范化 0/空为 None，避免悬空外键
            remark=remark or '',
            created_by=created_by,
        )
        db.session.add(doc)
        db.session.flush()  # 取 doc.id，流水用 doc.doc_no（无需 id，但确保单据先落库顺序）

        # P1-15：出入库单据留痕（与业务同事务，失败操作不会走到此处）
        from app.services.log_service import log_operation
        log_operation(
            module='warehouse', action='create', target_type='stock_document',
            target_id=doc.id,
            summary='%s单据 %s：%s#%s ×%s%s' % (
                '入库' if doc_type == 'in' else '出库', doc.doc_no,
                warehouse.name, material.name, qty,
                ('（关联工单#%s）' % doc.related_order_id) if doc.related_order_id else ''),
            operator_id=created_by,
        )

        # P1-07：同事务生成不可变流水（含变动前后余额）
        ledger = StockLedger(
            doc_no=doc.doc_no,
            doc_type=doc_type,
            warehouse_id=warehouse.id,
            material_id=material.id,
            quantity=qty,
            before_balance=before,
            after_balance=after,
            related_order_id=doc.related_order_id,
            handler_id=handler_id,
            remark=remark or '',
            created_at=now(),
        )
        db.session.add(ledger)

        # 领料场景：同事务追加工单操作日志（三步原子）
        if work_order_log:
            from app.services.log_service import log_operation
            log_operation(module='production', action='issue',
                          target_type='work_order',
                          target_id=work_order_log.get('order_id'),
                          summary=work_order_log.get('summary', '') or '工单领料',
                          operator_id=work_order_log.get('operator_id'))

        db.session.commit()
    except InsufficientStockError:
        raise
    except Exception:
        db.session.rollback()
        raise

    # 主事务已提交：预警独立处理，失败不影响单据（失败隔离）
    try:
        from app.services.notification_service import push_stock_warning
        push_stock_warning(warehouse.id, material.id)
    except Exception:  # 双保险：即便 notification_service 未捕获也不影响主流程
        try:
            current_app_logger = __import__('flask').current_app.logger
            current_app_logger.warning('stock warning hook failed, ignored')
        except Exception:
            pass

    return doc
