import hashlib
import os
import uuid
import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort, make_response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.forms import UploadForm
from app.models import Paper, CheckRecord
from app.utils.file_parser import extract_text
from app.utils.similarity import (
    tfidf_similarity,
    sentence_bert_similarity,
    sentence_level_similarity,
    doc2vec_similarity,
    jaccard_similarity,
    _get_sbert_model
)

# 计算文件哈希
def calculate_file_hash(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for block in iter(lambda: f.read(4096), b''):
            sha256.update(block)
    return sha256.hexdigest()

bp = Blueprint('paper', __name__, url_prefix='/paper')   # <--- 必须有这一行

@bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        f = form.file.data
        original_filename = secure_filename(f.filename)
        unique_name = str(uuid.uuid4()) + '_' + original_filename
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, unique_name)
        f.save(filepath)

        # 1. 计算哈希并检查重复
        file_hash = calculate_file_hash(filepath)
        existing_paper = Paper.query.filter_by(file_hash=file_hash).first()
        if existing_paper:
            os.remove(filepath)  # 删除刚上传的临时文件
            flash('该论文已存在，请勿重复上传！', 'warning')
            # 若有查重记录可直接跳转
            existing_record = CheckRecord.query.filter_by(paper_id=existing_paper.id).first()
            if existing_record:
                return redirect(url_for('paper.result', record_id=existing_record.id))
            else:
                return redirect(url_for('paper.upload'))

        # 2. 解析文本（只有在不重复时才执行）
        try:
            content = extract_text(filepath)
        except Exception as e:
            flash(f'文件解析失败: {str(e)}', 'danger')
            # 解析失败也要清理已上传的文件
            os.remove(filepath)
            return redirect(url_for('paper.upload'))

        # 3. 保存论文记录（含哈希）
        paper = Paper(
            title=form.title.data,
            filename=original_filename,
            file_path=filepath,
            content_text=content,
            user_id=current_user.id,
            file_hash=file_hash
        )
        db.session.add(paper)
        db.session.commit()

        # 获取语料库（排除当前论文 + 排除自己之前的论文）
        query = Paper.query.filter(Paper.id != paper.id)
        if not form.compare_self.data:
            query = query.filter(Paper.user_id != current_user.id)
        corpus_papers = query.all()
        corpus_texts = [p.content_text for p in corpus_papers if p.content_text]

        threshold = form.threshold.data
        algo = form.algorithm.data

        if corpus_texts:
            if algo == 'tfidf':
                sim_scores = tfidf_similarity(content, corpus_texts)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus_papers[i].id, 'title': corpus_papers[i].title, 'score': float(score)}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {
                    'similar_papers': similar_list,
                    'algorithm': algo,
                    'threshold': threshold
                }

            elif algo == 'bert':
                sim_scores = sentence_bert_similarity(content, corpus_texts)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus_papers[i].id, 'title': corpus_papers[i].title, 'score': float(score)}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {
                    'similar_papers': similar_list,
                    'algorithm': algo,
                    'threshold': threshold
                }

            elif algo == 'sentence_bert':
                model = _get_sbert_model()
                all_matches = []
                max_sim = 0.0
                for idx, cp in enumerate(corpus_papers):
                    sim_score, matches = sentence_level_similarity(content, cp.content_text, model, threshold)
                    if sim_score > max_sim:
                        max_sim = sim_score
                    if matches:
                        all_matches.append({
                            'paper_id': cp.id,
                            'paper_title': cp.title,
                            'score': sim_score,
                            'matches': matches
                        })
                details = {
                    'algorithm': algo,
                    'threshold': threshold,
                    'paper_matches': all_matches
                }

            elif algo == 'doc2vec':
                model_path = current_app.config['DOC2VEC_MODEL_PATH']
                sim_scores = doc2vec_similarity(content, corpus_texts, model_path)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus_papers[i].id, 'title': corpus_papers[i].title, 'score': float(score)}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {
                    'similar_papers': similar_list,
                    'algorithm': algo,
                    'threshold': threshold
                }

            # ---------- 新增 Jaccard 算法分支 ----------
            elif algo == 'jaccard':
                sim_scores = jaccard_similarity(content, corpus_texts)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus_papers[i].id, 'title': corpus_papers[i].title, 'score': float(score)}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {
                    'similar_papers': similar_list,
                    'algorithm': algo,
                    'threshold': threshold
                }
            # ----------------------------------------

            else:
                # 默认 TF-IDF
                sim_scores = tfidf_similarity(content, corpus_texts)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus_papers[i].id, 'title': corpus_papers[i].title, 'score': float(score)}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {
                    'similar_papers': similar_list,
                    'algorithm': 'tfidf',
                    'threshold': threshold
                }
        else:
            max_sim = 0.0
            details = {'algorithm': algo, 'threshold': threshold}

        record = CheckRecord(
            paper_id=paper.id,
            algorithm=algo,
            similarity_score=max_sim,
            details=json.dumps(details, ensure_ascii=False)
        )
        db.session.add(record)
        db.session.commit()

        flash('查重完成！', 'success')
        return redirect(url_for('paper.result', record_id=record.id))

    return render_template('upload.html', form=form)

@bp.route('/result/<int:record_id>')
@login_required
def result(record_id):
    record = CheckRecord.query.get_or_404(record_id)
    if record.paper.user_id != current_user.id:
        flash('无权访问', 'danger')
        return redirect(url_for('main.index'))
    return render_template('result.html', record=record)

@bp.route('/export/<int:record_id>')
@login_required
def export_pdf(record_id):
    record = CheckRecord.query.get_or_404(record_id)
    if record.paper.user_id != current_user.id:
        abort(403)
    try:
        import pdfkit
    except ImportError:
        flash('PDF导出功能未安装', 'danger')
        return redirect(url_for('paper.result', record_id=record_id))

    rendered = render_template('report_pdf.html', record=record)
    options = {'page-size': 'A4', 'encoding': 'UTF-8'}
    # 如果 wkhtmltopdf 不在 PATH，需指定路径
    # config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
    # pdf = pdfkit.from_string(rendered, False, options=options, configuration=config)
    pdf = pdfkit.from_string(rendered, False, options=options)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=report_{record_id}.pdf'
    return response