"""查重报告导出工具：纯 Python 生成 PDF(通过 reportlab) 与 Word(通过 python-docx)，
不依赖 wkhtmltopdf 等外部二进制。"""
from io import BytesIO

# ---------------- PDF (reportlab) ----------------
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)

# 注册内置中文字体（无需外部字体文件）
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
CJK = 'STSong-Light'


def _src_label(source):
    return '参考库' if source == 'reference' else '已上传报告'


def build_pdf(record):
    d = record.get_details()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title='查重报告')
    styles = getSampleStyleSheet()
    body = ParagraphStyle('body', parent=styles['Normal'], fontName=CJK,
                          fontSize=10, leading=15)
    h1 = ParagraphStyle('h1', parent=styles['Title'], fontName=CJK, fontSize=18)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontName=CJK, fontSize=13)

    flow = [Paragraph('课程报告查重报告', h1)]
    flow.append(Paragraph(f'课程报告标题：{record.paper.title}', body))
    flow.append(Paragraph(f'查重时间：{record.check_time.strftime("%Y-%m-%d %H:%M")}', body))
    flow.append(Paragraph(f'查重算法：{record.algorithm}', body))
    flow.append(Paragraph(f'总体相似度：{record.similarity_score * 100:.2f}%', body))
    flow.append(Spacer(1, 0.3 * cm))

    # 相似文献列表
    flow.append(Paragraph('相似文献列表', h2))
    sims = d.get('similar_papers') or []
    if sims:
        data = [['来源', '文献标题', '相似度']]
        for it in sims:
            data.append([_src_label(it.get('source')), it['title'],
                         f"{it['score'] * 100:.2f}%"])
        t = Table(data, colWidths=[2.5 * cm, 10 * cm, 2.5 * cm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), CJK),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        flow.append(t)
    else:
        flow.append(Paragraph('未发现相似文献。', body))

    # 疑似相似片段
    hs = d.get('highlights') or []
    if hs:
        flow.append(Spacer(1, 0.3 * cm))
        flow.append(Paragraph(f'疑似相似片段（{len(hs)} 句）', h2))
        for h in hs:
            flow.append(Paragraph(
                f"【{_src_label(h.get('matched_source'))}】{h['matched_title']}"
                f"（相似度 {h['score'] * 100:.2f}%）", body))
            flow.append(Paragraph(f"本句：{h['sentence']}", body))
            flow.append(Paragraph(f"相似句：{h['matched']}", body))
            flow.append(Spacer(1, 0.15 * cm))

    doc.build(flow)
    return buf.getvalue()


# ---------------- Word (python-docx) ----------------
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn


def _set_cjk(run):
    run.font.name = '宋体'
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = rpr.makeelement(qn('w:rFonts'), {})
        rpr.append(rfonts)
    rfonts.set(qn('w:eastAsia'), '宋体')


def build_docx(record):
    d = record.get_details()
    doc = Document()
    # 默认正文字体（中文）
    normal = doc.styles['Normal']
    normal.font.name = '宋体'
    normal.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

    doc.add_heading('课程报告查重报告', level=0)

    def para(text, bold=False):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.bold = bold
        _set_cjk(r)
        return p

    para(f'课程报告标题：{record.paper.title}')
    para(f'查重时间：{record.check_time.strftime("%Y-%m-%d %H:%M")}')
    para(f'查重算法：{record.algorithm}')
    para(f'总体相似度：{record.similarity_score * 100:.2f}%')

    doc.add_heading('相似文献列表', level=1)
    sims = d.get('similar_papers') or []
    if sims:
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Light Grid Accent 1'
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text = '来源', '文献标题', '相似度'
        for c in hdr:
            _set_cjk(c.paragraphs[0].runs[0])
        for it in sims:
            row = table.add_row().cells
            row[0].text = _src_label(it.get('source'))
            row[1].text = it['title']
            row[2].text = f"{it['score'] * 100:.2f}%"
            for c in row:
                if c.paragraphs[0].runs:
                    _set_cjk(c.paragraphs[0].runs[0])
    else:
        para('未发现相似文献。')

    hs = d.get('highlights') or []
    if hs:
        doc.add_heading(f'疑似相似片段（{len(hs)} 句）', level=1)
        for h in hs:
            para(f"【{_src_label(h.get('matched_source'))}】{h['matched_title']}"
                 f"（相似度 {h['score'] * 100:.2f}%）")
            p = doc.add_paragraph()
            r = p.add_run('本句：'); r.bold = True; _set_cjk(r)
            r = p.add_run(h['sentence']); _set_cjk(r)
            p = doc.add_paragraph()
            r = p.add_run('相似句：'); r.bold = True; _set_cjk(r)
            r = p.add_run(h['matched']); _set_cjk(r)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
