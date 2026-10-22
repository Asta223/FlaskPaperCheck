# 项目长期记忆：FlaskPaperCheck 课程报告查重系统

## 架构要点
- Flask + Flask-SQLAlchemy + Flask-Login + Flask-Migrate（alembic）。前端 Bootstrap5（CDN）。
- 查重算法：`app/utils/similarity.py`（TF-IDF / Jaccard / 文档级BERT / 句子级BERT / Doc2Vec）。Sentence-BERT 模型 `paraphrase-multilingual-MiniLM-L12-v2`，Doc2Vec 模型在 `models/doc2vec.model`。
- 语料库由两部分组成：**用户上传论文(Paper)** + **参考库(ReferencePaper)**。参考库来自 `data/processed_texts/*.txt`，通过 `services/seed_corpus.py` 导入。爬虫 `services/spider.py` 抓 arXiv 摘要存入 `processed_texts`（当前仅 2 篇示例，需扩充才有意义）。
- 文件解析 `app/utils/file_parser.py` 支持 **pdf/docx/txt**（**不支持旧版 .doc**）。

## 约定
- DB 默认 MySQL，已全部改为环境变量驱动（见 `.env.example` / `setup.sql`）；可用 `DB_ENGINE=sqlite` 或 `DATABASE_URL` 切到 SQLite 便于开发验证。
- 迁移 head 版本：`799e2ab02d72`，参考库表迁移 `a1b2c3d4e5f6`。
- 参考库接入后，早期用户也能得到有意义的相似度（之前只比对自己/他人上传，语料几乎为空）。
