import os
import sys
import jieba
from gensim.models.doc2vec import Doc2Vec, TaggedDocument

# 获取项目根目录（假设当前脚本位于 services/ 下）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_FOLDER = os.path.join(BASE_DIR, 'data', 'processed_texts')
MODEL_PATH = os.path.join(BASE_DIR, 'models', 'doc2vec.model')

def load_texts(folder):
    """
    读取指定文件夹中的所有 .txt 文件，返回分词后的列表和文件名列表。
    如果文件夹不存在，则自动创建。
    """
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"目录 {folder} 已自动创建，请放入 .txt 文件后再运行训练。")
        return [], []

    texts = []
    filenames = []
    for fname in os.listdir(folder):
        if fname.endswith('.txt'):
            filepath = os.path.join(folder, fname)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 中文分词
                words = jieba.lcut(content)
                # 可选：去除停用词（如果已有停用词表可以在此过滤）
                # 简单过滤掉单字词
                words = [w for w in words if len(w) > 1]
                if words:
                    texts.append(words)
                    filenames.append(fname)
                    print(f"已加载: {fname}")
            except Exception as e:
                print(f"读取文件 {fname} 出错: {e}")
    return texts, filenames

def train_doc2vec(texts, filenames, model_path, vector_size=100, epochs=20):
    """
    训练 Doc2Vec 模型并保存。
    """
    # 构建 TaggedDocument 列表
    documents = [TaggedDocument(words, [fname]) for words, fname in zip(texts, filenames)]
    # 初始化模型
    model = Doc2Vec(vector_size=vector_size, window=5, min_count=2, workers=4, epochs=epochs)
    # 构建词汇表
    model.build_vocab(documents)
    print("开始训练...")
    model.train(documents, total_examples=model.corpus_count, epochs=model.epochs)
    # 保存模型
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    model.save(model_path)
    print(f"模型已保存至: {model_path}")

if __name__ == '__main__':
    print("正在加载文本文件...")
    texts, filenames = load_texts(TEXT_FOLDER)
    if not texts:
        print(f"未找到任何文本文件，请将 .txt 文件放入 {TEXT_FOLDER} 后重试。")
        sys.exit(1)
    print(f"共加载 {len(texts)} 个文件，开始训练 Doc2Vec 模型...")
    train_doc2vec(texts, filenames, MODEL_PATH)
    print("训练完成。")