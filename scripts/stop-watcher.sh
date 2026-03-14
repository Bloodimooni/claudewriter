#!/usr/bin/env sh
# stop-watcher.sh — Stop the background thesis watcher.
#
# Usage: ./scripts/stop-watcher.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$SCRIPT_DIR/.watcher-state"
PID_FILE="$STATE_DIR/watcher.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "No watcher PID file found. Is the watcher running?"
    exit 0
fi

pid=$(cat "$PID_FILE")

if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    rm -f "$PID_FILE"
    echo "Thesis watcher stopped (was PID $pid)."
else
    echo "Process $pid is not running. Cleaning up stale PID file."
    rm -f "$PID_FILE"
fi
