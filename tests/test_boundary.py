# -*- coding: utf-8 -*-
"""边界与负面测试：CSRF、非整数参数、超长输入、IDOR、404/403 语义、缺字段表单。"""
import io

import pytest

from conftest import get_csrf, login

from app import db
from app.models import FactoryFile, Role, User, WorkOrder


# ---------------- CSRF 保护 ----------------

def test_post_without_csrf_rejected_clock(client):
    login(client, 'admin', 'admin123')
    resp = client.post('/attendance/clock', data={'action': 'in'})
    assert resp.status_code == 400


def test_post_without_csrf_rejected_chat_send(client):
    login(client, 'admin', 'admin123')
    resp = client.post('/chat/send', data={'receiver_id': '2', 'content': 'hi'})
    assert resp.status_code == 400


def test_post_without_csrf_rejected_order_status(client):
    login(client, 'producer1', '123456')
    order = WorkOrder(order_no='WO20250101777', product_name='CSRF测试', quantity=1,
                      created_by=1)
    db.session.add(order)
    db.session.commit()
    resp = client.post('/production/orders/%d/status' % order.id, data={'status': 'completed'})
    assert resp.status_code == 400


# ---------------- 非整数查询参数（不应 500） ----------------

@pytest.mark.parametrize('url', [
    '/production/orders?page=abc',
    '/production/orders?leader_id=abc&status=zzz',
    '/warehouse/inventory?warehouse_id=abc&only_warning=abc&page=xyz',
    '/warehouse/docs?page=abc&doc_type=zzz',
    '/hr/employees?dept_id=abc&page=xyz&keyword=<script>',
    '/attendance/records?page=abc&user_id=abc',
    '/attendance/monthly?year=abc&month=abc',
    '/files/?cat_id=abc&page=abc',
    '/material/list?cat_id=abc&page=abc',
])
def test_non_integer_params_no_500(client, url):
    login(client, 'admin', 'admin123')
    resp = client.get(url)
    assert resp.status_code == 200, '%s → %s' % (url, resp.status_code)


# ---------------- 不存在的资源 ID（404/优雅处理，不应 500） ----------------

@pytest.mark.parametrize('url', [
    '/production/orders/99999',
    '/files/99999/download',
    '/hr/employees/99999/edit',
    '/material/99999/edit',
    '/warehouse/warehouses',
])
def test_nonexistent_id_graceful(client, url):
    login(client, 'admin', 'admin123')
    resp = client.get(url)
    assert resp.status_code in (200, 302, 404), '%s → %s' % (url, resp.status_code)
    assert resp.status_code != 500


def test_nonexistent_order_status_post_404(client):
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/99999/status',
                       data={'csrf_token': token, 'status': 'completed'})
    assert resp.status_code == 404


def test_chat_page_nonexistent_peer_graceful(client):
    login(client, 'admin', 'admin123')
    resp = client.get('/chat/?peer_id=99999')
    assert resp.status_code in (200, 302, 404)
    assert resp.status_code != 500


# ---------------- IDOR：文件可见范围 ----------------

def _upload_as_admin(client, visibility='roles', role_ids=None):
    # 上传表单在独立页面，token 从 /files/upload 取（/files/ 页 token 为裸文本无 name 属性）
    token = get_csrf(client, '/files/upload')
    data = {'csrf_token': token, 'category_id': 0,
            'file': (io.BytesIO('机密图纸内容'.encode('utf-8')), 'secret.txt'),
            'visibility_type': visibility}
    if role_ids:
        data['role_ids'] = str(role_ids)
    resp = client.post('/files/upload', data=data, follow_redirects=True)
    assert resp.status_code == 200
    return FactoryFile.query.order_by(FactoryFile.id.desc()).first()


def test_file_roles_visibility_idor(client):
    """可见范围=指定角色：无该角色的员工下载应 403，有该角色可下载。"""
    login(client, 'admin', 'admin123')
    keeper_role = Role.query.filter_by(code='keeper').first()
    file_rec = _upload_as_admin(client, visibility='roles', role_ids=keeper_role.id)
    assert file_rec is not None
    # staff1（无 keeper 角色）→ 403
    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    resp = client.get('/files/%d/download' % file_rec.id)
    assert resp.status_code == 403
    # staff1 文件列表也不应出现该文件
    resp = client.get('/files/')
    assert 'secret.txt'.encode() not in resp.data
    # keeper1 → 200 且内容正确
    client.get('/auth/logout')
    login(client, 'keeper1', '123456')
    resp = client.get('/files/%d/download' % file_rec.id)
    assert resp.status_code == 200
    assert '机密图纸内容'.encode() in resp.data


