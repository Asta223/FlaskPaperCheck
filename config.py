# -*- coding: utf-8 -*-
"""应用配置。

在读取任何 os.environ 配置项之前，先用纯标准库加载项目根目录的 .env
（零新增依赖，不要求安装 python-dotenv）。真实环境变量优先级高于 .env：
只有 os.environ 中不存在某个 key 时，.env 的值才会被写入。
"""
import os
import re

basedir = os.path.abspath(os.path.dirname(__file__))

_ENV_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _strip_inline_comment(value):
    """去掉未被引号包裹的行尾 ``#`` 注释；引号内的 ``#`` 原样保留。"""
    quote = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == '\\':
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
            continue
        if char == '#' and (index == 0 or value[index - 1].isspace()):
            return value[:index]
    return value


def _unescape_double_quoted(value):
    """还原双引号值里的常见转义序列（\\n / \\t / \\r / \\\\ / \\"）。"""
    result = []
    escaped = False
    for char in value:
        if escaped:
            result.append({'n': '\n', 't': '\t', 'r': '\r'}.get(char, char))
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        result.append(char)
    if escaped:
        result.append('\\')
    return ''.join(result)


def _load_dotenv(path=None):
    """把 .env 中的 KEY=VALUE 注入 os.environ，已存在的环境变量不被覆盖。

    Args:
        path: 可选的 .env 路径；默认取项目根目录下的 .env。

    Returns:
        int: 本次实际写入 os.environ 的键数量；文件不存在时返回 0。
    """
    env_path = path if path is not None else os.path.join(basedir, '.env')
    try:
        with open(env_path, 'r', encoding='utf-8-sig') as env_file:
            lines = env_file.readlines()
    except OSError:
        return 0

    loaded = 0
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not _ENV_KEY_RE.match(key):
            continue
        value = _strip_inline_comment(value).strip()
        if len(value) >= 2 and value[0] == value[-1]:
            if value[0] == "'":
                value = value[1:-1]
            elif value[0] == '"':
                value = _unescape_double_quoted(value[1:-1])
        if key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


# 必须在 Config 类读取 os.environ 之前执行（VS Code Flask 扩展等启动方式
# 不继承终端里 set/export 的变量，只能靠项目根 .env 提供默认配置）。
_load_dotenv()


def _build_default_db_uri():
    """数据库连接串：优先 DATABASE_URL；DB_ENGINE=sqlite 时用本地 SQLite；否则按分项变量拼 MySQL。

    完全没有任何 DB_* 配置且本地没有 .env 时（例如刚 clone）默认走 SQLite，
    保证零配置/任意启动方式都能连上本地开发库；其余情况沿用原有优先级：
    DATABASE_URL > DB_ENGINE（环境变量或 .env）> MySQL 分项变量。
    """
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    db_engine = os.environ.get('DB_ENGINE')
    mysql_fields = ('DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME')
    if not db_engine and not any(os.environ.get(key) for key in mysql_fields):
        db_engine = 'sqlite'
    if db_engine and db_engine.lower() == 'sqlite':
        return 'sqlite:///' + os.path.join(basedir, 'factory_mgmt.db')
    return 'mysql+pymysql://{user}:{pw}@{host}:{port}/{db}?charset=utf8mb4'.format(
        user=os.environ.get('DB_USER', 'root'),
        pw=os.environ.get('DB_PASSWORD', '123'),
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '3306'),
        db=os.environ.get('DB_NAME', 'FactoryManagementSystem'),
    )


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'factory-mgmt-secret-key'
    SQLALCHEMY_DATABASE_URI = _build_default_db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 时间约定：全部字段统一存本地时间（Asia/Shanghai，naive datetime）。
    # 取当前时间一律走 app/utils/time_utils.now()，禁止散落 datetime.now()/utcnow()。
    TIMEZONE = 'Asia/Shanghai'

    # 文件上传（T08 文件管理）：复用 data/uploads 目录，50MB 上限 + 扩展名白名单
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'data', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
    UPLOAD_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md', '.csv',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp',
        '.zip', '.rar', '.7z',
        '.dwg', '.dxf',
    }

    # P1-02 考勤判定阈值（默认假设 A2）：标准班次 09:00–18:00，宽限 15 分钟
    # 签到晚于 09:15 记迟到；签退早于 17:45 记早退；工作日周一~周五
    SHIFT_START = '09:00'
    SHIFT_END = '18:00'
    LATE_GRACE_MIN = 15
    EARLY_GRACE_MIN = 15
    WORKDAYS = (0, 1, 2, 3, 4)  # Monday=0

    # P1-12 图片/PDF 内联预览扩展名
    PREVIEW_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'}

    # P1-16 CSV 单次导出行数上限（默认假设 A1）
    MAX_EXPORT_ROWS = 10000
