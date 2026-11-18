# -*- coding: utf-8 -*-
"""P2-3 硬删除测试：所有用户可新增数据支持物理删除。

覆盖设计约束：
- 无引用的错误数据可彻底删除（员工/部门/角色/工序/工单/物料/分类/文件/请假/考勤/消息）；
- 仍被业务数据引用时拒绝删除，不产生悬挂数据；
- 内置角色、当前登录账号、他人消息/记录受保护；
- 出入库单删除时反向冲销库存并追加冲销流水（账实一致 + 审计完整）；
- 操作日志、库存流水等审计数据没有删除路由。
"""
from datetime import date, datetime, timedelta

from conftest import get_csrf, login

from app import db
from app.models import (AttendanceRecord, ChatMessage, Department, FactoryFile,
                        FileCategory, Inventory, LeaveRequest, Material,
                        MaterialCategory, OperationLog, Process, Role, StockDocument,
                        StockLedger, User, Warehouse, WorkOrder, WorkOrderStep)
from app.services.inventory_service import apply_stock_document


def _user(username='tmpuser', **kw):
    u = User(username=username, employee_no=kw.pop('employee_no', 'TMP' + username),
             name=kw.pop('name', username), **kw)
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _dept(name='临时部门'):
    d = Department(name=name)
    db.session.add(d)
    db.session.commit()
    return d


def _material(code='MTEST', name='测试物料'):
    m = Material(code=code, name=name, unit='个')
    db.session.add(m)
    db.session.commit()
    return m


def _warehouse(name='测试仓库'):
    w = Warehouse(name=name)
    db.session.add(w)
    db.session.commit()
    return w


# ---------------- 组织人事 / 权限 ----------------

def test_employee_hard_delete_without_refs(client):
    """新建的错误员工账号无业务引用 → 可彻底删除。"""
    login(client, 'admin', 'admin123')
    target = _user('wrongacct')
    token = get_csrf(client, '/hr/employees')
    resp = client.post('/hr/employees/%d/delete' % target.id, data={'csrf_token': token})
    assert resp.status_code == 302
    assert db.session.get(User, target.id) is None


