# -*- coding: utf-8 -*-
"""三个页面的业务导入器：人员、考勤、库存。

统一约定：
- 入参为 import_service.read_table() 的 [(行号, {字段: 值})]；
- 先全量校验，任一行失败即抛 ImportValidationError，不写库；
- 校验通过后由调用方在同一事务中提交；
- 字段完全来自导出文件，不要求额外列。
"""
import re

from app.services.import_service import (ImportResult, clean, parse_choice, parse_date,
                                        parse_datetime, parse_int, require, validate_email,
                                        validate_rows)

_USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')

# 考勤状态：导出用的是中文标签，同时兼容导入短码。
_ATTENDANCE_STATUS = {
    '正常': 'normal', '迟到': 'late', '早退': 'early',
    '迟到,早退': 'late,early', '缺卡': 'absent', '请假': 'leave',
}
_ATTENDANCE_STATUS.update({code: code for code in _ATTENDANCE_STATUS.values()})


def import_employees(rows, allowed_department_ids=None) -> ImportResult:
    """按「工号」导入员工：存在则更新，不存在则新建账号。"""
    from flask import current_app

    from app import db
    from app.models.org import Department
    from app.models.user import User

    departments = Department.query.filter_by(is_active=True).all()
    dept_by_name = {dept.name: dept for dept in departments}
    if allowed_department_ids is not None:
        allowed_names = {dept.name for dept in departments if dept.id in allowed_department_ids}
    else:
        allowed_names = None

    users = User.query.all()
    by_no = {user.employee_no: user for user in users}
    by_username = {user.username: user for user in users}
    seen_numbers = set()

    def validate(values):
        employee_no = require(values['工号'], '工号')
        if len(employee_no) > 32:
            raise ValueError('工号长度不能超过 32')
        if employee_no in seen_numbers:
            raise ValueError('文件内工号「%s」重复' % employee_no)
        seen_numbers.add(employee_no)

        name = require(values['姓名'], '姓名')
        if len(name) > 64:
            raise ValueError('姓名长度不能超过 64')

        dept_name = clean(values['部门'])
        department_id = None
        if dept_name:
            dept = dept_by_name.get(dept_name)
            if dept is None:
                raise ValueError('部门「%s」不存在或已停用' % dept_name)
            if allowed_names is not None and dept_name not in allowed_names:
                raise ValueError('无权导入部门「%s」的员工' % dept_name)
            department_id = dept.id
        elif allowed_names is not None:
            raise ValueError('部门不能为空（不在管辖范围内）')

        position = clean(values['岗位'])
        if len(position) > 64:
            raise ValueError('岗位长度不能超过 64')
        phone = clean(values['手机'])
        if len(phone) > 20:
            raise ValueError('手机号长度不能超过 20')
        email = validate_email(values['邮箱'])
        if len(email) > 120:
            raise ValueError('邮箱长度不能超过 120')

        is_active = parse_choice(values['状态'], '状态', {'在职': True, '离职': False})

        if employee_no not in by_no:
            if not _USERNAME_RE.match(employee_no):
                raise ValueError('工号含非法字符，无法作为新建账号的登录名')
            occupant = by_username.get(employee_no)
            if occupant is not None and occupant.employee_no != employee_no:
                raise ValueError('登录名「%s」已被其他员工占用' % employee_no)

        return {
            'employee_no': employee_no,
            'name': name,
            'department_id': department_id,
            'position': position,
            'phone': phone,
            'email': email,
            'is_active': is_active,
        }

    prepared = validate_rows(rows, validate)
    default_password = current_app.config.get('IMPORT_DEFAULT_PASSWORD', '123456')
    result = ImportResult()

    for item in prepared:
        user = by_no.get(item['employee_no'])
        if user is None:
            user = User(username=item['employee_no'], employee_no=item['employee_no'],
                        password_hash='')
            user.set_password(default_password)
            db.session.add(user)
            result.created += 1
        else:
            result.updated += 1

        user.name = item['name']
        user.department_id = item['department_id']
        user.position = item['position']
        user.phone = item['phone']
        user.email = item['email']
        user.is_active = item['is_active']

    return result


