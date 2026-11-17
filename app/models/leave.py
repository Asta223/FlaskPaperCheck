"""P1 请假模型：LeaveRequest（单级审批状态机 pending→approved/rejected）。"""
from app import db
from app.utils.time_utils import now


class LeaveRequest(db.Model):
    """请假申请：申请人/部门自动带入；部门主管一级审批即终态（A3）。"""
    __tablename__ = 'leave_requests'
    __table_args__ = (
        db.Index('ix_leave_dept_status', 'department_id', 'status'),
        db.Index('ix_leave_applicant_created', 'applicant_id', 'created_at'),
    )

    STATUS_LABELS = {'pending': '待审批', 'approved': '已批准', 'rejected': '已驳回'}
    TYPE_LABELS = {'事假': '事假', '病假': '病假', '年假': '年假', '调休': '调休', '其他': '其他'}

    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False,
                             comment='申请人')
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True,
                              comment='申请时所属部门（冗余便于过滤）')
    leave_type = db.Column(db.String(32), nullable=False, comment='请假类型')
    start_at = db.Column(db.DateTime, nullable=False, comment='开始时间')
    end_at = db.Column(db.DateTime, nullable=False, comment='结束时间')
    days = db.Column(db.Float, nullable=False, default=0, comment='天数/时长')
    reason = db.Column(db.String(500), nullable=False, default='', comment='事由')
    status = db.Column(db.String(16), nullable=False, default='pending',
                       comment='pending/approved/rejected')
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True,
                            comment='审批人，可空')
    approved_at = db.Column(db.DateTime, nullable=True, comment='审批时间，可空')
    approve_comment = db.Column(db.String(500), nullable=False, default='',
                                comment='审批意见')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    applicant = db.relationship('User', foreign_keys=[applicant_id],
                                backref='leave_requests')
    approver = db.relationship('User', foreign_keys=[approver_id])
    department = db.relationship('Department', foreign_keys=[department_id])

    @property
    def status_label(self) -> str:
        return self.STATUS_LABELS.get(self.status, self.status)

    def __repr__(self) -> str:
        return '<LeaveRequest u=%s %s %s>' % (self.applicant_id, self.leave_type, self.status)
