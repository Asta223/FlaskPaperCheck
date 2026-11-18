"""
参考语料库种子脚本
==================
把 data/processed_texts/*.txt 导入数据库 reference_papers 表（按内容哈希去重，可重复执行）。

用法：
    # 在项目根目录，使用项目的 venv 运行
    venv\\Scripts\\python.exe services/seed_corpus.py

可选：导入后重新训练 Doc2Vec 模型（语料越大效果越好）
    venv\\Scripts\\python.exe services/seed_corpus.py --retrain
"""
import os
import sys
import hashlib
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, 'data', 'processed_texts')

sys.path.insert(0, BASE_DIR)

from app import create_app, db
from app.models import ReferencePaper


def parse_title(text):
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith('title:'):
            return line[len('title:'):].strip()
    return '未命名文献'


def seed():
    added = 0
    skipped = 0
    for fn in sorted(os.listdir(PROCESSED_DIR)):
        if not fn.endswith('.txt'):
            continue
        path = os.path.join(PROCESSED_DIR, fn)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except Exception as e:
            print(f'读取失败 {fn}: {e}')
            continue
        if not text.strip():
            continue
        content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if ReferencePaper.query.filter_by(content_hash=content_hash).first():
            skipped += 1
            continue
        rp = ReferencePaper(
            title=parse_title(text),
            source='arxiv' if fn.lower().startswith('arxiv') else 'import',
            content_text=text,
            file_path=path,
            content_hash=content_hash,
            is_active=True,
        )
        db.session.add(rp)
        added += 1
    db.session.commit()
    total = ReferencePaper.query.filter_by(is_active=True).count()
    print(f'本次新增 {added} 篇，跳过已存在 {skipped} 篇；参考库当前共 {total} 篇。')


def retrain_doc2vec():
    """基于 参考库 + 用户论文 重新训练 Doc2Vec（需要足够语料才有意义）。"""
    from app.utils.similarity import load_doc2vec_model
    import jieba
    from gensim.models.doc2vec import Doc2Vec, TaggedDocument

    rows = []
    refs = ReferencePaper.query.filter_by(is_active=True).all()
    for r in refs:
        if r.content_text:
            rows.append((f'ref_{r.id}', r.content_text))
    # 也可加入用户论文（取消下一行注释）
    # from app.models import Paper
    # for p in Paper.query.all():
    #     if p.content_text:
    #         rows.append((f'paper_{p.id}', p.content_text))

    if len(rows) < 2:
        print('语料过少（<2），跳过训练。请先向 data/processed_texts 放入更多 .txt。')
        return

    documents = [TaggedDocument(jieba.lcut(text), [tag]) for tag, text in rows]
    model = Doc2Vec(vector_size=100, window=5, min_count=1, workers=4, epochs=20)
    model.build_vocab(documents)
    model.train(documents, total_examples=model.corpus_count, epochs=model.epochs)
    out_path = os.path.join(BASE_DIR, 'models', 'doc2vec.model')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    model.save(out_path)
    print(f'Doc2Vec 已重新训练并保存至 {out_path}（共 {len(rows)} 篇语料）')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='导入参考语料库')
    parser.add_argument('--retrain', action='store_true', help='导入后重新训练 Doc2Vec 模型')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        seed()
        if args.retrain:
            retrain_doc2vec()
