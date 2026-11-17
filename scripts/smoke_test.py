# -*- coding: utf-8 -*-
"""端到端冒烟测试（T10）：登录 admin → 访问各模块主要页面 → 建工单 → 出入库 → 聊天。"""
import io
import os
import re
import sys

os.environ['DB_ENGINE'] = 'sqlite'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app import create_app, db  # noqa: E402
from app.models import ChatMessage, FactoryFile, Inventory, Material, Warehouse, \
    WorkOrder  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append('%s %s%s' % (name, '✓' if cond else '✗',
                                                 (' | ' + detail) if detail and not cond else ''))


def _get_csrf(client, url):
    """从页面抓 csrf_token。"""
    resp = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', resp.data)
    if m:
        return m.group(1).decode()
    m = re.search(rb'name="csrf_token"\s+type="hidden"\s+value="([^"]+)"', resp.data)
    return m.group(1).decode() if m else ''


app = create_app()
with app.app_context():
    client = app.test_client()

    # 1. 未登录跳转
    resp = client.get('/')
    check('未登录跳转登录页', resp.status_code == 302 and '/auth/login' in resp.headers['Location'])

    # 2. 登录（先取登录页 CSRF）
    csrf_login = _get_csrf(client, '/auth/login')
    resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin123',
                                            'csrf_token': csrf_login},
                       follow_redirects=True)
    check('admin 登录成功', resp.status_code == 200 and '工作台'.encode() in resp.data)

    def login(username, password):
        """登出 + 登录辅助，返回本次登录响应供调用方断言。"""
        client.get('/auth/logout')
        return client.post('/auth/login', data={'username': username, 'password': password,
                                                'csrf_token': _get_csrf(client, '/auth/login')},
                           follow_redirects=True)

    # 3. 各模块主要页面 200
    pages = [
        '/', '/hr/employees', '/hr/departments', '/rbac/roles', '/rbac/permissions',
        '/attendance/clock', '/attendance/records', '/attendance/monthly',
        '/production/orders', '/production/board', '/material/categories', '/material/list',
        '/warehouse/warehouses', '/warehouse/docs', '/warehouse/inventory',
        '/files/', '/chat/',
    ]
    for p in pages:
        resp = client.get(p)
        check('GET %s -> 200' % p, resp.status_code == 200,
              'status=%s' % resp.status_code)

    # 4. 无权限 403（用 staff1 验证 rbac 页面）
    resp = login('staff1', '123456')
    check('staff1 登录成功', resp.status_code == 200)
    resp = client.get('/rbac/roles')
    check('staff1 访问 /rbac/roles -> 403', resp.status_code == 403,
          'status=%s' % resp.status_code)
    resp = client.get('/attendance/clock')
    check('staff1 访问打卡页 -> 200', resp.status_code == 200)
    # staff1 菜单不包含生产
    resp = client.get('/')
    check('staff1 菜单无生产工单入口', '生产工单'.encode() not in resp.data)
    login('admin', 'admin123')

    # 5. 打卡（签到+签退，幂等）
    client.post('/attendance/clock', data={'csrf_token': _get_csrf(client, '/attendance/clock'),
                                           'action': 'in'}, follow_redirects=True)
    resp = client.post('/attendance/clock', data={
        'csrf_token': _get_csrf(client, '/attendance/clock'), 'action': 'out'},
        follow_redirects=True)
    check('签到+签退成功', '签退成功'.encode() in resp.data)

    # 6. 新建工单（CSRF）
    from app.models import User
    admin = User.query.filter_by(username='admin').first()
    leader = User.query.filter_by(username='leader1').first()
    csrf = _get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data={
        'csrf_token': csrf, 'product_name': '冒烟测试产品X', 'quantity': 10,
        'due_date': '2026-01-01', 'leader_id': leader.id, 'remark': 'e2e',
    }, follow_redirects=True)
    order = WorkOrder.query.filter_by(product_name='冒烟测试产品X').first()
    check('工单创建成功', order is not None and '创建成功'.encode() in resp.data)
    check('工单单号自动生成', order is not None and order.order_no.startswith('WO'))

    # 7. 工单状态流转 pending -> in_progress
    resp = client.post('/production/orders/%d/status' % order.id,
                       data={'csrf_token': _get_csrf(client, '/production/orders/%d' % order.id),
                             'status': 'in_progress'}, follow_redirects=True)
    check('工单流转至进行中', WorkOrder.query.get(order.id).status == 'in_progress')

    # 8. 入库 → 库存增加
    wh = Warehouse.query.filter_by(name='原材料仓').first()
    mat = Material.query.filter_by(code='M0001').first()
    csrf = _get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': csrf, 'doc_type': 'in', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 100, 'related_order_id': 0, 'remark': 'e2e入库',
    }, follow_redirects=True)
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    check('入库后库存=100', inv is not None and inv.quantity == 100,
          'qty=%s' % (inv.quantity if inv else None))

    # 9. 超量出库被拒并回滚
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': _get_csrf(client, '/warehouse/docs/new'), 'doc_type': 'out',
        'warehouse_id': wh.id, 'material_id': mat.id, 'quantity': 999, 'remark': '',
    }, follow_redirects=True)
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    check('超量出库被拒（库存不变）', inv.quantity == 100 and '库存不足'.encode() in resp.data)

    # 10. 正常出库 30 → 库存 70
    client.post('/warehouse/docs/new', data={
        'csrf_token': _get_csrf(client, '/warehouse/docs/new'), 'doc_type': 'out',
        'warehouse_id': wh.id, 'material_id': mat.id, 'quantity': 30, 'remark': 'e2e出库',
    }, follow_redirects=True)
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    check('出库后库存=70', inv.quantity == 70, 'qty=%s' % inv.quantity)

    # 11. 阈值标红数据（阈值80 > 70 → 预警）
    inv.warn_threshold = 80
    db.session.commit()
    resp = client.get('/warehouse/inventory')
    check('库存列表含预警标注', '低于阈值'.encode() in resp.data)
    inv.warn_threshold = 0
    db.session.commit()

    # 12. 站内聊天：admin → leader1 发消息
    csrf = _get_csrf(client, '/chat/?peer_id=%d' % leader.id)
    resp = client.post('/chat/send', data={'csrf_token': csrf, 'receiver_id': leader.id,
                                           'content': '冒烟测试消息'}, follow_redirects=True)
    check('消息发送成功', ChatMessage.query.filter_by(sender_id=admin.id,
                                                    receiver_id=leader.id).count() == 1)

    # 13. leader1 未读角标 API
    login('leader1', '123456')
    resp = client.get('/chat/api/unread')
    data = resp.get_json()
    check('未读API返回1条', resp.status_code == 200 and data['code'] == 0
          and data['data']['count'] == 1, str(data))
    resp = client.get('/chat/api/messages?peer_id=%d&after_id=0' % admin.id)
    check('增量消息API正常', resp.get_json()['code'] == 0)
    resp = client.post('/chat/api/read', json={'peer_id': admin.id})
    check('标记已读API正常', resp.get_json()['code'] == 0)
    resp = client.get('/chat/api/unread')
    check('已读后未读=0', resp.get_json()['data']['count'] == 0)

    # 14. 建员工 + 文件上传
    login('admin', 'admin123')
    csrf = _get_csrf(client, '/hr/employees/new')
    resp = client.post('/hr/employees/new', data={
        'csrf_token': csrf, 'username': 'e2euser', 'employee_no': 'EMP9999',
        'name': '冒烟员工', 'department_id': 0, 'hire_date': '2025-01-01',
        'password': 'abc12345', 'roles': [],
    }, follow_redirects=True)
    resp2 = client.get('/hr/employees?keyword=e2euser')
    check('新建员工成功', 'EMP9999'.encode() in resp2.data)

    import io
    csrf = _get_csrf(client, '/files/upload')
    resp = client.post('/files/upload', data={
        'csrf_token': csrf, 'category_id': 0,
        'file': (io.BytesIO('冒烟测试文件内容'.encode('utf-8')), 'smoke_test.txt'),
        'visibility_type': 'all',
    }, follow_redirects=True)
    resp2 = client.get('/files/')
    check('文件上传成功', 'smoke_test.txt'.encode() in resp2.data)
    file_rec = FactoryFile.query.order_by(FactoryFile.id.desc()).first()
    resp = client.get('/files/%d/download' % file_rec.id)
    check('文件下载可达', resp.status_code == 200 and '冒烟测试文件内容'.encode() in resp.data,
          'status=%s' % resp.status_code)

    print('\n===== 冒烟结果 =====')
    print('通过 %d 项' % len(PASS))
    for line in PASS:
        print(' ', line)
    if FAIL:
        print('失败 %d 项' % len(FAIL))
        for line in FAIL:
            print(' ', line)
        sys.exit(1)
    print('ALL PASS')
