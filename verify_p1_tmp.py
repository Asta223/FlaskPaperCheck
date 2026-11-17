"""P1 验证（临时脚本，验证后删除）"""
import os
import io
import re

BASE = os.path.dirname(os.path.abspath(__file__))
DB = 'sqlite:///' + BASE.replace('\\', '/') + '/paper_check_test.db'
os.environ['DATABASE_URL'] = DB
os.environ['USE_REFERENCE_CORPUS'] = '1'

from app import create_app, db
from app.models import User, ReferencePaper, CheckRecord, Paper
from werkzeug.security import generate_password_hash

app = create_app()
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

with app.app_context():
    if not User.query.filter_by(username='verify').first():
        db.session.add(User(username='verify', email='v@e.com',
                            password_hash=generate_password_hash('pw')))
        db.session.commit()
    ref = ReferencePaper.query.filter_by(is_active=True).first()
    assert ref, '参考库为空，请先 seed'
    upload_text = ref.content_text  # 与参考库某篇完全相同

client = app.test_client()
r = client.post('/auth/login', data={'username': 'verify', 'password': 'pw'},
                follow_redirects=True)
print('[1] 登录:', r.status_code)

data = {'title': 'verify paper', 'algorithm': 'tfidf', 'threshold': '0.1',
        'file': (io.BytesIO(upload_text.encode('utf-8')), 'verify.txt')}
r = client.post('/paper/upload', data=data,
                content_type='multipart/form-data', follow_redirects=True)
html = r.get_data(as_text=True)
print('[2] 上传查重:', r.status_code)
print('[3] 含高亮区块(疑似相似片段):', '疑似相似片段' in html)
print('[4] 含全文高亮(标红):', 'bg-danger' in html)

with app.app_context():
    rec = CheckRecord.query.join(Paper).filter(Paper.user_id == User.query.filter_by(username='verify').first().id)\
        .order_by(CheckRecord.id.desc()).first()
    rid = rec.id
    d = rec.get_details()
    print('[5] highlights 数量:', len(d.get('highlights') or []))

for fmt in ('pdf', 'docx', 'html'):
    rr = client.get(f'/paper/export/{rid}?format={fmt}')
    body = rr.get_data()
    ok = rr.status_code == 200
    magic = body[:4] if body else b''
    if fmt == 'pdf':
        ok = ok and magic == b'%PDF'
    elif fmt == 'docx':
        ok = ok and magic == b'PK\x03\x04'
    elif fmt == 'html':
        ok = ok and b'\xe5\x81\x9c\xe4\xbc\xbc\xe7\x9b\xb8\xe4\xbc\xbc\xe7\x89\x87\xe6\xae\xb5'.startswith(b'') and ('疑似相似片段' in body.decode('utf-8', 'ignore'))
    print(f'[6] 导出 {fmt}:', 'OK' if ok else 'FAIL', '|', rr.headers.get('Content-Type'), '|', len(body), 'bytes')

print('P1 验证完成。')
