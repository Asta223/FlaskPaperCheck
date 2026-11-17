import os

basedir = os.path.abspath(os.path.dirname(__file__))


def _build_default_db_uri():
    """优先使用 DATABASE_URL；否则用分项环境变量拼一个 MySQL 连接；都没有则回退 SQLite。"""
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    mysql_uri = 'mysql+pymysql://{user}:{pw}@{host}:{port}/{db}?charset=utf8mb4'.format(
        user=os.environ.get('DB_USER', 'root'),
        pw=os.environ.get('DB_PASSWORD', '123'),
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '3306'),
        db=os.environ.get('DB_NAME', 'paper_check'),
    )
    # 若显式声明用 SQLite（开发/演示），则用之
    if os.environ.get('DB_ENGINE', '').lower() == 'sqlite':
        return 'sqlite:///' + os.path.join(basedir, 'paper_check.db')
    return mysql_uri


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    SQLALCHEMY_DATABASE_URI = _build_default_db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'data', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    DOC2VEC_MODEL_PATH = os.environ.get('DOC2VEC_MODEL_PATH') or os.path.join(basedir, 'models', 'doc2vec.model')

    # 允许上传的扩展名（.doc 旧格式暂不原生支持，统一引导用户转 .docx/.pdf）
    ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt'}

    # 是否启用参考语料库（爬虫/导入的文献）。关闭后只比对已上传论文。
    USE_REFERENCE_CORPUS = os.environ.get('USE_REFERENCE_CORPUS', '1') != '0'
