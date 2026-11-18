# -*- coding: utf-8 -*-
"""向 FactoryManagementSystem 库填充丰富的测试数据（幂等：已存在则跳过）。

覆盖：子部门、员工、考勤（正常/迟到/早退/请假）、请假单、工单（多状态）、
工序、物料、仓库、出入库单据+库存+流水、预警通知、聊天消息、操作日志、文件分类。
"""
import os
import sys
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 目标：MySQL 库 FactoryManagementSystem
os.environ['DATABASE_URL'] = 'mysql+pymysql://root:123@127.0.0.1:3306/FactoryManagementSystem?charset=utf8mb4'
os.environ.pop('DB_ENGINE', None)

from app import create_app, db  # noqa: E402
from app.models import (AttendanceRecord, ChatMessage, ConversationRead, Department,  # noqa: E402
                        FactoryFile, FileCategory, Inventory, LeaveRequest, Material,
                        MaterialCategory, Notification, OperationLog, Role, StockDocument,
                        StockLedger, User, Warehouse, WorkOrder, WorkOrderStep)
from app.utils.time_utils import now  # noqa: E402

TODAY = date.today()


def ts(d, h, m=0):
    return datetime(d.year, d.month, d.day, h, m)


def add_unique(model, key_field, key_value, **kwargs):
    if model.query.filter_by(**{key_field: key_value}).first():
        return None
    obj = model(**{key_field: key_value}, **kwargs)
    db.session.add(obj)
    return obj


