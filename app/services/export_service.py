"""通用 CSV 导出服务（P1-16）。

- UTF-8 BOM（Excel 中文不乱码），文件名含导出日期；
- 字段白名单由调用方显式声明（禁含 password_hash）；手机号/邮箱原值导出（A1）；
- 单次上限 MAX_EXPORT_ROWS，超出抛 ExportLimitError；
- 导出行为由调用方成功后 log_operation(action='export') 留痕（本服务不触碰权限与日志，
  保持纯函数式、便于复用各列表 base_query 的结果）。
"""
import csv
import io
from datetime import datetime

from flask import Response, current_app, flash, redirect, url_for

from app.utils.time_utils import now


class ExportLimitError(ValueError):
    """导出行数超过上限。"""

    def __init__(self, limit: int):
        super().__init__('导出行数超过上限 %d' % limit)
        self.limit = limit


def export_csv(headers, rows, filename_prefix: str) -> Response:
    """生成 CSV 下载响应（含 UTF-8 BOM）。

    Args:
        headers: 字段名列表（白名单，调用方声明）。
        rows: 二维数据行。
        filename_prefix: 文件名前缀。

    Returns:
        Flask Response（text/csv; charset=utf-8，带 BOM）。
    """
    limit = int(current_app.config.get('MAX_EXPORT_ROWS', 10000))
    if len(rows) > limit:
        raise ExportLimitError(limit)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(['' if cell is None else cell for cell in row])

    content = '\ufeff' + buffer.getvalue()  # UTF-8 BOM
    date_str = now().strftime('%Y%m%d')
    filename = '%s_%s.csv' % (filename_prefix, date_str)
    return Response(
        content,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="%s"' % filename},
    )


def guard_export_or_redirect(rows, back_endpoint: str, **back_kwargs):
    """导出守卫：超过上限则 flash 并重定向回列表页，否则返回 None 继续导出。"""
    limit = int(current_app.config.get('MAX_EXPORT_ROWS', 10000))
    if len(rows) > limit:
        flash('导出数据量超过 %d 行，请缩小筛选范围' % limit, 'warning')
        return redirect(url_for(back_endpoint, **back_kwargs))
    return None
