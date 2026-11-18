"""考勤路由：打卡（含迟到判定落库）、个人记录、月度统计、部门汇总、请假申请与审批。

P1 数据权限：新增 base_attendance_query()/base_user_query() 单一出口，注入部门 IN 过滤；
写操作（审批）显式校验目标部门在管辖范围内，否则 403。
"""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.forms.attendance import ClockForm
from app.forms.leave import LeaveApplyForm, LeaveApproveForm
from app.models.attendance import AttendanceRecord
from app.models.leave import LeaveRequest
from app.models.org import Department
from app.models.user import User
from app.services import attendance_service
from app.services.log_service import log_operation
from app.utils.data_scope import apply_dept_scope, visible_department_ids
from app.utils.permissions import has_permission, permission_required
from app.utils.time_utils import now, today

bp = Blueprint('attendance', __name__, url_prefix='/attendance')


# ---------------- 数据权限单一出口（P1-04）----------------

def base_user_query():
    """可选员工 query：注入部门数据权限（P1 唯一出口）。"""
    return apply_dept_scope(User.query.filter_by(is_active=True), User.department_id, current_user)


def base_attendance_query():
    """打卡记录 query：按记录所属人的部门注入数据权限（P1 唯一出口）。"""
    query = AttendanceRecord.query
    scope = visible_department_ids(current_user)
    if scope is None:
        return query
    # 通过 user_id IN (SELECT id FROM users WHERE department_id IN scope) 收窄
    allowed_ids = db.session.query(User.id).filter(User.department_id.in_(scope or [-1]))
    return query.filter(AttendanceRecord.user_id.in_(allowed_ids))


# ---------------- 打卡 ----------------

@bp.route('/clock', methods=['GET', 'POST'])
@login_required
@permission_required('attendance.clock')
def clock():
    """每日签到/签退大按钮 + 当日状态（重复点击幂等）；判定落库。"""
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
                attendance_service.evaluate_record(record)
                db.session.commit()
                flash('签到成功：%s' % record.check_in_at.strftime('%H:%M:%S'), 'success')
            elif record.check_in_at is None:
                record.check_in_at = now()
                attendance_service.evaluate_record(record)
                db.session.commit()
                flash('签到成功：%s' % record.check_in_at.strftime('%H:%M:%S'), 'success')
            else:
                flash('今日已签到，无需重复操作', 'info')
        else:  # out
            if record is None or record.check_in_at is None:
                flash('请先签到再签退', 'warning')
            elif record.check_out_at is None:
                record.check_out_at = now()
                attendance_service.evaluate_record(record)
                db.session.commit()
                flash('签退成功：%s' % record.check_out_at.strftime('%H:%M:%S'), 'success')
            else:
                flash('今日已签退', 'info')
        return redirect(url_for('attendance.clock'))

    recent = (base_attendance_query().filter_by(user_id=current_user.id)
              .order_by(AttendanceRecord.work_date.desc()).limit(10).all())
    return render_template('attendance/clock.html', form=form, record=record,
                           work_date=work_date, recent=recent)


@bp.route('/records')
@login_required
@permission_required('attendance.view')
def records():
    """个人打卡记录（view_all 可查看指定员工，但受数据权限收窄）。"""
    page = request.args.get('page', 1, type=int)
    target_user = current_user
    if has_permission(current_user, 'attendance.view_all'):
        user_id = request.args.get('user_id', type=int)
        if user_id:
            candidate = db.session.get(User, user_id)
            # 数据权限收窄：目标必须落在可见部门内（superadmin 豁免）
            if candidate and _user_in_scope(candidate):
                target_user = candidate
    pagination = (base_attendance_query().filter_by(user_id=target_user.id)
                  .order_by(AttendanceRecord.work_date.desc())
                  .paginate(page=page, per_page=20, error_out=False))
    can_select = has_permission(current_user, 'attendance.view_all')
    users = base_user_query().order_by(User.employee_no).all() if can_select else []
    return render_template('attendance/records.html', pagination=pagination,
                           target_user=target_user, can_select=can_select, users=users)


