# -*- coding: utf-8 -*-
"""P1 系统通用测试：权限点注册、角色矩阵、操作日志只读筛选、CSV 导出（BOM/白名单/上限/留痕）。"""
from conftest import get_csrf, login

from app import db
from app.models import OperationLog, User
from app.services.log_service import log_operation
from app.utils.permissions import ALL_PERMISSION_CODES, PERMISSION_REGISTRY
from app.utils import menu


NEW_PERMS = [
    'attendance.leave.apply', 'attendance.leave.approve', 'attendance.summary.view',
    'production.issue', 'warehouse.ledger.view', 'system.log.view', 'system.export',
    'system.import',
]


# ---------------- P1 权限点 + 菜单 ----------------

def test_new_permissions_registered(client):
    """新增权限点在注册表唯一声明。"""
    for code in NEW_PERMS:
        assert code in ALL_PERMISSION_CODES
    found = [c for perms in PERMISSION_REGISTRY.values() for c in perms]
    assert len(found) == len(set(found)), '权限点不得重复声明'


def test_permission_seeded_into_db(client):
    """新权限点同步进 Permission 表。"""
    from app.models.rbac import Permission
    for code in NEW_PERMS:
        assert Permission.query.filter_by(code=code).first() is not None


def test_menu_items_for_superadmin(client):
    """superadmin 菜单含操作日志/库存流水/请假申请等新入口。"""
    login(client, 'admin', 'admin123')
    resp = client.get('/')
    assert resp.status_code == 200
    for text in ['操作日志', '库存流水', '请假申请', '待我审批']:
        assert text.encode() in resp.data


def test_menu_system_log_hidden_for_staff(client):
    """staff 无 system.log.view → 菜单不含操作日志。"""
    login(client, 'staff1', '123456')
    resp = client.get('/')
    assert '操作日志'.encode() not in resp.data


# ---------------- P1-15 操作日志 ----------------

def test_login_writes_operation_log(client):
    """登录成功写一条 OperationLog(login)。"""
    login(client, 'admin', 'admin123')
    log = OperationLog.query.filter_by(module='auth', action='login').first()
    assert log is not None and log.operator_id is not None


def test_log_operation_same_transaction(app_ctx):
    """log_operation 不自行 commit；rollback 后日志不落库（同事务语义）。"""
    log_operation(module='system', action='create', target_type='test', target_id=1,
                  summary='事务测试')
    db.session.rollback()
    assert OperationLog.query.filter_by(module='system', summary='事务测试').count() == 0
    # 显式提交后落库
    log_operation(module='system', action='create', target_type='test', target_id=2,
                  summary='事务测试2')
    db.session.commit()
    assert OperationLog.query.filter_by(summary='事务测试2').count() == 1


def test_operation_log_page_superadmin(client):
    """superadmin 可访问操作日志页并筛选。"""
    login(client, 'admin', 'admin123')
    resp = client.get('/system/logs?module=auth')
    assert resp.status_code == 200
    resp2 = client.get('/system/logs?action=login')
    assert resp2.status_code == 200


def test_operation_log_module_shown_in_chinese(client, app_ctx):
    """模块筛选和列表展示中文名，筛选值仍保留英文 code。"""
    log = OperationLog(module='qa_mod', action='create')
    assert log.module_label == 'qa_mod'  # 未知模块原样显示
    assert OperationLog(module='auth', action='login').module_label == '登录认证'

    login(client, 'admin', 'admin123')
    body = client.get('/system/logs?module=auth').data.decode('utf-8')
    assert '<option value="auth" selected>登录认证</option>' in body
    assert '<code>auth</code>' not in body


def test_operation_log_page_forbidden_for_staff(client):
    """staff 访问操作日志 → 403。"""
    login(client, 'staff1', '123456')
    resp = client.get('/system/logs')
    assert resp.status_code == 403


def test_operation_log_readonly_no_delete_route(client):
    """操作日志只读：无删除路由（POST 删除返回 404/405）。"""
    login(client, 'admin', 'admin123')
    resp = client.post('/system/logs/1/delete', data={})
    assert resp.status_code in (404, 405)


