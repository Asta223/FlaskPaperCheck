# -*- coding: utf-8 -*-
"""单位档案与换算：CRUD、唯一性、量纲守卫、引用守卫、权限。"""
from conftest import get_csrf, login

from app import db
from app.models import Material, Unit, UnitConversion


def _html(client):
    return client.get('/warehouse/units').get_data(as_text=True)


def test_unit_page_and_seed_data(client):
    login(client, 'admin', 'admin123')
    html = _html(client)
    assert 'PCS' in html and 'BOX' in html and '千克' in html
    assert '内六角螺丝' in html
    assert '已维护换算关系' in html


def test_unit_crud_unique_toggle_and_soft_delete(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/warehouse/units')

    client.post('/warehouse/units/new', data={
        'csrf_token': token, 'code': 'CAN', 'name': '罐', 'dimension': 'quantity',
        'remark': '',
    })
    unit = Unit.query.filter_by(code='CAN').first()
    assert unit is not None

    # 编码重复被应用层拒绝
    client.post('/warehouse/units/new', data={
        'csrf_token': token, 'code': 'CAN', 'name': '罐装', 'dimension': 'quantity',
    })
    assert Unit.query.filter_by(code='CAN').count() == 1

    token = get_csrf(client, '/warehouse/units')
    client.post('/warehouse/units/%d/edit' % unit.id, data={
        'csrf_token': token, 'code': 'CAN2', 'name': '听', 'dimension': 'quantity',
        'remark': '编辑后',
    })
    assert db.session.get(Unit, unit.id).code == 'CAN2'

    client.post('/warehouse/units/%d/toggle' % unit.id, data={'csrf_token': token})
    assert db.session.get(Unit, unit.id).is_active is False

    # 无引用单位可软删，回收站可见
    client.post('/warehouse/units/%d/delete' % unit.id, data={'csrf_token': token})
    # 身份映射会返回同一对象，按项目惯例断言 is_deleted 而非 None
    assert db.session.get(Unit, unit.id).is_deleted is True
    rows = Unit.query.execution_options(include_deleted=True).filter_by(id=unit.id).all()
    assert rows[0].is_deleted is True


def test_conversion_create_duplicate_dimension_guard_and_delete(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/warehouse/units')
    screw = Material.query.filter_by(code='M0001').first()
    bearing = Material.query.filter_by(code='M0002').first()
    box = Unit.query.filter_by(code='BOX').first()
    kg = Unit.query.filter_by(code='KG').first()

    # 种子已有 M0001/BOX=100，重复维护被拒
    before = UnitConversion.query.filter_by(material_id=screw.id, unit_id=box.id).count()
    client.post('/warehouse/unit-conversions/new', data={
        'csrf_token': token, 'material_id': screw.id, 'unit_id': box.id, 'factor': 100,
    })
    assert UnitConversion.query.filter_by(material_id=screw.id, unit_id=box.id).count() == before

    # 正常新增：1盒轴承 = 50个
    client.post('/warehouse/unit-conversions/new', data={
        'csrf_token': token, 'material_id': bearing.id, 'unit_id': box.id, 'factor': 50,
        'remark': '',
    })
    conv = UnitConversion.query.filter_by(material_id=bearing.id, unit_id=box.id).first()
    assert conv is not None and conv.factor == 50

    # 量纲不同拒绝
    client.post('/warehouse/unit-conversions/new', data={
        'csrf_token': token, 'material_id': bearing.id, 'unit_id': kg.id, 'factor': 1,
    })
    assert UnitConversion.query.filter_by(material_id=bearing.id, unit_id=kg.id).count() == 0

    # 软删换算关系
    client.post('/warehouse/unit-conversions/%d/delete' % conv.id,
                data={'csrf_token': token})
    assert db.session.get(UnitConversion, conv.id).is_deleted is True


def test_unit_delete_blocked_when_referenced(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/warehouse/units')
    box = Unit.query.filter_by(code='BOX').first()
    client.post('/warehouse/units/%d/delete' % box.id, data={'csrf_token': token})
    assert db.session.get(Unit, box.id) is not None


def test_unit_page_requires_permission(client):
    login(client, 'staff1', '123456')
    resp = client.get('/warehouse/units')
    assert resp.status_code == 403
