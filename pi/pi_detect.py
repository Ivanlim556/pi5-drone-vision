"""Object detection ON THE PI. Reads MediaMTX's camera feed, finds objects,
publishes the boxed video back to MediaMTX:

    watch:  http://pi5drone.local:8889/detect      (plain feed stays at /cam)

Two detectors, picked by the model file:
    .hef   Hailo-8L (AI HAT+) -- YOLOv8s, ~30 fps, NMS on the chip.  Default when /dev/hailo0 exists.
    .onnx  Pi CPU             -- YOLO11n 320 px, 15 fps cap (needs the fan).

Run on the Pi:  ~/detect/.venv/bin/python ~/detect/pi_detect.py
Check:          ~/detect/.venv/bin/python ~/detect/pi_detect.py --test 100
One image:      ~/detect/.venv/bin/python ~/detect/pi_detect.py --image photo.jpg
The venv needs include-system-site-packages = true (Hailo's python3-hailort is a system package).
"""
import argparse
import ast
import atexit
import csv
import os
import re
import signal
import subprocess
import sys
import threading
import time

# Low delay: no FFmpeg input buffer (it holds up to 0.5 s to reorder packets TCP never reorders).
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                      "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0|reorder_queue_size;0")
import cv2  # noqa: E402  (must come after the env var)
import numpy as np  # noqa: E402

HAILO_MODEL = "/usr/share/hailo-models/yolov8s_h8l.hef"
# The 80 COCO classes in model order; "_" keeps two-word names whole through split().
COCO = [n.replace("_", " ") for n in (
    "person bicycle car motorcycle airplane bus train truck boat traffic_light fire_hydrant stop_sign "
    "parking_meter bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack umbrella handbag "
    "tie suitcase frisbee skis snowboard sports_ball kite baseball_bat baseball_glove skateboard surfboard "
    "tennis_racket bottle wine_glass cup fork knife spoon bowl banana apple sandwich orange broccoli carrot "
    "hot_dog pizza donut cake chair couch potted_plant bed dining_table toilet tv laptop mouse remote "
    "keyboard cell_phone microwave oven toaster sink refrigerator book clock vase scissors teddy_bear "
    "hair_drier toothbrush").split()]
assert len(COCO) == 80


class LatestFrame:
    """Reads the stream on its own thread and keeps only the newest frame,
    so a slow detector drops frames instead of falling further behind."""

    def __init__(self, url):
        # 1 decoder thread: frame-threaded decoding holds back one frame per thread
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        if not self.cap.isOpened():
            raise SystemExit(f"Cannot open {url} -- is MediaMTX running?")
        self.frame, self.seq, self.ok = None, 0, True
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.ok:
            ok, frame = self.cap.read()
            if not ok:
                self.ok = False
                break
            with self.lock:
                self.frame, self.seq = frame, self.seq + 1

    def get(self, last_seq):
        with self.lock:
            if self.seq == last_seq:
                return None, last_seq
            return self.frame, self.seq


def letterbox(img, size):
    """Scale to fit a size x size square, pad the rest grey. Returns canvas (BGR), scale, left, top."""
    h, w = img.shape[:2]
    s = size / max(h, w)
    nh, nw = round(h * s), round(w * s)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas = np.full((size, size, 3), 114, np.uint8)
    canvas[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh))
    return canvas, s, left, top


def _clip(img, x1, y1, x2, y2):
    h, w = img.shape[:2]
    return max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))


class Detector:
    """YOLO (Ultralytics ONNX export) on the Pi CPU."""
    label = "Pi CPU"

    def __init__(self, model_path, conf=0.4, iou=0.5):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = 3  # leave one core for the camera encoder
        # idle worker threads sleep instead of busy-waiting; otherwise --max-fps saves no CPU (or heat)
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        self.sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0]
        self.size = self.inp.shape[2]  # square, e.g. 640 or 320
        meta = self.sess.get_modelmeta().custom_metadata_map
        self.names = ast.literal_eval(meta["names"])  # {0: 'person', ...} stored by the Ultralytics export
        self.conf, self.iou = conf, iou

    def __call__(self, img):
        """img: BGR frame -> list of (x1, y1, x2, y2, score, name) in img pixels."""
        canvas, s, left, top = letterbox(img, self.size)
        x = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0

        out = self.sess.run(None, {self.inp.name: x})[0][0].T  # (anchors, 4 + classes)
        scores = out[:, 4:].max(1)
        keep = scores > self.conf
        out, scores = out[keep], scores[keep]
        cls = out[:, 4:].argmax(1)
        cx, cy, bw, bh = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
        boxes = np.stack([cx - bw / 2 - left, cy - bh / 2 - top, bw, bh], 1) / s  # back to img pixels

        dets = []
        idx = cv2.dnn.NMSBoxesBatched(boxes.tolist(), scores.tolist(), cls.tolist(), self.conf, self.iou)
        for i in np.array(idx).flatten():
            x1, y1, bw_, bh_ = boxes[i]
            dets.append((*_clip(img, x1, y1, x1 + bw_, y1 + bh_), float(scores[i]), self.names[int(cls[i])]))
        return dets


