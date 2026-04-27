from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from passlib.hash import pbkdf2_sha256
from datetime import datetime, timedelta
import secrets

# 初始化数据库
db = SQLAlchemy()

class User(UserMixin, db.Model):
    """用户模型"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    api_keys = db.relationship('APIKey', backref='user', lazy=True)
    email_stats = db.relationship('EmailStat', backref='user', lazy=True)
    
    def set_password(self, password):
        """设置密码"""
        self.password_hash = pbkdf2_sha256.hash(password)
    
    def check_password(self, password):
        """验证密码"""
        return pbkdf2_sha256.verify(password, self.password_hash)

class APIKey(db.Model):
    """API Key模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    key = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=365))
    is_active = db.Column(db.Boolean, default=True)
    
    # 关系
    email_stats = db.relationship('EmailStat', backref='api_key', lazy=True)
    
    @staticmethod
    def generate_key():
        """生成API Key"""
        return secrets.token_urlsafe(32)

class EmailStat(db.Model):
    """邮件统计模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_key.id'), nullable=False)
    to_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # success 或 failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)