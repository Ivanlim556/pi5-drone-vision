#!/bin/sh
# One line per boot: did the AR0234 answer, and did the stream start? (ad17 cold-boot test)
sleep 60
id=$(journalctl -k -b --no-pager | grep -o "Success reading chip id: 0x[0-9a-f]*\|failed to read chip id" | tail -1)
cam=$(ffprobe -v error -rtsp_transport tcp -select_streams v -show_entries stream=width,height -of csv=p=0 rtsp://127.0.0.1:8554/cam 2>&1 | head -1)
echo "$(date "+%F %T") up=$(cut -d. -f1 /proc/uptime)s chip=[${id:-none}] cam=[${cam:-none}] $(vcgencmd get_throttled)" >> /home/pi/bootcheck.log
