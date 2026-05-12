import os
from PyPDF2 import PdfReader
from docx import Document

def extract_text_from_pdf(filepath):
    reader = PdfReader(filepath)
    text = ''
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text
    return text

def extract_text_from_docx(filepath):
    doc = Document(filepath)
    return '\n'.join([para.text for para in doc.paragraphs])

def extract_text_from_txt(filepath, encoding='utf-8'):
    with open(filepath, 'r', encoding=encoding) as f:
        return f.read()

def extract_text(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        return extract_text_from_pdf(filepath)
    elif ext == '.docx':
        return extract_text_from_docx(filepath)
    elif ext == '.txt':
        return extract_text_from_txt(filepath)
    else:
        raise ValueError(f'不支持的文件格式: {ext}')