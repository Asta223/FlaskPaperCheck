"""认证路由：登录/登出/个人信息/修改密码（自助注册已移除，账号由管理员创建）。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.forms.auth import LoginForm, PasswordChangeForm
from app.models.user import User

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录（停用账号拒绝登录）。"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('账号已停用，请联系管理员', 'danger')
                return render_template('login.html', form=form)
            login_user(user, remember=True)
            next_page = request.args.get('next')
            # 开放重定向防护：仅允许本站相对路径（拒绝 //evil.com、/\evil.com、绝对 URL）
            if (not next_page
                    or not next_page.startswith('/')
                    or next_page.startswith('//')
                    or next_page.startswith('/\\')):
                next_page = url_for('main.index')
            return redirect(next_page)
        flash('用户名或密码错误', 'danger')
    return render_template('login.html', form=form)


@bp.route('/logout')
@login_required
def logout():
    """登出。"""
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """个人信息 + 修改密码。"""
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.old_password.data):
            flash('原密码错误', 'danger')
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash('密码修改成功', 'success')
            return redirect(url_for('auth.profile'))
    return render_template('profile.html', user=current_user, form=form)