def _user_in_scope(user) -> bool:
    """用户是否落在当前用户数据权限范围内（superadmin 或不收窄时放行）。"""
    scope = visible_department_ids(current_user)
    if scope is None:
        return True
    return user.department_id in scope


@bp.route('/monthly')
@login_required
@permission_required('attendance.view')
def monthly():
    """月度统计：个人视图 + 主管视角部门汇总（数据权限收窄）。"""
    year = request.args.get('year', today().year, type=int)
    month = request.args.get('month', today().month, type=int)
    can_view_all = has_permission(current_user, 'attendance.view_all')

    user_id = request.args.get('user_id', type=int)
    dept_id = request.args.get('dept_id', type=int)
    target_user = current_user
    if can_view_all and user_id:
        candidate = db.session.get(User, user_id)
        if candidate and _user_in_scope(candidate):
            target_user = candidate

    stats = attendance_service.monthly_stats(target_user, year, month)

    # 部门汇总（view_all 或 attendance.summary.view，均受数据权限收窄）
    dept_rows = None
    can_summary = can_view_all or has_permission(current_user, 'attendance.summary.view')
    depts = []
    if can_summary:
        scope = visible_department_ids(current_user)
        dept_q = Department.query.filter_by(is_active=True)
        if scope is not None:
            dept_q = dept_q.filter(Department.id.in_(scope or [-1]))
        depts = dept_q.order_by(Department.sort_order).all()
        if dept_id:
            # 篡改的 dept_id 不在管辖范围 → 静默收窄为空，不报错、不越权
            allowed_dept_ids = {d.id for d in depts}
            if dept_id in allowed_dept_ids:
                members = (base_user_query().filter(User.department_id == dept_id)
                           .order_by(User.employee_no).all())
            else:
                members = []
            dept_rows = attendance_service.department_summary(members, year, month)
        return render_template('attendance/monthly.html', stats=stats, year=year, month=month,
                               can_view_all=can_view_all, can_summary=can_summary,
                               depts=depts, dept_id=dept_id, dept_rows=dept_rows,
                               target_user=target_user, users=_selectable_users())
    return render_template('attendance/monthly.html', stats=stats, year=year, month=month,
                           can_view_all=False, can_summary=False, depts=[], dept_id=None,
                           dept_rows=None, target_user=target_user, users=[])


def _selectable_users():
    """view_all 用户可选择的员工下拉（数据权限收窄）。"""
    return base_user_query().order_by(User.employee_no).all()


# ---------------- 请假申请与审批（P1-01）----------------

@bp.route('/export/csv')
@login_required
@permission_required('system.export')
def export_csv():
    """导出考勤汇总 CSV（P1-16）：复用数据权限收窄 + 当前年月/部门筛选。"""
    from app.services.export_service import guard_export_or_redirect, export_csv as _export_csv

    year = request.args.get('year', today().year, type=int)
    month = request.args.get('month', today().month, type=int)
    dept_id = request.args.get('dept_id', type=int)

    members = base_user_query().order_by(User.employee_no)
    if dept_id:
        scope = visible_department_ids(current_user)
        allowed = None if scope is None else set(scope or [])
        if allowed is None or dept_id in allowed:
            members = members.filter(User.department_id == dept_id)
        else:
            members = members.filter(db.false())

    rows = []
    for member in members.all():
        stats = attendance_service.monthly_stats(member, year, month)
        for rec in stats['records']:
            rows.append([
                member.department.name if member.department else '',
                member.display_name(),
                rec.work_date.strftime('%Y-%m-%d'),
                rec.check_in_at.strftime('%Y-%m-%d %H:%M') if rec.check_in_at else '',
                rec.check_out_at.strftime('%Y-%m-%d %H:%M') if rec.check_out_at else '',
                rec.day_status_labels,
                rec.late_minutes or 0,
                rec.early_leave_minutes or 0,
            ])
    guard = guard_export_or_redirect(rows, 'attendance.monthly', year=year, month=month)
    if guard is not None:
        return guard

    log_operation(module='attendance', action='export', target_type='attendance',
                  summary='导出考勤 %d-%02d 部门%s，共%d行' % (
                      year, month, dept_id or '全部', len(rows)))
    db.session.commit()
    return _export_csv(['部门', '姓名', '日期', '签到', '签退', '状态', '迟到分钟', '早退分钟'],
                       rows, 'attendance_%d%02d' % (year, month))


