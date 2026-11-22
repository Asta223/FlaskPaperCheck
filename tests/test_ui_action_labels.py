# -*- coding: utf-8 -*-
"""前端文案一致性：所有“搜索/筛选”统一叫“查询”。"""
import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / 'app' / 'templates'

OLD_LABEL_RE = re.compile(r'搜索|筛选')
QUERY_ACTION_RE = re.compile(
    r'<button[^>]*>\s*(?:<i[^>]*></i>\s*)?查询\s*</button>'
)


def test_query_labels_are_consistent():
    offenders = []
    query_count = 0
    for path in TEMPLATES_DIR.rglob('*.html'):
        html = path.read_text(encoding='utf-8')
        for match in OLD_LABEL_RE.finditer(html):
            offenders.append('%s: %s' % (path.relative_to(TEMPLATES_DIR), match.group(0)))
        query_count += len(QUERY_ACTION_RE.findall(html))

    assert not offenders, '前端不应再出现“搜索/筛选”文案：%s' % offenders
    assert query_count >= 5, '未找到预期的查询按钮'
