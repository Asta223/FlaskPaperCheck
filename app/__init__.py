"""应用工厂：初始化扩展、注册全部蓝图、注入模板上下文（权限菜单/时间过滤器）。"""
from flask import Flask, render_template
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_class=Config):
    """创建并配置 Flask 应用（应用工厂模式）。"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'

    # 注册全部业务蓝图
    from app.routes import attendance, auth, chat, files, hr, main, material, production, rbac, \
        system, warehouse
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(hr.bp)
    app.register_blueprint(rbac.bp)
    app.register_blueprint(attendance.bp)
    app.register_blueprint(production.bp)
    app.register_blueprint(material.bp)
    app.register_blueprint(warehouse.bp)
    app.register_blueprint(files.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(system.bp)

    # 加载模型包（迁移自动发现 + user_loader 绑定）
    from app import models  # noqa: F401

    # 统一错误页
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(_error):
        return render_template('errors/404.html'), 404

    # 模板上下文：按权限过滤后的左侧菜单
    from app.utils.menu import get_current_menu

    @app.context_processor
    def inject_base_context():
        menu = []
        if current_user.is_authenticated:
            menu = get_current_menu(current_user)
        return {'current_menu': menu}

    # 模板过滤器：时间/日期格式化（YYYY-MM-DD HH:mm / YYYY-MM-DD）
    from app.utils.time_utils import fmt_date, fmt_dt
    app.add_template_filter(fmt_dt, 'fmt_dt')
    app.add_template_filter(fmt_date, 'fmt_date')

    # 模板过滤器：返回用户权限码集合（模板中 'xxx' in user|perm_codes 判断）
    from app.utils.permissions import get_user_permission_codes
    app.add_template_filter(get_user_permission_codes, 'perm_codes')

    return app
