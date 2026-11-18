# -*- coding: utf-8 -*-
"""一次性数据迁移：SQLite -> MySQL。

从工厂系统的 SQLite 库读取全部业务表数据，按外键依赖顺序写入已建好表结构的
MySQL 库。仅搬运数据，不改结构（结构由 alembic 迁移负责）。
"""
import os
import sys

# 目标 MySQL（空密码阶段）
os.environ['DATABASE_URL'] = 'mysql+pymysql://root:@127.0.0.1:3306/factory_mgmt?charset=utf8mb4'
os.environ.pop('DB_ENGINE', None)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import sqlite3
from app import create_app, db

SRC = os.path.join(ROOT, 'factory_mgmt.db')

# 按外键依赖顺序：先父后子。alembic_version 由迁移自动生成，不搬运。
ORDER = [
    'roles', 'permissions', 'role_permissions',
    'departments', 'users', 'user_roles',
    'material_categories', 'materials',
    'warehouses', 'inventories', 'stock_documents', 'stock_ledgers',
    'stock_warning_states',
    'work_orders', 'work_order_steps',
    'attendance_records', 'leave_requests',
    'file_categories', 'factory_files', 'file_role_visibility',
    'file_department_visibility',
    'conversation_reads', 'chat_messages', 'notifications',
    'operation_logs',
]

src = sqlite3.connect(SRC)
src.row_factory = sqlite3.Row

app = create_app()
with app.app_context():
    # 先清空 MySQL 业务表（逆序删，避免外键冲突）
    for table in reversed(ORDER):
        db.session.execute(db.text('DELETE FROM `%s`' % table))
    db.session.commit()

    report = []
    errors = []
    for table in ORDER:
        cols = [r[1] for r in src.execute('PRAGMA table_info(%s)' % table).fetchall()]
        rows = src.execute('SELECT * FROM `%s`' % table).fetchall()
        if not rows:
            report.append((table, 0, 0, 'empty'))
            continue
        col_list = ', '.join('`%s`' % c for c in cols)
        placeholders = ', '.join(':%s' % c for c in cols)
        sql = db.text('INSERT INTO `%s` (%s) VALUES (%s)' % (table, col_list, placeholders))
        data = [dict((c, row[c]) for c in cols) for row in rows]
        try:
            db.session.execute(sql, data)
            db.session.commit()
            # 校验目标行数
            dst_count = db.session.execute(
                db.text('SELECT COUNT(*) FROM `%s`' % table)
            ).scalar()
            ok = (dst_count == len(rows))
            report.append((table, len(rows), dst_count, 'OK' if ok else 'MISMATCH'))
            if not ok:
                errors.append('%s: src=%d dst=%d' % (table, len(rows), dst_count))
        except Exception as exc:
            db.session.rollback()
            report.append((table, len(rows), 0, 'ERROR'))
            errors.append('%s: %s' % (table, str(exc)[:200]))

    print('%-32s %8s %8s %s' % ('TABLE', 'SRC', 'DST', 'STATUS'))
    for t, s, d, st in report:
        print('%-32s %8d %8d %s' % (t, s, d, st))
    print()
    if errors:
        print('ERRORS:')
        for e in errors:
            print('  -', e)
        sys.exit(1)
    print('MIGRATION OK: all tables matched')

src.close()
