from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
#
# app.config['JSON_AS_ASCII'] = False  # 如果有 JSON 响应
# app.config['TEMPLATES_AUTO_RELOAD'] = True

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'

    # 注册蓝图
    from app.routes import auth, main, paper, history
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(paper.bp)
    app.register_blueprint(history.bp)

    # 确保模型被加载（用于迁移）
    from app import models

    return app