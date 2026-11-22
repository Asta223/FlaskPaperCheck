# -*- coding: utf-8 -*-
"""确保 .env 中配置的 MySQL 数据库存在；SQLite 配置直接跳过。

由 deploy_env.bat 在 flask db upgrade 之前调用，避免全新部署时
因数据库尚未创建导致迁移失败。连接参数全部来自 config.py 加载后的配置。
"""
import os
import re
import sys

# 直接执行 scripts/ensure_database.py 时，sys.path[0] 是 scripts/ 目录；
# 先把项目根目录加进去，才能导入 config.py。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pymysql
from sqlalchemy.engine import make_url

from config import Config

_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_]+$')


def create_database_sql(db_name):
    """生成建库 SQL；数据库名只允许字母、数字、下划线，防止注入。"""
    if not _IDENTIFIER_RE.match(db_name or ''):
        raise ValueError('非法数据库名：%r（仅允许字母、数字、下划线）' % db_name)
    return ('CREATE DATABASE IF NOT EXISTS `%s` '
            'DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci' % db_name)


def ensure_database():
    """按当前配置确保目标数据库存在。"""
    uri = Config.SQLALCHEMY_DATABASE_URI
    if uri.startswith('sqlite:'):
        print('[OK] 当前使用 SQLite，无需预先创建数据库')
        return

    url = make_url(uri)
    backend = url.get_backend_name()
    if backend != 'mysql':
        print('[OK] 当前数据库类型无需预先建库：%s' % backend)
        return

    db_name = url.database
    if not db_name:
        raise RuntimeError('MySQL 连接串中没有数据库名')

    sql = create_database_sql(db_name)
    conn = pymysql.connect(
        host=url.host or 'localhost',
        port=int(url.port or 3306),
        user=url.username or 'root',
        password=url.password or '',
        charset='utf8mb4',
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
        conn.commit()
    finally:
        conn.close()

    print('[OK] MySQL 数据库已就绪：%s' % db_name)


if __name__ == '__main__':
    try:
        ensure_database()
    except Exception as exc:
        print('[ERROR] 创建数据库失败：%s' % exc)
        sys.exit(1)
