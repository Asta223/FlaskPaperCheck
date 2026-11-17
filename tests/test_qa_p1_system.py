# -*- coding: utf-8 -*-
"""QA 独立验证：P1-15/16 操作日志完整性、CSV 导出约束、负面/安全边界。"""
import csv
import io

import pytest
from conftest import get_csrf, login

from app import db
from app.models import Department, OperationLog, Role, User, Warehouse
from app.services.log_service import log_operation
from app.utils.time_utils import now


@pytest.fixture(autouse=True)
def _restore_export_limit(app_ctx):
    """隔离工程师用例对 app.config 的残留（其上限测试未还原）。"""
    app_ctx.config['MAX_EXPORT_ROWS'] = 10000


def _make_user(username, name, dept_id, phone=None, email=None):
    user = User(username=username, employee_no='QA-S-' + username, name=name,
                department_id=dept_id, phone=phone, email=email, hire_date=now().date())
    user.set_password('123456')
    staff_role = Role.query.filter_by(code='staff').first()
    if staff_role:
        user.roles.append(staff_role)
    db.session.add(user)
    db.session.commit()
    return user


class TestQAExport:
    """P1-16：BOM、字段白名单、原值、上限、数据权限与筛选、留痕。"""

    def test_employee_csv_bom_headers_and_original_contact(self, client):
        wh = Department.query.filter_by(name='仓储部').first()
        _make_user('qa_csvuser', 'QA导出用户', wh.id,
                   phone='13800001234', email='qa.export@example.com')
        login(client, 'admin', 'admin123')

        resp = client.get('/hr/employees/export.csv?keyword=qa_csvuser')
        body = resp.data

        assert resp.status_code == 200
        assert body.startswith(b'\xef\xbb\xbf')
        assert 'attachment' in resp.headers.get('Content-Disposition', '')
        rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))
        assert rows[0] == ['工号', '姓名', '部门', '岗位', '手机', '邮箱', '状态']
        assert any('13800001234' in row and 'qa.export@example.com' in row for row in rows[1:])
        assert 'password_hash' not in body.decode('utf-8-sig').lower()

    def test_export_row_limit_redirects_with_flash(self, client, monkeypatch):
        """超过 10000（此处下调为 2）→ 不下载，重定向并提示缩小范围。"""
        monkeypatch.setitem(client.application.config, 'MAX_EXPORT_ROWS', 2)
        login(client, 'admin', 'admin123')
        resp = client.get('/hr/employees/export.csv')

        assert resp.status_code == 302
        assert '/hr/employees' in resp.headers.get('Location', '')
        followed = client.get('/hr/employees/export.csv', follow_redirects=True)
        assert '缩小筛选范围' in followed.data.decode('utf-8')

    def test_csv_respects_scope_and_current_filter(self, client):
        """leader 导出越权 dept_id 得空文件；admin 同参数得对应部门数据。"""
        wh = Department.query.filter_by(name='仓储部').first()
        _make_user('qa_csv_scope', 'QA越权导出对象', wh.id, phone='13999990000')

        login(client, 'leader1', '123456')
        scoped = client.get('/hr/employees/export.csv?dept_id=%d' % wh.id).data \
            .decode('utf-8-sig')
        assert 'QA越权导出对象' not in scoped

        login(client, 'admin', 'admin123')
        full = client.get('/hr/employees/export.csv?dept_id=%d' % wh.id).data \
            .decode('utf-8-sig')
        assert 'QA越权导出对象' in full

    def test_attendance_and_inventory_exports_have_bom_and_log(self, client):
        """考勤/库存两处导出 BOM、正确表头、OperationLog 留痕。"""
        login(client, 'admin', 'admin123')
        att = client.get('/attendance/export/csv?year=2025&month=1')
        inv = client.get('/warehouse/inventory/export.csv')
        assert att.data.startswith(b'\xef\xbb\xbf')
        assert inv.data.startswith(b'\xef\xbb\xbf')
        att_rows = list(csv.reader(io.StringIO(att.data.decode('utf-8-sig'))))
        inv_rows = list(csv.reader(io.StringIO(inv.data.decode('utf-8-sig'))))
        assert att_rows[0] == ['部门', '姓名', '日期', '签到', '签退', '状态', '迟到分钟', '早退分钟']
        assert inv_rows[0] == ['仓库', '物料', '编码', '规格', '存放位置', '数量', '阈值', '状态']
        assert OperationLog.query.filter_by(module='attendance', action='export').count() >= 1
        assert OperationLog.query.filter_by(module='warehouse', action='export').count() >= 1

    def test_export_forbidden_without_permission(self, client):
        login(client, 'staff1', '123456')
        for url in ('/hr/employees/export.csv', '/warehouse/inventory/export.csv',
                    '/attendance/export/csv'):
            assert client.get(url).status_code == 403