# ---------------- P1-16 CSV 导出 ----------------

def test_employee_export_bom_and_no_password(client):
    """员工导出：UTF-8 BOM、无 password_hash、含手机邮箱原值、留痕。"""
    login(client, 'admin', 'admin123')
    resp = client.get('/hr/employees/export.csv')
    assert resp.status_code == 200
    data = resp.data
    assert data.startswith(b'\xef\xbb\xbf'), 'CSV 必须以 UTF-8 BOM 开头'
    text = data.decode('utf-8-sig')
    assert '工号' in text and '邮箱' in text
    assert 'password' not in text.lower() and 'scrypt' not in text.lower()
    assert 'attachment' in resp.headers.get('Content-Disposition', '')
    assert OperationLog.query.filter_by(module='hr', action='export').count() >= 1


def test_inventory_export(client):
    """库存导出 200 且留痕。"""
    login(client, 'admin', 'admin123')
    resp = client.get('/warehouse/inventory/export.csv')
    assert resp.status_code == 200
    assert resp.data.startswith(b'\xef\xbb\xbf')
    assert OperationLog.query.filter_by(module='warehouse', action='export').count() >= 1


def test_export_forbidden_without_permission(client):
    """无 system.export 的角色导出 → 403。"""
    login(client, 'staff1', '123456')
    assert client.get('/hr/employees/export.csv').status_code == 403
    assert client.get('/warehouse/inventory/export.csv').status_code == 403
    assert client.get('/attendance/export/csv').status_code == 403


def test_export_row_limit(app_ctx):
    """超过行数上限：export_csv 抛 ExportLimitError（路由据此 flash 提示）。"""
    from app.services import export_service
    original = app_ctx.config['MAX_EXPORT_ROWS']
    app_ctx.config['MAX_EXPORT_ROWS'] = 1
    try:
        export_service.export_csv(['a'], [[1], [2]], 'x')
        raised = False
    except export_service.ExportLimitError:
        raised = True
    finally:
        app_ctx.config['MAX_EXPORT_ROWS'] = original  # 还原，避免污染同会话后续用例
    assert raised


# ---------------- QA Bug5/6 回归：操作日志完整性 ----------------

def test_employee_create_and_edit_are_logged(client):
    """QA-Bug5：员工新建/编辑/停用均写 OperationLog(hr/employee)。"""
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/hr/employees/new')
    resp = client.post('/hr/employees/new', data={
        'csrf_token': token, 'username': 'qa_log_user', 'employee_no': 'EQA001',
        'name': '日志测试', 'department_id': 0, 'hire_date': '2025-01-01',
        'password': 'abc12345',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert OperationLog.query.filter_by(module='hr', action='create',
                                        target_type='employee').count() >= 1
    user = User.query.filter_by(username='qa_log_user').first()
    assert user is not None
    # 编辑
    token = get_csrf(client, '/hr/employees/%d/edit' % user.id)
    client.post('/hr/employees/%d/edit' % user.id, data={
        'csrf_token': token, 'username': 'qa_log_user', 'employee_no': 'EQA001',
        'name': '日志测试改', 'department_id': 0, 'hire_date': '2025-01-01',
    }, follow_redirects=True)
    assert OperationLog.query.filter_by(module='hr', action='update',
                                        target_type='employee').count() >= 1


def test_stock_document_in_out_is_logged(client):
    """QA-Bug6：普通出入库单据（非领料）也写 OperationLog(warehouse/stock_document)。"""
    from app.models import Material, Warehouse
    from app.services.inventory_service import apply_stock_document

    wh = Warehouse.query.filter_by(name='原材料仓').first()
    mat = Material.query.filter_by(code='M0001').first()
    before = OperationLog.query.filter_by(module='warehouse', action='create',
                                          target_type='stock_document').count()
    apply_stock_document('in', wh.id, mat.id, 3, handler_id=1, created_by=1)
    after = OperationLog.query.filter_by(module='warehouse', action='create',
                                         target_type='stock_document').count()
    assert after == before + 1
