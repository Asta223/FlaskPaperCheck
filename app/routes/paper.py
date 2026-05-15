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
        original_filename = f.filename

        # ========== 1. 安全处理文件名，保留扩展名 ==========
        name_part, ext = os.path.splitext(original_filename)
        safe_name = secure_filename(name_part) if name_part else ''
        if not safe_name:
            safe_name = 'file'
        unique_name = f"{uuid.uuid4()}_{safe_name}{ext}"

        # ========== 2. 保存上传文件 ==========
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, unique_name)
        f.save(filepath)

        # ========== 3. 计算文件哈希 ==========
        def compute_hash(file_path):
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as fh:
                for chunk in iter(lambda: fh.read(4096), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()

        file_hash = compute_hash(filepath)

        # ========== 4. 检查是否已存在相同哈希的论文 ==========
        # existing_paper = Paper.query.filter_by(file_hash=file_hash).first()
        # if existing_paper:
        #     os.remove(filepath)  # 删除刚上传的临时文件
        #     flash('该论文已存在，请勿重复上传！', 'warning')
        #     # 如果已有查重记录，直接跳转到结果页
        #     existing_record = CheckRecord.query.filter_by(paper_id=existing_paper.id).first()
        #     if existing_record:
        #         return redirect(url_for('paper.result', record_id=existing_record.id))
        #     else:
        #         return redirect(url_for('paper.upload'))

        # ========== 5. 解析文件内容 ==========
        try:
            content = extract_text(filepath)
        except Exception as e:
            current_app.logger.error(f"文件解析失败: {str(e)}", exc_info=True)
            flash(f'文件解析失败: {str(e)}', 'danger')
            os.remove(filepath)
            return redirect(url_for('paper.upload'))

        # ========== 6. 保存论文记录（含哈希） ==========
        paper = Paper(
            title=form.title.data,
            filename=original_filename,
            file_path=filepath,
            content_text=content,
            user_id=current_user.id,
            file_hash=file_hash  # 关键：保存哈希值
        )
        db.session.add(paper)
        db.session.commit()

        # ========== 7. 获取语料库（排除当前论文 + 可选的排除自己） ==========
        query = Paper.query.filter(Paper.id != paper.id)
        # 如果用户未勾选“与自己的历史论文比对”，则排除自己
        if not form.compare_self.data:
            query = query.filter(Paper.user_id != current_user.id)
        corpus_papers = query.all()
        corpus_texts = [p.content_text for p in corpus_papers if p.content_text]

        threshold = form.threshold.data
        algo = form.algorithm.data

        # ========== 8. 根据算法计算相似度（完整保留你的所有分支） ==========
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

        # ========== 9. 保存查重记录 ==========
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