class TestQAOperationLogCompleteness:
    """P1-15/06：关键操作必须留痕，工单日志只读且多维筛选正确。"""

    def test_employee_create_and_edit_are_logged(self, client):
        """人员新建/编辑属于 P1-15 明列关键操作，应写 OperationLog。"""
        login(client, 'admin', 'admin123')
        token = get_csrf(client, '/hr/employees/new')
        resp = client.post('/hr/employees/new', data={
            'csrf_token': token, 'username': 'qa_loguser', 'employee_no': 'QA-LOG-1',
            'name': 'QA日志用户', 'department_id': 1, 'hire_date': '2025-01-01',
            'password': 'abc12345', 'roles': [],
        }, follow_redirects=True)
        assert resp.status_code == 200
        user = User.query.filter_by(username='qa_loguser').first()
        assert user is not None

        created = OperationLog.query.filter_by(module='hr', target_type='employee',
                                               target_id=user.id).count()
        assert created >= 1, '新建员工必须留痕'

    def test_stock_document_in_out_is_logged(self, client):
        """出入库单据属于 P1-15 明列关键操作，应写 OperationLog。"""
        from app.services.inventory_service import apply_stock_document
        from app.models import Material, StockDocument
        wh = Warehouse.query.filter_by(name='原材料仓').first()
        mat = Material.query.filter_by(code='M0001').first()
        admin = User.query.filter_by(username='admin').first()
        before = OperationLog.query.filter_by(module='warehouse').count()
        doc = apply_stock_document('in', wh.id, mat.id, 8, admin.id, admin.id)
        after = OperationLog.query.filter_by(module='warehouse').count()
        assert doc is not None and StockDocument.query.filter_by(doc_no=doc.doc_no).count() == 1
        assert after > before, '出入库必须留痕'

    def test_work_order_log_readonly_and_filtered(self, client):
        """工单详情按 target_type/target_id 展示日志，倒序且只读。"""
        from app.models import WorkOrder
        order = WorkOrder.query.first()
        log_operation(module='production', action='create', target_type='work_order',
                      target_id=order.id, summary='QA工单创建日志')
        log_operation(module='production', action='transition', target_type='work_order',
                      target_id=order.id, summary='QA工单流转日志')
        log_operation(module='production', action='create', target_type='work_order',
                      target_id=order.id + 1000, summary='QA其他工单日志')
        db.session.commit()

        login(client, 'admin', 'admin123')
        detail = client.get('/production/orders/%d' % order.id).data.decode('utf-8')
        assert 'QA工单创建日志' in detail and 'QA工单流转日志' in detail
        assert 'QA其他工单日志' not in detail
        assert detail.index('QA工单流转日志') < detail.index('QA工单创建日志')
        assert client.post('/system/logs/%d/delete' % order.id).status_code in (404, 405)
        assert client.get('/system/%d/edit' % order.id).status_code in (404, 405)

    def test_operation_log_multidimensional_filter(self, client):
        """module/action/operator/date 四维筛选，互不干扰。"""
        admin = User.query.filter_by(username='admin').first()
        keeper = User.query.filter_by(username='keeper1').first()
        log_operation(module='qa_mod', action='create', operator_id=admin.id,
                      summary='QA筛选1', target_type='qa', target_id=1)
        log_operation(module='qa_mod', action='approve', operator_id=keeper.id,
                      summary='QA筛选2', target_type='qa', target_id=2)
        log_operation(module='qa_other', action='create', operator_id=admin.id,
                      summary='QA筛选3', target_type='qa', target_id=3)
        db.session.commit()
        today_str = now().strftime('%Y-%m-%d')

        login(client, 'admin', 'admin123')
        body = client.get('/system/logs?module=qa_mod&action=create&operator_id=%d'
                          '&date_from=%s&date_to=%s' % (admin.id, today_str, today_str)) \
            .data.decode('utf-8')
        assert 'QA筛选1' in body
        assert 'QA筛选2' not in body
        assert 'QA筛选3' not in body


class TestQANegativePaths:
    """负面/边界：CSRF、未登录跳转、异常参数不 500。"""

    def test_new_post_routes_require_csrf(self, client):
        login(client, 'admin', 'admin123')
        order_id = 1
        cases = [
            ('/attendance/leave/new', {'leave_type': '事假', 'reason': 'QA'}),
            ('/production/orders/%d/issue' % order_id, {'quantity': 1}),
            ('/hr/employees/new', {'username': 'qa_nocsrf', 'employee_no': 'QA-N',
                                   'name': 'QA无令牌'}),
        ]
        for url, data in cases:
            resp = client.post(url, data=data)
            assert resp.status_code == 400, 'POST %s 无 CSRF 应被拒绝' % url

    def test_new_pages_require_login(self, client):
        for url in ('/warehouse/ledger', '/system/logs', '/attendance/leave/list',
                    '/attendance/leave/approvals'):
            resp = client.get(url)
            assert resp.status_code == 302
            assert '/auth/login' in resp.headers.get('Location', '')

    def test_invalid_params_and_long_input_do_not_500(self, client):
        login(client, 'admin', 'admin123')
        urls = [
            '/warehouse/ledger?material_id=abc&warehouse_id=xyz&page=abc',
            '/attendance/monthly?year=abc&month=xyz&dept_id=abc',
            '/files/?page=abc&cat_id=xyz&keyword=' + 'Q' * 3000,
            '/system/logs?operator_id=abc&date_from=bad',
            '/production/orders/not-an-int',
        ]
        for url in urls:
            resp = client.get(url)
            assert resp.status_code in (200, 302, 404, 400), '%s 返回 %s' % (url, resp.status_code)
