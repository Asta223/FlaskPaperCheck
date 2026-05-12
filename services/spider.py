import os
import sys
import requests
from bs4 import BeautifulSoup

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIR = os.path.join(BASE_DIR, 'data', 'processed_texts')

# arXiv 论文 ID 列表（可替换为其他公开论文）
ARXIV_IDS = [
    '2106.09685',  # LoRA: Low-Rank Adaptation of Large Language Models
    '2005.11401'   # RAG: Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
]

def fetch_arxiv_abstract(arxiv_id):
    """从 arXiv 抓取指定 ID 的论文标题和摘要，返回文本内容。"""
    url = f"https://arxiv.org/abs/{arxiv_id}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"抓取 arXiv:{arxiv_id} 失败: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    # 提取标题
    title_tag = soup.find('h1', class_='title')
    title = title_tag.text.replace('Title:', '').strip() if title_tag else 'No Title'
    # 提取摘要
    abstract_tag = soup.find('blockquote', class_='abstract')
    if abstract_tag:
        # 去除前面的 "Abstract:" 字样
        abstract = abstract_tag.text.replace('Abstract:', '', 1).strip()
    else:
        abstract = 'No Abstract'

    # 合并为文本
    content = f"Title: {title}\n\nAbstract:\n{abstract}"
    return content

def save_to_file(content, filename):
    """将内容保存为 txt 文件到目标目录。"""
    os.makedirs(TARGET_DIR, exist_ok=True)
    filepath = os.path.join(TARGET_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"已保存: {filepath}")

def main():
    print("开始抓取 arXiv 论文...")
    for idx, arxiv_id in enumerate(ARXIV_IDS, 1):
        print(f"正在处理第 {idx} 篇: arXiv:{arxiv_id}")
        content = fetch_arxiv_abstract(arxiv_id)
        if content:
            filename = f"arxiv_{arxiv_id}.txt"
            save_to_file(content, filename)
        else:
            print(f"跳过 arXiv:{arxiv_id}")
    print("抓取完成。")

if __name__ == '__main__':
    main()