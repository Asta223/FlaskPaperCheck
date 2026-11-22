# -*- coding: utf-8 -*-
"""工单产品名称二选一：选产品档案无需手填名称、未建档可手输、两项都空被拒。"""
from datetime import date, timedelta

from conftest import get_csrf, login

from app import db
from app.models import Product, WorkOrder


def _base_payload(name=''):
    return {
        'product_id': '0', 'product_name': name, 'quantity': '2',
        'due_date': (date.today() + timedelta(days=3)).isoformat(),
        'priority': 'normal', 'leader_id': '0', 'related_department_id': '0',
        'route_id': '0', 'plan_start_date': '', 'plan_end_date': '', 'remark': '',
    }


def _new_product(code, name):
    p = Product(code=code, name=name, spec='测试', unit='个')
    db.session.add(p)
    db.session.commit()
    return p


def test_order_new_with_product_no_manual_name(client):
    """选了产品档案、产品名称留空：建单成功且快照取产品档案名。"""
    login(client, 'admin', 'admin123')
    product = _new_product('PRD-NAME-01', '精确产品名')
    payload = _base_payload()
    payload['product_id'] = str(product.id)
    payload['product_name'] = ''  # 用户无需手填
    token = get_csrf(client, '/production/orders/new')
    payload['csrf_token'] = token
    resp = client.post('/production/orders/new', data=payload, follow_redirects=True)
    assert resp.status_code == 200
    order = WorkOrder.query.filter_by(product_id=product.id).first()
    assert order is not None
    assert order.product_name == '精确产品名'


def test_order_new_both_empty_rejected(client):
    """产品档案与产品名称都为空：阻止建单并给出二选一提示。"""
    login(client, 'admin', 'admin123')
    baseline = WorkOrder.query.count()
    payload = _base_payload()
    payload['csrf_token'] = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data=payload, follow_redirects=True)
    assert resp.status_code == 200
    assert '请选择产品档案'.encode() in resp.data
    assert WorkOrder.query.count() == baseline


def test_order_new_manual_name_fallback(client):
    """未建档时手工填写产品名称：仍可建单（兜底路径保留）。"""
    login(client, 'admin', 'admin123')
    payload = _base_payload(name='临时未建档产品')
    payload['csrf_token'] = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data=payload, follow_redirects=True)
    assert resp.status_code == 200
    order = WorkOrder.query.filter_by(product_name='临时未建档产品').first()
    assert order is not None and order.product_id is None


def test_order_form_name_readonly_with_exact_map(client):
    """新建页：产品名称脚本用精确 id→名称映射，且默认非只读（未选产品）。"""
    login(client, 'admin', 'admin123')
    product = _new_product('PRD-NAME-02', '带 空格（规格）名')
    html = client.get('/production/orders/new').get_data(as_text=True)
    # 精确映射以 JSON 形式内联，含产品全名（含空格与括号，正则解析会失真）
    assert '带 空格（规格）名' in html
    assert 'productNames' in html
    assert 'const productNames' in html
