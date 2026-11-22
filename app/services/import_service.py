# -*- coding: utf-8 -*-
"""CSV / Excel 导入基础服务。

- 支持 .csv（UTF-8 BOM / 普通 UTF-8 / GBK）、.xlsx、.xls；
- 表头以导出文件字段为准：允许列顺序不同，必须包含全部必需列，多余列忽略；
- 先解析并校验所有行，再由业务导入器在单事务中写库；
- 所有校验失败以 ImportValidationError 汇总返回，页面一次性展示。
"""
import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, List, Tuple

from werkzeug.datastructures import FileStorage

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}


class ImportValidationError(ValueError):
    """导入校验失败，errors 为可直接展示的中文提示列表。"""

    def __init__(self, errors: List[str]):
        super().__init__('；'.join(errors))
        self.errors = errors


@dataclass
class ImportResult:
    """导入结果统计。"""

    created: int = 0
    updated: int = 0
    skipped: int = 0

    def summary(self) -> str:
        return '新增 %d 行，更新 %d 行，跳过 %d 行' % (self.created, self.updated, self.skipped)


def clean(value) -> str:
    """统一转字符串并去除首尾空白。"""
    return '' if value is None else str(value).strip()


def _cell_text(value) -> str:
    """把 Excel/CSV 单元格转为导入所需的字符串。"""
    if value is None:
        return ''
    if isinstance(value, datetime):
        if value.hour or value.minute or value.second:
            return value.strftime('%Y-%m-%d %H:%M')
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_csv(raw: bytes) -> List[List[str]]:
    text = None
    for encoding in ('utf-8-sig', 'gbk'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ImportValidationError(['CSV 文件编码无法识别，请使用 UTF-8 或 GBK 保存'])
    return [[_cell_text(cell) for cell in row] for row in csv.reader(io.StringIO(text))]


def _read_xlsx(raw: bytes) -> List[List[str]]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportValidationError(['服务器缺少 openpyxl，无法解析 .xlsx'])
    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        sheet = book.worksheets[0]
        return [[_cell_text(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
    finally:
        book.close()


def _read_xls(raw: bytes) -> List[List[str]]:
    try:
        import xlrd
    except ImportError:
        raise ImportValidationError(['服务器缺少 xlrd，无法解析 .xls'])
    book = xlrd.open_workbook(file_contents=raw)
    sheet = book.sheet_by_index(0)
    rows = []
    for row_idx in range(sheet.nrows):
        row = []
        for col_idx in range(sheet.ncols):
            cell = sheet.cell(row_idx, col_idx)
            value = cell.value
            if cell.ctype == xlrd.XL_CELL_DATE:
                value = xlrd.xldate.xldate_as_datetime(value, book.datemode)
            row.append(_cell_text(value))
        rows.append(row)
    return rows


def read_table(file_storage: FileStorage, expected_headers: List[str],
               max_rows: int = None) -> List[Tuple[int, dict]]:
    """读取上传文件并校验表头。

    Returns:
        [(行号, {字段名: 值}), ...]，行号从 2 开始（第 1 行为表头）。
    """
    from flask import current_app

    if file_storage is None or not file_storage.filename:
        raise ImportValidationError(['请选择要导入的文件'])

    ext = '.' + file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in _ALLOWED_EXTENSIONS:
        raise ImportValidationError(['仅支持 CSV / XLSX / XLS 文件'])

    raw = file_storage.read()
    if not raw:
        raise ImportValidationError(['文件为空'])

    if ext == '.csv':
        table = _read_csv(raw)
    elif ext == '.xlsx':
        table = _read_xlsx(raw)
    else:
        table = _read_xls(raw)

    table = [row for row in table if any(clean(cell) for cell in row)]
    if not table:
        raise ImportValidationError(['文件只有表头，没有数据行'])

    headers = [clean(cell).lstrip('\ufeff') for cell in table[0]]
    seen = set()
    for header in headers:
        if header in seen:
            raise ImportValidationError(['表头「%s」重复' % header])
        seen.add(header)

    missing = [header for header in expected_headers if header not in seen]
    if missing:
        raise ImportValidationError(['缺少必需列：%s' % '、'.join(missing)])

    index = {header: headers.index(header) for header in expected_headers}
    rows = []
    for row_no, raw_row in enumerate(table[1:], start=2):
        values = {}
        for header in expected_headers:
            pos = index[header]
            values[header] = clean(raw_row[pos]) if pos < len(raw_row) else ''
        rows.append((row_no, values))

    if max_rows is None:
        max_rows = int(current_app.config.get('MAX_EXPORT_ROWS', 10000))
    if len(rows) > max_rows:
        raise ImportValidationError(['数据行数 %d 超过上限 %d' % (len(rows), max_rows)])
    return rows


def validate_rows(rows: List[Tuple[int, dict]], validator: Callable[[dict], dict]) -> List[dict]:
    """逐行校验；任一行失败则汇总所有错误并抛出。"""
    prepared = []
    errors = []
    for row_no, values in rows:
        try:
            item = validator(values)
            item['_row_no'] = row_no
            prepared.append(item)
        except ValueError as exc:
            errors.append('第 %d 行：%s' % (row_no, exc))
    if errors:
        raise ImportValidationError(errors)
    return prepared


def require(value, field: str) -> str:
    text = clean(value)
    if not text:
        raise ValueError('%s不能为空' % field)
    return text


def parse_int(value, field: str, default=None, min_value=None) -> int:
    text = clean(value)
    if not text:
        if default is not None:
            return default
        raise ValueError('%s不能为空' % field)
    try:
        number = int(text)
    except ValueError:
        raise ValueError('%s必须是整数' % field)
    if min_value is not None and number < min_value:
        raise ValueError('%s不能小于 %d' % (field, min_value))
    return number


def parse_date(value, field: str) -> date:
    text = require(value, field)
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError('%s格式不正确，应为 YYYY-MM-DD' % field)


def parse_datetime(value, field: str, allow_blank=True):
    text = clean(value)
    if not text:
        if allow_blank:
            return None
        raise ValueError('%s不能为空' % field)
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError('%s格式不正确，应为 YYYY-MM-DD HH:MM' % field)


def parse_choice(value, field: str, mapping: dict) -> object:
    text = require(value, field)
    if text not in mapping:
        raise ValueError('%s「%s」无效，可选：%s' % (field, text, ' / '.join(mapping.keys())))
    return mapping[text]


def validate_email(value, field: str = '邮箱') -> str:
    text = clean(value)
    if text and not _EMAIL_RE.match(text):
        raise ValueError('%s格式不正确' % field)
    return text