@bp.route('/leave/new', methods=['GET', 'POST'])
@login_required
@permission_required('attendance.leave.apply')
def leave_new():
    """提交请假申请：申请人/部门自动带入，状态 pending。"""
    form = LeaveApplyForm()
    if form.validate_on_submit():
        start_at, end_at = form.start_at.data, form.end_at.data
        if end_at <= start_at:
            form.end_at.errors.append('结束时间必须晚于开始时间')
        else:
            days = round((end_at - start_at).total_seconds() / 86400.0, 4)
            leave_rec = LeaveRequest(
                applicant_id=current_user.id,
                department_id=current_user.department_id,
                leave_type=form.leave_type.data,
                start_at=start_at,
                end_at=end_at,
                days=days,
                reason=form.reason.data.strip(),
                status='pending',
                created_at=now(),
            )
            db.session.add(leave_rec)
            db.session.commit()
            flash('请假申请已提交，等待审批', 'success')
            return redirect(url_for('attendance.leave_list'))
    return render_template('attendance/leave_form.html', form=form)


@bp.route('/leave/list')
@login_required
@permission_required('attendance.leave.apply')
def leave_list():
    """我的请假：时间线状态列表。"""
    page = request.args.get('page', 1, type=int)
    pagination = (LeaveRequest.query.filter_by(applicant_id=current_user.id)
                  .order_by(LeaveRequest.created_at.desc())
                  .paginate(page=page, per_page=20, error_out=False))
    return render_template('attendance/leave_list.html', pagination=pagination,
                           view='mine', status_labels=LeaveRequest.STATUS_LABELS)


@bp.route('/leave/approvals')
@login_required
@permission_required('attendance.leave.approve')
def leave_approvals():
    """待我审批：仅本部门（含子部门）的 pending 申请（数据权限收窄）。"""
    page = request.args.get('page', 1, type=int)
    scope = visible_department_ids(current_user)
    query = LeaveRequest.query.filter_by(status='pending')
    if scope is not None:
        query = query.filter(LeaveRequest.department_id.in_(scope or [-1]))
    pagination = query.order_by(LeaveRequest.created_at.asc()) \
        .paginate(page=page, per_page=20, error_out=False)
    return render_template('attendance/leave_list.html', pagination=pagination,
                           view='approvals', status_labels=LeaveRequest.STATUS_LABELS,
                           approve_form=LeaveApproveForm())


@bp.route('/leave/<int:leave_id>/approve', methods=['POST'])
@login_required
@permission_required('attendance.leave.approve')
def leave_approve(leave_id):
    """审批请假：批准/驳回（单级终态）。目标不在管辖部门或非法决策 → 403/拒绝。"""
    leave_rec = db.get_or_404(LeaveRequest, leave_id)
    scope = visible_department_ids(current_user)
    if scope is not None and leave_rec.department_id not in scope:
        abort(403)
    if leave_rec.status != 'pending':
        flash('该申请已处理，不能重复审批', 'warning')
        return redirect(url_for('attendance.leave_approvals'))

    form = LeaveApproveForm()
    decision = request.form.get('decision', '')
    if decision not in ('approve', 'reject'):
        abort(400)
    if not form.validate_on_submit():
        flash('审批意见格式不正确', 'danger')
        return redirect(url_for('attendance.leave_approvals'))

    leave_rec.status = 'approved' if decision == 'approve' else 'rejected'
    leave_rec.approver_id = current_user.id
    leave_rec.approved_at = now()
    leave_rec.approve_comment = form.approve_comment.data or ''
    log_operation(module='attendance', action='approve', target_type='leave_request',
                  target_id=leave_rec.id,
                  summary='%s请假申请#%s（%s）' % (
                      '批准' if decision == 'approve' else '驳回',
                      leave_rec.id, leave_rec.applicant.display_name()))
    db.session.commit()
    flash('已%s' % ('批准' if decision == 'approve' else '驳回'), 'success')
    return redirect(url_for('attendance.leave_approvals'))

