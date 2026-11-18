"""文件在线预览服务：按扩展名分派到内联二进制或结构化内容预览。

设计口径（小型工厂内网文档库）：
- 图片/PDF 直接内联原始字节流，浏览器原生渲染，保真度最高；
- txt/md/csv 解析文本（自动识别 UTF-8 BOM/UTF-8/GB18030），csv 渲染成表格；
- docx/xlsx 提取段落、表格、工作表内容做「内容级预览」——保留文字、标题层级、
  加粗/斜体与表格结构，但不做 WYSIWYG 排版（复杂版式/批注/宏/图片不在预览范围）；
- .xlsx 用 openpyxl、旧版 .xls 用 xlrd 解析；.doc/.ppt 无可靠纯 Python 解析器，明确提示下载查看；
- 所有解析均有大小/行列/块数上限，解析异常只影响预览页，绝不影响下载原文件。

服务只产出字典数据，HTML 渲染交给 Jinja2 模板自动转义，杜绝文档内容注入。
"""
import codecs
import csv
import io
import os
from datetime import date, datetime

from flask import current_app

# 扩展名 → 预览类型。image/pdf 走 preview_file 原始字节流；其余走本服务解析。
PREVIEW_KINDS = {
    '.pdf': 'pdf',
    '.png': 'image', '.jpg': 'image', '.jpeg': 'image',
    '.gif': 'image', '.bmp': 'image', '.webp': 'image',
    '.txt': 'text', '.md': 'text', '.csv': 'csv',
    '.docx': 'docx', '.xlsx': 'xlsx', '.xls': 'xlsx',
}

# 旧版 Office 二进制格式：上传允许、下载正常，但不提供内容级预览。
UNSUPPORTED_OFFICE = {'.doc', '.ppt'}


def preview_kind(ext: str) -> str:
    """返回预览类型；不可预览返回 'unsupported'。"""
    return PREVIEW_KINDS.get((ext or '').lower(), 'unsupported')


def is_previewable(ext: str) -> bool:
    """列表页是否展示预览按钮。"""
    return preview_kind(ext) != 'unsupported'


def _limits():
    cfg = current_app.config
    return (
        cfg.get('PREVIEW_TEXT_MAX_BYTES', 2 * 1024 * 1024),
        cfg.get('PREVIEW_MAX_ROWS', 200),
        cfg.get('PREVIEW_MAX_COLS', 30),
        cfg.get('PREVIEW_MAX_SHEETS', 20),
        cfg.get('PREVIEW_DOCX_MAX_BLOCKS', 300),
    )


def _decode_text(raw: bytes) -> str:
    """文本解码：BOM 优先，其次 UTF-8，再 GB18030（兼容 GBK），最后容错解码。"""
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode('utf-8-sig', errors='replace')
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode('utf-16', errors='replace')
    for encoding in ('utf-8', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _preview_text(path: str) -> dict:
    max_bytes, _, _, _, _ = _limits()
    with open(path, 'rb') as fh:
        raw = fh.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    return {'kind': 'text', 'text': _decode_text(raw),
            'truncated': truncated, 'max_bytes': max_bytes}


def _preview_csv(path: str) -> dict:
    max_bytes, max_rows, max_cols, _, _ = _limits()
    with open(path, 'rb') as fh:
        raw = fh.read(max_bytes + 1)
    byte_truncated = len(raw) > max_bytes
    if byte_truncated:
        raw = raw[:max_bytes]
    text = _decode_text(raw)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel  # 探测失败按逗号分隔处理
    rows = []
    row_truncated = False
    for index, row in enumerate(csv.reader(io.StringIO(text, newline=''), dialect)):
        if index >= max_rows:
            row_truncated = True
            break
        cells = [cell[:500] for cell in row[:max_cols]]
        if len(row) > max_cols:
            row_truncated = True
        rows.append(cells)
    return {
        'kind': 'csv', 'rows': rows,
        'truncated': byte_truncated or row_truncated,
        'max_rows': max_rows, 'max_cols': max_cols,
    }


def _run_bold(run) -> bool:
    """run.bold 可能为 None（继承），只有显式 True 才加粗。"""
    return run.bold is True


def _docx_blocks(doc) -> list:
    """按文档顺序抽取段落与表格，保留标题层级和显式加粗/斜体。"""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    _, _, max_cols, _, max_blocks = _limits()
    blocks = []
    children = list(doc.element.body.iterchildren())
    for child in children:
        if len(blocks) >= max_blocks:
            break
        if child.tag == qn('w:p'):
            paragraph = Paragraph(child, doc)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name if paragraph.style else '') or ''
            style_l = style.lower().strip()
            if style_l in ('heading 1', '标题 1', 'title', '标题'):
                level = 1
            elif style_l in ('heading 2', '标题 2', 'subtitle', '副标题'):
                level = 2
            elif style_l in ('heading 3', '标题 3'):
                level = 3
            elif style_l.startswith(('heading', '标题')):
                level = 4
            else:
                level = 0
            spans = [{'text': run.text, 'bold': _run_bold(run),
                      'italic': run.italic is True}
                     for run in paragraph.runs if run.text]
            if not spans:
                spans = [{'text': text, 'bold': False, 'italic': False}]
            if 'list' in style_l:
                kind = 'list'
            elif level:
                kind = 'heading'
            else:
                kind = 'paragraph'
            blocks.append({'kind': kind, 'level': level, 'spans': spans[:200]})
        elif child.tag == qn('w:tbl'):
            table = Table(child, doc)
            table_rows = []
            for row in table.rows[:200]:
                table_rows.append([cell.text[:500] for cell in row.cells[:max_cols]])
            if table_rows:
                blocks.append({'kind': 'table', 'rows': table_rows})
    return {
        'kind': 'docx', 'blocks': blocks,
        'truncated': len(children) > max_blocks,
        'max_blocks': max_blocks,
    }


