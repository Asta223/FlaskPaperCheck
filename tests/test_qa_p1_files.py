# -*- coding: utf-8 -*-
"""QA 独立验证：P1-10/11/12 文件部门可见（含子部门）、检索、预览鉴权。"""
import os
from datetime import timedelta

from conftest import login

from app import db
from app.models import Department, FactoryFile, FileCategory, Role, User
from app.utils.time_utils import now


def _make_user(username, name, dept_id, role_code):
    user = User(username=username, employee_no='QA-F-' + username, name=name,
                department_id=dept_id, hire_date=now().date())
    user.set_password('123456')
    role = Role.query.filter_by(code=role_code).first()
    if role:
        user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return user


def _make_dept(name, parent_id=None):
    dept = Department(name=name, parent_id=parent_id, sort_order=8)
    db.session.add(dept)
    db.session.commit()
    return dept


def _make_file(name, visibility='all', depts=None, roles=None, category_id=None,
               ext='.txt', created_at=None):
    """直接建模文件并在上传目录落一个真实文件（避免逐条走上传表单）。"""
    from flask import current_app
    filename = 'qa_' + name + ext
    rec = FactoryFile(
        name=name, original_filename=filename, stored_filename=filename,
        file_ext=ext, size_bytes=7, category_id=category_id,
        visibility_type=visibility, uploaded_by=User.query.filter_by(username='admin').first().id,
        created_at=created_at or now())
    if depts:
        rec.visible_departments = list(depts)
    if roles:
        rec.visible_roles = list(roles)
    db.session.add(rec)
    db.session.commit()
    folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, filename), 'wb') as fh:
        fh.write(b'QA-DATA')
    return rec


class TestQAFileDepartmentVisibility:
    """P1-10：部门可见含子部门，列表与下载鉴权必须一致。"""

    def test_child_dept_user_sees_parent_authorized_file_in_list(self, client):
        """授权父部门的文件：子部门用户应可在列表看到并下载。"""
        prod = Department.query.filter_by(name='生产部').first()
        child = _make_dept('QA文件子部门', prod.id)
        child_user = _make_user('qa_fchild', 'QA文件子部门用户', child.id, 'staff')
        rec = _make_file('QA父部门授权文件', visibility='departments', depts=[prod])

        login(client, 'qa_fchild', '123456')
        body = client.get('/files/').data.decode('utf-8')
        download = client.get('/files/%d/download' % rec.id)

        assert download.status_code == 200
        assert 'QA父部门授权文件' in body, '子部门用户应在列表看到父部门授权文件'

    def test_parent_dept_user_does_not_see_child_authorized_file(self, client):
        """授权子部门的文件：父部门用户不应在列表看到，直接下载 403。"""
        prod = Department.query.filter_by(name='生产部').first()
        child = _make_dept('QA文件子部门2', prod.id)
        rec = _make_file('QA子部门隐私文件', visibility='departments', depts=[child])

        login(client, 'staff1', '123456')  # staff1 在父部门生产部
        body = client.get('/files/').data.decode('utf-8')
        download = client.get('/files/%d/download' % rec.id)

        assert download.status_code == 403
        assert 'QA子部门隐私文件' not in body, '父部门用户不应看到仅授权子部门的文件'

    def test_unauthorized_dept_direct_url_403_and_list_hidden(self, client):
        """未授权部门：列表不可见，download/preview 直链均 403。"""
        wh = Department.query.filter_by(name='仓储部').first()
        rec = _make_file('QA仓储机密', visibility='departments', depts=[wh], ext='.pdf')

        login(client, 'staff1', '123456')
        assert 'QA仓储机密' not in client.get('/files/').data.decode('utf-8')
        assert client.get('/files/%d/download' % rec.id).status_code == 403
        assert client.get('/files/%d/preview' % rec.id).status_code == 403
        assert client.get('/files/%d/preview_file' % rec.id).status_code == 403

    def test_legacy_all_and_roles_still_work(self, client):
        """P0 兼容：all 全员可见；roles 命中角色可见、未命中不可见。"""
        from app.models.rbac import Role
        staff_role = Role.query.filter_by(code='staff').first()
        keeper_role = Role.query.filter_by(code='keeper').first()
        all_file = _make_file('QA全员文件')
        role_file = _make_file('QA角色文件', visibility='roles', roles=[keeper_role])

        login(client, 'staff1', '123456')
        body = client.get('/files/').data.decode('utf-8')
        assert 'QA全员文件' in body
        assert 'QA角色文件' not in body
        assert client.get('/files/%d/download' % all_file.id).status_code == 200
        assert client.get('/files/%d/download' % role_file.id).status_code == 403
        assert staff_role.code == 'staff'


