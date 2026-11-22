# -*- coding: utf-8 -*-
"""工单详情页三页签回归：结构、深链激活、POST 后保持当前页签。"""
from conftest import get_csrf, login

from app.models import Process, WorkOrder, WorkOrderStep


def _order():
    return WorkOrder.query.filter_by(order_no='WO20250101001').first()


def test_detail_has_three_tabs_with_default_info(client):
    login(client, 'admin', 'admin123')
    o = _order()
    resp = client.get('/production/orders/%d' % o.id)
    assert resp.status_code == 200
    for tab in (b'id="tab-info"', b'id="tab-steps"', b'id="tab-logs"'):
        assert tab in resp.data
    for pane in (b'id="pane-info"', b'id="pane-steps"', b'id="pane-logs"'):
        assert pane in resp.data
    # 默认激活工单资料；其余两个页签在 DOM 中但不激活
    assert b'class="tab-pane fade show active" id="pane-info"' in resp.data
    assert b'class="tab-pane fade " id="pane-steps"' in resp.data
    assert b'class="tab-pane fade " id="pane-logs"' in resp.data
    # 六个板块全部仍一次性渲染，JS 与既有测试不受影响
    for text in ('工单信息', '质量记录', '添加工序', '工序步骤（时间线）',
                 '物料领用（关联出库单）', '操作日志'):
        assert text.encode('utf-8') in resp.data


def test_detail_tab_query_selects_pane_and_header_actions(client):
    login(client, 'admin', 'admin123')
    o = _order()
    for tab in ('steps', 'logs'):
        resp = client.get('/production/orders/%d?tab=%s' % (o.id, tab))
        assert resp.status_code == 200
        assert ('class="tab-pane fade show active" id="pane-%s"' % tab).encode() in resp.data
        # 页头全局操作在当前页签下发觉提交，返回时才能回到原页签
        assert ('/status?tab=%s' % tab).encode() in resp.data
    # 非法 tab 回退到工单资料
    resp = client.get('/production/orders/%d?tab=bogus' % o.id)
    assert b'class="tab-pane fade show active" id="pane-info"' in resp.data


def test_step_new_keeps_steps_tab_after_submit(client):
    login(client, 'admin', 'admin123')
    o = _order()
    pid = Process.query.filter_by(code='OP01').first().id
    token = get_csrf(client, '/production/orders/%d?tab=steps' % o.id)
    resp = client.post('/production/orders/%d/steps/new?tab=steps' % o.id, data={
        'csrf_token': token, 'process_id': pid, 'seq': 9,
        'operator_id': 0, 'remark': '页签回归工序',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'class="tab-pane fade show active" id="pane-steps"' in resp.data
    assert '页签回归工序'.encode() in resp.data
    assert WorkOrderStep.query.filter_by(work_order_id=o.id, seq=9).first() is not None
