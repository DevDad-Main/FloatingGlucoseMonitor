#!/usr/bin/env bash
PIDFILE="/tmp/glucose-recording.pid"

if [ -f "$PIDFILE" ]; then
    pid=$(cat "$PIDFILE")
    kill "$pid" 2>/dev/null
    rm -f "$PIDFILE"
    notify-send -u normal "Recording" "Stopped"
else
    out="$HOME/Pictures/Screenshots/$(date +%Y-%m-%d_%H.%M.%S).mp4"
    slop -f "%x %y %w %h" > /tmp/slop-region.txt
    read -r x y w h < /tmp/slop-region.txt
    ffmpeg -f x11grab -s "${w}x${h}" -i ":0.0+$x,$y" -r 15 "$out" &
    pid=$!
    echo "$pid" > "$PIDFILE"
    notify-send -u low "Recording" "Started → $(basename "$out")"
fi
