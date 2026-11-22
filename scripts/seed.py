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
from app.models import (AttendanceRecord, BomItem, Customer, Department, Inventory,  # noqa: E402
                        Material, MaterialCategory, Process, Product, ProcessRoute,
                        ProcessRouteItem, Role, Supplier, Unit, UnitConversion, User,
                        Warehouse, WorkOrder, WorkOrderStep)
from app.utils.permissions import ALL_PERMISSION_CODES, PERMISSION_REGISTRY  # noqa: E402
from app.utils.time_utils import now  # noqa: E402

# 内置角色 → 权限矩阵
BUILTIN_ROLES = [
    ('superadmin', '超级管理员', sorted(ALL_PERMISSION_CODES), '内置角色：全权限（代码硬编码放行）'),
    ('leader', '部门主管', ['hr.view', 'attendance.clock', 'attendance.view', 'attendance.view_all',
                            'production.view', 'production.manage', 'production.product.manage',
                            'production.process.manage', 'production.route.manage',
                            'production.defect_reason.manage', 'production.customer.manage',
                            'files.view', 'attendance.leave.apply', 'attendance.leave.approve',
                            'attendance.summary.view', 'system.export'],
     '内置角色：本部门人员/考勤、打卡、工单调度、请假审批、导出'),
    ('keeper', '仓管员', ['attendance.clock', 'warehouse.view', 'warehouse.manage',
                          'material.manage', 'material.unit.manage', 'files.view',
                          'warehouse.ledger.view', 'warehouse.supplier.manage', 'production.issue',
                          'attendance.leave.apply'],
     '内置角色：打卡/出入库/库存/物料/流水/领料'),
    ('producer', '生产管理员', ['attendance.clock', 'production.view', 'production.manage',
                                'production.product.manage', 'production.process.manage',
                                'production.route.manage', 'production.defect_reason.manage',
                                'production.customer.manage',
                                'warehouse.view', 'material.manage', 'material.unit.manage',
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
        ('M0001', '内六角螺丝', 'M8×30', '个', '五金件', '原材料仓 A区-03排-2层'),
        ('M0002', '轴承', '6204', '个', '五金件', '原材料仓 B区-01排-1层'),
        ('M0003', '纸箱', '400×300×200', '个', '包装耗材', '成品仓 C区-02排'),
    ]
    for code, name, spec, unit, cat_name, location in sample_materials:
        if Material.query.filter_by(code=code).first():
            continue
        category = MaterialCategory.query.filter_by(name=cat_name).first()
        db.session.add(Material(code=code, name=name, spec=spec, unit=unit,
                                storage_location=location, category=category))

    # 计量单位与示例换算：1盒螺丝 = 100个（库存基本单位=个）
    sample_units = [
        ('PCS', '个', 'quantity'), ('BOX', '盒', 'quantity'), ('CTN', '箱', 'quantity'),
        ('KG', '千克', 'weight'), ('M', '米', 'length'),
    ]
    for code, name, dimension in sample_units:
        if Unit.query.filter_by(code=code).first() is None:
            db.session.add(Unit(code=code, name=name, dimension=dimension))
    db.session.flush()
    screw = Material.query.filter_by(code='M0001').first()
    box = Unit.query.filter_by(code='BOX').first()
    pcs = Unit.query.filter_by(code='PCS').first()
    # 示例换算只在物料基本单位确为“个”时写入，避免历史库（原来单位=盒）产生错误换算
    if screw is not None and box is not None and pcs is not None and screw.unit == pcs.name:
        if UnitConversion.query.filter_by(material_id=screw.id, unit_id=box.id).first() is None:
            db.session.add(UnitConversion(material_id=screw.id, unit_id=box.id, factor=100,
                                          remark='示例：1盒=100个'))

    # 仓库
    warehouse = Warehouse.query.filter_by(name='原材料仓').first()
    if warehouse is None:
        warehouse = Warehouse(name='原材料仓', location='1号厂房东侧')
        db.session.add(warehouse)
    warehouse2 = Warehouse.query.filter_by(name='成品仓').first()
    if warehouse2 is None:
        warehouse2 = Warehouse(name='成品仓', location='2号厂房')
        db.session.add(warehouse2)

    # 客户与供应商（幂等：按编码查）
    sample_customers = [
        ('CUS001', '圣诞礼品贸易公司', '陈经理', '13800000001', '上海市浦东新区'),
        ('CUS002', '华东百货批发', '李主管', '13800000002', '江苏省苏州市'),
    ]
    for code, name, contact, phone, address in sample_customers:
        if Customer.query.filter_by(code=code).first() is None:
            db.session.add(Customer(code=code, name=name, contact=contact,
                                    phone=phone, address=address))
    sample_suppliers = [
        ('SUP001', '宏远五金厂', '王经理', '13900000001', '浙江省宁波市'),
        ('SUP002', '恒信包装材料', '赵主管', '13900000002', '广东省东莞市'),
    ]
    for code, name, contact, phone, address in sample_suppliers:
        if Supplier.query.filter_by(code=code).first() is None:
            db.session.add(Supplier(code=code, name=name, contact=contact,
                                    phone=phone, address=address))

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

    # 产品档案与 BOM（主数据：工单/工艺路线只引用，避免手输同物多名）
    product = Product.query.filter_by(code='PRD001').first()
    if product is None:
        product = Product(code='PRD001', name='圣诞树', spec='12cm / 标准款', unit='个',
                          remark='示例产品，配套 RT01 工艺路线')
        db.session.add(product)
        db.session.flush()
        for mat_code, qty in (('M0001', 0.2), ('M0002', 2), ('M0003', 1)):
            mat = Material.query.filter_by(code=mat_code).first()
            if mat is not None:
                db.session.add(BomItem(product_id=product.id, material_id=mat.id,
                                       quantity=qty, unit=mat.unit))

    # 示例工艺路线（幂等：按编码查）：圣诞树 = 下料→机加工→组装→质检→包装
    route = ProcessRoute.query.filter_by(code='RT01').first()
    if route is None:
        route = ProcessRoute(code='RT01', name='圣诞树工艺路线',
                             product_id=product.id if product else None,
                             product_name=product.name if product else '圣诞树',
                             remark='示例工序组，新建工单时可直接选用')
        db.session.add(route)
        db.session.flush()
        for seq, code in enumerate(('OP01', 'OP02', 'OP03', 'OP04', 'OP05'), 1):
            process = Process.query.filter_by(code=code).first()
            if process is not None:
                db.session.add(ProcessRouteItem(route_id=route.id,
                                                process_id=process.id, seq=seq))
    elif product is not None and route.product_id is None:
        # 历史路线补关联，保证工单选产品后能推荐到这条路线
        route.product_id = product.id
        route.product_name = product.name

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
