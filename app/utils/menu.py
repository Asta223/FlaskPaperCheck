"""左侧导航菜单注册表 + 按权限过滤。

约定（架构文档共享知识 §3）：新增菜单项只改 MENU_REGISTRY，不改 base.html。
"""
from flask import current_app

from app.utils.permissions import has_permission


def _endpoint_available(endpoint: str) -> bool:
    """endpoint 是否已注册（防止分阶段上线/蓝图缺失导致 url_for 断链）。"""
    return bool(endpoint) and endpoint in current_app.view_functions

# 菜单结构：{'name','icon','endpoint','permission'} 或 {'name','icon','children':[...]}
MENU_REGISTRY = [
    {
        'name': '工作台',
        'icon': 'bi-speedometer2',
        'endpoint': 'main.index',
        'permission': None,
    },
    {
        'name': '组织人事',
        'icon': 'bi-people',
        'children': [
            {'name': '人员管理', 'endpoint': 'hr.employee_list', 'permission': 'hr.view'},
            {'name': '部门管理', 'endpoint': 'hr.departments', 'permission': 'dept.manage'},
            {'name': '角色权限', 'endpoint': 'rbac.role_list', 'permission': 'rbac.manage'},
            {'name': '权限点总览', 'endpoint': 'rbac.permission_list', 'permission': 'rbac.manage'},
        ],
    },
    {
        'name': '考勤管理',
        'icon': 'bi-clock-history',
        'children': [
            {'name': '考勤打卡', 'endpoint': 'attendance.clock', 'permission': 'attendance.clock'},
            {'name': '打卡记录', 'endpoint': 'attendance.records', 'permission': 'attendance.view'},
            {'name': '月度统计', 'endpoint': 'attendance.monthly', 'permission': 'attendance.view'},
            {'name': '请假申请', 'endpoint': 'attendance.leave_new', 'permission': 'attendance.leave.apply'},
            {'name': '我的请假', 'endpoint': 'attendance.leave_list', 'permission': 'attendance.leave.apply'},
            {'name': '待我审批', 'endpoint': 'attendance.leave_approvals', 'permission': 'attendance.leave.approve'},
        ],
    },
    {
        'name': '生产管理',
        'icon': 'bi-diagram-3',
        'children': [
            {'name': '生产工单', 'endpoint': 'production.order_list', 'permission': 'production.view'},
            {'name': '进度看板', 'endpoint': 'production.board', 'permission': 'production.view'},
            {'name': '工序档案', 'endpoint': 'production.process_list', 'permission': 'production.view'},
        ],
    },
    {
        'name': '物料仓库',
        'icon': 'bi-box-seam',
        'children': [
            {'name': '物料分类', 'endpoint': 'material.category_list', 'permission': 'material.manage'},
            {'name': '物料档案', 'endpoint': 'material.material_list', 'permission': 'material.manage'},
            {'name': '仓库档案', 'endpoint': 'warehouse.warehouse_list', 'permission': 'warehouse.manage'},
            {'name': '出入库单据', 'endpoint': 'warehouse.doc_list', 'permission': 'warehouse.manage'},
            {'name': '库存查询', 'endpoint': 'warehouse.inventory', 'permission': 'warehouse.view'},
            {'name': '库存流水', 'endpoint': 'warehouse.ledger', 'permission': 'warehouse.ledger.view'},
        ],
    },
    {
        'name': '文件管理',
        'icon': 'bi-folder2',
        'children': [
            {'name': '文件资料', 'endpoint': 'files.index', 'permission': 'files.view'},
        ],
    },
    {
        'name': '站内聊天',
        'icon': 'bi-chat-dots',
        'endpoint': 'chat.index',
        'permission': None,
    },
    {
        'name': '系统管理',
        'icon': 'bi-gear',
        'children': [
            {'name': '操作日志', 'endpoint': 'system.operation_logs', 'permission': 'system.log.view'},
        ],
    },
]


def get_current_menu(user) -> list:
    """按用户权限过滤 MENU_REGISTRY，剔除可见子项为空的分组。"""
    result = []
    for item in MENU_REGISTRY:
        children = item.get('children')
        if children is not None:
            visible = [
                dict(sub) for sub in children
                if _endpoint_available(sub.get('endpoint'))
                and (not sub.get('permission') or has_permission(user, sub['permission']))
            ]
            if visible:
                entry = {k: v for k, v in item.items() if k != 'children'}
                entry['children'] = visible
                result.append(entry)
        else:
            perm = item.get('permission')
            if _endpoint_available(item.get('endpoint')) and (
                    not perm or has_permission(user, perm)):
                result.append(dict(item))
    return result
