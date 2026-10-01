"""Pi -> flight controller: report obstacles the way ArduPilot expects from a companion computer.

    OBSTACLE_DISTANCE  ~10 Hz   distances by direction, from the VL53L5CX 8x8 grid
    HEARTBEAT           1 Hz    "companion computer alive"
    STATUSTEXT      on change   "OBSTACLE person 1.2m ahead" -- for the ground station / pilot

The Pi REPORTS; it never commands. ArduPilot (PRX1_TYPE=2, AVOID_ENABLE) decides how to react,
and the pilot's RC always overrides.

Where the messages go is one string (pymavlink connection syntax):
    udpin:0.0.0.0:14550        bench demo: the laptop's fc_view.py (or Mission Planner) connects in
    /dev/ttyAMA0,921600        the real FC on J11 (SERIALn_PROTOCOL=2, SERIALn_BAUD=921)
    tcp:<laptop>:5762          ArduPilot SITL (the simulator in Mission Planner)
"""
import math
import os
import time

import numpy as np

os.environ.setdefault("MAVLINK20", "1")  # OBSTACLE_DISTANCE is a MAVLink 2 message
from pymavlink import mavutil  # noqa: E402

mavutil.set_dialect("ardupilotmega")

UNKNOWN = 65535  # OBSTACLE_DISTANCE: "no information for this direction" -- ArduPilot ignores it


def sectors(g, rows=(2, 6)):
    """8x8 grid (m, NaN = no target, already flipped to match the camera) -> nearest distance per
    column (left..right), using only the middle rows so floor and ceiling don't count as obstacles."""
    if g is None:
        return [None] * 8
    band = g[rows[0]:rows[1]]
    return [None if np.isnan(col).all() else float(np.nanmin(col)) for col in band.T]


class MavlinkOut:
    # VL53L5CX: ~45 deg across 8 zones, centred straight ahead
    FOV_DEG, ZONES, MIN_CM, MAX_CM = 45.0, 8, 10, 400

    def __init__(self, target, alert_m=1.5):
        # serial ports as "/dev/ttyAMA0,921600"; network targets ("udpin:0.0.0.0:14550") have no comma
        dev, _, baud = target.partition(",")
        self.m = mavutil.mavlink_connection(dev, baud=int(baud or 115200), source_system=1,
                                            source_component=mavutil.mavlink.MAV_COMP_ID_OBSTACLE_AVOIDANCE)
        self.alert_m = alert_m
        self.t0, self.t_hb, self.t_obs, self.t_alert, self.last_alert = time.time(), 0.0, 0.0, 0.0, None

    def update(self, g, dets=(), dists=()):
        """Call every frame; sends at the right rates. g = 8x8 metres grid or None."""
        # read (and discard) what arrived: in udpin mode this is how the link learns where the
        # laptop / FC is -- without it every message goes nowhere. Never blocks.
        for _ in range(20):
            try:
                if self.m.recv_msg() is None:
                    break
            except OSError:  # nothing to read (Windows reports this as an error): fine
                break
        now = time.time()
        if now - self.t_hb >= 1.0:
            self.m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                                      mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
            self.t_hb = now
        if g is None or now - self.t_obs < 0.1:
            return
        self.t_obs = now
        step = self.FOV_DEG / self.ZONES
        cm = [UNKNOWN] * 72
        for i, d in enumerate(sectors(g)):
            # nothing valid in that column = clear up to max range (max+1 means "no obstacle")
            cm[i] = self.MAX_CM + 1 if d is None else int(min(max(d * 100, self.MIN_CM), self.MAX_CM))
        self.m.mav.obstacle_distance_send(
            int((now - self.t0) * 1e6), mavutil.mavlink.MAV_DISTANCE_SENSOR_LASER, cm, 0,
            self.MIN_CM, self.MAX_CM, step, -self.FOV_DEG / 2 + step / 2, mavutil.mavlink.MAV_FRAME_BODY_FRD)
        self._alert(g, dets, dists)

    def _alert(self, g, dets, dists):
        """One STATUSTEXT when the nearest obstacle inside alert_m changes -- not 10 a second."""
        near = [(m, d[5]) for d, m in zip(dets, dists) if m is not None and m < self.alert_m]
        s = sectors(g)
        valid = [(d, i) for i, d in enumerate(s) if d is not None and d < self.alert_m]
        if not valid:
            self.last_alert = None
            return
        d, i = min(valid)
        name = min(near)[1] if near else "object"
        side = "left" if i < 3 else "right" if i > 4 else "ahead"
        text = f"OBSTACLE {name} {d * 100:.0f}cm {side}"
        # at most 1 a second, sooner only if the object or its side changed -- don't flood the pilot
        new_kind = self.last_alert is None or self.last_alert.split()[1::2] != text.split()[1::2]
        if text != self.last_alert and (new_kind or time.time() - self.t_alert >= 1.0):
            self.m.mav.statustext_send(mavutil.mavlink.MAV_SEVERITY_WARNING, text.encode()[:50])
            self.last_alert, self.t_alert = text, time.time()


if __name__ == "__main__":
    # self-check without the Pi's sensor: a fake object sweeps in and out, sent to the given target
    import sys
    out = MavlinkOut(sys.argv[1] if len(sys.argv) > 1 else "udpout:127.0.0.1:14550")
    t0 = time.time()
    while time.time() - t0 < float(sys.argv[2] if len(sys.argv) > 2 else 20):
        t = time.time() - t0
        g = np.full((8, 8), np.nan)
        col = int(3.5 + 3.5 * math.sin(t / 2))            # drifts left <-> right
        g[3:5, col] = 0.6 + 1.4 * (1 + math.cos(t)) / 2    # 0.6 m .. 2.0 m
        g[2:6, 0] = 3.0                                     # a wall far left
        out.update(g, [(0, 0, 1, 1, 0.9, "person")], [float(np.nanmin(g[3:5, col]))])
        time.sleep(1 / 30)
