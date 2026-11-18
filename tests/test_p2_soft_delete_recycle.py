# -*- coding: utf-8 -*-
"""P2-4 软删除 + 管理员回收站测试。

覆盖：
- 删除后业务列表/详情/下拉不再显示，但数据库记录保留（用 include_deleted 可见）；
- 管理员回收站可见并恢复；普通用户无权限；
- 软删后同编码/同日记录可重建；恢复时唯一性冲突被拒绝；
- 出入库单删除反向冲销库存、恢复时重新入账（两次流水留痕）；
- 删除操作与恢复操作均写 OperationLog。
"""
from datetime import date, datetime

from sqlalchemy import select

from conftest import get_csrf, login

from app import db
from app.models import (AttendanceRecord, Inventory, Material, OperationLog,
                        StockDocument, StockLedger, User, Warehouse)
from app.services.inventory_service import apply_stock_document


def _material(code, name):
    m = Material(code=code, name=name, unit='个')
    db.session.add(m)
    db.session.commit()
    return m


def _warehouse(name):
    w = Warehouse(name=name, location='测试库')
    db.session.add(w)
    db.session.commit()
    return w


def _include_deleted_get(model, obj_id):
    stmt = select(model).where(model.id == obj_id).execution_options(include_deleted=True)
    return db.session.execute(stmt).scalar_one_or_none()


def test_delete_hides_from_list_but_keeps_row(client):
    """物料删除后列表不可见，回收站可见且数据库记录仍在。"""
    login(client, 'admin', 'admin123')
    m = _material('RMAT001', '回收站物料')
    token = get_csrf(client, '/material/list')
    resp = client.post('/material/%d/delete' % m.id, data={'csrf_token': token},
                       follow_redirects=True)
    assert resp.status_code == 200
    # 全局过滤：新查询看不到，列表页也不显示
    assert Material.query.filter_by(code='RMAT001').count() == 0
    assert '回收站物料'.encode() not in client.get('/material/list').data
    kept = _include_deleted_get(Material, m.id)
    assert kept is not None and kept.is_deleted is True    # 数据库保留

    page = client.get('/system/recycle?type=material')
    assert page.status_code == 200
    assert '回收站物料'.encode() in page.data


def test_admin_can_restore_and_non_admin_forbidden(client):
    """superadmin 可恢复；staff 访问回收站被 403 拒绝。"""
    login(client, 'admin', 'admin123')
    m = _material('RMAT002', '恢复测试物料')
    token = get_csrf(client, '/material/list')
    client.post('/material/%d/delete' % m.id, data={'csrf_token': token})

    token2 = get_csrf(client, '/system/recycle?type=material')
    r = client.post('/system/recycle/material/%d/restore' % m.id,
                    data={'csrf_token': token2})
    assert r.status_code == 302
    assert db.session.get(Material, m.id) is not None
    assert _include_deleted_get(Material, m.id).is_deleted is False
    assert OperationLog.query.filter_by(action='restore', target_type='material',
                                        target_id=m.id).count() == 1

    login(client, 'staff1', '123456')
    assert client.get('/system/recycle').status_code == 403


def test_soft_deleted_code_can_be_reused_and_restore_rejected(client):
    """软删不占用唯一编码；若已重建同编码，则旧记录恢复时被拒绝。"""
    login(client, 'admin', 'admin123')
    old = _material('RMAT003', '旧错误物料')
    token = get_csrf(client, '/material/list')
    client.post('/material/%d/delete' % old.id, data={'csrf_token': token})

    # 同编码重建应成功（唯一约束只校验未删除记录）
    r = client.post('/material/new', data={
        'csrf_token': token, 'code': 'RMAT003', 'name': '新正确物料',
        'spec': '', 'unit': '个', 'storage_location': '', 'category_id': 0,
    }, follow_redirects=True)
    assert r.status_code == 200
    new = Material.query.filter_by(code='RMAT003').first()
    assert new is not None and new.id != old.id

    token2 = get_csrf(client, '/system/recycle?type=material')
    resp = client.post('/system/recycle/material/%d/restore' % old.id,
                       data={'csrf_token': token2}, follow_redirects=True)
    assert '无法恢复'.encode() in resp.data
    assert _include_deleted_get(Material, old.id).is_deleted is True


def test_document_delete_and_restore_keeps_inventory_consistent(client):
    """入库单删除扣回库存；恢复后重新入账，恢复流水可追溯。"""
    login(client, 'admin', 'admin123')
    w = _warehouse('回收站测试仓')
    m = _material('RMAT004', '回收站单据物料')
    db.session.add(Inventory(warehouse_id=w.id, material_id=m.id, quantity=10))
    db.session.commit()
    doc = apply_stock_document('in', w.id, m.id, 5, 1, 1)

    token = get_csrf(client, '/warehouse/docs')
    client.post('/warehouse/docs/%d/delete' % doc.id, data={'csrf_token': token})
    inv = Inventory.query.filter_by(warehouse_id=w.id, material_id=m.id).first()
    assert inv.quantity == 10

    token2 = get_csrf(client, '/system/recycle?type=stock_document')
    r = client.post('/system/recycle/stock_document/%d/restore' % doc.id,
                    data={'csrf_token': token2})
    assert r.status_code == 302
    db.session.refresh(inv)
    assert inv.quantity == 15
    assert _include_deleted_get(StockDocument, doc.id).is_deleted is False
    assert StockLedger.query.filter_by(doc_no=doc.doc_no + '-RS', doc_type='in').count() == 1
    assert OperationLog.query.filter_by(action='restore', target_type='stock_document',
                                        target_id=doc.id).count() == 1


def test_attendance_record_can_be_reclocked_after_delete(client):
    """软删当天打卡后可重新签到（唯一约束只在未删除记录中校验）。"""
    login(client, 'admin', 'admin123')
    staff = User.query.filter_by(username='staff1').first()
    rec = AttendanceRecord(user_id=staff.id, work_date=date(2026, 5, 6),
                           check_in_at=datetime(2026, 5, 6, 8, 0))
    db.session.add(rec)
    db.session.commit()
    token = get_csrf(client, '/attendance/leave/new')
    client.post('/attendance/records/%d/delete' % rec.id, data={'csrf_token': token})
    assert db.session.get(AttendanceRecord, rec.id).is_deleted is True

    other = AttendanceRecord(user_id=staff.id, work_date=date(2026, 5, 6),
                             check_in_at=datetime(2026, 5, 6, 9, 0))
    db.session.add(other)
    db.session.commit()
    assert AttendanceRecord.query.filter_by(user_id=staff.id,
                                            work_date=date(2026, 5, 6)).count() == 1
