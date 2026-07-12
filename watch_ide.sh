#!/bin/bash
# Monitor WeChat IDE stderr for new mini-program errors
IDE_DIR="/mnt/c/Users/A/AppData/Local/微信开发者工具/User Data/44be4a7b66be378568c192f1bf90044a"
LAST_LINES=$(wc -l < "$IDE_DIR/WeappLog/stderr.log" 2>/dev/null || echo 0)
echo "Watching IDE logs (starting at line $LAST_LINES)..."
while true; do
    CURRENT=$(wc -l < "$IDE_DIR/WeappLog/stderr.log" 2>/dev/null || echo 0)
    if [ "$CURRENT" -gt "$LAST_LINES" ]; then
        # New lines added
        tail -n $((CURRENT - LAST_LINES)) "$IDE_DIR/WeappLog/stderr.log" | \
            grep -v "ActionRegistry\|DOMModel\|device_event\|USB" | \
            grep -i "error\|fail\|warn\|错误" || true
        LAST_LINES=$CURRENT
    fi
    sleep 2
done
