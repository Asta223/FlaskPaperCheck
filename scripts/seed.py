# -*- coding: utf-8 -*-
"""种子数据脚本（幂等，存在即跳过）。

内容：
1. 权限点同步（来自 app/utils/permissions.py 的 PERMISSION_REGISTRY）
2. 内置角色 + 权限矩阵（superadmin/leader/keeper/producer/staff/archivist）
3. 超管账号 admin（初始密码 admin123 —— 首次登录后请立即修改！）
4. 示例部门 / 示例员工 / 物料分类与物料 / 仓库 / 示例工单

用法（开发验证用 SQLite）：
    set DB_ENGINE=sqlite          # bash: export DB_ENGINE=sqlite
    python scripts/seed.py

注意：示例账号初始密码均为 123456，上线前务必修改！
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models import (AttendanceRecord, Department, Inventory, Material,  # noqa: E402
                        MaterialCategory, Process, Role, User, Warehouse, WorkOrder,
                        WorkOrderStep)
from app.utils.permissions import ALL_PERMISSION_CODES, PERMISSION_REGISTRY  # noqa: E402
from app.utils.time_utils import now  # noqa: E402

# 内置角色 → 权限矩阵
BUILTIN_ROLES = [
    ('superadmin', '超级管理员', sorted(ALL_PERMISSION_CODES), '内置角色：全权限（代码硬编码放行）'),
    ('leader', '部门主管', ['hr.view', 'attendance.clock', 'attendance.view', 'attendance.view_all',
                            'production.view', 'production.manage', 'production.process.manage',
                            'production.defect_reason.manage',
                            'files.view', 'attendance.leave.apply', 'attendance.leave.approve',
                            'attendance.summary.view', 'system.export'],
     '内置角色：本部门人员/考勤、打卡、工单调度、请假审批、导出'),
    ('keeper', '仓管员', ['attendance.clock', 'warehouse.view', 'warehouse.manage',
                          'material.manage', 'files.view', 'warehouse.ledger.view',
                          'production.issue', 'attendance.leave.apply'],
     '内置角色：打卡/出入库/库存/物料/流水/领料'),
    ('producer', '生产管理员', ['attendance.clock', 'production.view', 'production.manage',
                                'production.process.manage', 'production.defect_reason.manage',
                                'warehouse.view', 'material.manage',
                                'files.view', 'production.issue', 'attendance.leave.apply'],
     '内置角色：打卡/工单创建与流转、领料'),
    ('staff', '普通员工', ['attendance.clock', 'attendance.view', 'files.view',
                           'attendance.leave.apply'],
     '内置角色：打卡/查考勤/看文件/请假'),
    ('archivist', '档案管理员', ['attendance.clock', 'files.view', 'files.manage',
                                 'attendance.leave.apply'],
     '内置角色：打卡/文件上传/分类/可见范围'),
]


def seed_permissions() -> int:
    """从注册表同步权限点，返回新增数。"""
    from app.models.rbac import Permission
    created = 0
    for module, perms in PERMISSION_REGISTRY.items():
        for code, name in perms.items():
            row = Permission.query.filter_by(code=code).first()
            if row is None:
                db.session.add(Permission(code=code, name=name, module=module))
                created += 1
            else:
                row.name = name
                row.module = module
    return created


def seed_roles() -> int:
    """创建内置角色并绑定权限矩阵，返回新增数。"""
    from app.models.rbac import Permission
    created = 0
    for code, name, perm_codes, remark in BUILTIN_ROLES:
        role = Role.query.filter_by(code=code).first()
        if role is None:
            role = Role(code=code, name=name, is_builtin=True, remark=remark)
            db.session.add(role)
            created += 1
        else:
            role.name = name
            role.remark = remark
        role.permissions = Permission.query.filter(Permission.code.in_(perm_codes)).all()
    return created


def seed_admin() -> bool:
    """创建超管账号（admin/admin123，首登改密）。"""
    if User.query.filter_by(username='admin').first():
        return False
    admin = User(
        username='admin',
        employee_no='EMP0001',
        name='系统管理员',
        position='信息化负责人',
        hire_date=now().date(),
    )
    admin.set_password('admin123')  # 初始密码，首次登录后请立即修改！
    role = Role.query.filter_by(code='superadmin').first()
    if role:
        admin.roles.append(role)
    db.session.add(admin)
    return True


def seed_sample_data() -> None:
    """示例部门/员工/物料/仓库/工单（存在即跳过）。"""
    # 部门
    dept_names = ['生产部', '仓储部', '综合部']
    depts = {}
    for name in dept_names:
        dept = Department.query.filter_by(name=name).first()
        if dept is None:
            dept = Department(name=name, sort_order=0)
            db.session.add(dept)
        depts[name] = dept
    db.session.flush()  # 取部门 id，避免后续 backref 触发 autoflush 告警

    # 示例员工（密码 123456，上线前务必修改！）
    sample_users = [
        ('leader1', 'EMP0002', '张主管', '生产部', 'leader', '生产主管'),
        ('keeper1', 'EMP0003', '王仓管', '仓储部', 'keeper', '仓库管理员'),
        ('producer1', 'EMP0004', '刘生产', '生产部', 'producer', '生产调度'),
        ('staff1', 'EMP0005', '赵员工', '生产部', 'staff', '操作工'),
        ('arch1', 'EMP0006', '陈档案', '综合部', 'archivist', '档案管理员'),
    ]
    for username, emp_no, name, dept_name, role_code, position in sample_users:
        if User.query.filter_by(username=username).first():
            continue
        user = User(username=username, employee_no=emp_no, name=name,
                    position=position, hire_date=now().date())
        user.set_password('123456')  # 示例账号初始密码，上线前务必修改！
        user.department_id = depts[dept_name].id
        role = Role.query.filter_by(code=role_code).first()
        if role:
            user.roles.append(role)
        db.session.add(user)

    # 部门负责人
    leader = User.query.filter_by(username='leader1').first()
    keeper = User.query.filter_by(username='keeper1').first()
    if leader and not depts['生产部'].leader_id:
        depts['生产部'].leader_id = leader.id
    if keeper and not depts['仓储部'].leader_id:
        depts['仓储部'].leader_id = keeper.id

    # 物料分类与物料
    cat = MaterialCategory.query.filter_by(name='五金件').first()
    if cat is None:
        cat = MaterialCategory(name='五金件')
        db.session.add(cat)
    cat2 = MaterialCategory.query.filter_by(name='包装耗材').first()
    if cat2 is None:
        cat2 = MaterialCategory(name='包装耗材')
        db.session.add(cat2)

    sample_materials = [
        ('M0001', '内六角螺丝', 'M8×30', '盒', '五金件', '原材料仓 A区-03排-2层'),
        ('M0002', '轴承', '6204', '个', '五金件', '原材料仓 B区-01排-1层'),
        ('M0003', '纸箱', '400×300×200', '个', '包装耗材', '成品仓 C区-02排'),
    ]
    for code, name, spec, unit, cat_name, location in sample_materials:
        if Material.query.filter_by(code=code).first():
            continue
        category = MaterialCategory.query.filter_by(name=cat_name).first()
        db.session.add(Material(code=code, name=name, spec=spec, unit=unit,
                                storage_location=location, category=category))

    # 仓库
    warehouse = Warehouse.query.filter_by(name='原材料仓').first()
    if warehouse is None:
        warehouse = Warehouse(name='原材料仓', location='1号厂房东侧')
        db.session.add(warehouse)
    warehouse2 = Warehouse.query.filter_by(name='成品仓').first()
    if warehouse2 is None:
        warehouse2 = Warehouse(name='成品仓', location='2号厂房')
        db.session.add(warehouse2)

    # 工序档案（主数据：工厂标准工序，工单只能引用）
    sample_processes = [
        ('OP01', '下料', 1.0, 1),
        ('OP02', '机加工', 2.0, 2),
        ('OP03', '组装', 1.5, 3),
        ('OP04', '质检', 0.5, 4),
        ('OP05', '包装', 0.5, 5),
    ]
    for code, name, std_hours, sort in sample_processes:
        if Process.query.filter_by(code=code).first() is None:
            db.session.add(Process(code=code, name=name, standard_hours=std_hours,
                                   sort_order=sort))

    # 示例工单（幂等：按单号查）
    if not WorkOrder.query.filter_by(order_no='WO20250101001').first():
        admin = User.query.filter_by(username='admin').first()
        order = WorkOrder(
            order_no='WO20250101001',
            product_name='示例产品A',
            quantity=100,
            leader=leader,
            created_by=admin.id if admin else 1,
            created_at=now(),
            remark='种子数据示例工单',
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(WorkOrderStep(work_order_id=order.id,
                                     process_id=Process.query.filter_by(code='OP01').first().id,
                                     name='下料', seq=1))
        db.session.add(WorkOrderStep(work_order_id=order.id,
                                     process_id=Process.query.filter_by(code='OP03').first().id,
                                     name='组装', seq=2))
        db.session.add(WorkOrderStep(work_order_id=order.id,
                                     process_id=Process.query.filter_by(code='OP04').first().id,
                                     name='质检', seq=3))

    db.session.flush()

    # 示例库存（直接建档，数值由出入库单据维护）
    mat = Material.query.filter_by(code='M0001').first()
    if mat and warehouse:
        exist = Inventory.query.filter_by(warehouse_id=warehouse.id, material_id=mat.id).first()
        if exist is None:
            db.session.add(Inventory(warehouse_id=warehouse.id, material_id=mat.id,
                                     quantity=0, warn_threshold=10))


def main() -> None:
    app = create_app()
    with app.app_context():
        perm_created = seed_permissions()
        role_created = seed_roles()
        admin_created = seed_admin()
        seed_sample_data()
        db.session.commit()

        print('===== 种子数据完成 =====')
        print('权限点新增：%d（现共 %d）' % (perm_created, _count('permissions')))
        print('内置角色新增：%d（现共 %d）' % (role_created, _count('roles')))
        print('超管账号：%s（新增 %s），初始密码 admin123 —— 首次登录后请立即修改！' % (
            'admin', '是' if admin_created else '否（已存在）'))
        print('示例员工初始密码均为 123456，上线前务必修改！')


def _count(table: str) -> int:
    """简单行数统计（避免模型依赖顺序问题）。"""
    return db.session.execute(db.text('SELECT COUNT(*) FROM %s' % table)).scalar()


if __name__ == '__main__':
    main()
