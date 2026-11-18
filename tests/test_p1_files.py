# -*- coding: utf-8 -*-
"""P1 文件测试：部门可见（含子部门）、检索受可见约束、图片/PDF 内联预览、越权 403。"""
import io

from conftest import get_csrf, login

from app import db
from app.models import Department, FactoryFile, User


def _dept(name):
    return Department.query.filter_by(name=name).first()


def _upload(client, filename, visibility, depts=None, roles=None, ext='.txt'):
    token = get_csrf(client, '/files/upload')
    data = {
        'csrf_token': token, 'category_id': 0,
        'file': (io.BytesIO(('内容-' + filename).encode('utf-8')), filename + ext),
        'visibility_type': visibility,
    }
    if depts:
        data['department_ids'] = [str(d.id) for d in depts]
    if roles:
        data['role_ids'] = [str(r.id) for r in roles]
    resp = client.post('/files/upload', data=data, follow_redirects=True)
    assert resp.status_code == 200
    return FactoryFile.query.filter_by(original_filename=filename + ext).first()


# ---------------- P1-10 部门可见 ----------------

def test_department_visibility_allows_and_denies(client):
    """指定生产部可见：staff1（生产部）可下载；keeper1（仓储部）403。"""
    login(client, 'arch1', '123456')
    prod_dept = _dept('生产部')
    f = _upload(client, 'prod_only', 'departments', depts=[prod_dept])
    assert f is not None and f.visibility_type == 'departments'
    assert len(f.visible_departments) == 1

    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    resp = client.get('/files/%d/download' % f.id)
    assert resp.status_code == 200

    client.get('/auth/logout')
    login(client, 'keeper1', '123456')
    resp = client.get('/files/%d/download' % f.id)
    assert resp.status_code == 403


def test_department_visibility_includes_children(client):
    """可见范围含子部门：父部门文件对子部门员工可见。"""
    prod_dept = _dept('生产部')
    child = Department(name='装配车间', parent_id=prod_dept.id, sort_order=1)
    db.session.add(child)
    db.session.commit()
    child_leader = User.query.filter_by(username='staff1').first()
    child_leader.department_id = child.id
    db.session.commit()

    login(client, 'arch1', '123456')
    f = _upload(client, 'parent_dept_file', 'departments', depts=[prod_dept])
    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    resp = client.get('/files/%d/download' % f.id)
    assert resp.status_code == 200

    db.session.expire_all()


def test_departments_requires_selection(client):
    """departments 但未选部门 → 拒绝，不落库。"""
    login(client, 'arch1', '123456')
    f = _upload(client, 'no_dept', 'departments', depts=[])
    assert f is None


def test_departments_not_in_list(client):
    """越权文件不出现在列表。"""
    login(client, 'arch1', '123456')
    f = _upload(client, 'secret_prod', 'departments', depts=[_dept('生产部')])
    client.get('/auth/logout')
    login(client, 'keeper1', '123456')
    resp = client.get('/files/')
    assert 'secret_prod'.encode() not in resp.data


# ---------------- P1-11 检索 ----------------

def test_keyword_search_only_visible(client):
    """关键词检索：仅返回可见且名称命中的文件。"""
    login(client, 'admin', 'admin123')
    _upload(client, '年度报告', 'all')
    login(client, 'arch1', '123456')
    _upload(client, '机密图纸', 'departments', depts=[_dept('综合部')])
    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    resp = client.get('/files/?keyword=年度')
    assert resp.status_code == 200
    assert '年度报告'.encode() in resp.data
    resp2 = client.get('/files/?keyword=机密')
    assert '机密图纸'.encode() not in resp2.data


# ---------------- P1-12 预览 ----------------

def test_preview_image_inline(client):
    """图片预览页 200 且内联文件流 Content-Disposition 为 inline。"""
    import io as _io
    login(client, 'admin', 'admin123')
    # 构造一张最小 PNG 字节
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
    token = get_csrf(client, '/files/upload')
    resp = client.post('/files/upload', data={
        'csrf_token': token, 'category_id': 0,
        'file': (_io.BytesIO(png), 'pic.png'), 'visibility_type': 'all',
    }, follow_redirects=True)
    assert resp.status_code == 200
    f = FactoryFile.query.filter_by(original_filename='pic.png').first()
    assert f is not None
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    resp2 = client.get('/files/%d/preview_file' % f.id)
    assert resp2.status_code == 200
    assert 'inline' in resp2.headers.get('Content-Disposition', '')


def test_preview_text_format_inline(client):
    """txt 等文本格式支持在线预览，不再跳转下载。"""
    login(client, 'admin', 'admin123')
    f = _upload(client, 'doc_file', 'all', ext='.txt')
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    assert '内容-doc_file'.encode() in resp.data
    assert f.file_ext == '.txt'
    # 原始字节流端点仅服务图片/PDF，文本走解析后的预览页
    assert client.get('/files/%d/preview_file' % f.id).status_code == 302


def test_preview_forbidden_403(client):
    """越权文件预览 → 403。"""
    login(client, 'arch1', '123456')
    f = _upload(client, 'private_pdf', 'departments', depts=[_dept('仓储部')], ext='.pdf')
    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 403


# ---------------- QA Bug3 回归：列表与 can_view 口径一致 ----------------

def test_child_dept_user_sees_parent_authorized_file_in_list(client):
    """QA-Bug3A：文件授权父部门，子部门用户列表可见且可下载（含子部门）。"""
    prod = _dept('生产部')
    child = Department(name='装配三车间', parent_id=prod.id, sort_order=2)
    db.session.add(child)
    staff = User.query.filter_by(username='staff1').first()
    staff.department_id = child.id
    db.session.commit()
    login(client, 'arch1', '123456')
    f = _upload(client, 'parent_auth', 'departments', depts=[prod])
    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    resp = client.get('/files/')
    assert 'parent_auth'.encode() in resp.data, '子部门用户应在列表看到父部门授权文件'
    assert client.get('/files/%d/download' % f.id).status_code == 200


def test_parent_dept_user_does_not_see_child_authorized_file(client):
    """QA-Bug3B：文件授权子部门，父部门用户列表不可见且下载 403（不向上扩散）。"""
    prod = _dept('生产部')
    child = Department(name='质检班组', parent_id=prod.id, sort_order=3)
    db.session.add(child)
    db.session.commit()
    login(client, 'arch1', '123456')
    f = _upload(client, 'child_auth', 'departments', depts=[child])
    client.get('/auth/logout')
    login(client, 'staff1', '123456')  # staff1 属父部门生产部
    resp = client.get('/files/')
    assert 'child_auth'.encode() not in resp.data, '父部门用户不应看到子部门授权文件'
    assert client.get('/files/%d/download' % f.id).status_code == 403
