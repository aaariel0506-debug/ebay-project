#!/usr/bin/env python3
"""
eBay Platform Notification 接收服务
极简版 — 接收通知 + 返回 200 + 记录日志

部署方式:
    1. 上传到 VPS
    2. pip install flask
    3. 运行: python3 notification_server.py
    4. 用 nginx 反代到 443 端口 (HTTPS)
    5. 把 https://你的域名/ebay/notifications 填入 eBay 开发者后台

生产部署建议用 gunicorn:
    gunicorn notification_server:app -b 0.0.0.0:5000 -w 2
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)

# 日志配置
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "notifications.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ebay_notify")


@app.route("/ebay/notifications", methods=["POST", "GET"])
def receive_notification():
    """
    接收 eBay 平台通知

    eBay 要求:
    - 在 3000ms 内返回 HTTP 200
    - 连续 1000 次失败会停止推送
    """
    # GET 请求 = eBay 健康检查 ping
    if request.method == "GET":
        logger.info("eBay health check ping received")
        return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()}), 200

    # POST 请求 = 实际通知
    try:
        # 尝试解析 JSON
        if request.content_type and "json" in request.content_type:
            data = request.get_json(silent=True) or {}
        else:
            # eBay 有时发送 XML
            data = {"raw_body": request.data.decode("utf-8", errors="replace")[:2000]}

        notification_type = data.get("NotificationEventName", data.get("topic", "unknown"))

        logger.info(f"收到通知 | 类型: {notification_type}")
        logger.info(f"  Headers: {dict(request.headers)}")
        logger.info(f"  Body: {json.dumps(data, ensure_ascii=False)[:500]}")

        # 保存通知到文件（方便后续分析）
        save_notification(notification_type, data)

    except Exception as e:
        logger.error(f"处理通知异常: {e}")

    # 无论如何都返回 200（eBay 只关心这个）
    return jsonify({"status": "received"}), 200


@app.route("/health", methods=["GET"])
def health_check():
    """本地健康检查"""
    return jsonify({
        "status": "healthy",
        "service": "ebay-notification-receiver",
        "timestamp": datetime.utcnow().isoformat(),
    }), 200


def save_notification(event_type, data):
    """保存通知到 JSON 文件"""
    notify_dir = LOG_DIR / "notifications"
    notify_dir.mkdir(exist_ok=True)

    filename = f"{datetime.utcnow():%Y%m%d_%H%M%S}_{event_type}.json"
    filepath = notify_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "received_at": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "data": data,
        }, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("eBay Notification Server 启动")
    logger.info("端口: 5000")
    logger.info("通知端点: /ebay/notifications")
    logger.info("健康检查: /health")
    logger.info("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
