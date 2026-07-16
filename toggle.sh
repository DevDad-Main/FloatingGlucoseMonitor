#!/bin/sh
# Toggle glucose monitor on/off for i3wm
PIDFILE="${TMPDIR:-/tmp}/glucose-monitor.pid"
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
    notify-send "Glucose Monitor" "Stopped" 2>/dev/null || true
else
    kitty --class glucose-monitor -e "$DIR/run.sh" &
    echo $! > "$PIDFILE"
fi