class TestQAFileSearchPreview:
    """P1-11/12：检索受可见性约束、分类递归、分页、内联预览。"""

    def test_keyword_and_category_filter_scoped_and_paginated(self, client):
        """关键词+分类树组合过滤，越权文件不入结果，分页正确。"""
        root = FileCategory(name='QA根分类')
        db.session.add(root)
        db.session.commit()
        child_cat = FileCategory(name='QA子分类', parent_id=root.id)
        db.session.add(child_cat)
        db.session.commit()
        wh = Department.query.filter_by(name='仓储部').first()
        target = _make_file('QA检索目标', category_id=child_cat.id,
                            created_at=now() + timedelta(seconds=1))
        _make_file('QA检索噪声', category_id=child_cat.id)
        _make_file('QA越权检索', category_id=child_cat.id, visibility='departments', depts=[wh])
        _make_file('QA其他分类', category_id=None)

        login(client, 'staff1', '123456')
        body = client.get('/files/?keyword=QA检索&cat_id=%d' % root.id).data.decode('utf-8')

        assert 'QA检索目标' in body
        assert 'QA越权检索' not in body
        assert 'QA其他分类' not in body

        many = [_make_file('QA分页%02d' % i, created_at=now() + timedelta(seconds=i + 10))
                for i in range(25)]
        page1 = client.get('/files/?keyword=QA分页&page=1').data.decode('utf-8')
        page2 = client.get('/files/?keyword=QA分页&page=2').data.decode('utf-8')
        assert 'QA分页24' in page1 and 'QA分页00' not in page1
        assert 'QA分页00' in page2 and 'QA分页24' not in page2
        assert len(many) == 25

    def test_preview_inline_for_image_and_pdf_text_gets_parsed_page(self, client):
        """图片/PDF 内联预览；txt 展示解析后的预览页（均可从列表点入）。"""
        png = _make_file('QA图片', ext='.png')
        pdf = _make_file('QA文档', ext='.pdf')
        txt = _make_file('QA文本', ext='.txt')

        login(client, 'staff1', '123456')
        for rec, ext in ((png, '.png'), (pdf, '.pdf')):
            preview_page = client.get('/files/%d/preview' % rec.id)
            stream = client.get('/files/%d/preview_file' % rec.id)
            assert preview_page.status_code == 200
            assert stream.status_code == 200
            assert 'inline' in stream.headers.get('Content-Disposition', '')
            assert ext in (rec.file_ext,)

        listing = client.get('/files/').data.decode('utf-8')
        txt_preview_link = '/files/%d/preview' % txt.id
        assert txt_preview_link in listing
        assert client.get('/files/%d/preview' % txt.id).status_code == 200

    def test_migration_expands_visibility_type_to_16(self, app_ctx):
        """静态核对：迁移用 batch_alter_table 将 visibility_type 扩到 String(16)。"""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'migrations', 'versions', 'a1b2c3d4e5f6_p1_increment.py')
        with open(path, encoding='utf-8') as fh:
            source = fh.read()
        assert "batch_alter_table('factory_files'" in source
        assert "alter_column('visibility_type'" in source
        assert 'String(length=16)' in source
        assert FactoryFile.__table__.c.visibility_type.type.length >= 16