def _format_cell(value) -> str:
    """Excel 单元格值转展示字符串。"""
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, float):
        return ('%.6f' % value).rstrip('0').rstrip('.')
    return str(value)[:500]


def _preview_xlsx(path: str) -> dict:
    from openpyxl import load_workbook

    _, max_rows, max_cols, max_sheets, _ = _limits()
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheets = []
    try:
        for worksheet in list(workbook.worksheets)[:max_sheets]:
            rows = []
            for row in worksheet.iter_rows(max_row=max_rows + 1,
                                           max_col=max_cols, values_only=True):
                rows.append([_format_cell(value) for value in row])
            sheet_truncated = len(rows) > max_rows
            if sheet_truncated:
                rows = rows[:max_rows]
            sheets.append({
                'name': worksheet.title, 'rows': rows, 'truncated': sheet_truncated,
            })
        sheet_truncated = len(workbook.worksheets) > max_sheets
    finally:
        workbook.close()
    return {
        'kind': 'xlsx', 'sheets': sheets,
        'truncated': sheet_truncated or any(s['truncated'] for s in sheets),
        'max_rows': max_rows, 'max_cols': max_cols, 'max_sheets': max_sheets,
    }


def _preview_xls(path: str) -> dict:
    """旧版 .xls（BIFF）：xlrd 解析，输出与 _preview_xlsx 相同的结构。"""
    import xlrd

    _, max_rows, max_cols, max_sheets, _ = _limits()
    workbook = xlrd.open_workbook(path, on_demand=True)
    try:
        worksheets = workbook.sheets()
        sheets = []
        for worksheet in worksheets[:max_sheets]:
            rows = []
            row_count = min(worksheet.nrows, max_rows + 1)
            col_count = min(worksheet.ncols, max_cols)
            for row_idx in range(row_count):
                cells = []
                for col_idx in range(col_count):
                    value = worksheet.cell_value(row_idx, col_idx)
                    if worksheet.cell_type(row_idx, col_idx) == xlrd.XL_CELL_DATE:
                        value = xlrd.xldate_as_datetime(value, workbook.datemode)
                    cells.append(_format_cell(value))
                rows.append(cells)
            sheet_truncated = worksheet.nrows > max_rows or worksheet.ncols > max_cols
            if sheet_truncated:
                rows = rows[:max_rows]
            sheets.append({'name': worksheet.name, 'rows': rows,
                           'truncated': sheet_truncated})
        sheet_truncated = len(worksheets) > max_sheets
    finally:
        workbook.release_resources()
    return {
        'kind': 'xlsx', 'sheets': sheets,
        'truncated': sheet_truncated or any(s['truncated'] for s in sheets),
        'max_rows': max_rows, 'max_cols': max_cols, 'max_sheets': max_sheets,
    }


LEGACY_HINT = ('旧版二进制格式暂不支持在线预览，请下载后用 Office/WPS 打开，'
               '或另存为 .docx/.xlsx 后重新上传即可在线预览。')


def build_preview(file_rec, path: str) -> dict:
    """构建预览上下文；只返回可安全渲染的字典，失败时返回 error 状态。"""
    ext = (file_rec.file_ext or '').lower()
    kind = preview_kind(ext)
    if kind in ('image', 'pdf'):
        return {'kind': kind}
    if not os.path.exists(path):
        return {'kind': 'error', 'message': '文件已丢失，请联系管理员'}
    if kind == 'unsupported':
        return {'kind': 'unsupported', 'message': LEGACY_HINT}
    try:
        if kind == 'text':
            result = _preview_text(path)
        elif kind == 'csv':
            result = _preview_csv(path)
        elif kind == 'docx':
            from docx import Document
            result = _docx_blocks(Document(path))
        elif kind == 'xlsx':
            result = _preview_xls(path) if ext == '.xls' else _preview_xlsx(path)
        else:
            result = {'kind': 'unsupported', 'message': LEGACY_HINT}
    except Exception as exc:  # 损坏/加密/不合法文档不应影响下载与列表
        current_app.logger.warning('文件预览失败 file_id=%s ext=%s: %s',
                                   file_rec.id, ext, exc)
        return {
            'kind': 'error',
            'message': '文件解析失败（可能已损坏或加密），请下载原文件查看',
        }
    result.setdefault('truncated', False)
    return result
