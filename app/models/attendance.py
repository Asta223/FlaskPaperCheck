"""考勤模型：每日打卡记录。"""
from app import db
from app.models.mixins import SoftDeleteMixin


class AttendanceRecord(SoftDeleteMixin, db.Model):
    """打卡记录：未删除的 (user_id, work_date) 每日一条，由业务层保证。

    软删后同一天可重新签到（旧记录保留在回收站），因此不放数据库唯一约束。
    """
    __tablename__ = 'attendance_records'

    # day_status 短码（逗号分隔组合位）：normal / late / early / late,early / absent / leave
    DAY_NORMAL = 'normal'
    DAY_LATE = 'late'
    DAY_EARLY = 'early'
    DAY_ABSENT = 'absent'
    DAY_LEAVE = 'leave'
    DAY_STATUS_LABELS = {
        'normal': '正常', 'late': '迟到', 'early': '早退',
        'late,early': '迟到,早退', 'absent': '缺卡', 'leave': '请假',
    }

    id = db.Column(db.Integer, primary_key=True)
    # 唯一性由 clock 路由只校验未删除记录（全局查询自动过滤）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='员工')
    work_date = db.Column(db.Date, nullable=False, comment='打卡日期')
    check_in_at = db.Column(db.DateTime, nullable=True, comment='签到时间')
    check_out_at = db.Column(db.DateTime, nullable=True, comment='签退时间')
    late_minutes = db.Column(db.Integer, nullable=False, default=0,
                             comment='迟到分钟数（P1，落库判定）')
    early_leave_minutes = db.Column(db.Integer, nullable=False, default=0,
                                    comment='早退分钟数（P1，落库判定）')
    day_status = db.Column(db.String(16), nullable=False, default=DAY_NORMAL,
                           comment='日状态短码，逗号分隔组合（P1）')

    user = db.relationship('User', backref='attendance_records')

    @property
    def is_late(self) -> bool:
        return (self.late_minutes or 0) > 0

    @property
    def is_early(self) -> bool:
        return (self.early_leave_minutes or 0) > 0

    @property
    def day_status_labels(self) -> str:
        """把逗号分隔短码映射为中文标签（UI 展示用，统计一律用分钟字段）。"""
        codes = [c for c in (self.day_status or '').split(',') if c]
        return ','.join(self.DAY_STATUS_LABELS.get(c, c) for c in codes) or self.DAY_NORMAL

    def __repr__(self) -> str:
        return '<AttendanceRecord u=%s %s>' % (self.user_id, self.work_date)