def test_employee_hard_delete_rejected_when_referenced(client):
    """已有考勤记录的员工 → 拒绝硬删并列出引用来源。"""
    login(client, 'admin', 'admin123')
    target = _user('withrec')
    db.session.add(AttendanceRecord(user_id=target.id, work_date=date(2026, 1, 1),
                                    check_in_at=datetime(2026, 1, 1, 8, 0)))
    db.session.commit()
    token = get_csrf(client, '/hr/employees')
    resp = client.post('/hr/employees/%d/delete' % target.id, data={'csrf_token': token},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert db.session.get(User, target.id) is not None
    assert '考勤记录'.encode() in resp.data


def test_employee_cannot_delete_self(client):
    """不能删除当前登录账号。"""
    login(client, 'admin', 'admin123')
    admin = User.query.filter_by(username='admin').first()
    token = get_csrf(client, '/hr/employees')
    resp = client.post('/hr/employees/%d/delete' % admin.id, data={'csrf_token': token},
                       follow_redirects=True)
    assert '不能删除当前登录账号'.encode() in resp.data
    assert db.session.get(User, admin.id) is not None


def test_department_hard_delete(client):
    """空部门可硬删；有员工引用的部门拒绝。"""
    login(client, 'admin', 'admin123')
    empty = _dept('空部门')
    used = _dept('有用部门')
    worker = _user('deptworker')
    worker.department_id = used.id
    db.session.commit()
    token = get_csrf(client, '/hr/departments')
    r1 = client.post('/hr/departments/%d/purge' % empty.id, data={'csrf_token': token})
    assert r1.status_code == 302
    assert db.session.get(Department, empty.id) is None
    r2 = client.post('/hr/departments/%d/purge' % used.id, data={'csrf_token': token},
                     follow_redirects=True)
    assert r2.status_code == 200
    assert db.session.get(Department, used.id) is not None


def test_role_hard_delete_builtin_and_custom(client):
    """内置角色不可删；无用户持有的自定义角色可删。"""
    login(client, 'admin', 'admin123')
    builtin = Role.query.filter_by(code='staff').first()
    custom = Role(code='wrongrole', name='误建角色', is_builtin=False)
    db.session.add(custom)
    db.session.commit()
    token = get_csrf(client, '/rbac/roles')
    r1 = client.post('/rbac/roles/%d/delete' % builtin.id, data={'csrf_token': token},
                     follow_redirects=True)
    assert '内置角色不能删除'.encode() in r1.data
    r2 = client.post('/rbac/roles/%d/delete' % custom.id, data={'csrf_token': token})
    assert r2.status_code == 302
    assert db.session.get(Role, custom.id) is None


# ---------------- 生产 ----------------

def test_process_hard_delete_referenced_rejected(client):
    """被工单步骤引用的工序拒绝硬删；未引用的可删。"""
    login(client, 'admin', 'admin123')
    free = Process(code='OPF', name='空闲工序')
    used = Process(code='OPU', name='已用工序')
    db.session.add_all([free, used])
    db.session.commit()
    order = WorkOrder(order_no='WOTEST', product_name='测试品', quantity=1,
                      created_by=1)
    db.session.add(order)
    db.session.flush()
    db.session.add(WorkOrderStep(work_order_id=order.id, name='已用工序', seq=1,
                                 process_id=used.id))
    db.session.commit()
    token = get_csrf(client, '/production/processes')
    r1 = client.post('/production/processes/%d/delete' % used.id,
                     data={'csrf_token': token}, follow_redirects=True)
    assert '工单工序'.encode() in r1.data
    assert db.session.get(Process, used.id) is not None
    r2 = client.post('/production/processes/%d/delete' % free.id,
                     data={'csrf_token': token})
    assert r2.status_code == 302
    assert db.session.get(Process, free.id) is None


def test_order_hard_delete_with_step_rejected(client):
    """已有工序的工单拒绝硬删；空工单可删。"""
    login(client, 'admin', 'admin123')
    empty = WorkOrder(order_no='WOEMPTY', product_name='空工单', quantity=1, created_by=1)
    used = WorkOrder(order_no='WOSTEP', product_name='有工序', quantity=1, created_by=1)
    db.session.add_all([empty, used])
    db.session.flush()
    db.session.add(WorkOrderStep(work_order_id=used.id, name='下料', seq=1))
    db.session.commit()
    token = get_csrf(client, '/production/orders')
    r1 = client.post('/production/orders/%d/delete' % used.id,
                     data={'csrf_token': token}, follow_redirects=True)
    assert r1.status_code == 200
    assert db.session.get(WorkOrder, used.id) is not None
    r2 = client.post('/production/orders/%d/delete' % empty.id,
                     data={'csrf_token': token})
    assert r2.status_code == 302
    assert db.session.get(WorkOrder, empty.id) is None


# ---------------- 物料 / 仓库 ----------------

def test_material_and_category_hard_delete(client):
    """无引用物料/分类可硬删；有库存的物料拒绝。"""
    login(client, 'admin', 'admin123')
    cat = MaterialCategory(name='误建分类')
    free = _material('MFREE', '空闲物料')
    used = _material('MUSED', '在用物料')
    db.session.add(cat)
    db.session.commit()
    w = _warehouse()
    db.session.add(Inventory(warehouse_id=w.id, material_id=used.id, quantity=2))
    db.session.commit()
    token = get_csrf(client, '/material/list')
    r1 = client.post('/material/%d/delete' % used.id, data={'csrf_token': token},
                     follow_redirects=True)
    assert '库存记录'.encode() in r1.data
    assert db.session.get(Material, used.id) is not None
    r2 = client.post('/material/%d/delete' % free.id, data={'csrf_token': token})
    assert r2.status_code == 302
    assert db.session.get(Material, free.id) is None
    token2 = get_csrf(client, '/material/categories')
    r3 = client.post('/material/categories/%d/purge' % cat.id, data={'csrf_token': token2})
    assert r3.status_code == 302
    assert db.session.get(MaterialCategory, cat.id) is None


def test_document_hard_delete_reverses_inventory(client):
    """删除入库单 → 库存扣回、追加反向冲销流水，原流水保留。"""
    login(client, 'admin', 'admin123')
    w = _warehouse()
    m = _material('MREVERSE', '冲销测试物料')
    db.session.add(Inventory(warehouse_id=w.id, material_id=m.id, quantity=10))
    db.session.commit()
    doc = apply_stock_document('in', w.id, m.id, 5, 1, 1)
    inv = Inventory.query.filter_by(warehouse_id=w.id, material_id=m.id).first()
    assert inv.quantity == 15
    token = get_csrf(client, '/warehouse/docs')
    resp = client.post('/warehouse/docs/%d/delete' % doc.id, data={'csrf_token': token})
    assert resp.status_code == 302
    assert db.session.get(StockDocument, doc.id) is None
    db.session.refresh(inv)
    assert inv.quantity == 10
    reversals = StockLedger.query.filter_by(doc_no=doc.doc_no + '-R', doc_type='out').all()
    assert len(reversals) == 1
    assert reversals[0].before_balance == 15 and reversals[0].after_balance == 10
    assert StockLedger.query.filter_by(doc_no=doc.doc_no, doc_type='in').count() == 1


def test_document_delete_rejected_when_stock_consumed(client):
    """原入库货已被后续出库消耗 → 拒绝删入库单，库存不变。"""
    login(client, 'admin', 'admin123')
    w = _warehouse()
    m = _material('MCONSUME', '消耗测试物料')
    db.session.add(Inventory(warehouse_id=w.id, material_id=m.id, quantity=0))
    db.session.commit()
    doc_in = apply_stock_document('in', w.id, m.id, 5, 1, 1)
    apply_stock_document('out', w.id, m.id, 5, 1, 1)
    token = get_csrf(client, '/warehouse/docs')
    resp = client.post('/warehouse/docs/%d/delete' % doc_in.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '无法彻底删除'.encode() in resp.data
    assert db.session.get(StockDocument, doc_in.id) is not None
    inv = Inventory.query.filter_by(warehouse_id=w.id, material_id=m.id).first()
    assert inv.quantity == 0


# ---------------- 文件 / 考勤 / 请假 / 聊天 ----------------

def test_file_and_category_hard_delete(client):
    """文件记录可硬删（含磁盘文件）；有文件引用的分类拒绝硬删。"""
    login(client, 'admin', 'admin123')
    cat = FileCategory(name='误建文件分类')
    db.session.add(cat)
    db.session.commit()
    f = FactoryFile(name='测试文件', original_filename='a.txt', stored_filename='harddel.txt',
                    file_ext='.txt', size_bytes=3, uploaded_by=1, category_id=cat.id)
    db.session.add(f)
    db.session.commit()
    from flask import current_app
    disk = '%s/harddel.txt' % current_app.config['UPLOAD_FOLDER'].rstrip('/')
    with open(disk, 'wb') as fp:
        fp.write(b'abc')
    token = get_csrf(client, '/files/')
    r1 = client.post('/files/categories/%d/purge' % cat.id, data={'csrf_token': token},
                     follow_redirects=True)
    assert '文件'.encode() in r1.data  # 有文件引用 → 拒绝
    assert db.session.get(FileCategory, cat.id) is not None
    r2 = client.post('/files/%d/purge' % f.id, data={'csrf_token': token})
    assert r2.status_code == 302
    assert db.session.get(FactoryFile, f.id) is None
    import os
    assert not os.path.exists(disk)


def test_leave_delete_owner_and_forbidden(client):
    """请假：本人可硬删；无权限的其他员工越权返回 403。"""
    staff = User.query.filter_by(username='staff1').first()
    other = User.query.filter_by(username='keeper1').first()
    lv = LeaveRequest(applicant_id=staff.id, department_id=staff.department_id,
                      leave_type='事假', start_at=datetime(2026, 3, 1, 9),
                      end_at=datetime(2026, 3, 1, 10), days=0.04, reason='误提交',
                      status='pending', created_at=datetime(2026, 2, 1, 9))
    db.session.add(lv)
    db.session.commit()
    login(client, other.username, '123456')
    # 我的请假列表无该申请 → 无删除表单，从请假申请页取 CSRF
    token = get_csrf(client, '/attendance/leave/new')
    r1 = client.post('/attendance/leave/%d/delete' % lv.id, data={'csrf_token': token})
    assert r1.status_code == 403
    assert db.session.get(LeaveRequest, lv.id) is not None
    logout_then = login(client, staff.username, '123456')
    token2 = get_csrf(client, '/attendance/leave/list')
    r2 = client.post('/attendance/leave/%d/delete' % lv.id, data={'csrf_token': token2})
    assert r2.status_code == 302
    assert db.session.get(LeaveRequest, lv.id) is None


def test_attendance_record_delete_by_owner(client):
    """员工可硬删自己的打卡记录。"""
    staff = User.query.filter_by(username='staff1').first()
    rec = AttendanceRecord(user_id=staff.id, work_date=date(2026, 4, 1),
                           check_in_at=datetime(2026, 4, 1, 8, 0))
    db.session.add(rec)
    db.session.commit()
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/records')
    resp = client.post('/attendance/records/%d/delete' % rec.id, data={'csrf_token': token})
    assert resp.status_code == 302
    assert db.session.get(AttendanceRecord, rec.id) is None


def test_chat_message_delete_only_sender(client):
    """聊天消息仅发送人可硬删；接收人越权返回 403。"""
    admin = User.query.filter_by(username='admin').first()
    staff = User.query.filter_by(username='staff1').first()
    msg = ChatMessage(sender_id=admin.id, receiver_id=staff.id, content='误发的消息')
    db.session.add(msg)
    db.session.commit()
    # 聊天首页未选会话时无表单 CSRF，从请假申请页取（同一会话 token 通用）
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/leave/new')
    r1 = client.post('/chat/messages/%d/delete' % msg.id, data={'csrf_token': token})
    assert r1.status_code == 403
    assert db.session.get(ChatMessage, msg.id) is not None
    login(client, 'admin', 'admin123')
    r2 = client.post('/chat/messages/%d/delete' % msg.id, data={'csrf_token': token})
    assert r2.status_code == 200
    assert r2.get_json()['code'] == 0
    assert db.session.get(ChatMessage, msg.id) is None


def test_audit_tables_have_no_delete_route(app):
    """操作日志、库存流水等审计数据不提供任何删除路由。"""
    rules = [str(r) for r in app.url_map.iter_rules()]
    assert not any('operation' in r and 'delete' in r for r in rules)
    assert not any('ledger' in r and 'delete' in r for r in rules)
