"""P1 增量迁移：7 张新表 + 4 个字段 + visibility_type 扩宽 + 索引。

Revision ID: a1b2c3d4e5f6
Revises: d220c1496af3
Create Date: 2026-10-24

变更清单（对齐架构 §6）：
- create_table: leave_requests, stock_ledgers, operation_logs, notifications,
  stock_warning_states, conversation_reads, file_department_visibility
- add_column: attendance_records.late_minutes/early_leave_minutes/day_status,
  work_orders.related_department_id
- alter_column: factory_files.visibility_type String(10) -> String(16)（batch_alter 兼容 SQLite）
- 旧数据：conversation_reads 按 (receiver, sender) 用 is_read=True 最大 id 初始化位点
- 其余旧值（all/roles、related_order_id=NULL、历史考勤）原样保留，不回溯
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'd220c1496af3'
branch_labels = None
depends_on = None


def upgrade():
    # ---------- 新表 ----------
    op.create_table(
        'operation_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('operator_id', sa.Integer(), nullable=True, comment='操作人，可空'),
        sa.Column('module', sa.String(length=32), nullable=False, comment='模块'),
        sa.Column('action', sa.String(length=32), nullable=False, comment='动作类型'),
        sa.Column('target_type', sa.String(length=32), nullable=True, comment='多态目标类型'),
        sa.Column('target_id', sa.Integer(), nullable=True, comment='多态目标ID'),
        sa.Column('summary', sa.String(length=500), nullable=False, comment='摘要'),
        sa.Column('ip', sa.String(length=64), nullable=True, comment='操作IP'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='操作时间'),
        sa.ForeignKeyConstraint(['operator_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('operation_logs', schema=None) as batch_op:
        batch_op.create_index('ix_oplog_module_created', ['module', 'created_at'], unique=False)
        batch_op.create_index('ix_oplog_operator_created', ['operator_id', 'created_at'], unique=False)
        batch_op.create_index('ix_oplog_target', ['target_type', 'target_id', 'created_at'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('receiver_id', sa.Integer(), nullable=False, comment='接收人'),
        sa.Column('notif_type', sa.String(length=32), nullable=False, comment='消息类型'),
        sa.Column('title', sa.String(length=128), nullable=False, comment='标题'),
        sa.Column('content', sa.String(length=500), nullable=False, comment='内容'),
        sa.Column('material_id', sa.Integer(), nullable=True, comment='关联物料'),
        sa.Column('warehouse_id', sa.Integer(), nullable=True, comment='关联仓库'),
        sa.Column('link_url', sa.String(length=255), nullable=False, comment='跳转链接'),
        sa.Column('is_read', sa.Boolean(), nullable=False, comment='是否已读'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id']),
        sa.ForeignKeyConstraint(['receiver_id'], ['users.id']),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index('ix_notif_receiver_read', ['receiver_id', 'is_read', 'created_at'],
                              unique=False)

    op.create_table(
        'stock_warning_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('warehouse_id', sa.Integer(), nullable=False, comment='仓库'),
        sa.Column('material_id', sa.Integer(), nullable=False, comment='物料'),
        sa.Column('is_low', sa.Boolean(), nullable=False, comment='当前是否低位'),
        sa.Column('last_notified_at', sa.DateTime(), nullable=True, comment='最近推送时间'),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id']),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('warehouse_id', 'material_id', name='uq_stock_warn_wh_mat'),
    )

    op.create_table(
        'leave_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('applicant_id', sa.Integer(), nullable=False, comment='申请人'),
        sa.Column('department_id', sa.Integer(), nullable=True, comment='申请时部门'),
        sa.Column('leave_type', sa.String(length=32), nullable=False, comment='请假类型'),
        sa.Column('start_at', sa.DateTime(), nullable=False, comment='开始时间'),
        sa.Column('end_at', sa.DateTime(), nullable=False, comment='结束时间'),
        sa.Column('days', sa.Float(), nullable=False, comment='天数'),
        sa.Column('reason', sa.String(length=500), nullable=False, comment='事由'),
        sa.Column('status', sa.String(length=16), nullable=False, comment='状态'),
        sa.Column('approver_id', sa.Integer(), nullable=True, comment='审批人'),
        sa.Column('approved_at', sa.DateTime(), nullable=True, comment='审批时间'),
        sa.Column('approve_comment', sa.String(length=500), nullable=False, comment='审批意见'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.ForeignKeyConstraint(['applicant_id'], ['users.id']),
        sa.ForeignKeyConstraint(['approver_id'], ['users.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('leave_requests', schema=None) as batch_op:
        batch_op.create_index('ix_leave_dept_status', ['department_id', 'status'], unique=False)
        batch_op.create_index('ix_leave_applicant_created', ['applicant_id', 'created_at'], unique=False)

    op.create_table(
        'stock_ledgers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('doc_no', sa.String(length=32), nullable=False, comment='单据号'),
        sa.Column('doc_type', sa.String(length=8), nullable=False, comment='in/out'),
        sa.Column('warehouse_id', sa.Integer(), nullable=False, comment='仓库'),
        sa.Column('material_id', sa.Integer(), nullable=False, comment='物料'),
        sa.Column('quantity', sa.Integer(), nullable=False, comment='变动数量'),
        sa.Column('before_balance', sa.Integer(), nullable=False, comment='变动前余额'),
        sa.Column('after_balance', sa.Integer(), nullable=False, comment='变动后余额'),
        sa.Column('related_order_id', sa.Integer(), nullable=True, comment='关联工单'),
        sa.Column('handler_id', sa.Integer(), nullable=True, comment='经手人'),
        sa.Column('remark', sa.String(length=255), nullable=False, comment='摘要'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='变动时间'),
        sa.ForeignKeyConstraint(['handler_id'], ['users.id']),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id']),
        sa.ForeignKeyConstraint(['related_order_id'], ['work_orders.id']),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('stock_ledgers', schema=None) as batch_op:
        batch_op.create_index('ix_ledger_mat_created', ['material_id', 'created_at'], unique=False)
        batch_op.create_index('ix_ledger_wh_type_created', ['warehouse_id', 'doc_type', 'created_at'], unique=False)
        batch_op.create_index('ix_ledger_order', ['related_order_id'], unique=False)

    op.create_table(
        'conversation_reads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False, comment='本端用户'),
        sa.Column('peer_id', sa.Integer(), nullable=False, comment='对方用户'),
        sa.Column('last_read_message_id', sa.Integer(), nullable=False, comment='已读位点'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['peer_id'], ['users.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'peer_id', name='uq_conversation_read_user_peer'),
    )

    op.create_table(
        'file_department_visibility',
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.ForeignKeyConstraint(['file_id'], ['factory_files.id']),
        sa.PrimaryKeyConstraint('file_id', 'department_id'),
    )

    # ---------- 加字段 ----------
    with op.batch_alter_table('attendance_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('late_minutes', sa.Integer(), nullable=False,
                                      server_default='0', comment='迟到分钟数'))
        batch_op.add_column(sa.Column('early_leave_minutes', sa.Integer(), nullable=False,
                                      server_default='0', comment='早退分钟数'))
        batch_op.add_column(sa.Column('day_status', sa.String(length=16), nullable=False,
                                      server_default='normal', comment='日状态短码'))
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('related_department_id', sa.Integer(), nullable=True,
                                      comment='归属部门'))
        batch_op.create_index('ix_work_order_related_dept', ['related_department_id'], unique=False)

    # ---------- 扩宽 visibility_type ----------
    with op.batch_alter_table('factory_files', schema=None) as batch_op:
        batch_op.alter_column('visibility_type', type_=sa.String(length=16),
                              existing_type=sa.String(length=10), nullable=False)

    # ---------- 旧数据兼容：已读位点初始化 ----------
    # 说明：迁移脚本不运行于 Flask app context，无法调用 time_utils.now()；
    # updated_at 用 SQL CURRENT_TIMESTAMP，仅作位点初始化审计时间，不参与业务逻辑。
    op.execute("""
        INSERT INTO conversation_reads (user_id, peer_id, last_read_message_id, updated_at)
        SELECT receiver_id, sender_id, MAX(id), CURRENT_TIMESTAMP
        FROM chat_messages
        WHERE is_read = 1
        GROUP BY receiver_id, sender_id
    """)


def downgrade():
    op.execute("DELETE FROM conversation_reads")

    with op.batch_alter_table('factory_files', schema=None) as batch_op:
        batch_op.alter_column('visibility_type', type_=sa.String(length=10),
                              existing_type=sa.String(length=16), nullable=False)
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.drop_index('ix_work_order_related_dept')
        batch_op.drop_column('related_department_id')
    with op.batch_alter_table('attendance_records', schema=None) as batch_op:
        batch_op.drop_column('day_status')
        batch_op.drop_column('early_leave_minutes')
        batch_op.drop_column('late_minutes')

    op.drop_table('file_department_visibility')
    op.drop_table('conversation_reads')
    with op.batch_alter_table('stock_ledgers', schema=None) as batch_op:
        batch_op.drop_index('ix_ledger_order')
        batch_op.drop_index('ix_ledger_wh_type_created')
        batch_op.drop_index('ix_ledger_mat_created')
    op.drop_table('stock_ledgers')
    with op.batch_alter_table('leave_requests', schema=None) as batch_op:
        batch_op.drop_index('ix_leave_applicant_created')
        batch_op.drop_index('ix_leave_dept_status')
    op.drop_table('leave_requests')
    op.drop_table('stock_warning_states')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_notif_receiver_read')
    op.drop_table('notifications')
    with op.batch_alter_table('operation_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_oplog_target')
        batch_op.drop_index('ix_oplog_operator_created')
        batch_op.drop_index('ix_oplog_module_created')
    op.drop_table('operation_logs')
