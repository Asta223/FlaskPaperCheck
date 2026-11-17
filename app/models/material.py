"""物料模型：分类（自引用树）+ 物料档案。"""
from app import db


class MaterialCategory(db.Model):
    """物料分类：parent_id 自引用，可空为根分类。"""
    __tablename__ = 'material_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, comment='分类名称')
    parent_id = db.Column(db.Integer, db.ForeignKey('material_categories.id'), nullable=True,
                          comment='上级分类')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='停用=软删')

    parent = db.relationship('MaterialCategory', remote_side=[id], backref='children')

    def __repr__(self) -> str:
        return '<MaterialCategory %s>' % self.name


class Material(db.Model):
    """物料档案：编码唯一；与仓库库存（Inventory）关联查询。"""
    __tablename__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, comment='物料编码')
    name = db.Column(db.String(128), nullable=False, comment='物料名称')
    spec = db.Column(db.String(128), nullable=False, default='', comment='规格')
    unit = db.Column(db.String(16), nullable=False, default='个', comment='单位')
    storage_location = db.Column(db.String(128), nullable=False, default='',
                                 comment='存放位置（仓位/货位），如「原材料仓 A区-03排-2层」')
    category_id = db.Column(db.Integer, db.ForeignKey('material_categories.id'), nullable=True,
                            comment='分类，可空')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='停用=软删')

    category = db.relationship('MaterialCategory', backref='materials')

    def __repr__(self) -> str:
        return '<Material %s %s>' % (self.code, self.name)
