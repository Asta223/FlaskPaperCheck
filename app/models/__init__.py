"""数据模型包：统一 re-export 全部模型，供迁移与业务代码导入。"""
from app.models.user import User, user_roles
from app.models.rbac import Permission, Role, role_permissions
from app.models.org import Department
from app.models.attendance import AttendanceRecord
from app.models.production import WorkOrder, WorkOrderStep
from app.models.material import Material, MaterialCategory
from app.models.warehouse import Inventory, StockDocument, Warehouse
from app.models.file import FactoryFile, FileCategory, file_role_visibility, \
    file_department_visibility
from app.models.chat import ChatMessage, ConversationRead
# P1 新增模型
from app.models.system import OperationLog, Notification, StockWarningState
from app.models.leave import LeaveRequest
from app.models.ledger import StockLedger

__all__ = [
    'User', 'user_roles',
    'Role', 'Permission', 'role_permissions',
    'Department',
    'AttendanceRecord',
    'WorkOrder', 'WorkOrderStep',
    'MaterialCategory', 'Material',
    'Warehouse', 'Inventory', 'StockDocument',
    'FileCategory', 'FactoryFile', 'file_role_visibility', 'file_department_visibility',
    'ChatMessage', 'ConversationRead',
    'OperationLog', 'Notification', 'StockWarningState',
    'LeaveRequest', 'StockLedger',
]
