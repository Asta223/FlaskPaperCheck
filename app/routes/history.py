from flask import Blueprint, render_template, request  # 添加 Blueprint
from flask_login import login_required, current_user
from app.models import CheckRecord, Paper
from app import db

bp = Blueprint('history', __name__, url_prefix='/history')

@bp.route('/')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '')

    query = CheckRecord.query.join(Paper).filter(Paper.user_id == current_user.id)
    if search:
        query = query.filter(Paper.title.contains(search))

    # 统计信息
    total_count = query.count()
    avg_similarity = db.session.query(db.func.avg(CheckRecord.similarity_score))\
        .join(Paper).filter(Paper.user_id == current_user.id).scalar() or 0

    records = query.order_by(CheckRecord.check_time.desc()).paginate(page=page, per_page=per_page)

    return render_template('history.html',
                           records=records,
                           search=search,
                           total_count=total_count,
                           avg_similarity=round(avg_similarity * 100, 2))