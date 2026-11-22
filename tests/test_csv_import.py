# -*- coding: utf-8 -*-
"""CSV / Excel 导入测试：字段与导出一致、全量校验、单事务写库、权限控制。"""
import csv
import io
from datetime import date

from conftest import get_csrf, login

from app import db
from app.models.attendance import AttendanceRecord
from app.models.material import Material
from app.models.user import User
from app.models.warehouse import Inventory
from app.services.csv_specs import ATTENDANCE_HEADERS, EMPLOYEE_HEADERS, INVENTORY_HEADERS


def _post_csv(client, url, headers, rows, filename='import.csv'):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    payload = '\ufeff' + buffer.getvalue()
    token = get_csrf(client, url)
    return client.post(
        url,
        data={'csrf_token': token,
              'file': (io.BytesIO(payload.encode('utf-8')), filename)},
        content_type='multipart/form-data',
        follow_redirects=True,
    )


def _post_xlsx(client, url, headers, rows):
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    token = get_csrf(client, url)
    return client.post(
        url,
        data={'csrf_token': token,
              'file': (stream, 'import.xlsx')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )


def test_employee_import_creates_and_updates(client, app_ctx):
    login(client, 'admin', 'admin123')
    url = '/import/hr/employees'

    resp = _post_csv(client, url, EMPLOYEE_HEADERS, [
        ['EMP9999', '测试导入', '生产部', '检验员', '13800009999',
         'import@example.com', '在职'],
    ])
    assert resp.status_code == 200
    assert '导入成功' in resp.get_data(as_text=True)

    with app_ctx.app_context():
        user = User.query.filter_by(employee_no='EMP9999').first()
        assert user is not None
        assert user.username == 'EMP9999'
        assert user.name == '测试导入'
        assert user.department.name == '生产部'
        assert user.position == '检验员'
        assert user.phone == '13800009999'
        assert user.email == 'import@example.com'
        assert user.is_active is True
        assert user.check_password('123456')

    resp = _post_csv(client, url, EMPLOYEE_HEADERS, [
        ['EMP9999', '测试导入改名', '生产部', '质检员', '', '', '离职'],
    ])
    assert '导入成功' in resp.get_data(as_text=True)
    with app_ctx.app_context():
        user = User.query.filter_by(employee_no='EMP9999').first()
        assert user.name == '测试导入改名'
        assert user.position == '质检员'
        assert user.is_active is False
        assert User.query.filter_by(employee_no='EMP9999').count() == 1


def test_employee_import_rejects_entire_file_on_error(client, app_ctx):
    login(client, 'admin', 'admin123')
    resp = _post_csv(client, '/import/hr/employees', EMPLOYEE_HEADERS, [
        ['EMP9998', '合法行', '生产部', '', '', 'ok@example.com', '在职'],
        ['EMP9997', '非法行', '生产部', '', '', 'bad-email', '在职'],
    ])
    body = resp.get_data(as_text=True)
    assert '导入失败' in body
    assert '第 3 行' in body
    assert '邮箱格式不正确' in body

    with app_ctx.app_context():
        assert User.query.filter_by(employee_no='EMP9998').first() is None
        assert User.query.filter_by(employee_no='EMP9997').first() is None


def test_attendance_import_creates_then_updates(client, app_ctx):
    login(client, 'admin', 'admin123')
    url = '/import/attendance/monthly'
    row = ['生产部', '张主管', '2026-11-23', '2026-11-23 09:30',
           '2026-11-23 18:00', '迟到', 30, 0]

    resp = _post_csv(client, url, ATTENDANCE_HEADERS, [row])
    assert '导入成功' in resp.get_data(as_text=True)
    with app_ctx.app_context():
        user = User.query.filter_by(employee_no='EMP0002').first()
        record = AttendanceRecord.query.filter_by(
            user_id=user.id, work_date=date(2026, 11, 23)).first()
        assert record is not None
        assert record.day_status == 'late'
        assert record.late_minutes == 30

    updated = ['生产部', '张主管', '2026-11-23', '2026-11-23 09:00',
               '2026-11-23 18:00', '正常', 0, 0]
    resp = _post_csv(client, url, ATTENDANCE_HEADERS, [updated])
    assert '更新 1 行' in resp.get_data(as_text=True)
    with app_ctx.app_context():
        assert AttendanceRecord.query.filter_by(
            user_id=user.id, work_date=date(2026, 11, 23)).count() == 1
        record = AttendanceRecord.query.filter_by(
            user_id=user.id, work_date=date(2026, 11, 23)).first()
        assert record.day_status == 'normal'
        assert record.late_minutes == 0


def test_inventory_import_csv_and_material_sync(client, app_ctx):
    login(client, 'admin', 'admin123')
    resp = _post_csv(client, '/import/warehouse/inventory', INVENTORY_HEADERS, [
        ['原材料仓', '内六角螺丝', 'M0001', 'M8×30', 'A区-新库位', 50, 10, '正常'],
    ])
    assert '导入成功' in resp.get_data(as_text=True)
    with app_ctx.app_context():
        material = Material.query.filter_by(code='M0001').first()
        inventory = Inventory.query.filter_by(material_id=material.id).first()
        assert inventory.quantity == 50
        assert inventory.warn_threshold == 10
        assert material.storage_location == 'A区-新库位'

    # 状态与数量/阈值矛盾时必须拒绝，且不改库
    resp = _post_csv(client, '/import/warehouse/inventory', INVENTORY_HEADERS, [
        ['原材料仓', '内六角螺丝', 'M0001', 'M8×30', 'A区-新库位', 50, 10, '预警'],
    ])
    assert '状态与数量/阈值不一致' in resp.get_data(as_text=True)
    with app_ctx.app_context():
        material = Material.query.filter_by(code='M0001').first()
        assert Inventory.query.filter_by(material_id=material.id).first().quantity == 50


def test_xlsx_import_supported(client, app_ctx):
    login(client, 'admin', 'admin123')
    resp = _post_xlsx(client, '/import/hr/employees', EMPLOYEE_HEADERS, [
        ['EMP9996', 'Excel导入', '生产部', '', '', 'excel@example.com', '在职'],
    ])
    assert '导入成功' in resp.get_data(as_text=True)
    with app_ctx.app_context():
        assert User.query.filter_by(employee_no='EMP9996').first() is not None


def test_import_rejects_missing_headers(client):
    login(client, 'admin', 'admin123')
    resp = _post_csv(client, '/import/hr/employees', ['工号', '姓名'], [
        ['EMP9995', '少列'],
    ])
    body = resp.get_data(as_text=True)
    assert '缺少必需列' in body
    assert '部门' in body


def test_import_forbidden_without_permission(client):
    login(client, 'staff1', '123456')
    resp = client.get('/import/hr/employees')
    assert resp.status_code == 403