def import_attendance(rows, allowed_department_ids=None) -> ImportResult:
    """按「部门 + 姓名 + 日期」导入考勤记录。"""
    from app import db
    from app.models.attendance import AttendanceRecord
    from app.models.org import Department
    from app.models.user import User

    departments = Department.query.filter_by(is_active=True).all()
    allowed_names = None
    if allowed_department_ids is not None:
        allowed_names = {dept.name for dept in departments if dept.id in allowed_department_ids}

    users = User.query.all()
    user_by_key = {}
    duplicate_keys = set()
    for user in users:
        dept_name = user.department.name if user.department else ''
        key = (dept_name, user.name)
        if key in user_by_key:
            duplicate_keys.add(key)
        else:
            user_by_key[key] = user

    records = AttendanceRecord.query.all()
    record_by_key = {(record.user_id, record.work_date): record for record in records}
    seen_keys = set()

    def validate(values):
        dept_name = require(values['部门'], '部门')
        name = require(values['姓名'], '姓名')
        if allowed_names is not None and dept_name not in allowed_names:
            raise ValueError('无权导入部门「%s」的考勤' % dept_name)

        key = (dept_name, name)
        if key in duplicate_keys:
            raise ValueError('部门「%s」下存在多个同名「%s」，无法唯一匹配' % (dept_name, name))
        user = user_by_key.get(key)
        if user is None:
            raise ValueError('未找到员工「%s / %s」' % (dept_name, name))

        work_date = parse_date(values['日期'], '日期')
        seen_key = (dept_name, name, work_date)
        if seen_key in seen_keys:
            raise ValueError('文件内「%s / %s / %s」重复' % (dept_name, name, work_date))
        seen_keys.add(seen_key)

        check_in = parse_datetime(values['签到'], '签到')
        check_out = parse_datetime(values['签退'], '签退')
        day_status = parse_choice(values['状态'], '状态', _ATTENDANCE_STATUS)
        late_minutes = parse_int(values['迟到分钟'], '迟到分钟', default=0, min_value=0)
        early_minutes = parse_int(values['早退分钟'], '早退分钟', default=0, min_value=0)

        return {
            'user_id': user.id,
            'work_date': work_date,
            'check_in_at': check_in,
            'check_out_at': check_out,
            'day_status': day_status,
            'late_minutes': late_minutes,
            'early_minutes': early_minutes,
        }

    prepared = validate_rows(rows, validate)
    result = ImportResult()

    for item in prepared:
        key = (item['user_id'], item['work_date'])
        record = record_by_key.get(key)
        if record is None:
            record = AttendanceRecord(user_id=item['user_id'], work_date=item['work_date'])
            db.session.add(record)
            record_by_key[key] = record
            result.created += 1
        else:
            result.updated += 1

        record.check_in_at = item['check_in_at']
        record.check_out_at = item['check_out_at']
        record.day_status = item['day_status']
        record.late_minutes = item['late_minutes']
        record.early_leave_minutes = item['early_minutes']

    return result


def import_inventory(rows) -> ImportResult:
    """按「仓库 + 物料编码」导入库存快照。"""
    from app import db
    from app.models.material import Material
    from app.models.warehouse import Inventory, Warehouse

    warehouses = Warehouse.query.filter_by(is_active=True).all()
    warehouse_by_name = {warehouse.name: warehouse for warehouse in warehouses}
    materials = Material.query.filter_by(is_active=True).all()
    material_by_code = {material.code: material for material in materials}
    inventory_by_key = {
        (item.warehouse_id, item.material_id): item for item in Inventory.query.all()
    }
    seen_keys = set()

    def validate(values):
        warehouse_name = require(values['仓库'], '仓库')
        material_name = require(values['物料'], '物料')
        code = require(values['编码'], '编码')

        warehouse = warehouse_by_name.get(warehouse_name)
        if warehouse is None:
            raise ValueError('仓库「%s」不存在或已停用' % warehouse_name)
        material = material_by_code.get(code)
        if material is None:
            raise ValueError('物料编码「%s」不存在或已停用' % code)
        if material.name != material_name:
            raise ValueError('物料名称「%s」与编码「%s」的档案名称「%s」不一致' % (
                material_name, code, material.name))

        spec = clean(values['规格'])
        location = clean(values['存放位置'])
        if len(spec) > 128 or len(location) > 128:
            raise ValueError('规格或存放位置长度不能超过 128')

        quantity = parse_int(values['数量'], '数量', min_value=0)
        threshold = parse_int(values['阈值'], '阈值', min_value=0)
        status = parse_choice(values['状态'], '状态', {'预警': 'warning', '正常': 'normal'})
        expected = 'warning' if quantity <= threshold else 'normal'
        if status != expected:
            raise ValueError('状态与数量/阈值不一致，应为「%s」' % (
                '预警' if expected == 'warning' else '正常'))

        key = (warehouse.id, material.id)
        if key in seen_keys:
            raise ValueError('文件内「%s / %s」重复' % (warehouse_name, code))
        seen_keys.add(key)

        return {
            'warehouse_id': warehouse.id,
            'material_id': material.id,
            'material': material,
            'spec': spec,
            'location': location,
            'quantity': quantity,
            'threshold': threshold,
        }

    prepared = validate_rows(rows, validate)
    result = ImportResult()

    for item in prepared:
        key = (item['warehouse_id'], item['material_id'])
        inventory = inventory_by_key.get(key)
        if inventory is None:
            inventory = Inventory(warehouse_id=item['warehouse_id'],
                                  material_id=item['material_id'])
            db.session.add(inventory)
            inventory_by_key[key] = inventory
            result.created += 1
        else:
            result.updated += 1

        inventory.quantity = item['quantity']
        inventory.warn_threshold = item['threshold']

        material = item['material']
        material.spec = item['spec']
        material.storage_location = item['location']

    return result
