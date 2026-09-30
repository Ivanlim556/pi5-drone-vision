#!/bin/bash
# Run on the Pi: ./start-stream.sh [laptop-ip]
# No IP given -> uses the IP of the laptop you are SSH'd in from.
IP=${1:-${SSH_CLIENT%% *}}
[ -z "$IP" ] && { echo "usage: $0 <laptop-ip>"; exit 1; }
# viewer listens on IPv4 only; hotspots hand out IPv6 too
[[ $IP == *:* ]] && { echo "Got IPv6 ($IP). SSH in with: ssh -4 pi@pi5drone.local  (or pass the laptop IPv4)"; exit 1; }
pkill -x rpicam-vid; sleep 1
# HDMI preview too, if the Pi desktop is running
export WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u)
setsid nohup rpicam-vid -t 0 --fullscreen --inline --intra 15 --low-latency \
  --bitrate 3000000 --width 1280 --height 720 --framerate 30 --rotation 180 \
  --autofocus-mode manual --lens-position 0 \
  -o udp://$IP:5600 > /tmp/stream.log 2>&1 < /dev/null &
sleep 3
pgrep -x rpicam-vid > /dev/null && echo "Streaming to $IP:5600" || { echo "Failed:"; tail -5 /tmp/stream.log; }
