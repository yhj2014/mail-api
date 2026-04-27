#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
from dotenv import load_dotenv
from models import db, User, APIKey, EmailStat

# 加载 .env 文件
load_dotenv()

app = Flask(__name__)
# 配置密钥
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mail_api.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
db.init_app(app)

# 初始化登录管理器
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ========== 从环境变量加载配置 ==========

# SMTP 默认配置（有默认值）
DEFAULT_SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.163.com")
DEFAULT_SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
DEFAULT_SMTP_USER = os.getenv("SMTP_USER", "")
DEFAULT_SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DEFAULT_SMTP_FROM = os.getenv("SMTP_FROM", "")

# 管理员密钥（用于查看统计等）
ADMIN_KEY = os.getenv("ADMIN_KEY", "")

# ========== 辅助函数 ==========

@login_manager.user_loader
def load_user(user_id):
    """加载用户"""
    return User.query.get(int(user_id))

def admin_required(f):
    """管理员权限装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def verify_auth(secret):
    """验证用户密钥"""
    api_key = APIKey.query.filter_by(key=secret, is_active=True).first()
    return api_key is not None

def get_user_by_api_key(secret):
    """通过API Key获取用户"""
    api_key = APIKey.query.filter_by(key=secret, is_active=True).first()
    if api_key:
        return api_key.user
    return None

def send_email(smtp_server, smtp_port, smtp_user, smtp_password, smtp_from, to_email, subject, content, content_type="html"):
    """发送邮件"""
    try:
        if content_type == "html":
            msg = MIMEText(content, "html", "utf-8")
        else:
            msg = MIMEText(content, "plain", "utf-8")
        
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = Header(subject, "utf-8")
        
        # 发送邮件
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [to_email], msg.as_string())
        server.quit()
        
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)

# ========== API 路由 ==========

@app.route("/send", methods=["POST"])
def send_mail():
    """发送邮件接口"""
    
    # 1. 获取请求数据
    try:
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "Invalid JSON"}), 400
    except Exception as e:
        return jsonify({"code": 400, "message": str(e)}), 400
    
    # 2. 验证密钥
    secret = data.get("secret", "")
    api_key = APIKey.query.filter_by(key=secret, is_active=True).first()
    if not api_key:
        return jsonify({"code": 401, "message": "Invalid secret key"}), 401
    
    # 3. 获取收件人（必填，无默认值）
    to_email = data.get("to_email")
    if not to_email:
        return jsonify({"code": 400, "message": "Missing field: to_email"}), 400
    
    # 4. 获取邮件内容（必填）
    subject = data.get("subject")
    if not subject:
        return jsonify({"code": 400, "message": "Missing field: subject"}), 400
    
    content = data.get("content")
    if not content:
        return jsonify({"code": 400, "message": "Missing field: content"}), 400
    
    content_type = data.get("content_type", "html")
    
    # 5. 获取 SMTP 配置（优先使用客户端提供的，否则用默认）
    smtp_server = data.get("smtp_server") or DEFAULT_SMTP_SERVER
    smtp_port = data.get("smtp_port") or DEFAULT_SMTP_PORT
    smtp_user = data.get("smtp_user") or DEFAULT_SMTP_USER
    smtp_password = data.get("smtp_password") or DEFAULT_SMTP_PASSWORD
    smtp_from = data.get("smtp_from") or DEFAULT_SMTP_FROM
    
    # 6. 验证 SMTP 配置完整性
    if not smtp_user or not smtp_password or not smtp_from:
        return jsonify({
            "code": 400, 
            "message": "SMTP configuration incomplete. Please provide smtp_user, smtp_password, smtp_from or configure defaults."
        }), 400
    
    # 7. 发送邮件
    success, result = send_email(
        smtp_server, smtp_port, smtp_user, smtp_password, smtp_from,
        to_email, subject, content, content_type
    )
    
    # 8. 记录邮件发送状态
    email_stat = EmailStat(
        user_id=api_key.user_id,
        api_key_id=api_key.id,
        to_email=to_email,
        subject=subject,
        status="success" if success else "failed"
    )
    db.session.add(email_stat)
    db.session.commit()
    
    if success:
        return jsonify({"code": 200, "message": result})
    else:
        return jsonify({"code": 500, "message": result}), 500

@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({"code": 200, "status": "ok"})

@app.route("/info", methods=["GET"])
def info():
    """获取 API 信息（公开）"""
    return jsonify({
        "code": 200,
        "message": "Minecraft Server Mail API",
        "has_default_smtp": bool(DEFAULT_SMTP_USER and DEFAULT_SMTP_PASSWORD),
        "requires": {
            "secret": "your_secret_key",
            "to_email": "recipient@example.com",
            "subject": "email subject",
            "content": "email content"
        },
        "optional": {
            "smtp_server": "override default",
            "smtp_port": "override default",
            "smtp_user": "override default",
            "smtp_password": "override default",
            "smtp_from": "override default",
            "content_type": "html or plain (default: html)"
        }
    })

# ========== 用户认证路由 ==========

@app.route("/register", methods=["GET", "POST"])
def register():
    """用户注册"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 验证输入
        if not username or not email or not password:
            flash('请填写所有字段')
            return redirect(url_for('register'))
        
        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            flash('用户名已存在')
            return redirect(url_for('register'))
        
        # 检查邮箱是否已存在
        if User.query.filter_by(email=email).first():
            flash('邮箱已存在')
            return redirect(url_for('register'))
        
        # 创建新用户
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # 登录用户
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    """用户登录"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 验证输入
        if not username or not password:
            flash('请填写所有字段')
            return redirect(url_for('login'))
        
        # 查找用户
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('用户名或密码错误')
            return redirect(url_for('login'))
        
        # 登录用户
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route("/logout")
@login_required
def logout():
    """用户登出"""
    logout_user()
    return redirect(url_for('login'))

# ========== 控制面板路由 ==========

@app.route("/dashboard")
@login_required
def dashboard():
    """控制面板"""
    # 获取用户的邮件统计
    total_emails = EmailStat.query.filter_by(user_id=current_user.id).count()
    success_emails = EmailStat.query.filter_by(user_id=current_user.id, status="success").count()
    failed_emails = EmailStat.query.filter_by(user_id=current_user.id, status="failed").count()
    
    return render_template('dashboard.html', 
                          total_emails=total_emails, 
                          success_emails=success_emails, 
                          failed_emails=failed_emails)

# ========== API Key 管理路由 ==========

@app.route("/api_keys")
@login_required
def api_keys():
    """API Key 管理"""
    # 获取用户的API Key
    keys = APIKey.query.filter_by(user_id=current_user.id).all()
    return render_template('api_keys.html', keys=keys)

@app.route("/api_keys/create", methods=["POST"])
@login_required
def create_api_key():
    """创建API Key"""
    # 生成新的API Key
    key = APIKey.generate_key()
    # 确保密钥唯一
    while APIKey.query.filter_by(key=key).first():
        key = APIKey.generate_key()
    
    # 创建API Key
    api_key = APIKey(user_id=current_user.id, key=key)
    db.session.add(api_key)
    db.session.commit()
    
    flash('API Key 创建成功')
    return redirect(url_for('api_keys'))

@app.route("/api_keys/revoke/<int:key_id>")
@login_required
def revoke_api_key(key_id):
    """撤销API Key"""
    api_key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if api_key:
        api_key.is_active = False
        db.session.commit()
        flash('API Key 已撤销')
    else:
        flash('API Key 不存在')
    return redirect(url_for('api_keys'))

# ========== 邮件统计路由 ==========

@app.route("/email_stats")
@login_required
def email_stats():
    """邮件统计"""
    # 获取用户的邮件记录
    stats = EmailStat.query.filter_by(user_id=current_user.id).order_by(EmailStat.created_at.desc()).all()
    return render_template('email_stats.html', stats=stats)

# ========== 管理员路由 ==========

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """管理员控制面板"""
    # 系统统计
    total_users = User.query.count()
    total_api_keys = APIKey.query.count()
    total_emails = EmailStat.query.count()
    success_emails = EmailStat.query.filter_by(status="success").count()
    failed_emails = EmailStat.query.filter_by(status="failed").count()
    
    return render_template('admin/dashboard.html', 
                          total_users=total_users,
                          total_api_keys=total_api_keys,
                          total_emails=total_emails,
                          success_emails=success_emails,
                          failed_emails=failed_emails)

@app.route("/admin/users")
@admin_required
def admin_users():
    """用户管理"""
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route("/admin/users/delete/<int:user_id>")
@admin_required
def admin_delete_user(user_id):
    """删除用户"""
    user = User.query.get(user_id)
    if user and not user.is_admin:
        # 删除用户的API Key
        APIKey.query.filter_by(user_id=user_id).delete()
        # 删除用户的邮件统计
        EmailStat.query.filter_by(user_id=user_id).delete()
        # 删除用户
        db.session.delete(user)
        db.session.commit()
        flash('用户已删除')
    else:
        flash('无法删除用户')
    return redirect(url_for('admin_users'))

@app.route("/admin/users/toggle_admin/<int:user_id>")
@admin_required
def admin_toggle_admin(user_id):
    """切换用户管理员权限"""
    user = User.query.get(user_id)
    if user:
        user.is_admin = not user.is_admin
        db.session.commit()
        flash('用户权限已更新')
    else:
        flash('用户不存在')
    return redirect(url_for('admin_users'))

@app.route("/admin/email_stats")
@admin_required
def admin_email_stats():
    """系统邮件统计"""
    stats = EmailStat.query.order_by(EmailStat.created_at.desc()).all()
    return render_template('admin/email_stats.html', stats=stats)

if __name__ == "__main__":
    # 创建数据库表
    with app.app_context():
        db.create_all()
        
        # 创建默认管理员账户（如果不存在）
        admin_user = User.query.filter_by(username="admin").first()
        if not admin_user:
            admin_user = User(username="admin", email="admin@example.com", is_admin=True)
            admin_user.set_password("admin123")
            db.session.add(admin_user)
            db.session.commit()
            print("默认管理员账户已创建: 用户名=admin, 密码=admin123")
    
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
