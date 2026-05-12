import re
import jieba
import os

def load_stopwords(filepath='app/utils/stopwords.txt'):
    stopwords = set()
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip()
                if word:
                    stopwords.add(word)
    return stopwords

STOPWORDS = load_stopwords()

def chinese_word_segmentation(text, stopwords=STOPWORDS):
    # 去除标点符号（保留中文、字母、数字）
    text = re.sub(r'[^\w\u4e00-\u9fff]', ' ', text)
    words = jieba.lcut(text)
    # 过滤停用词和单字词
    words = [w for w in words if w not in stopwords and len(w.strip()) > 1]
    return words

def preprocess_text(text):
    return chinese_word_segmentation(text)

def split_sentences(text):
    """
    将文本分割成句子列表，以 。！？等标点分割。
    """
    sentences = re.split(r'[。！？!?]', text)
    # 去除空白句子并去除首尾空格
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences