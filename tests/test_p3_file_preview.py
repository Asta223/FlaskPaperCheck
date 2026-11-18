# -*- coding: utf-8 -*-
"""P3 文件在线预览：txt/csv/docx/xlsx 内容级预览、编码兼容、上限与越权边界。"""
import io

from conftest import get_csrf, login

from app import db
from app.models import Department, FactoryFile


def _upload_bytes(client, filename, payload, visibility='all', depts=None):
    """走真实上传表单落库，返回文件记录。"""
    token = get_csrf(client, '/files/upload')
    data = {
        'csrf_token': token,
        'category_id': 0,
        'file': (io.BytesIO(payload), filename),
        'visibility_type': visibility,
    }
    if depts:
        data['department_ids'] = [str(d.id) for d in depts]
    resp = client.post('/files/upload', data=data, follow_redirects=True)
    assert resp.status_code == 200
    return FactoryFile.query.filter_by(original_filename=filename).first()


def _make_docx():
    from docx import Document
    doc = Document()
    doc.add_heading('生产通知', level=1)
    para = doc.add_paragraph()
    para.add_run('请于明日').bold = True
    para.add_run('完成设备检修')
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = '工序'
    table.cell(0, 1).text = '工时'
    table.cell(1, 0).text = '装配'
    table.cell(1, 1).text = '3.5'
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = '库存'
    ws.append(['物料', '数量'])
    ws.append(['螺丝', 120])
    ws2 = wb.create_sheet('明细')
    ws2.append(['工序', '工时'])
    ws2.append(['装配', 3.5])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_text_preview_and_html_escaping(client):
    """UTF-8 文本正常显示；文件内容按文本转义，不注入 HTML。"""
    login(client, 'admin', 'admin123')
    payload = '今日排班\n<script>alert(1)</script>'.encode('utf-8')
    f = _upload_bytes(client, 'shift.txt', payload)
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert '今日排班' in body
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in body
    assert '<script>alert(1)</script>' not in body


def test_gbk_text_preview(client):
    """GBK 编码的中文文本自动识别，不乱码。"""
    login(client, 'admin', 'admin123')
    f = _upload_bytes(client, 'gbk.txt', '中文GBK内容'.encode('gbk'))
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    assert '中文GBK内容'.encode() in resp.data


def test_csv_preview_renders_table(client):
    """分号分隔的 CSV 自动识别并按表格展示。"""
    login(client, 'admin', 'admin123')
    payload = '名称;数量\n螺丝;100\n螺母;50\n'.encode('utf-8')
    f = _upload_bytes(client, 'stock.csv', payload)
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert '<table' in body and '螺丝' in body and '100' in body and '螺母' in body
    assert 'CSV 预览' in body


def test_docx_preview_shows_heading_bold_and_table(client):
    """Word 内容预览保留标题、加粗文字与表格。"""
    login(client, 'admin', 'admin123')
    f = _upload_bytes(client, 'notice.docx', _make_docx())
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert '生产通知' in body
    assert '<strong>请于明日</strong>' in body
    assert '完成设备检修' in body
    assert '装配' in body and '3.5' in body
    listing = client.get('/files/').data.decode('utf-8')
    assert '/files/%d/preview' % f.id in listing


def test_xlsx_preview_shows_all_sheets(client):
    """Excel 内容预览展示多工作表及单元格值。"""
    login(client, 'admin', 'admin123')
    f = _upload_bytes(client, 'inventory.xlsx', _make_xlsx())
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert '库存' in body and '明细' in body
    assert '螺丝' in body and '120' in body and '装配' in body and '3.5' in body


def _make_xls():
    import xlwt
    wb = xlwt.Workbook()
    ws = wb.add_sheet('旧版库存')
    ws.write(0, 0, '物料')
    ws.write(0, 1, '数量')
    ws.write(1, 0, 'E2E螺丝')
    ws.write(1, 1, 77)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_legacy_xls_preview(client):
    """旧版 .xls 同样支持内容预览。"""
    login(client, 'admin', 'admin123')
    f = _upload_bytes(client, 'legacy.xls', _make_xls())
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert '旧版库存' in body and 'E2E螺丝' in body and '77' in body


def test_legacy_office_shows_hint_and_other_files_redirect(client):
    """旧版 .doc 给出改造提示；压缩包等非文档格式仍跳下载。"""
    login(client, 'admin', 'admin123')
    legacy = _upload_bytes(client, 'old.doc', b'\xd0\xcf\x11\xe0OLD-DOC')
    resp = client.get('/files/%d/preview' % legacy.id)
    assert resp.status_code == 200
    assert '旧版二进制格式'.encode() in resp.data
    other = _upload_bytes(client, 'bundle.zip', b'PK\x03\x04')
    resp = client.get('/files/%d/preview' % other.id)
    assert resp.status_code == 302
    assert '/download' in resp.headers.get('Location', '')


def test_corrupted_document_preview_degrades_gracefully(client):
    """损坏的 docx/xlsx 返回友好提示，下载原文件仍可用。"""
    login(client, 'admin', 'admin123')
    f = _upload_bytes(client, 'broken.docx', b'not-a-real-docx')
    resp = client.get('/files/%d/preview' % f.id)
    assert resp.status_code == 200
    assert '文件解析失败'.encode() in resp.data
    download = client.get('/files/%d/download' % f.id)
    assert download.status_code == 200
    assert 'attachment' in download.headers.get('Content-Disposition', '')


def test_text_preview_respects_permission_and_size_limit(client, app_ctx, monkeypatch):
    """越权预览 403；超长文本截断提示；原始字节端点不服务文本。"""
    prod = Department.query.filter_by(name='生产部').first()
    login(client, 'arch1', '123456')
    f = _upload_bytes(client, 'scoped.txt', '生产部内部资料'.encode('utf-8'),
                      visibility='departments', depts=[prod])

    login(client, 'keeper1', '123456')
    assert client.get('/files/%d/preview' % f.id).status_code == 403
    assert client.get('/files/%d/preview_file' % f.id).status_code == 403

    login(client, 'admin', 'admin123')
    assert client.get('/files/%d/preview' % f.id).status_code == 200
    monkeypatch.setitem(app_ctx.config, 'PREVIEW_TEXT_MAX_BYTES', 8)
    big = _upload_bytes(client, 'big.txt', ('行数' * 100).encode('utf-8'))
    resp = client.get('/files/%d/preview' % big.id)
    assert resp.status_code == 200
    assert '内容过长'.encode() in resp.data
    assert client.get('/files/%d/preview_file' % big.id).status_code == 302
