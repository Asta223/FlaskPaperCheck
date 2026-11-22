# -*- coding: utf-8 -*-
"""领料数量单位显示 Bug 修复 QA 专项验证。

验证目标（不接受橡皮图章式确认）：
1. 工单详情领用表格数量列渲染"物料真实单位"，故意使用非默认单位「箱」，
   证明不是写死「个」；表头须为「数量(单位)」；走真实领料路由产生出库单。
2. 领料弹窗数量 label 带 id 且 JS 用 api_stock 返回的 unit 联动；
   api_stock 成功分支返回 unit + 原有字段（向后兼容），失败分支返回 unit:''/ok=False。
3. 空值兜底：unit 为空字符串、以及物料被软删导致 doc.material 为 None 时，
   数量单元格只显示数字，不出现 None/undefined/多余尾随空格。
4. 出入库单列表数量列同样带单位、表头同步变更。

所有数据基于 conftest 的函数级内存 SQLite 夹具，跑完不污染正式库。
"""
import re

from conftest import get_csrf, login

from app import db
from app.models import Inventory, Material, StockDocument, User, Warehouse, WorkOrder

UNIT = '箱'          # 非默认单位（Material.unit 默认为「个」）——证明取的是物料真实 unit
QTY = 10


# ---------------- 测试数据构造 ----------------

def _material(code='MUNIT01', name='单位测试物料', unit=UNIT):
    m = Material(code=code, name=name, spec='QA-SPEC', unit=unit)
    db.session.add(m)
    db.session.commit()
    return m


def _warehouse(name='单位测试仓'):
    w = Warehouse(name=name, location='QA-01')
    db.session.add(w)
    db.session.commit()
    return w


def _inventory(w, m, qty=100):
    row = Inventory(warehouse_id=w.id, material_id=m.id, quantity=qty)
    db.session.add(row)
    db.session.commit()
    return row


def _order(no='WOU0001'):
    admin = User.query.filter_by(username='admin').first()
    o = WorkOrder(order_no=no, product_name='单位测试产品', quantity=1,
                  created_by=admin.id)
    db.session.add(o)
    db.session.commit()
    return o


def _doc(w, m, qty=QTY, order=None):
    """直接建一张出库单，用于模板渲染类断言（不经过领料路由）。"""
    admin = User.query.filter_by(username='admin').first()
    d = StockDocument(doc_no='OUTQA%04d' % (StockDocument.query.count() + 1),
                      doc_type='out', warehouse_id=w.id, material_id=m.id,
                      quantity=qty, handler_id=admin.id, created_by=admin.id,
                      related_order_id=order.id if order else None)
    db.session.add(d)
    db.session.commit()
    return d


# ---------------- HTML 提取辅助 ----------------

def _issue_table(html):
    """截取工单详情「物料领用」卡片，避免误命中页面其它表格。"""
    assert '物料领用（关联出库单）' in html, '工单详情缺少物料领用区块'
    seg = html.split('物料领用（关联出库单）', 1)[1]
    seg = seg.split('操作日志页签', 1)[0]
    return seg


def _data_rows(seg):
    """返回片段中含 <td> 的 <tr> 原始内容。"""
    rows = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', seg, re.S):
        if re.search(r'<td[^>]*>', row):
            rows.append(row)
    return rows


def _cells(row):
    return [re.sub(r'\s+', ' ', c).strip()
            for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]


def _qty_cell(seg):
    """领用表格数据行第 4 列（数量）内容。"""
    for row in _data_rows(seg):
        cells = _cells(row)
        if len(cells) == 6:
            return cells[3]
    raise AssertionError('未找到 6 列的领用表格数据行: %s' % seg[:600])


# ---------------- 1. 领用表格：非默认单位真实渲染 ----------------

