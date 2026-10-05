"""Laptop stand-in for the flight controller: receives the Pi's MAVLink obstacle reports and shows
what ArduPilot would get -- a radar of the forward view plus the Pi's alerts.

Run:   .\fc_view.ps1                              connects to the Pi (pi5drone, UDP 14550)
       .\fc_view.ps1 --target udpin:0.0.0.0:14550 listen instead (for mavlink_out.py's self-test)
Check: .\fc_view.ps1 --test 5 --target udpin:0.0.0.0:14550   (no window; prints what arrived)

udpout to the Pi = the laptop speaks first (a GCS heartbeat each second) and the Pi answers the
same address, so no Windows firewall rule is needed. Mission Planner can connect the same way.
"""
import argparse
import math
import os
import time

import cv2
import numpy as np

os.environ.setdefault("MAVLINK20", "1")  # OBSTACLE_DISTANCE is a MAVLink 2 message
from pymavlink import mavutil  # noqa: E402

mavutil.set_dialect("ardupilotmega")

W, H, R_PX, MAX_M = 720, 560, 420, 4.0


def colour(d):
    t = min(d / 2.0, 1.0)  # 0 m red -> 2 m and beyond green, same scale as the /detect grid
    return (0, int(255 * t), int(255 * (1 - t)))


def radar(sect, alerts, rate, hb_age):
    img = np.full((H, W, 3), 24, np.uint8)
    cx, cy = W // 2, H - 110
    for r_m in (1, 2, 3, 4):  # range rings
        cv2.ellipse(img, (cx, cy), (int(R_PX * r_m / MAX_M),) * 2, 0, 180, 360, (70, 70, 70), 1)
        cv2.putText(img, f"{r_m * 100} cm", (cx + 4, cy - int(R_PX * r_m / MAX_M) + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
    for a0, a1, d in sect:  # angles in degrees, 0 = straight ahead, + = right
        if d is None:
            continue
        r = int(R_PX * min(d, MAX_M) / MAX_M)
        # cv2 angles: 0 = +x, clockwise; forward (up) = -90
        cv2.ellipse(img, (cx, cy), (r, r), 0, -90 + a0, -90 + a1, colour(d), -1)
        mid = math.radians(-90 + (a0 + a1) / 2)
        cv2.putText(img, f"{d * 100:.0f}", (int(cx + (r + 14) * math.cos(mid)) - 12, int(cy + (r + 14) * math.sin(mid))),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)
    cv2.circle(img, (cx, cy), 8, (255, 200, 0), -1)
    cv2.putText(img, "drone", (cx - 22, cy + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)
    hb = f"heartbeat {hb_age:.1f}s ago" if hb_age is not None else "no heartbeat yet"
    cv2.putText(img, f"Pi -> FC  OBSTACLE_DISTANCE {rate:4.1f} Hz   {hb}", (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 255, 255) if hb_age is not None and hb_age < 3 else (0, 0, 255), 1)
    for i, (t, s) in enumerate(alerts[-4:]):
        cv2.putText(img, f"[{t}] {s}", (12, H - 70 + i * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 160, 255), 1)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="udpout:pi5drone:14550")
    ap.add_argument("--test", type=float, default=0, metavar="S", help="no window: listen S seconds, print a summary")
    ap.add_argument("--save", metavar="PNG", help="with --test: also write the radar picture to this file")
    a = ap.parse_args()

    m = mavutil.mavlink_connection(a.target, source_system=255, source_component=mavutil.mavlink.MAV_COMP_ID_MISSIONPLANNER)
    sect, alerts, times = [], [], []
    t_hb_sent, t_hb_got, t0 = 0.0, None, time.time()
    while True:
        now = time.time()
        if now - t_hb_sent >= 1:  # speak first, so the Pi learns where to send
            m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            t_hb_sent = now
        msg = m.recv_match(blocking=True, timeout=0.05)
        if msg is not None:
            typ = msg.get_type()
            if typ == "HEARTBEAT":
                t_hb_got = now
            elif typ == "OBSTACLE_DISTANCE":
                times = [t for t in times if now - t < 2] + [now]
                inc, off = msg.increment_f or msg.increment, msg.angle_offset
                sect = []
                for i, cm in enumerate(msg.distances):
                    if cm == 65535:  # UNKNOWN: no information for that direction
                        continue
                    d = None if cm > msg.max_distance else cm / 100
                    sect.append((off + (i - 0.5) * inc, off + (i + 0.5) * inc, d))
            elif typ == "STATUSTEXT":
                alerts.append((time.strftime("%H:%M:%S"), msg.text))
        rate = len(times) / 2
        age = None if t_hb_got is None else now - t_hb_got
        if a.test:
            if now - t0 >= a.test:
                near = [d for *_, d in sect if d is not None]
                print(f"OK: OBSTACLE_DISTANCE {rate:.1f} Hz, {len(sect)} sectors, nearest "
                      f"{min(near) if near else '-'} m, heartbeat {'yes' if age is not None else 'no'}, "
                      f"alerts {[s for _, s in alerts][-3:]}")
                assert rate > 5 and age is not None, "not receiving from the Pi"
                if a.save:
                    cv2.imwrite(a.save, radar(sect, alerts, rate, age))
                    print("saved", a.save)
                return
            continue
        cv2.imshow("FC view - what ArduPilot would receive (q to quit)", radar(sect, alerts, rate, age))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return


if __name__ == "__main__":
    main()
