# -*- coding: utf-8 -*-
"""认证模块测试：未登录重定向、登录成功/失败、停用账号、改密后旧密码失效、开放重定向。"""
from conftest import get_csrf, login

from app import db
from app.models import User


def test_login_success(client):
    resp = login(client, 'admin', 'admin123')
    assert resp.status_code == 200
    assert '工作台'.encode() in resp.data


def test_login_wrong_password(client):
    resp = login(client, 'admin', 'wrong-password')
    assert '用户名或密码错误'.encode() in resp.data


def test_login_nonexistent_user(client):
    resp = login(client, 'ghost', 'whatever')
    assert '用户名或密码错误'.encode() in resp.data


def test_inactive_account_cannot_login(client):
    """离职停用（is_active=False）后无法登录。"""
    user = User.query.filter_by(username='staff1').first()
    user.is_active = False
    db.session.commit()
    resp = login(client, 'staff1', '123456')
    assert '账号已停用'.encode() in resp.data


def test_logout_then_redirect(client):
    login(client, 'admin', 'admin123')
    client.get('/auth/logout')
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_change_password_invalidates_old(client):
    """改密成功 → 旧密码失效、新密码可登录。"""
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/auth/profile')
    resp = client.post('/auth/profile', data={
        'old_password': 'admin123', 'new_password': 'newpass66',
        'confirm_password': 'newpass66', 'csrf_token': token},
        follow_redirects=True)
    assert '密码修改成功'.encode() in resp.data
    client.get('/auth/logout')
    resp = login(client, 'admin', 'admin123')
    assert '用户名或密码错误'.encode() in resp.data
    resp = login(client, 'admin', 'newpass66')
    assert resp.status_code == 200 and '工作台'.encode() in resp.data


def test_change_password_wrong_old_rejected(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/auth/profile')
    resp = client.post('/auth/profile', data={
        'old_password': 'not-old-pwd', 'new_password': 'newpass66',
        'confirm_password': 'newpass66', 'csrf_token': token},
        follow_redirects=True)
    assert '原密码错误'.encode() in resp.data
    client.get('/auth/logout')
    resp = login(client, 'admin', 'admin123')
    assert resp.status_code == 200  # 旧密码仍然有效


def test_change_password_mismatch_confirm(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/auth/profile')
    resp = client.post('/auth/profile', data={
        'old_password': 'admin123', 'new_password': 'newpass66',
        'confirm_password': 'different66', 'csrf_token': token},
        follow_redirects=True)
    assert '两次输入的密码不一致'.encode() in resp.data
    client.get('/auth/logout')
    assert login(client, 'admin', 'admin123').status_code == 200


def test_open_redirect_via_next_param(client):
    """安全边界：next=//evil.com 这类协议相对地址不应导致站外跳转。"""
    token = get_csrf(client, '/auth/login')
    resp = client.post('/auth/login?next=//evil.com',
                       data={'username': 'admin', 'password': 'admin123',
                             'csrf_token': token})
    loc = resp.headers.get('Location', '')
    assert 'evil.com' not in loc, '疑似开放重定向：Location=%s' % loc
