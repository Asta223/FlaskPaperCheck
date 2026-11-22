# -*- coding: utf-8 -*-
"""数据导入蓝图：人员、考勤、库存三个页面的 CSV/Excel 导入入口。

字段模板直接复用导出端的字段常量；权限要求“对应模块管理权限 + system.import”。
"""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.imports import ImportUploadForm
from app.services.csv_specs import (ATTENDANCE_HEADERS, EMPLOYEE_HEADERS, IMPORT_RULES,
                                    INVENTORY_HEADERS)
from app.services.import_service import ImportValidationError, read_table
from app.services.importers import import_attendance, import_employees, import_inventory
from app.services.log_service import log_operation
from app.utils.data_scope import visible_department_ids
from app.utils.permissions import permission_required
from app.utils.time_utils import today

bp = Blueprint('data_import', __name__, url_prefix='/import')


def _render(title, form, headers, rules, action_url, back_url, template_url, errors=None):
    return render_template(
        'import_form.html', title=title, form=form, headers=headers, rules=rules,
        action_url=action_url, back_url=back_url, template_url=template_url,
        errors=errors or [],
    )


def _handle(title, headers, rules_key, action_url, back_url, template_url,
            module, target_type, importer):
    """通用导入处理：解析 → 全量校验 → 写库 → 操作日志（单事务）。"""
    form = ImportUploadForm()
    errors = []
    if form.validate_on_submit():
        try:
            rows = read_table(form.file.data, headers)
            result = importer(rows)
            log_operation(
                module=module, action='import', target_type=target_type,
                summary='导入%s：%s（文件 %s）' % (
                    title, result.summary(), form.file.data.filename),
            )
            db.session.commit()
            flash('导入成功：%s' % result.summary(), 'success')
            return redirect(back_url)
        except ImportValidationError as exc:
            db.session.rollback()
            errors = exc.errors
        except Exception:
            db.session.rollback()
            raise

    return _render(title, form, headers, IMPORT_RULES[rules_key],
                   action_url, back_url, template_url, errors)


@bp.route('/hr/employees', methods=['GET', 'POST'])
@login_required
@permission_required('hr.manage')
@permission_required('system.import')
def employees():
    """员工导入：工号为主键；部门数据权限收窄。"""
    scope = visible_department_ids(current_user)
    return _handle(
        title='导入员工', headers=EMPLOYEE_HEADERS, rules_key='employee',
        action_url=url_for('data_import.employees'),
        back_url=url_for('hr.employee_list'),
        template_url=url_for('hr.employee_export_csv', dept_id=0, keyword=''),
        module='hr', target_type='employee',
        importer=lambda rows: import_employees(rows, allowed_department_ids=scope),
    )


@bp.route('/attendance/monthly', methods=['GET', 'POST'])
@login_required
@permission_required('attendance.view_all')
@permission_required('system.import')
def attendance():
    """考勤导入：部门+姓名+日期为主键；部门数据权限收窄。"""
    scope = visible_department_ids(current_user)
    return _handle(
        title='导入考勤', headers=ATTENDANCE_HEADERS, rules_key='attendance',
        action_url=url_for('data_import.attendance'),
        back_url=url_for('attendance.monthly'),
        template_url=url_for('attendance.export_csv', year=today().year,
                             month=today().month, dept_id=0),
        module='attendance', target_type='attendance',
        importer=lambda rows: import_attendance(rows, allowed_department_ids=scope),
    )


@bp.route('/warehouse/inventory', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse.manage')
@permission_required('system.import')
def inventory():
    """库存导入：仓库+物料编码为主键。"""
    return _handle(
        title='导入库存', headers=INVENTORY_HEADERS, rules_key='inventory',
        action_url=url_for('data_import.inventory'),
        back_url=url_for('warehouse.inventory'),
        template_url=url_for('warehouse.export_inventory_csv', warehouse_id=0,
                             keyword='', only_warning=0),
        module='warehouse', target_type='inventory',
        importer=import_inventory,
    )
