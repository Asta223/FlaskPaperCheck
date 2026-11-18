"""站内通知服务（P1-09）：库存预警推送（去重 + 失败隔离）+ 未读聚合 + 标记已读。

去重（A4）：同一 (仓库, 物料) 在低位期间只推一次；回升后复位可再推。
并发兜底：StockWarningState 的 UNIQUE(warehouse_id, material_id) + IntegrityError 处理。
失败隔离：push_stock_warning 内部捕获所有异常并记日志，绝不向上抛出影响库存主流程。
"""
from flask import current_app

from app import db
from app.models.system import Notification, StockWarningState
from app.models.user import User
from app.models.warehouse import Inventory
from app.utils.time_utils import now


def _keeper_user_ids() -> list:
    """所有 keeper 角色用户 id（A9：默认推给全体仓管员）。"""
    from app.models.rbac import Role, role_permissions
    from app.models.user import user_roles
    rows = (db.session.query(User.id)
            .join(user_roles, user_roles.c.user_id == User.id)
            .join(Role, Role.id == user_roles.c.role_id)
            .filter(Role.code == 'keeper', User.is_active.is_(True))
            .all())
    return [r[0] for r in rows]


def push_stock_warning(warehouse_id: int, material_id: int) -> int:
    """库存预警推送（主流程提交后调用；失败仅记日志，返回推送条数）。

    返回本次新增的 Notification 条数（低位首次触发=keeper 人数，跳过/失败=0）。
    """
    try:
        inv = (Inventory.query
               .filter_by(warehouse_id=warehouse_id, material_id=material_id)
               .first())
        if inv is None:
            return 0
        is_low = (inv.quantity or 0) <= (inv.warn_threshold or 0)

        state = (StockWarningState.query
                 .filter_by(warehouse_id=warehouse_id, material_id=material_id)
                 .first())

        if not is_low:
            # 已回升：复位，使下次跌破可再推
            if state is not None and state.is_low:
                state.is_low = False
                db.session.commit()
            return 0

        # 处于低位且未处于 is_low → 推送一次
        if state is not None and state.is_low:
            return 0

        # upsert 去重状态（并发兜底：唯一约束冲突视为已被其他请求推送）
        created_state = False
        if state is None:
            state = StockWarningState(warehouse_id=warehouse_id, material_id=material_id,
                                      is_low=True, last_notified_at=now())
            db.session.add(state)
            created_state = True
        else:
            state.is_low = True
            state.last_notified_at = now()

        material_name = inv.material.name if inv.material else '物料'
        wh_name = inv.warehouse.name if inv.warehouse else '仓库'
        content = '%s / %s 当前库存 %d，已低于预警阈值 %d' % (
            wh_name, material_name, inv.quantity or 0, inv.warn_threshold or 0)
        keepers = _keeper_user_ids()
        for uid in keepers:
            db.session.add(Notification(
                receiver_id=uid, notif_type='stock_warning',
                title='库存预警：%s' % material_name, content=content,
                material_id=material_id, warehouse_id=warehouse_id,
                link_url='/warehouse/inventory?only_warning=1', is_read=False,
                created_at=now()))
        db.session.commit()
        return len(keepers)
    except Exception as exc:  # 失败隔离：绝不因通知失败影响单据主流程
        db.session.rollback()
        try:
            current_app.logger.warning('push_stock_warning failed: %s', exc)
        except Exception:
            pass
        return 0


def unread_warning_count(user_id: int) -> int:
    """某用户未读预警数（顶部角标聚合）。"""
    return (Notification.query
            .filter_by(receiver_id=user_id, notif_type='stock_warning', is_read=False)
            .count())


def list_warnings(user_id: int, limit: int = 50) -> list:
    """某用户的预警消息列表（倒序）。"""
    return (Notification.query
            .filter_by(receiver_id=user_id, notif_type='stock_warning')
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit).all())


def mark_warning_read(notif_id: int, user_id: int) -> bool:
    """标记某条预警为已读（仅接收人本人）。"""
    notif = db.session.get(Notification, notif_id)
    if notif is None or notif.receiver_id != user_id:
        return False
    notif.is_read = True
    db.session.commit()
    return True


def mark_all_warnings_read(user_id: int) -> int:
    """标记某用户全部预警为已读，返回更新条数。"""
    return (Notification.query
            .filter_by(receiver_id=user_id, notif_type='stock_warning', is_read=False)
            .update({'is_read': True}))
