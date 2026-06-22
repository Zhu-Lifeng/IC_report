#!/usr/bin/env python3
"""
GitHub Webhook 接收器 —— 收到 main 分支 push 后自动部署。

监听 0.0.0.0:9000，校验 GitHub 的 HMAC-SHA256 签名后运行同目录的 deploy.sh。
共享密钥从环境变量 WEBHOOK_SECRET 读取（由 systemd 的 EnvironmentFile 注入），
必须与 GitHub 仓库 Webhook 设置里的 Secret 完全一致。
"""
import hmac, hashlib, os, subprocess
from flask import Flask, request, abort

app = Flask(__name__)

SECRET = os.environ.get("WEBHOOK_SECRET", "").encode()
DEPLOY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deploy.sh")
BRANCH = "refs/heads/main"


def verify(req) -> bool:
    """校验 GitHub 的 X-Hub-Signature-256 签名。"""
    if not SECRET:
        return False
    sig = req.headers.get("X-Hub-Signature-256", "")
    if not sig.startswith("sha256="):
        return False
    mac = hmac.new(SECRET, req.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + mac, sig)


@app.route("/deploy", methods=["POST"])
def deploy():
    if not verify(request):
        abort(401)
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":            # GitHub 创建 webhook 时发的测试请求
        return "pong", 200
    if event != "push":
        return "ignored (not a push)", 200
    payload = request.get_json(silent=True) or {}
    if payload.get("ref") != BRANCH:
        return f"ignored (ref={payload.get('ref')})", 200
    # 后台异步执行部署，立刻返回，避免 GitHub 请求超时
    subprocess.Popen(["bash", DEPLOY])
    return "deploying", 202


@app.route("/health")
def health():
    return "ok", 200