def main():
    app = create_app()
    with app.app_context():
        counts = {}

        def c(name, n):
            counts[name] = counts.get(name, 0) + n

        # ---- 部门（含子部门）----
        prod = Department.query.filter_by(name='生产部').first()
        wh = Department.query.filter_by(name='仓储部').first()
        admin_user = User.query.filter_by(username='admin').first()
        leader = User.query.filter_by(username='leader1').first()
        keeper = User.query.filter_by(username='keeper1').first()

        sub_depts = []
        for name, parent in [('一车间', prod), ('二车间', prod), ('质检组', prod), ('原料组', wh)]:
            d = Department.query.filter_by(name=name).first()
            if not d:
                d = Department(name=name, parent_id=parent.id if parent else None, sort_order=1)
                db.session.add(d)
                sub_depts.append(name)
        c('部门', len(sub_depts))

        # ---- 员工（8 名，staff 角色）----
        staff_role = Role.query.filter_by(code='staff').first()
        new_staff = [
            ('staff2', 'EMP0007', '钱师傅', '一车间', '装配工'),
            ('staff3', 'EMP0008', '孙师傅', '一车间', '焊工'),
            ('staff4', 'EMP0009', '周师傅', '二车间', '操作工'),
            ('staff5', 'EMP0010', '吴师傅', '二车间', '操作工'),
            ('staff6', 'EMP0011', '郑质检', '质检组', '质检员'),
            ('staff7', 'EMP0012', '冯库工', '原料组', '库工'),
            ('staff8', 'EMP0013', '陈文员', None, '文员'),
            ('staff9', 'EMP0014', '褚学徒', '一车间', '学徒'),
        ]
        added = 0
        for username, emp_no, name, dept_name, position in new_staff:
            if User.query.filter_by(username=username).first():
                continue
            u = User(username=username, employee_no=emp_no, name=name,
                     position=position, hire_date=TODAY - timedelta(days=200),
                     phone='138%08d' % (10000000 + added))
            u.set_password('123456')
            dept = Department.query.filter_by(name=dept_name).first() if dept_name else None
            if dept:
                u.department_id = dept.id
            if staff_role:
                u.roles.append(staff_role)
            db.session.add(u)
            added += 1
        c('员工', added)

        all_users = User.query.filter(User.username != 'admin').all()
        db.session.flush()

        # ---- 考勤：近 30 天工作日，按用户生成正常/迟到/早退/请假 ----
        att_added = 0
        for uidx, u in enumerate(all_users):
            for back in range(1, 31):
                d = TODAY - timedelta(days=back)
                if d.weekday() >= 5:  # 周末不生成
                    continue
                if AttendanceRecord.query.filter_by(user_id=u.id, work_date=d).first():
                    continue
                pattern = (uidx + back) % 10
                if pattern == 0:      # 请假
                    status = AttendanceRecord.DAY_LEAVE
                    cin = cout = None
                elif pattern == 1:    # 迟到 12 分钟
                    status = AttendanceRecord.DAY_LATE
                    cin, cout = ts(d, 9, 12), ts(d, 18, 5)
                elif pattern == 2:    # 早退 20 分钟
                    status = AttendanceRecord.DAY_EARLY
                    cin, cout = ts(d, 8, 55), ts(d, 17, 40)
                elif pattern == 3:    # 迟到+早退
                    status = 'late,early'
                    cin, cout = ts(d, 9, 25), ts(d, 17, 30)
                else:
                    status = AttendanceRecord.DAY_NORMAL
                    cin, cout = ts(d, 8, 50), ts(d, 18, 10)
                db.session.add(AttendanceRecord(
                    user_id=u.id, work_date=d, check_in_at=cin, check_out_at=cout,
                    late_minutes=12 if 'late' in status else 0,
                    early_leave_minutes=20 if 'early' in status else 0,
                    day_status=status))
                att_added += 1
        c('考勤', att_added)

        # ---- 请假单 ----
        leave_data = [
            (all_users[0], '事假', 'approved', leader, '家中有事'),
            (all_users[1], '病假', 'pending', None, '身体不适就医'),
            (all_users[2], '年假', 'approved', leader, '年假休息'),
            (all_users[3], '调休', 'rejected', leader, '加班调休申请'),
            (all_users[4], '事假', 'pending', None, '个人事务'),
        ]
        la = 0
        for applicant, ltype, status, approver, reason in leave_data:
            start = TODAY - timedelta(days=(la % 5) + 1)
            if LeaveRequest.query.filter_by(applicant_id=applicant.id, start_at=ts(start, 9)).first():
                continue
            db.session.add(LeaveRequest(
                applicant_id=applicant.id,
                department_id=applicant.department_id,
                leave_type=ltype, start_at=ts(start, 9), end_at=ts(start, 18),
                days=1.0, reason=reason, status=status,
                approver_id=approver.id if approver else None,
                approved_at=ts(start, 10) if approver else None,
                approve_comment='同意' if status == 'approved' else ('不同意' if status == 'rejected' else ''),
                created_at=ts(start - timedelta(days=2), 10)))
            la += 1
        c('请假单', la)

        # ---- 物料分类与物料（扩充）----
        cat_elec = MaterialCategory.query.filter_by(name='电子元件').first()
        if not cat_elec:
            cat_elec = MaterialCategory(name='电子元件')
            db.session.add(cat_elec)
        mats = [
            ('M0004', '电阻', '10KΩ', '个', '电子元件'),
            ('M0005', '电容', '100μF', '个', '电子元件'),
            ('M0006', 'PCB板', 'A型', '块', '电子元件'),
            ('M0007', '螺丝刀', '十字', '把', '五金件'),
            ('M0008', '胶带', '宽48mm', '卷', '包装耗材'),
            ('M0009', '泡沫垫', 'A4', '片', '包装耗材'),
        ]
        ma = 0
        for code, name, spec, unit, cat_name in mats:
            cat = MaterialCategory.query.filter_by(name=cat_name).first()
            if Material.query.filter_by(code=code).first():
                continue
            db.session.add(Material(code=code, name=name, spec=spec, unit=unit,
                                    category_id=cat.id if cat else None))
            ma += 1
        c('物料', ma)

        # ---- 仓库（扩充）----
        wh3 = None
        if not Warehouse.query.filter_by(name='半成品仓').first():
            wh3 = Warehouse(name='半成品仓', location='1号厂房西侧')
            db.session.add(wh3)
            c('仓库', 1)

        warehouses = Warehouse.query.all()
        materials = Material.query.all()
        keeper_id = keeper.id if keeper else admin_user.id

        # ---- 出入库单据 + 库存 + 流水 ----
        inv_added = doc_added = led_added = 0
        for widx, warehouse in enumerate(warehouses):
            for midx, mat in enumerate(materials[:6]):
                inv = Inventory.query.filter_by(warehouse_id=warehouse.id, material_id=mat.id).first()
                base = (widx + 1) * 30 + midx * 5
                if not inv:
                    inv = Inventory(warehouse_id=warehouse.id, material_id=mat.id,
                                    quantity=base, warn_threshold=10)
                    db.session.add(inv)
                    inv_added += 1
                else:
                    inv.quantity = max(inv.quantity or 0, base)
                    inv.warn_threshold = 10

                # 为部分物料生成入库 + 出库单据与流水
                for dtype, qty in [('in', 50), ('out', 15)]:
                    doc_no = '%s-TEST-%d-%d-%s' % ('IN' if dtype == 'in' else 'OUT',
                                                  warehouse.id, mat.id, dtype)
                    if StockDocument.query.filter_by(doc_no=doc_no).first():
                        continue
                    before = inv.quantity
                    after = before + qty if dtype == 'in' else max(0, before - qty)
                    db.session.add(StockDocument(
                        doc_no=doc_no, doc_type=dtype, warehouse_id=warehouse.id,
                        material_id=mat.id, quantity=qty, handler_id=keeper_id,
                        created_by=keeper_id,
                        created_at=ts(TODAY - timedelta(days=(midx % 7) + 1), 10),
                        remark='测试数据-%s' % dtype))
                    inv.quantity = after
                    db.session.add(StockLedger(
                        doc_no=doc_no, doc_type=dtype, warehouse_id=warehouse.id,
                        material_id=mat.id, quantity=qty, before_balance=before,
                        after_balance=after, handler_id=keeper_id,
                        remark='测试数据流水',
                        created_at=ts(TODAY - timedelta(days=(midx % 7) + 1), 10)))
                    doc_added += 1
                    led_added += 1
        c('库存', inv_added)
        c('出入库单据', doc_added)
        c('库存流水', led_added)

        # ---- 工单（多状态）+ 工序 ----
        wo_data = [
            ('WO-TEST-001', '精密支架', 500, 'in_progress', leader),
            ('WO-TEST-002', '控制盒外壳', 300, 'in_progress', leader),
            ('WO-TEST-003', '连接器组件', 1000, 'completed', leader),
            ('WO-TEST-004', '包装套件', 2000, 'accepted', leader),
            ('WO-TEST-005', '传感器底座', 150, 'pending', leader),
        ]
        wo_added = step_added = 0
        for order_no, product, qty, status, leader_user in wo_data:
            if WorkOrder.query.filter_by(order_no=order_no).first():
                continue
            prod_dept = Department.query.filter_by(name='生产部').first()
            wo = WorkOrder(
                order_no=order_no, product_name=product, quantity=qty,
                due_date=TODAY + timedelta(days=10),
                leader_id=leader_user.id if leader_user else None,
                related_department_id=prod_dept.id if prod_dept else None,
                status=status,
                created_by=admin_user.id if admin_user else 1,
                created_at=ts(TODAY - timedelta(days=8), 9),
                remark='测试数据工单')
            db.session.add(wo)
            db.session.flush()
            for seq, (sname, sstat) in enumerate(
                    [('下料', 'completed' if status in ('completed', 'accepted') else 'in_progress'),
                     ('组装', 'completed' if status in ('completed', 'accepted') else 'pending'),
                     ('质检', 'completed' if status == 'accepted' else 'pending')], 1):
                db.session.add(WorkOrderStep(work_order_id=wo.id, name=sname, seq=seq,
                                             status=sstat))
                step_added += 1
            wo_added += 1
        c('工单', wo_added)
        c('工序', step_added)

        # ---- 库存预警通知 ----
        notif_added = 0
        if keeper:
            for i in range(2):
                if Notification.query.filter_by(title='库存预警-测试-%d' % i).first():
                    continue
                db.session.add(Notification(
                    receiver_id=keeper.id, notif_type='stock_warning',
                    title='库存预警-测试-%d' % i,
                    content='物料库存低于预警阈值，请及时补货（测试数据）',
                    created_at=ts(TODAY - timedelta(days=i), 8), is_read=(i == 1)))
                notif_added += 1
        c('预警通知', notif_added)

        # ---- 聊天消息 + 已读位点 ----
        msg_added = 0
        pairs = [(admin_user, leader), (leader, keeper), (admin_user, keeper)]
        for idx, (sender, receiver) in enumerate(pairs):
            if not sender or not receiver:
                continue
            for j in range(4):
                content = '测试消息 %d-%d：你好，这是一条用于演示的站内消息。' % (idx + 1, j + 1)
                if ChatMessage.query.filter_by(sender_id=sender.id, receiver_id=receiver.id,
                                               content=content).first():
                    continue
                db.session.add(ChatMessage(
                    sender_id=sender.id, receiver_id=receiver.id, content=content,
                    is_read=(j < 2), created_at=ts(TODAY, 9, j * 5)))
                msg_added += 1
            # 已读位点
            if not ConversationRead.query.filter_by(user_id=receiver.id, peer_id=sender.id).first():
                db.session.add(ConversationRead(user_id=receiver.id, peer_id=sender.id,
                                                last_read_message_id=0))
        c('聊天消息', msg_added)

        # ---- 文件分类 + 文件记录（不含真实文件，仅列表展示）----
        fc = FileCategory.query.filter_by(name='技术文档').first()
        if not fc:
            fc = FileCategory(name='技术文档')
            db.session.add(fc)
            c('文件分类', 1)
        ff_added = 0
        for i, (name, ext) in enumerate([('产品图纸A', '.pdf'), ('作业指导书', '.docx'),
                                         ('车间照片', '.png'), ('检验标准', '.pdf')]):
            stored = 'test_%d%s' % (i + 1, ext)
            if FactoryFile.query.filter_by(stored_filename=stored).first():
                continue
            db.session.add(FactoryFile(
                name=name, original_filename=stored, stored_filename=stored,
                file_ext=ext, size_bytes=102400 * (i + 1),
                category_id=fc.id, visibility_type='all',
                uploaded_by=admin_user.id if admin_user else 1,
                created_at=ts(TODAY - timedelta(days=i), 11)))
            ff_added += 1
        c('文件', ff_added)

        # ---- 操作日志 ----
        log_added = 0
        for i in range(15):
            summary = '测试操作日志 %d：系统演示数据' % (i + 1)
            if OperationLog.query.filter_by(summary=summary).first():
                continue
            db.session.add(OperationLog(
                operator_id=admin_user.id if admin_user else None,
                module=['hr', 'warehouse', 'production', 'attendance', 'files'][i % 5],
                action='create', target_type='test', target_id=i + 1,
                summary=summary, ip='127.0.0.1',
                created_at=ts(TODAY - timedelta(days=(i % 5)), 12, i)))
            log_added += 1
        c('操作日志', log_added)

        db.session.commit()
        print('===== 测试数据填充完成（幂等，已存在跳过）=====')
        for k, v in counts.items():
            print('  %-12s +%d' % (k, v))
        print()
        print('===== 各表最终行数 =====')
        tables = ['users', 'departments', 'attendance_records', 'leave_requests',
                  'work_orders', 'work_order_steps', 'materials', 'warehouses',
                  'inventories', 'stock_documents', 'stock_ledgers', 'notifications',
                  'chat_messages', 'operation_logs', 'factory_files']
        for t in tables:
            n = db.session.execute(db.text('SELECT COUNT(*) FROM %s' % t)).scalar()
            print('  %-24s %d' % (t, n))


if __name__ == '__main__':
    main()