def test_file_all_visibility_downloadable_by_staff(client):
    login(client, 'admin', 'admin123')
    file_rec = _upload_as_admin(client, visibility='all')
    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    resp = client.get('/files/%d/download' % file_rec.id)
    assert resp.status_code == 200


def test_upload_disallowed_extension_rejected(client):
    """非白名单扩展名上传应被拒绝（不落盘不落库）。"""
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/files/upload')
    resp = client.post('/files/upload', data={
        'csrf_token': token, 'category_id': 0,
        'file': (io.BytesIO(b'MZ malicious'), 'evil.exe'),
        'visibility_type': 'all'}, follow_redirects=True)
    assert resp.status_code == 200  # 表单校验失败重新渲染
    assert FactoryFile.query.filter(FactoryFile.original_filename == 'evil.exe').count() == 0


# ---------------- 表单缺字段 / 超长输入 ----------------

def test_order_new_missing_fields_no_500(client):
    login(client, 'producer1', '123456')
    baseline = WorkOrder.query.count()
    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data={'csrf_token': token},
                       follow_redirects=True)
    assert resp.status_code == 200  # 重新渲染表单
    assert WorkOrder.query.count() == baseline


def test_order_new_overlong_name_no_500(client):
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data={
        'csrf_token': token, 'product_name': '长' * 300, 'quantity': 1,
        'leader_id': 0, 'remark': ''}, follow_redirects=True)
    assert resp.status_code != 500
    assert WorkOrder.query.filter(WorkOrder.product_name == '长' * 300).count() == 0


def test_employee_new_missing_password_rejected(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/hr/employees/new')
    resp = client.post('/hr/employees/new', data={
        'csrf_token': token, 'username': 'nopwd', 'employee_no': 'E9001',
        'name': '无密码', 'department_id': 0, 'hire_date': '2025-01-01',
        'password': ''}, follow_redirects=True)
    assert '初始密码'.encode() in resp.data
    assert User.query.filter_by(username='nopwd').first() is None


def test_employee_new_duplicate_username_rejected(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/hr/employees/new')
    resp = client.post('/hr/employees/new', data={
        'csrf_token': token, 'username': 'staff1', 'employee_no': 'E9002',
        'name': '重复名', 'department_id': 0, 'hire_date': '2025-01-01',
        'password': 'abc12345'}, follow_redirects=True)
    assert '登录名已存在'.encode() in resp.data
    assert User.query.filter_by(employee_no='E9002').first() is None


def test_employee_new_invalid_username_charset_rejected(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/hr/employees/new')
    resp = client.post('/hr/employees/new', data={
        'csrf_token': token, 'username': 'bad name!', 'employee_no': 'E9003',
        'name': '非法登录名', 'department_id': 0, 'hire_date': '2025-01-01',
        'password': 'abc12345'}, follow_redirects=True)
    assert resp.status_code != 500
    assert User.query.filter_by(employee_no='E9003').first() is None


def test_warehouse_doc_new_missing_fields_no_500(client):
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={'csrf_token': token},
                       follow_redirects=True)
    assert resp.status_code == 200


# ---------------- 停用账号无法登录后的数据保留 ----------------

def test_toggle_employee_blocks_login_keeps_data(client):
    """离职停用后：无法登录，但历史数据（考勤记录等）保留。"""
    from app.models import AttendanceRecord
    from datetime import date, datetime
    login(client, 'admin', 'admin123')
    staff = User.query.filter_by(username='staff1').first()
    db.session.add(AttendanceRecord(user_id=staff.id, work_date=date(2025, 1, 6),
                                    check_in_at=datetime(2025, 1, 6, 9, 0)))
    db.session.commit()
    staff_id = staff.id
    token = get_csrf(client, '/hr/employees')
    resp = client.post('/hr/employees/%d/toggle' % staff_id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '已停用'.encode() in resp.data
    db.session.expire_all()
    assert User.query.get(staff_id).is_active is False
    assert AttendanceRecord.query.filter_by(user_id=staff_id).count() == 1
    client.get('/auth/logout')
    resp = login(client, 'staff1', '123456')
    assert '账号已停用'.encode() in resp.data
