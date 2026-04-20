#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

app = Flask(__name__)

# ========== 从环境变量加载配置 ==========

# 用户密钥列表（支持多种格式）
SECRETS_STR = os.getenv("SECRETS", "")
ALLOWED_SECRETS = []

if SECRETS_STR:
    # 支持 "key1,key2,key3" 或 "key1, key2, key3" 或混用
    for part in SECRETS_STR.split(","):
        key = part.strip()
        if key:
            ALLOWED_SECRETS.append(key)

# ========== SMTP 默认配置（有默认值）==========
DEFAULT_SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.163.com")
DEFAULT_SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
DEFAULT_SMTP_USER = os.getenv("SMTP_USER", "")
DEFAULT_SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DEFAULT_SMTP_FROM = os.getenv("SMTP_FROM", "")

# ========== 收件人没有默认值，必须由客户端提供 ==========

# 管理员密钥（用于查看统计等）
ADMIN_KEY = os.getenv("ADMIN_KEY", "")

# ========== 辅助函数 ==========

def verify_auth(secret):
    """验证用户密钥"""
    return secret in ALLOWED_SECRETS

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
    if not verify_auth(secret):
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

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
