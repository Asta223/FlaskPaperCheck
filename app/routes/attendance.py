"""考勤路由：打卡、个人记录、月度统计。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.attendance import ClockForm
from app.models.attendance import AttendanceRecord
from app.models.org import Department
from app.models.user import User
from app.services import attendance_service
from app.utils.permissions import has_permission, permission_required
from app.utils.time_utils import now, today

bp = Blueprint('attendance', __name__, url_prefix='/attendance')


@bp.route('/clock', methods=['GET', 'POST'])
@login_required
@permission_required('attendance.clock')
def clock():
    """每日签到/签退大按钮 + 当日状态（重复点击幂等）。"""
    form = ClockForm()
    work_date = today()
    record = AttendanceRecord.query.filter_by(user_id=current_user.id,
                                              work_date=work_date).first()
    if form.validate_on_submit():
        action = request.form.get('action', 'in')
        record = AttendanceRecord.query.filter_by(user_id=current_user.id,
                                                  work_date=work_date).first()
        if action == 'in':
            if record is None:
                record = AttendanceRecord(user_id=current_user.id, work_date=work_date,
                                          check_in_at=now())
                db.session.add(record)
                db.session.commit()
                flash('签到成功：%s' % record.check_in_at.strftime('%H:%M:%S'), 'success')
            elif record.check_in_at is None:
                record.check_in_at = now()
                db.session.commit()
                flash('签到成功：%s' % record.check_in_at.strftime('%H:%M:%S'), 'success')
            else:
                flash('今日已签到，无需重复操作', 'info')
        else:  # out
            if record is None or record.check_in_at is None:
                flash('请先签到再签退', 'warning')
            elif record.check_out_at is None:
                record.check_out_at = now()
                db.session.commit()
                flash('签退成功：%s' % record.check_out_at.strftime('%H:%M:%S'), 'success')
            else:
                flash('今日已签退', 'info')
        return redirect(url_for('attendance.clock'))

    # 近 10 条个人记录
    recent = (AttendanceRecord.query.filter_by(user_id=current_user.id)
              .order_by(AttendanceRecord.work_date.desc()).limit(10).all())
    return render_template('attendance/clock.html', form=form, record=record,
                           work_date=work_date, recent=recent)


@bp.route('/records')
@login_required
@permission_required('attendance.view')
def records():
    """个人打卡记录（view_all 可查看指定员工）。"""
    page = request.args.get('page', 1, type=int)
    target_user = current_user
    if has_permission(current_user, 'attendance.view_all'):
        user_id = request.args.get('user_id', type=int)
        if user_id:
            target_user = db.session.get(User, user_id) or current_user
    pagination = (AttendanceRecord.query.filter_by(user_id=target_user.id)
                  .order_by(AttendanceRecord.work_date.desc())
                  .paginate(page=page, per_page=20, error_out=False))
    can_select = has_permission(current_user, 'attendance.view_all')
    users = User.query.filter_by(is_active=True).order_by(User.employee_no).all() \
        if can_select else []
    return render_template('attendance/records.html', pagination=pagination,
                           target_user=target_user, can_select=can_select, users=users)


@bp.route('/monthly')
@login_required
@permission_required('attendance.view')
def monthly():
    """月度统计：个人视图 + 主管视角部门汇总。"""
    year = request.args.get('year', today().year, type=int)
    month = request.args.get('month', today().month, type=int)
    can_view_all = has_permission(current_user, 'attendance.view_all')

    user_id = request.args.get('user_id', type=int)
    dept_id = request.args.get('dept_id', type=int)
    target_user = current_user
    if can_view_all and user_id:
        target_user = db.session.get(User, user_id) or current_user

    stats = attendance_service.monthly_stats(target_user, year, month)

    # 部门汇总（仅 view_all）
    dept_rows = None
    if can_view_all:
        depts = Department.query.filter_by(is_active=True).order_by(Department.sort_order).all()
        if dept_id:
            members = (User.query.filter(User.department_id == dept_id, User.is_active.is_(True))
                       .order_by(User.employee_no).all())
            dept_rows = [
                {'user': m, 'stats': attendance_service.monthly_stats(m, year, month)}
                for m in members
            ]
        return render_template('attendance/monthly.html', stats=stats, year=year, month=month,
                               can_view_all=can_view_all, depts=depts, dept_id=dept_id,
                               dept_rows=dept_rows, target_user=target_user,
                               users=_selectable_users())
    return render_template('attendance/monthly.html', stats=stats, year=year, month=month,
                           can_view_all=False, depts=[], dept_id=None, dept_rows=None,
                           target_user=target_user, users=[])


def _selectable_users():
    """view_all 用户可选择的员工下拉。"""
    return User.query.filter_by(is_active=True).order_by(User.employee_no).all()
