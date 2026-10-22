# -*- coding: utf-8 -*-
"""pytest 公共夹具（QA Edward）：
- 独立临时 SQLite 库（通过 DATABASE_URL 指向系统临时目录），不污染项目 factory_mgmt.db；
- 函数级隔离：每个测试 drop_all → create_all → 重新种子；
- 复用 scripts/seed.py 的种子函数，保证与交付环境一致。
"""
import os
import re

import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 必须在导入 app 之前设置（config.py 在导入期读取环境变量）
os.environ['DB_ENGINE'] = 'sqlite'
os.environ['DATABASE_URL'] = 'sqlite://'  # 内存库
# 内存库需 StaticPool 共享同一连接（Flask 每个请求新建 app context，
# 默认连接池会拿到全新的空库），测试为单线程，无并发风险
from sqlalchemy.pool import StaticPool  # noqa: E402
from config import Config  # noqa: E402
Config.SQLALCHEMY_ENGINE_OPTIONS = {
    'poolclass': StaticPool,
    'connect_args': {'check_same_thread': False},
}

# 仅测试提速：降低 PBKDF2 轮次（check_password_hash 按存储哈希自带的参数校验，
# 不影响被测代码逻辑；生产代码行为不变）
from werkzeug.security import generate_password_hash as _real_gph  # noqa: E402
import app.models.user as _user_mod  # noqa: E402
_user_mod.generate_password_hash = lambda p, **kw: _real_gph(p, method='pbkdf2:sha256:10000')

import pytest  # noqa: E402

from app import create_app, db as _db  # noqa: E402
from scripts.seed import seed_admin, seed_permissions, seed_roles, seed_sample_data  # noqa: E402


@pytest.fixture(scope='session')
def app():
    """会话级应用实例（不开启 TESTING，让异常走正常 500 处理，便于断言状态码）。"""
    application = create_app()
    yield application
    with application.app_context():  # teardown 必须在应用上下文内操作 session
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def app_ctx(app):
    """函数级干净数据库：每测一个用例重建全部表并重新播种。"""
    with app.app_context():
        _db.session.rollback()
        _db.session.remove()
        _db.drop_all()
        _db.create_all()
        seed_permissions()
        seed_roles()
        seed_admin()
        seed_sample_data()
        _db.session.commit()
        yield app
        _db.session.rollback()
        _db.session.remove()


@pytest.fixture()
def client(app_ctx):
    """绑定干净数据库的测试客户端（每个用例全新会话，无登录态残留）。"""
    return app_ctx.test_client()


# ---------------- 通用辅助 ----------------

def get_csrf(client, url):
    """从指定页面抓取 CSRF token（同一会话内 token 通用）。"""
    resp = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', resp.data)
    assert m, '页面无 CSRF token: %s (status=%s)' % (url, resp.status_code)
    return m.group(1).decode()


def login(client, username, password):
    """登录（若已有会话先登出，避免 /auth/login 302 走向工作台拿不到 token）。"""
    client.get('/auth/logout')
    token = get_csrf(client, '/auth/login')
    return client.post('/auth/login',
                       data={'username': username, 'password': password,
                             'csrf_token': token},
                       follow_redirects=True)


def logout(client):
    return client.get('/auth/logout')
