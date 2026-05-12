from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import jieba
import numpy as np
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'  # 添加这一行
from sentence_transformers import SentenceTransformer
from gensim.models import Doc2Vec
from app.utils.text_preprocess import split_sentences

# ---------- TF-IDF ----------
def tokenize_chinese(text):
    return ' '.join(jieba.cut(text))

def tfidf_similarity(new_text, corpus_texts):
    all_texts = [tokenize_chinese(new_text)] + [tokenize_chinese(t) for t in corpus_texts]
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(all_texts)
    sim_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
    return sim_scores

# ---------- Sentence-BERT ----------
_sbert_model = None

def _get_sbert_model():
    global _sbert_model
    if _sbert_model is None:
        _sbert_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _sbert_model

def sentence_bert_similarity(new_text, corpus_texts):
    model = _get_sbert_model()
    all_texts = [new_text] + corpus_texts
    embeddings = model.encode(all_texts, convert_to_tensor=True)
    from torch.nn.functional import cosine_similarity
    new_emb = embeddings[0].unsqueeze(0)
    corpus_emb = embeddings[1:]
    sim_scores = cosine_similarity(new_emb, corpus_emb).cpu().numpy()
    return sim_scores

def sentence_level_similarity(text1, text2, model=None, threshold=0.5):
    if model is None:
        model = _get_sbert_model()
    sents1 = split_sentences(text1)
    sents2 = split_sentences(text2)
    if not sents1 or not sents2:
        return 0.0, []
    emb1 = model.encode(sents1, convert_to_tensor=False)
    emb2 = model.encode(sents2, convert_to_tensor=False)
    sim_matrix = cosine_similarity(emb1, emb2)
    matches = []
    for i, sent1 in enumerate(sents1):
        best_idx = np.argmax(sim_matrix[i])
        best_score = sim_matrix[i][best_idx]
        if best_score >= threshold:
            matches.append({
                'sentence_a': sent1,
                'sentence_b': sents2[best_idx],
                'score': float(best_score)
            })
    overall_sim = np.mean([m['score'] for m in matches]) if matches else 0.0
    return overall_sim, matches

# ---------- Doc2Vec ----------
_doc2vec_model = None
_doc2vec_path = None

def load_doc2vec_model(model_path):
    global _doc2vec_model, _doc2vec_path
    if _doc2vec_model is None or _doc2vec_path != model_path:
        if os.path.exists(model_path):
            _doc2vec_model = Doc2Vec.load(model_path)
            _doc2vec_path = model_path
        else:
            _doc2vec_model = None
    return _doc2vec_model

def doc2vec_similarity(new_text, corpus_texts, model_path):
    model = load_doc2vec_model(model_path)
    if model is None:
        return np.zeros(len(corpus_texts))
    words = list(jieba.cut(new_text))
    new_vec = model.infer_vector(words)
    corpus_vecs = []
    for text in corpus_texts:
        words = list(jieba.cut(text))
        vec = model.infer_vector(words)
        corpus_vecs.append(vec)
    corpus_vecs = np.array(corpus_vecs)
    sim_scores = cosine_similarity([new_vec], corpus_vecs).flatten()
    return sim_scores

# ---------- 新增 Jaccard 相似度算法 ----------
def jaccard_similarity(new_text, corpus_texts):
    """
    基于词集的 Jaccard 相似度（新增算法示例）
    """
    def get_words_set(text):
        # 使用 jieba 分词，返回词集合
        words = jieba.lcut(text)
        # 可选：去除停用词（这里简化处理）
        return set(words)

    new_set = get_words_set(new_text)
    sim_scores = []
    for text in corpus_texts:
        corpus_set = get_words_set(text)
        if not new_set or not corpus_set:
            sim = 0.0
        else:
            intersection = new_set & corpus_set
            union = new_set | corpus_set
            sim = len(intersection) / len(union)
        sim_scores.append(sim)
    return np.array(sim_scores)