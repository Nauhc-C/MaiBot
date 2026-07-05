#!/bin/bash
# 启动 MaiBot 并实时显示日志中的 SeiyuuMatch 相关信息

echo "=========================================="
echo "启动 MaiBot 并监控 SeiyuuMatch 集成"
echo "=========================================="
echo ""
echo "请在另一个终端发送包含声优照片的消息进行测试"
echo ""
echo "启动 MaiBot..."
echo ""

cd "D:/Sakiko/project/MaiBot"

# 启动 MaiBot（后台运行）
uv run python -X utf8 bot.py &
MAIBOT_PID=$!

echo "MaiBot 已启动 (PID: $MAIBOT_PID)"
echo ""
echo "等待初始化..."
sleep 10

echo ""
echo "=========================================="
echo "实时监控日志中的 SeiyuuMatch 活动"
echo "=========================================="
echo ""

# 找到最新的日志文件并监控
LATEST_LOG=$(ls -t logs/app_*.log.jsonl 2>/dev/null | head -1)

if [ -n "$LATEST_LOG" ]; then
    echo "监控日志: $LATEST_LOG"
    echo ""

    # 实时监控日志，过滤 SeiyuuMatch 和图片识别相关内容
    tail -f "$LATEST_LOG" | grep --line-buffered -i "seiyuu\|图片.*描述\|image.*description" | while read line; do
        echo "[$(date '+%H:%M:%S')] $line"
    done
else
    echo "找不到日志文件"
fi

# 等待用户按 Ctrl+C
wait
