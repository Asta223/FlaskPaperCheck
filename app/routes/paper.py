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
    highlight_sentences,
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

        # ========== 7. 构建查重语料库：用户论文 + 参考库 ==========
        from app.models import ReferencePaper
        user_query = Paper.query.filter(Paper.id != paper.id)
        # 如果用户未勾选“与自己的历史论文比对”，则排除自己
        if not form.compare_self.data:
            user_query = user_query.filter(Paper.user_id != current_user.id)
        user_papers = user_query.all()

        corpus = []
        for p in user_papers:
            if p.content_text:
                corpus.append({'id': p.id, 'title': p.title,
                               'text': p.content_text, 'source': 'user'})
        # 参考语料库（爬虫/导入的文献），让查重真正有“参照物”
        if current_app.config.get('USE_REFERENCE_CORPUS', True):
            for r in ReferencePaper.query.filter_by(is_active=True).all():
                if r.content_text:
                    corpus.append({'id': r.id, 'title': r.title,
                                   'text': r.content_text, 'source': 'reference'})

        corpus_texts = [c['text'] for c in corpus]

        threshold = form.threshold.data
        algo = form.algorithm.data

        # ========== 8. 根据算法计算相似度（语料库已统一为 corpus） ==========
        if corpus_texts:
            if algo in ('tfidf', 'jaccard'):
                func = tfidf_similarity if algo == 'tfidf' else jaccard_similarity
                sim_scores = func(content, corpus_texts)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus[i]['id'], 'title': corpus[i]['title'],
                     'score': float(score), 'source': corpus[i]['source']}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {'algorithm': algo, 'threshold': threshold,
                           'corpus_size': len(corpus), 'similar_papers': similar_list}

            elif algo == 'bert':
                sim_scores = sentence_bert_similarity(content, corpus_texts)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus[i]['id'], 'title': corpus[i]['title'],
                     'score': float(score), 'source': corpus[i]['source']}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {'algorithm': algo, 'threshold': threshold,
                           'corpus_size': len(corpus), 'similar_papers': similar_list}

            elif algo == 'doc2vec':
                model_path = current_app.config['DOC2VEC_MODEL_PATH']
                sim_scores = doc2vec_similarity(content, corpus_texts, model_path)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus[i]['id'], 'title': corpus[i]['title'],
                     'score': float(score), 'source': corpus[i]['source']}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {'algorithm': algo, 'threshold': threshold,
                           'corpus_size': len(corpus), 'similar_papers': similar_list}

            elif algo == 'sentence_bert':
                model = _get_sbert_model()
                all_matches = []
                max_sim = 0.0
                for item in corpus:
                    sim_score, matches = sentence_level_similarity(
                        content, item['text'], model, threshold)
                    if sim_score > max_sim:
                        max_sim = sim_score
                    if matches:
                        all_matches.append({
                            'id': item['id'],
                            'paper_title': item['title'],
                            'score': sim_score,
                            'source': item['source'],
                            'matches': matches
                        })
                details = {'algorithm': algo, 'threshold': threshold,
                           'corpus_size': len(corpus), 'paper_matches': all_matches}

            else:
                # 默认 TF-IDF
                sim_scores = tfidf_similarity(content, corpus_texts)
                max_sim = sim_scores.max() if sim_scores.size > 0 else 0.0
                similar_list = [
                    {'id': corpus[i]['id'], 'title': corpus[i]['title'],
                     'score': float(score), 'source': corpus[i]['source']}
                    for i, score in enumerate(sim_scores) if score > threshold
                ]
                details = {'algorithm': 'tfidf', 'threshold': threshold,
                           'corpus_size': len(corpus), 'similar_papers': similar_list}
        else:
            max_sim = 0.0
            details = {'algorithm': algo, 'threshold': threshold, 'corpus_size': 0}

        # ========== 8.5 句子级高亮（所有算法通用，基于 TF-IDF 句子余弦） ==========
        highlights = highlight_sentences(content, corpus, threshold)
        details['highlights'] = highlights
        details['highlight_count'] = len(highlights)

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

    reference_count = 0
    if current_app.config.get('USE_REFERENCE_CORPUS', True):
        from app.models import ReferencePaper
        reference_count = ReferencePaper.query.filter_by(is_active=True).count()
    return render_template('upload.html', form=form, reference_count=reference_count)

@bp.route('/result/<int:record_id>')
@login_required
def result(record_id):
    record = CheckRecord.query.get_or_404(record_id)
    if record.paper.user_id != current_user.id:
        flash('无权访问', 'danger')
        return redirect(url_for('main.index'))
    # 构建全文高亮视图（按句拆分，标记疑似相似句）
    highlight_view = None
    details = record.get_details()
    highlights = details.get('highlights') or []
    if highlights:
        from app.utils.text_preprocess import split_sentences
        sents = split_sentences(record.paper.content_text or '')
        idx_set = {int(h['index']) for h in highlights}
        highlight_view = [(i, s, i in idx_set) for i, s in enumerate(sents)]
    return render_template('result.html', record=record, highlight_view=highlight_view)

@bp.route('/export/<int:record_id>')
@login_required
def export(record_id):
    """导出查重报告，支持 ?format=pdf(默认) / docx / html，均不依赖 wkhtmltopdf。"""
    record = CheckRecord.query.get_or_404(record_id)
    if record.paper.user_id != current_user.id:
        abort(403)
    fmt = (request.args.get('format') or 'pdf').lower()

    if fmt == 'docx':
        from app.utils.report import build_docx
        data = build_docx(record)
        resp = make_response(data)
        resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        resp.headers['Content-Disposition'] = f'attachment; filename=report_{record_id}.docx'
        return resp

    if fmt == 'html':
        rendered = render_template('report_pdf.html', record=record)
        resp = make_response(rendered)
        resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename=report_{record_id}.html'
        return resp

    # 默认 PDF：优先用 reportlab（无需外部二进制）
    try:
        from app.utils.report import build_pdf
        data = build_pdf(record)
        resp = make_response(data)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = f'attachment; filename=report_{record_id}.pdf'
        return resp
    except Exception as e:
        current_app.logger.error(f"PDF 生成失败: {e}", exc_info=True)
        flash('PDF 生成失败，已改为导出 HTML（可用浏览器打印为 PDF）', 'warning')
        rendered = render_template('report_pdf.html', record=record)
        resp = make_response(rendered)
        resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename=report_{record_id}.html'
        return resp