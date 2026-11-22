# -*- coding: utf-8 -*-
"""生产看板回归：状态统计条形图 + 工单备注展示。"""
from conftest import login

from app import db
from app.models import WorkOrder

STATUSES = ('pending', 'in_progress', 'completed', 'accepted')


def _make_order(status, remark):
    n = WorkOrder.query.count() + 1
    o = WorkOrder(order_no='WO20251122%03d' % n, product_name='看板测试产品',
                  quantity=1, created_by=1, status=status, remark=remark)
    db.session.add(o)
    db.session.commit()
    return o


def test_board_chart_counts_match_visible_orders(client):
    login(client, 'admin', 'admin123')
    _make_order('pending', '待开始备注')
    _make_order('in_progress', '进行中备注：关注物料齐套')

    expected = {s: WorkOrder.query.filter_by(status=s).count() for s in STATUSES}
    html = client.get('/production/board').get_data(as_text=True)

    for status, count in expected.items():
        assert 'data-status="%s" data-count="%d"' % (status, count) in html
    assert '共 %d 单' % sum(expected.values()) in html
    # 顶部是带横轴刻度的条形统计图，而不是四张独立进度卡
    assert '横轴为工单数量，最大值 %d 单' % max(expected.values()) in html
    assert 'linear-gradient(to right, #e9ecef 1px, transparent 1px)' in html
    # 备注直接显示在对应卡片上，短文本无需截断
    assert '备注：进行中备注：关注物料齐套' in html


def test_board_long_remark_truncated_with_full_title(client):
    login(client, 'admin', 'admin123')
    long_remark = '长备注内容需要完整保留' * 6
    _make_order('completed', long_remark)

    html = client.get('/production/board').get_data(as_text=True)
    assert long_remark in html, 'title 属性应保留完整备注'
    assert '…' in html, '卡片上应显示截断省略号'
