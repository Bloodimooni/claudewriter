#!/usr/bin/env sh
# start-watcher.sh — Launch the thesis watcher in the background.
#
# Usage: ./scripts/start-watcher.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$SCRIPT_DIR/.watcher-state"
PID_FILE="$STATE_DIR/watcher.pid"
LOG_FILE="$STATE_DIR/watcher.log"
WATCHER="$SCRIPT_DIR/watcher.sh"

mkdir -p "$STATE_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    old_pid=$(cat "$PID_FILE")
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "Watcher is already running (PID $old_pid)."
        echo "Use ./scripts/stop-watcher.sh to stop it first."
        exit 1
    else
        echo "Stale PID file found. Cleaning up."
        rm -f "$PID_FILE"
    fi
fi

# Make scripts executable
chmod +x "$WATCHER"

# Launch in background, redirect output to log
nohup sh "$WATCHER" >> "$LOG_FILE" 2>&1 &
pid=$!
echo "$pid" > "$PID_FILE"

echo "Thesis watcher started (PID $pid)"
echo "Log: $LOG_FILE"
echo "Stop: ./scripts/stop-watcher.sh"
echo ""
echo "Write /claude:compile (or memory/check/qa/all) in a notes file and save to trigger."
