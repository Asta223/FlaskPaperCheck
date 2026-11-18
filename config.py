import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:123@localhost:3306/paper_check?charset=utf8mb4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'data', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    # 添加 Doc2Vec 模型路径配置
    DOC2VEC_MODEL_PATH = os.path.join(basedir, 'models', 'doc2vec.model')