class HailoDetector:
    """YOLOv8 compiled for the Hailo-8L (.hef from hailo-models). NMS runs on the chip, so the
    output is already boxes per class: (y1, x1, y2, x2, score), normalised to the 640 input."""
    label = "Hailo-8L"

    def __init__(self, model_path, conf=0.4):
        from hailo_platform import (HEF, VDevice, ConfigureParams, HailoStreamInterface, FormatType,
                                    InputVStreamParams, OutputVStreamParams, InferVStreams)
        hef = HEF(model_path)
        self.dev = VDevice()
        ng = self.dev.configure(hef, ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe))[0]
        self.inp = hef.get_input_vstream_infos()[0]
        self.out = hef.get_output_vstream_infos()[0]
        self.size = self.inp.shape[0]  # 640
        self.conf = conf
        # pipeline first, then activate -- the order Hailo's examples use; both stay open for the process
        self._pipe = InferVStreams(ng, InputVStreamParams.make(ng, format_type=FormatType.UINT8),
                                   OutputVStreamParams.make(ng, format_type=FormatType.FLOAT32))
        self._pipe.__enter__()
        self._act = ng.activate(ng.create_params())
        self._act.__enter__()
        # left to Python's own teardown these close in the wrong order and segfault at exit (code 139)
        atexit.register(self.close)

    def close(self):
        if self._act:
            self._act.__exit__(None, None, None)
            self._pipe.__exit__(None, None, None)
            self.dev.release()
            self._act = None

    def __call__(self, img):
        canvas, s, left, top = letterbox(img, self.size)
        rgb = np.ascontiguousarray(canvas[:, :, ::-1])[None]  # model wants RGB uint8, batch of 1
        per_class = self._pipe.infer({self.inp.name: rgb})[self.out.name][0]
        dets = []
        for c, boxes in enumerate(per_class):
            for y1, x1, y2, x2, score in boxes:
                if score < self.conf:
                    continue
                px = lambda v, off: (v * self.size - off) / s  # noqa: E731  normalised -> img pixels
                dets.append((*_clip(img, px(x1, left), px(y1, top), px(x2, left), px(y2, top)),
                             float(score), COCO[c]))
        return dets


def _tof_worker(buf, stamp, frames, errors, flip, min_m):
    """Runs in its OWN PROCESS. 2026-09-30: when the sensor froze, each I2C read hung ~1 s while
    holding Python's global lock (the driver's I2C callbacks run in Python), and detection, the
    flight log and MAVLink all crawled with it. In a separate process a frozen sensor can only stop
    its own readings; the parent's watchdog kills and respawns it."""
    import vl53l5cx_ctypes as vl53l5cx
    # Power-cycle, not just power-on: a frozen sensor holds SDA low and still answers at 0x29
    # half-started. PWREN low -> high resets it. (PWREN/LPn go back low at every boot.)
    subprocess.run(["pinctrl", "set", "17", "op", "dl"], check=True)
    time.sleep(0.3)
    for pin in (17, 27):
        subprocess.run(["pinctrl", "set", str(pin), "op", "dh"], check=True)
    time.sleep(0.1)
    s = vl53l5cx.VL53L5CX()  # uploads the sensor's firmware (~84 KB): ~2 s at 400 kHz, ~9 s at 100 kHz
    s.set_resolution(8 * 8)
    s.set_ranging_frequency_hz(15)
    s.start_ranging()
    while True:
        try:
            if not s.data_ready():
                time.sleep(0.01)
                continue
            d = s.get_data()
        except OSError:  # I2C glitch: the grid goes stale; the parent respawns us if it lasts
            errors.value += 1
            time.sleep(0.05)
            continue
        mm = np.array(d.distance_mm[0][:64], float).reshape(8, 8)
        ok = np.isin(np.array(d.target_status[0][:64]).reshape(8, 8), (5, 9))
        # ponytail: fixed near cut-off. Closer than min_m is the desk / own frame / props, not an
        # obstacle (bench: 4-9 cm from the desk made a cup at 26 cm read 0.05 m). Revisit for landing.
        g = np.where(ok & (mm >= min_m * 1000), mm / 1000, np.nan)
        if "ud" in flip:
            g = np.flipud(g)
        if "lr" in flip:
            g = np.fliplr(g)
        if "t" in flip:  # sensor turned 90° relative to the camera: swap rows and columns
            g = g.T
        with buf.get_lock():
            buf[:] = g.ravel()
            stamp.value = time.monotonic()  # CLOCK_MONOTONIC is system-wide: comparable across processes
        frames.value += 1


