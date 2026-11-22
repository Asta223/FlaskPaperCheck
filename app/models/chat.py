"""站内聊天模型：一对一消息。"""
from app import db
from app.models.mixins import SoftDeleteMixin
from app.utils.time_utils import now


class ChatMessage(SoftDeleteMixin, db.Model):
    """私聊消息：is_read 默认 False，接收方打开会话/轮询时标记已读。"""
    __tablename__ = 'chat_messages'
    __table_args__ = (
        db.Index('ix_chat_receiver_read', 'receiver_id', 'is_read'),
        db.Index('ix_chat_pair_time', 'sender_id', 'receiver_id', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='发送人')
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='接收人')
    content = db.Column(db.Text, nullable=False, comment='消息内容')
    is_read = db.Column(db.Boolean, nullable=False, default=False, comment='已读标记')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='发送时间')

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

    def to_dict(self) -> dict:
        """序列化为 JSON API 载荷。"""
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.display_name() if self.sender else '未知用户',
            'receiver_id': self.receiver_id,
            'content': self.content,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }

    def __repr__(self) -> str:
        return '<ChatMessage %s->%s>' % (self.sender_id, self.receiver_id)


class ConversationRead(db.Model):
    """会话已读位点（P1-14）：UNIQUE(user_id, peer_id) 持久化最后已读消息 id。

    未读计数按 id > last_read_message_id 精确计算，支持多设备/多标签（位点服务端持久化）。
    is_read 字段保留兼容 P0 数据语义。
    """
    __tablename__ = 'conversation_reads'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'peer_id', name='uq_conversation_read_user_peer'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='本端用户')
    peer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='对方用户')
    last_read_message_id = db.Column(db.Integer, nullable=False, default=0,
                                     comment='该 peer→user 的最后已读消息 id')
    is_hidden = db.Column(db.Boolean, nullable=False, default=False,
                          comment='是否从最近会话移除（消息保留，新消息到达后重现）')
    updated_at = db.Column(db.DateTime, nullable=False, default=now,
                           onupdate=now, comment='更新时间')

    user = db.relationship('User', foreign_keys=[user_id])
    peer = db.relationship('User', foreign_keys=[peer_id])

    def __repr__(self) -> str:
        return '<ConversationRead u=%s peer=%s id=%s>' % (
            self.user_id, self.peer_id, self.last_read_message_id)
