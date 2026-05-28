#!/usr/bin/env bash
# ============================================================
# 🦞 Lobster Engine 控制腳本
# 使用: lobster-ctl.sh [start|stop|status|logs|once]
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOBSTER_PY="$SCRIPT_DIR/lobster.py"
LOG_FILE="/home/ubuntu/agent-data/logs/lobster.log"
PID_FILE="/tmp/lobster-engine.pid"

case "${1:-status}" in
  start)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
      echo "🦞 Lobster Engine 已經在運行 (PID: $(cat $PID_FILE))"
    else
      echo "🚀 啟動 Lobster Engine (持續迴圈模式)..."
      nohup python3 "$LOBSTER_PY" --loop --cool-down 60 > "$LOG_FILE" 2>&1 &
      echo $! > "$PID_FILE"
      echo "✅ 已啟動 PID: $(cat $PID_FILE)"
    fi
    ;;
  stop)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat $PID_FILE)
      kill "$PID" 2>/dev/null && echo "🛑 已停止 PID: $PID" || echo "⚠️ 進程不存在"
      rm -f "$PID_FILE"
    else
      echo "🦞 Lobster Engine 未運行"
    fi
    ;;
  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
      echo "🦞 Lobster Engine 運行中 (PID: $(cat $PID_FILE))"
      echo "最近日誌："
      tail -5 "$LOG_FILE" 2>/dev/null
    else
      echo "😴 Lobster Engine 未運行"
    fi
    ;;
  logs)
    tail -f "$LOG_FILE"
    ;;
  once)
    # 只執行一次（不循環）
    echo "🦞 執行單次任務掃描..."
    python3 "$LOBSTER_PY" ${2:+--project "$2"}
    ;;
  once-project)
    echo "🦞 執行單個專案任務: $2"
    python3 "$LOBSTER_PY" --project "$2"
    ;;
  *)
    echo "使用方法: $0 [start|stop|status|logs|once|once-project <專案名>]"
    echo ""
    echo "  start              啟動持續迴圈（背景執行）"
    echo "  stop               停止後台進程"
    echo "  status             查看運行狀態"
    echo "  logs               跟蹤日誌"
    echo "  once               執行一輪任務掃描（所有專案）"
    echo "  once-project 名稱  只執行指定專案的下一個任務"
    ;;
esac
