项目目录如下：
FlaskPaperCheck/
├── run.py                          # 应用启动入口
├── config.py                       # 全局配置（数据库、上传路径、模型路径等）
├── requirements.txt                # 项目依赖清单
├── README.txt                       # 项目说明文档
├── .gitignore                      # Git忽略文件
├── app/                             # Flask 主应用包（查重服务）
│   ├── __init__.py                  # 应用工厂，初始化扩展、注册蓝图
│   ├── models.py                     # 数据库模型（User, Paper, CheckRecord, AlgorithmConfig）
│   ├── forms.py                      # WTForms 表单（登录、注册、上传）
│   ├── utils/                        # 工具模块
│   │   ├── __init__.py
│   │   ├── file_parser.py             # 文件解析（PDF/DOCX/TXT → 纯文本）
│   │   ├── text_preprocess.py         # 文本预处理（分词、停用词、句子分割）
│   │   └── similarity.py               # 相似度算法集（TF-IDF, BERT文档级, BERT句子级, Doc2Vec等）
│   ├── routes/                        # 蓝图路由模块
│   │   ├── __init__.py                 # 导入各蓝图模块
│   │   ├── auth.py                      # 认证相关路由（登录、注册、注销、个人中心）
│   │   ├── main.py                      # 首页等公共路由
│   │   ├── paper.py                     # 论文上传、查重、结果、导出PDF
│   │   └── history.py                   # 历史记录查看
│   ├── templates/                      # Jinja2 模板
│   │   ├── base.html                    # 基础模板
│   │   ├── index.html                   # 首页
│   │   ├── login.html                   # 登录页
│   │   ├── register.html                 # 注册页
│   │   ├── profile.html                  # 个人资料页
│   │   ├── upload.html                   # 上传论文页
│   │   ├── result.html                   # 查重结果页（含相似文献列表和句子匹配）
│   │   ├── history.html                  # 历史记录页
│   │   └── report_pdf.html               # PDF报告专用模板
│   └── static/                          # 静态文件（CSS, JS, images等）
│       ├── css/
│       ├── js/
│       └── images/
├── services/                         # 独立服务脚本
│   ├── train_model.py                  # 模型训练脚本（定期从 processed_texts 读取文件训练 Doc2Vec）
│   ├── spider.py                       # 爬虫脚本（定时抓取论文，存入 raw_papers 并提取文本到 processed_texts）
│   └── __init__.py                     # 可为空，标记为包
├── data/                              # 数据存储目录
│   ├── raw_papers/                     # 爬虫下载的原始论文文件（PDF等）
│   ├── processed_texts/                 # 转换后的纯文本文件（.txt），供训练和查重语料库使用
│   └── uploads/                         # 用户上传的论文文件（由Flask配置 UPLOAD_FOLDER 指定）
└── models/                             # 训练好的模型文件存放目录
    └── doc2vec.model                     # Doc2Vec 模型（示例）

1、从app/models.py中修改对应的模型以映射数据库，执行：
flask db migrate -m "add 新增字段"
flask db upgrade
