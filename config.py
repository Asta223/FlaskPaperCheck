import os

basedir = os.path.abspath(os.path.dirname(__file__))


def _build_default_db_uri():
    """数据库连接串：优先 DATABASE_URL；DB_ENGINE=sqlite 时用本地 SQLite；否则按分项变量拼 MySQL。"""
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    if os.environ.get('DB_ENGINE', '').lower() == 'sqlite':
        return 'sqlite:///' + os.path.join(basedir, 'factory_mgmt.db')
    return 'mysql+pymysql://{user}:{pw}@{host}:{port}/{db}?charset=utf8mb4'.format(
        user=os.environ.get('DB_USER', 'root'),
        pw=os.environ.get('DB_PASSWORD', '123'),
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '3306'),
        db=os.environ.get('DB_NAME', 'factory_mgmt'),
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