def test_order_detail_issue_table_shows_actual_material_unit(client):
    """经真实领料路由产生出库单后，数量列须显示「10 箱」而非写死「个」。"""
    # Arrange
    m = _material()
    w = _warehouse()
    _inventory(w, m, 100)
    o = _order('WOU0001')
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % o.id)

    # Act
    resp = client.post('/production/orders/%d/issue' % o.id, data={
        'csrf_token': token, 'warehouse_id': w.id, 'material_id': m.id,
        'quantity': QTY, 'remark': 'QA单位验证领料',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '领料成功'.encode() in resp.data, '领料路由未成功'
    db.session.expire_all()

    # Assert
    html = client.get('/production/orders/%d' % o.id).get_data(as_text=True)
    seg = _issue_table(html)
    assert '数量(单位)' in seg, '领用表格表头未改为「数量(单位)」'
    cell = _qty_cell(seg)
    assert cell == '%d %s' % (QTY, UNIT), '数量列期望「%d %s」，实际「%s」' % (QTY, UNIT, cell)
    assert '10 个' not in seg, '仍残留写死的默认单位「个」'


# ---------------- 2. 弹窗 label id + api_stock 单位字段 ----------------

def test_issue_modal_label_and_stock_api_unit(client):
    """弹窗 label 需有 id 且 JS 联动；api_stock 成功/失败分支均返回 unit。"""
    # Arrange
    m = _material()
    w = _warehouse()
    _inventory(w, m, 66)
    o = _order('WOU0002')
    login(client, 'producer1', '123456')

    # Assert — 静态结构：label id 与 JS 联动逻辑存在
    html = client.get('/production/orders/%d' % o.id).get_data(as_text=True)
    assert 'id="issueQuantityLabel"' in html, '数量 label 缺少 id="issueQuantityLabel"'
    assert "getElementById('issueQuantityLabel')" in html, 'JS 未获取数量 label'
    assert "'数量（' + (unitName || baseUnit || '基本单位') + '）'" in html, \
        'JS 未用 api_stock 的 unit 联动 label'
    assert 'baseUnit = d.unit' in html, 'JS 未用 unit 联动余量提示/库存不足警告'

    # Assert — api_stock 成功分支：新增 unit，且原有字段全部保留（向后兼容）
    r = client.get('/production/api/stock?warehouse_id=%d&material_id=%d' % (w.id, m.id))
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert data['unit'] == UNIT, 'api_stock 成功分支 unit 期望「%s」，实际「%s」' % (UNIT, data.get('unit'))
    assert data['available'] == 66
    assert data['warehouse'] == w.name
    assert data['material'] == m.name

    # Assert — 失败分支（未选仓库/物料）：ok=False 且 unit=''
    r2 = client.get('/production/api/stock')
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert d2['ok'] is False
    assert d2['unit'] == '', '失败分支 unit 应为空串，实际「%s」' % d2.get('unit')
    assert d2['available'] == 0
    assert 'message' in d2

    # Assert — 失败分支（非法 material_id）同样带 unit:''
    r3 = client.get('/production/api/stock?warehouse_id=%d&material_id=999999' % w.id)
    assert r3.get_json()['ok'] is False
    assert r3.get_json()['unit'] == ''


# ---------------- 3. 空值兜底 ----------------

def test_order_detail_issue_table_empty_unit_fallback(client):
    """物料 unit 为空字符串时，数量列只显示数字，不留孤立空格/None。"""
    # Arrange
    m = _material(code='MUNIT02', name='空单位物料', unit='')
    w = _warehouse('空单位仓')
    o = _order('WOU0003')
    _doc(w, m, QTY, o)
    login(client, 'producer1', '123456')

    # Act
    html = client.get('/production/orders/%d' % o.id).get_data(as_text=True)
    seg = _issue_table(html)

    # Assert
    cell = _qty_cell(seg)
    assert cell == str(QTY), '空单位时数量列应恰为「10」，实际「%s」' % cell
    assert 'None' not in seg and 'undefined' not in seg, '空单位兜底出现 None/undefined'
    assert re.search(r'<td>10\s+</td>', seg) is None, '数量后残留多余空格'


def test_order_detail_issue_table_deleted_material_fallback(client):
    """物料软删后 doc.material 为 None（全局过滤），数量仍正常显示且不露 None。"""
    # Arrange
    m = _material(code='MUNIT03', name='将软删物料', unit=UNIT)
    w = _warehouse('软删物料仓')
    o = _order('WOU0004')
    d = _doc(w, m, QTY, o)
    doc_id = d.id  # commit 后对象会过期，先取出主键
    order_id = o.id
    m.soft_delete()
    db.session.commit()
    # 多对一关系会优先命中 identity map 而不发 SELECT；需清空身份缓存，
    # 让 with_loader_criteria 在真实查询中过滤掉软删物料，才能构造出 material=None。
    db.session.expunge_all()

    # 前置确认：软删过滤确实让关联对象为 None（否则本用例失去意义）
    assert db.session.get(StockDocument, doc_id).material is None, '软删物料未被关联过滤'

    login(client, 'producer1', '123456')
    html = client.get('/production/orders/%d' % order_id).get_data(as_text=True)
    seg = _issue_table(html)

    # Assert
    cell = _qty_cell(seg)
    assert cell == str(QTY), '物料为 None 时数量列应恰为「10」，实际「%s」' % cell
    assert 'None' not in seg and 'undefined' not in seg, '物料为 None 时页面出现 None/undefined'
    assert '10 箱' not in seg, '物料已软删不应再带出单位'


# ---------------- 4. 出入库单列表 ----------------

def test_warehouse_doc_list_shows_unit_and_header(client):
    """出入库单列表数量列须带真实单位，表头改为「数量(单位)」。"""
    # Arrange
    m = _material(code='MUNIT04', name='列表单位物料', unit=UNIT)
    w = _warehouse('列表测试仓')
    _doc(w, m, QTY)
    login(client, 'keeper1', '123456')

    # Act
    html = client.get('/warehouse/docs').get_data(as_text=True)

    # Assert
    assert '数量(单位)' in html, '出入库单列表表头未改为「数量(单位)」'
    hits = [row for row in _data_rows(html) if '列表单位物料' in row]
    assert hits, '单据列表未找到测试物料所在行'
    cells = _cells(hits[0])
    assert cells[4] == '%d %s' % (QTY, UNIT), '列表数量列期望「%d %s」，实际「%s」' % (
        QTY, UNIT, cells[4])
