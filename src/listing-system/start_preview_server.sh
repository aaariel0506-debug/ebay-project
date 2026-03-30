#!/bin/bash
# eBay Listing 预审核页面服务器启动脚本
# 用法：./start_preview_server.sh [start|stop|restart|status]

SERVER_DIR="/Users/arielhe/.openclaw/workspace/scripts/ebay_automation/output"
PORT=8081
LOG_FILE="/tmp/preview_server.log"
PID_FILE="/tmp/preview_server.pid"

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  服务器已在运行 (PID: $PID)"
            return 1
        fi
    fi
    
    cd "$SERVER_DIR"
    nohup python3 -m http.server $PORT > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    sleep 2
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ 预审核页面已启动"
        echo ""
        echo "📋 访问链接："
        echo "  预发布预览：http://127.0.0.1:$PORT/hedgehog_tarot_preview.html"
        echo "  HTML 描述：http://127.0.0.1:$PORT/hedgehog_tarot_listing.html"
        echo ""
        echo "📝 日志文件：$LOG_FILE"
        echo "🛑 停止命令：./start_preview_server.sh stop"
        return 0
    else
        echo "❌ 启动失败，请查看日志：$LOG_FILE"
        return 1
    fi
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID
            rm -f "$PID_FILE"
            echo "✅ 服务器已停止 (PID: $PID)"
            return 0
        fi
    fi
    
    # 备用方案：pkill
    pkill -f "http.server $PORT" 2>/dev/null
    echo "✅ 服务器已停止"
    return 0
}

restart() {
    stop
    sleep 1
    start
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "✅ 服务器运行中 (PID: $PID)"
            echo "📋 访问链接：http://127.0.0.1:$PORT/"
            return 0
        fi
    fi
    
    if pgrep -f "http.server $PORT" > /dev/null 2>&1; then
        echo "✅ 服务器运行中"
        echo "📋 访问链接：http://127.0.0.1:$PORT/"
        return 0
    fi
    
    echo "❌ 服务器未运行"
    return 1
}

case "${1:-start}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    *)
        echo "用法：$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
