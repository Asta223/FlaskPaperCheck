"""软删除改造迁移：15 张用户可新增数据表增加 is_deleted 标记。

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-18

变更清单：
- 15 张表新增 is_deleted（Boolean, default 0, indexed）；
- 删除 7 个"业务唯一"数据库约束/索引：users.username / users.employee_no /
  roles.code / processes.code / processes.name / materials.code / warehouses.name；
  唯一性改由业务层只校验未删除记录，使软删后允许重建同编码/名称的数据；
- 删除 attendance_records.uq_attendance_user_date：软删当天打卡后允许重新签到；
- 保留 work_orders.order_no、stock_documents.doc_no、permissions.code、
  inventories/stock_warning_states/conversation_reads 等唯一约束（系统生成或状态数据）。
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

SOFT_DELETE_TABLES = (
    'users', 'departments', 'roles', 'processes', 'work_orders', 'work_order_steps',
    'material_categories', 'materials', 'warehouses', 'stock_documents',
    'file_categories', 'factory_files', 'attendance_records', 'leave_requests',
    'chat_messages',
)

# (表名, 索引名, 列名)
DROP_UNIQUE_INDEXES = (
    ('users', 'username', 'username'),
    ('users', 'employee_no', 'employee_no'),
    ('roles', 'code', 'code'),
    ('processes', 'code', 'code'),
    ('processes', 'name', 'name'),
    ('materials', 'code', 'code'),
    ('warehouses', 'name', 'name'),
)


def _index_names(table):
    return {idx['name'] for idx in sa.inspect(op.get_bind()).get_indexes(table)}


def _constraint_names(table):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_unique_constraints(table)}


def upgrade():
    # 先去掉唯一约束，避免软删记录占用唯一键导致无法重建同编码数据
    for table, index_name, _ in DROP_UNIQUE_INDEXES:
        if index_name in _index_names(table):
            op.drop_index(index_name, table_name=table)

    # MySQL 5.5：复合唯一索引可能同时充当 user_id 外键的引用索引，
    # 必须先补一个普通索引，否则 DROP INDEX 报 1553。
    if 'uq_attendance_user_date' in _constraint_names('attendance_records'):
        if 'ix_attendance_records_user_id' not in _index_names('attendance_records'):
            op.create_index('ix_attendance_records_user_id', 'attendance_records', ['user_id'])
        op.drop_constraint('uq_attendance_user_date', 'attendance_records', type_='unique')

    for table in SOFT_DELETE_TABLES:
        columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
        if 'is_deleted' not in columns:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.add_column(sa.Column(
                    'is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                    comment='软删除标记：页面默认不显示，可在回收站恢复'))
        idx_name = 'ix_%s_is_deleted' % table
        if idx_name not in _index_names(table):
            op.create_index(idx_name, table, ['is_deleted'])


def downgrade():
    for table in SOFT_DELETE_TABLES:
        idx_name = 'ix_%s_is_deleted' % table
        if idx_name in _index_names(table):
            op.drop_index(idx_name, table_name=table)
        columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
        if 'is_deleted' in columns:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_column('is_deleted')

    if 'uq_attendance_user_date' not in _constraint_names('attendance_records'):
        op.create_unique_constraint('uq_attendance_user_date', 'attendance_records',
                                    ['user_id', 'work_date'])
    if 'ix_attendance_records_user_id' in _index_names('attendance_records'):
        op.drop_index('ix_attendance_records_user_id', table_name='attendance_records')
    for table, index_name, column in DROP_UNIQUE_INDEXES:
        if index_name not in _index_names(table):
            op.create_index(index_name, table, [column], unique=True)
