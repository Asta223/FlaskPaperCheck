# -*- coding: utf-8 -*-
"""菜单搜索：模板渲染层回归测试。

过滤逻辑是 base.html 里的纯原生 JS，这里验证搜索框、菜单 data 属性和脚本已注入；
浏览器交互不作自动化断言，避免为 40 行 JS 引入前端测试框架。
"""
from conftest import login
from app.utils.menu import MENU_REGISTRY


def test_menu_search_ui_is_rendered_for_admin(client):
    login(client, 'admin', 'admin123')
    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')

    assert 'id="menuSearch"' in html
    assert 'id="menuSearchClear"' in html
    assert 'id="menuSearchEmpty"' in html
    assert 'id="menuList"' in html
    assert 'menu-search-item' in html

    # 分组名与具体页面名都进入搜索索引
    assert 'data-menu-name="生产管理"' in html
    assert 'data-menu-name="生产工单"' in html
    assert 'data-menu-name="供应商档案"' in html

    # 过滤与状态恢复脚本存在
    assert 'runSearch' in html
    assert 'resetSearch' in html


def test_rbac_menu_items_moved_to_system_group():
    groups = {item['name']: item for item in MENU_REGISTRY}
    org_names = [c['name'] for c in groups['组织人事']['children']]
    system_names = [c['name'] for c in groups['系统管理']['children']]
    assert '角色权限' not in org_names and '权限点总览' not in org_names
    assert '角色权限' in system_names and '权限点总览' in system_names


def test_menu_search_not_rendered_for_anonymous(client):
    resp = client.get('/auth/login')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'id="menuSearch"' not in html