class ToF:
    """VL53L5CX 8x8 time-of-flight grid, read in a separate process (see _tof_worker).
    grid() -> 8x8 array of metres, NaN where the zone has no valid target (status not 5/9)."""

    STALE_RESTART_S = 3.0  # no fresh grid for this long -> kill the reader process and respawn it

    def __init__(self, flip="ud", min_m=0.10):
        import multiprocessing as mp
        self.ctx = mp.get_context("spawn")  # a clean child: no Hailo/OpenCV threads copied in
        self.buf = self.ctx.Array("d", 64)
        self.stamp, self.frames, self.errors = self.ctx.Value("d", 0.0), self.ctx.Value("i", 0), self.ctx.Value("i", 0)
        self.args, self.proc, self.resets = (flip, min_m), None, -1
        self._spawn()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _spawn(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.join(timeout=5)
        self.proc = self.ctx.Process(target=_tof_worker, daemon=True,
                                     args=(self.buf, self.stamp, self.frames, self.errors, *self.args))
        self.proc.start()
        self.t_spawn, self.resets = time.monotonic(), self.resets + 1
        if self.resets:
            print(f"VL53L5CX reader restarted (reset {self.resets}): no fresh data for "
                  f"{self.STALE_RESTART_S:.0f} s", file=sys.stderr)

    def _watchdog(self):
        while True:
            time.sleep(0.5)
            now = time.monotonic()
            fresh_ref = max(self.stamp.value, self.t_spawn + 20)  # power-up + firmware upload: ~2 s at 400 kHz, ~9 s at 100 kHz
            if now - fresh_ref > self.STALE_RESTART_S or not self.proc.is_alive():
                self._spawn()

    def grid(self, max_age=0.5):
        """Latest grid, or None if it is older than max_age seconds -- a stale distance is worse
        than none, because it looks valid. Never blocks on the sensor."""
        with self.buf.get_lock():
            if time.monotonic() - self.stamp.value > max_age:
                return None
            return np.array(self.buf[:]).reshape(8, 8)


def _ar0234(cfg="/boot/firmware/config.txt"):
    try:
        return any(l.startswith("dtoverlay=ar0234") for l in open(cfg))
    except OSError:
        return False


def default_tof_flip():
    """How the sensor sits next to each camera (bench hand tests). CM3 2026-09-28: udlr.
    AR0234 2026-10-05 (sensor right of the camera, turned 90°): udlr showed an upright hand as a
    sideways band; t: torso at 70 cm read 3 m, near zones above the head = upside down.
    Flips run before the transpose, so the picture's up/down flip is "lr" here -> lrt."""
    return "lrt" if _ar0234() else "udlr"


def default_tof_fov(cfg="/boot/firmware/config.txt"):
    """45° sensor vs the camera's view. CM3 66°x41°: 0.64,1.10. AR0234 + 4 mm (70°) lens,
    full 1920x1200 sensor 71.5°x48.5°: tan(22.5)/tan(35.8) = 0.58, /tan(24.3) = 0.92."""
    return "0.58,0.92" if _ar0234(cfg) else "0.64,1.10"


def tof_edges(w, h, fov):
    """Pixel edges of the 8x8 zones. fov = the sensor's view as a fraction of the camera's
    (width, height): 45° sensor vs 66°x41° CM3 -> tan(22.5)/tan(33) = 0.64, /tan(20.5) = 1.10.
    Assumes the sensor sits right next to the camera, pointing the same way."""
    fx, fy = fov
    return np.linspace(w / 2 * (1 - fx), w / 2 * (1 + fx), 9), np.linspace(h / 2 * (1 - fy), h / 2 * (1 + fy), 9)


def box_distance(g, xs, ys, box):
    """Nearest valid distance among the zones whose centre falls inside the box, or None."""
    x1, y1, x2, y2 = box
    cx, cy = (xs[:-1] + xs[1:]) / 2, (ys[:-1] + ys[1:]) / 2
    sub = g[np.ix_((cy >= y1) & (cy <= y2), (cx >= x1) & (cx <= x2))]
    return None if sub.size == 0 or np.isnan(sub).all() else float(np.nanmin(sub))


class FlightLog:
    """One CSV per run: a row per processed frame -- what the drone saw, when, and how far.
    Line-buffered, so pulling the battery loses at most the last line.
    The Pi has no battery clock: at boot it restores the time it had at shutdown, then jumps when it
    reaches the internet. So files are numbered by run (0001_..., never reused -- a date-only name
    overwrote the previous log on 2026-09-30) and t_s is monotonic (it never jumps)."""

    def __init__(self, log_dir):
        os.makedirs(log_dir, exist_ok=True)
        runs = [int(f[:4]) for f in os.listdir(log_dir) if re.match(r"\d{4}_", f)]  # not old date-named logs
        run = max(runs, default=0) + 1
        self.path = os.path.join(log_dir, f"{run:04d}_{time.strftime('%Y%m%d-%H%M%S')}.csv")
        self.f = open(self.path, "x", buffering=1, newline="")  # "x": refuse to overwrite, ever
        self.w = csv.writer(self.f)
        self.w.writerow(["time", "t_s", "fps", "nearest_m", "temp_c", "detections"])
        self.t0 = time.monotonic()

    def write(self, fps, g, dets, dists):
        try:
            temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
        except OSError:
            temp = ""
        near = "" if g is None or np.isnan(g).all() else f"{np.nanmin(g):.2f}"
        seen = "; ".join(f"{d[5]} {d[4]:.2f} " + (f"{m:.2f}m" if m is not None else "-") for d, m in zip(dets, dists))
        self.w.writerow([time.strftime("%H:%M:%S"), f"{time.monotonic() - self.t0:.2f}", f"{fps:.1f}", near, temp, seen])


def box_distances(g, dets, w, h, fov):
    """Distance (m) for each detection, None where the grid has nothing valid under the box."""
    if g is None:
        return [None] * len(dets)
    xs, ys = tof_edges(w, h, fov)
    return [box_distance(g, xs, ys, d[:4]) for d in dets]


def draw(img, dets, fps, label, g=None, fov=(0.64, 1.10), dists=None):
    dists = dists if dists is not None else box_distances(g, dets, img.shape[1], img.shape[0], fov)
    if g is not None:
        xs, ys = tof_edges(img.shape[1], img.shape[0], fov)
        shade = img.copy()
        for r in range(8):
            for c in range(8):
                if np.isnan(g[r, c]):
                    continue
                t = min(g[r, c] / 2.0, 1.0)  # 0 m red -> 2 m and beyond green
                p1, p2 = (int(xs[c]), int(ys[r])), (int(xs[c + 1]) - 1, int(ys[r + 1]) - 1)
                cv2.rectangle(shade, p1, p2, (0, int(255 * t), int(255 * (1 - t))), -1)
                cv2.putText(img, f"{g[r, c] * 100:.0f}", (p1[0] + 4, max(12, p1[1] + 16)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.addWeighted(shade, 0.25, img, 0.75, 0, img)
    for (x1, y1, x2, y2, score, name), dist in zip(dets, dists):
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, f"{name} {score:.2f}" + (f"  {dist * 100:.0f} cm" if dist is not None else ""),
                    (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(img, f"{fps:.1f} fps ({label})", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    if g is not None and not np.isnan(g).all():
        cv2.putText(img, f"nearest {np.nanmin(g) * 100:.0f} cm", (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
    return img


class Publisher:
    """Boxed video -> ffmpeg -> MediaMTX (/detect), on its own thread.

    2026-09-30: with -use_wallclock_as_timestamps, the Pi's clock jumping 21 h at boot stalled
    ffmpeg; the main loop blocked writing to it, and detection, the flight log and the MAVLink
    obstacle reports all froze behind a video hiccup. Now:
      - the main loop only hands over its latest frame (never blocks);
      - this thread feeds ffmpeg at a fixed rate on a monotonic clock, repeating the last frame if
        detection is slower, so timestamps are simply frame-count / fps and no clock can jump them;
      - a watchdog kills and restarts ffmpeg if a write hangs for 5 s.
    """

    def __init__(self, url, fps):
        self.url, self.fps = url, fps
        self.frame, self.proc, self.ok = None, None, True
        self.t_write, self.restarts = time.monotonic(), 0
        self.lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def push(self, frame):
        with self.lock:
            self.frame = frame

    def _spawn(self, w, h):
        return subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
             "-framerate", str(self.fps), "-i", "-",
             "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
             "-g", "10", "-b:v", "1500k", "-f", "rtsp", "-rtsp_transport", "tcp", self.url],
            stdin=subprocess.PIPE)

    def _run(self):
        period, nxt = 1 / self.fps, time.monotonic()
        while self.ok:
            with self.lock:
                f = self.frame
            if f is not None:
                if self.proc is None or self.proc.poll() is not None:
                    self.proc = self._spawn(f.shape[1], f.shape[0])
                try:
                    self.proc.stdin.write(f.tobytes())
                    self.t_write = time.monotonic()
                except (BrokenPipeError, OSError, ValueError):  # ffmpeg died / was killed: respawn
                    self._kill()
                    time.sleep(1)
            nxt += period
            time.sleep(max(0.0, nxt - time.monotonic()))
            if time.monotonic() - nxt > 1:  # fell far behind (e.g. after a restart): don't burst
                nxt = time.monotonic()

    def _watchdog(self):
        while self.ok:
            time.sleep(1)
            if self.proc is not None and time.monotonic() - self.t_write > 5:
                self.restarts += 1
                print(f"video publisher stalled 5 s -> restarting ffmpeg (restart {self.restarts})", file=sys.stderr)
                self._kill()
                self.t_write = time.monotonic()

    def _kill(self):
        p, self.proc = self.proc, None
        if p is not None:
            p.kill()
            p.wait(timeout=5)

    def close(self):
        self.ok = False
        self._kill()


def main():
    # SIGTERM (kill, systemctl stop/restart) would end Python without running atexit, so the Hailo is
    # never closed; 2026-09-29 that left the driver "Device disconnected" until a reboot. Exit normally.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="rtsp://127.0.0.1:8554/cam")
    ap.add_argument("--out", default="rtsp://127.0.0.1:8554/detect")
    ap.add_argument("--model", default=HAILO_MODEL if os.path.exists("/dev/hailo0") else "yolo11n-320.onnx",
                    help=".hef = Hailo-8L; .onnx = Pi CPU (yolo11n-320.onnx ~22 fps, -640 ~5 fps)")
    ap.add_argument("--conf", type=float, default=0.4)
    # ponytail: fixed caps. CPU: 15 fps holds 66-69 °C with the fan (10 fps hit 85 °C without it).
    # Hailo: 30 = the camera's rate; the CPU then only decodes, draws and re-encodes.
    ap.add_argument("--max-fps", type=float, default=None, help="cap detection rate (default: 30 Hailo, 15 CPU; 0 = none)")
    ap.add_argument("--test", type=int, default=0, metavar="N", help="N frames, no output stream, report fps")
    ap.add_argument("--image", help="detect on one image, print results, exit")
    ap.add_argument("--no-tof", action="store_true", help="skip the VL53L5CX distance sensor")
    # calibration knobs: set once from the hand test (hand on the left of the picture -> grid red on the left).
    # 2026-09-28, sensor taped beside the camera: 'ud' showed a left hand on the right -> 'udlr'.
    ap.add_argument("--tof-flip", default=default_tof_flip(),
                    help="orient the 8x8 grid: any of ud, lr, t (transpose, applied last); default from the camera")
    ap.add_argument("--tof-fov", default=default_tof_fov(), help="sensor view as a fraction of the camera's width,height "
                    "(default: from the camera picked with the `camera` command)")
    ap.add_argument("--tof-min", type=float, default=0.10, help="ignore distance readings closer than this (m)")
    ap.add_argument("--log-dir", default=os.path.expanduser("~/detect/logs"), help="flight log folder (one CSV per run)")
    ap.add_argument("--no-log", action="store_true", help="do not write a flight log")
    # obstacle reports for the FC (mavlink_out.py). Bench: the laptop's fc_view.ps1 / Mission Planner connect
    # in over UDP 14550. Drone: "/dev/ttyAMA0,921600" (J11). "" = off.
    ap.add_argument("--mavlink", default="udpin:0.0.0.0:14550", help="MAVLink target for obstacle reports ('' = off)")
    a = ap.parse_args()
    fov = tuple(float(v) for v in a.tof_fov.split(","))

    det = HailoDetector(a.model, a.conf) if a.model.endswith(".hef") else Detector(a.model, a.conf)
    if a.max_fps is None:
        a.max_fps = 30 if isinstance(det, HailoDetector) else 15
    if a.image:
        for d in det(cv2.imread(a.image)):
            print(f"{d[5]:<14} {d[4]:.2f}  box {d[:4]}")
        return

    tof = None
    if not a.no_tof:
        try:
            tof = ToF(a.tof_flip, a.tof_min)
        except Exception as e:  # no sensor wired, or I2C off: carry on with boxes only
            print(f"VL53L5CX not available ({e}) -- running without distances", file=sys.stderr)

    mav = None
    if a.mavlink and not a.test:
        try:
            from mavlink_out import MavlinkOut
            mav = MavlinkOut(a.mavlink)
            print(f"MAVLink obstacle reports -> {a.mavlink}", file=sys.stderr)
        except Exception as e:  # never let the FC link stop detection
            print(f"MAVLink off ({e})", file=sys.stderr)

    # created at the first processed frame, not here: 2026-09-30 a camera outage made the service
    # restart ~80 times, and each start left an empty log file behind
    log, want_log = None, not (a.no_log or a.test)

    stream = LatestFrame(a.source)
    pub, seq, done, seen, fps, t0 = None, 0, 0, {}, 0.0, time.time()
    while stream.ok:
        frame, seq = stream.get(seq)
        if frame is None:
            time.sleep(0.003)
            continue
        t = time.time()
        dets = det(frame)
        if a.max_fps and not a.test:
            time.sleep(max(0.0, 1 / a.max_fps - (time.time() - t)))
        fps = 0.9 * fps + 0.1 / max(time.time() - t, 1e-6) if done else 1 / max(time.time() - t, 1e-6)
        done += 1
        for d in dets:
            seen[d[5]] = seen.get(d[5], 0) + 1
        if a.test:
            if done >= a.test:
                break
            continue
        g = tof.grid() if tof else None  # one grid per frame: the picture and the log agree
        dists = box_distances(g, dets, frame.shape[1], frame.shape[0], fov)
        if want_log and log is None:
            log = FlightLog(a.log_dir)
            print(f"flight log: {log.path}", file=sys.stderr)
        if log:
            log.write(fps, g, dets, dists)
        if mav:
            try:
                mav.update(g, dets, dists)
            except OSError:  # nobody connected yet / link hiccup: detection carries on
                pass
        if pub is None:
            pub = Publisher(a.out, int(a.max_fps) if a.max_fps else 30)
        pub.push(draw(frame, dets, fps, det.label, g, fov, dists))  # never blocks

    # stop the reader cleanly: killing it mid-read aborts with "FATAL: exception not rethrown"
    stream.ok = False
    stream.thread.join(timeout=2)
    stream.cap.release()
    if pub:
        pub.close()
    if not a.test:
        sys.exit(1)  # the live loop only ends on failure; non-zero lets systemd restart it
    assert done >= a.test, f"stream ended after {done} frames"
    print(f"OK: {done} frames in {time.time() - t0:.1f} s, {det.label} {fps:.1f} fps, "
          f"saw {dict(sorted(seen.items(), key=lambda kv: -kv[1]))}")
    if tof:
        g = tof.grid()
        near = "no valid zone" if g is None or np.isnan(g).all() else f"nearest {np.nanmin(g) * 100:.0f} cm"
        print(f"VL53L5CX: {tof.frames.value} grids, {tof.errors.value} I2C errors, {tof.resets} restarts, {near}")
        if g is not None:
            for row in g:
                print("  " + " ".join("   x" if np.isnan(v) else f"{v * 100:4.0f}" for v in row))


if __name__ == "__main__":
    main()
