# -*- coding: utf-8 -*-
"""RBAC 权限体系测试：403 拦截 / superadmin 放行 / 菜单按权限过滤 / 装饰器覆盖抽查。"""
import pytest

from conftest import get_csrf, login

from app import db
from app.models import User, WorkOrder

# 每个受限蓝图至少抽查 1 个路由（权限点）
PERMISSION_PROTECTED = [
    ('/hr/employees', 'hr.view'),
    ('/hr/employees/new', 'hr.manage'),
    ('/hr/departments', 'dept.manage'),
    ('/rbac/roles', 'rbac.manage'),
    ('/rbac/permissions', 'rbac.manage'),
    ('/attendance/clock', 'attendance.clock'),
    ('/attendance/records', 'attendance.view'),
    ('/production/orders', 'production.view'),
    ('/production/orders/new', 'production.manage'),
    ('/material/categories', 'material.manage'),
    ('/material/list', 'material.manage'),
    ('/warehouse/inventory', 'warehouse.view'),
    ('/warehouse/docs', 'warehouse.manage'),
    ('/files/', 'files.view'),
]


# ---------------- 未登录 ----------------

def test_unauthenticated_redirect_to_login(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_unauthenticated_all_protected_redirect(client):
    for url, _perm in PERMISSION_PROTECTED:
        resp = client.get(url)
        assert resp.status_code == 302, url
        assert '/auth/login' in resp.headers['Location'], url


# ---------------- 无权限 403 ----------------

def test_staff_no_permission_403(client):
    """staff1（打卡/查考勤/看文件）访问人事、RBAC、生产、物料、仓库等路由应 403。"""
    login(client, 'staff1', '123456')
    for url, _perm in PERMISSION_PROTECTED:
        if url.startswith(('/attendance', '/files')):
            continue  # staff 持有这些权限
        resp = client.get(url)
        assert resp.status_code == 403, '应 403: %s (got %s)' % (url, resp.status_code)


def test_post_route_permission_403(client):
    """写操作路由同样受 @permission_required 保护（POST 带合法 CSRF 但无权限）。"""
    login(client, 'staff1', '123456')
    order = WorkOrder(order_no='WO20250101099', product_name='权限测试品', quantity=1,
                      created_by=1)
    db.session.add(order)
    db.session.commit()
    token = get_csrf(client, '/attendance/clock')  # staff 可访问页面，取同会话 token
    resp = client.post('/production/orders/%d/status' % order.id,
                       data={'csrf_token': token, 'status': 'in_progress'})
    assert resp.status_code == 403
    assert WorkOrder.query.get(order.id).status == 'pending'


# ---------------- superadmin 放行 ----------------

def test_superadmin_bypass_all(client):
    login(client, 'admin', 'admin123')
    for url, _perm in PERMISSION_PROTECTED:
        resp = client.get(url)
        assert resp.status_code == 200, 'superadmin 应放行: %s (got %s)' % (url, resp.status_code)


# ---------------- 最小权限角色可达/不可达 ----------------

def test_staff_allowed_routes_200(client):
    login(client, 'staff1', '123456')
    for url in ['/', '/chat/', '/attendance/clock', '/attendance/records',
                '/attendance/monthly', '/files/']:
        resp = client.get(url)
        assert resp.status_code == 200, '应 200: %s (got %s)' % (url, resp.status_code)


def test_keeper_scope(client):
    login(client, 'keeper1', '123456')
    assert client.get('/warehouse/inventory').status_code == 200
    assert client.get('/warehouse/docs').status_code == 200
    assert client.get('/material/list').status_code == 200
    assert client.get('/production/orders').status_code == 403
    assert client.get('/hr/employees').status_code == 403


def test_leader_scope(client):
    login(client, 'leader1', '123456')
    assert client.get('/production/orders').status_code == 200
    assert client.get('/production/orders/new').status_code == 200
    assert client.get('/attendance/records').status_code == 200
    assert client.get('/warehouse/docs').status_code == 403
    assert client.get('/rbac/roles').status_code == 403


# ---------------- 菜单按权限过滤 ----------------

def _menu_names(user):
    from app.utils.menu import get_current_menu
    tree = get_current_menu(user)
    names = []
    for item in tree:
        names.append(item['name'])
        for sub in item.get('children', []):
            names.append(sub['name'])
    return names


def test_staff_menu_filtered(client):
    login(client, 'staff1', '123456')
    html = client.get('/').data
    # 侧边栏不应出现无权限路由的链接
    for absent_href in ['/hr/employees', '/rbac/roles', '/production/orders',
                        '/material/list', '/warehouse/inventory', '/warehouse/docs',
                        '/hr/departments']:
        assert ('href="%s"' % absent_href).encode() not in html, \
            'staff 页面不应含链接: %s' % absent_href
    # 应出现有权限路由链接与免权限菜单
    for present in ['工作台', '考勤打卡', '打卡记录', '文件资料', '站内聊天']:
        assert present.encode() in html, 'staff 菜单应含: %s' % present
    # 菜单注册表过滤（单元级验证）
    names = _menu_names(User.query.filter_by(username='staff1').first())
    assert '生产工单' not in names and '人员管理' not in names and '角色权限' not in names
    assert '考勤打卡' in names and '文件资料' in names and '工作台' in names


def test_admin_menu_full(client):
    login(client, 'admin', 'admin123')
    html = client.get('/').data
    for present in ['人员管理', '部门管理', '角色权限', '权限点总览', '考勤打卡',
                    '生产工单', '进度看板', '物料分类', '物料档案', '仓库档案',
                    '出入库单据', '库存查询', '文件资料']:
        assert present.encode() in html, 'admin 菜单应含: %s' % present


def test_leader_menu_has_clock_no_rbac(client):
    login(client, 'leader1', '123456')
    html = client.get('/').data
    assert '生产工单'.encode() in html       # 有 production.view
    assert '打卡记录'.encode() in html       # 有 attendance.view
    assert '考勤打卡'.encode() in html       # 全体内置角色均可打卡
    assert '角色权限'.encode() not in html   # 无 rbac.manage
    assert '库存查询'.encode() not in html   # 无 warehouse.view


def test_context_menu_empty_for_anonymous(client):
    """未登录时 context processor 注入空菜单，不抛异常（登录页可渲染）。"""
    resp = client.get('/auth/login')
    assert resp.status_code == 200


# ---------------- 权限查询健壮性 ----------------

def test_user_without_role_has_no_permissions(client):
    """无任何角色的用户：非免权限路由全部 403。"""
    user = User(username='norole', employee_no='EMP7788', name='无角色')
    user.set_password('abc12345')
    db.session.add(user)
    db.session.commit()
    login(client, 'norole', 'abc12345')
    assert client.get('/').status_code == 200            # 免权限
    assert client.get('/chat/').status_code == 200       # 免权限
    assert client.get('/hr/employees').status_code == 403
    assert client.get('/attendance/clock').status_code == 403
