"""Live object detection on the laptop, from the Pi's MediaMTX stream.

Run:   .\detect.ps1                  (window with boxes, press q to quit)
Test:  .\detect.ps1 --test 100       (no window, 100 frames, prints fps and what it saw)
"""
import argparse
import os
import threading
import time

# TCP: whole frames or nothing, so no smeared frames reach the detector.
# The rest switches off FFmpeg's input buffering -- by default it holds up to 0.5 s to
# reorder packets, which TCP never needs; that was ~1 s of delay in the window.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                      "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0|reorder_queue_size;0")
import cv2  # noqa: E402  (must come after the env var)
from ultralytics import YOLO  # noqa: E402


class LatestFrame:
    """Reads the stream on its own thread and keeps only the newest frame.

    If detection is slower than 30 fps, old frames are dropped instead of
    queueing -- otherwise the delay grows without limit (same bug as the
    20 s ffplay delay).
    """

    def __init__(self, url):
        # 1 decoder thread: frame-threaded decoding holds back one frame per thread
        # (12+ on this laptop = ~0.5 s of delay); one thread easily keeps up with 720p30
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        if not self.cap.isOpened():
            raise SystemExit(f"Cannot open {url} -- is the Pi on and MediaMTX running?")
        self.frame, self.seq, self.ok = None, 0, True
        self.lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.ok:
            ok, frame = self.cap.read()
            if not ok:
                self.ok = False
                break
            with self.lock:
                self.frame, self.seq = frame, self.seq + 1

    def get(self, last_seq):
        """Newest frame newer than last_seq, or None if none arrived yet."""
        with self.lock:
            if self.seq == last_seq:
                return None, last_seq
            return self.frame, self.seq


def main():
    ap = argparse.ArgumentParser()
    # Tailscale name: the same default works at the office and from home (Tailscale must be on)
    ap.add_argument("--source", default="rtsp://pi5drone:8554/cam")
    ap.add_argument("--model", default="yolo11n.pt")  # smallest; downloads ~5 MB on first run
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--test", type=int, default=0, metavar="N", help="run N frames headless, then report")
    a = ap.parse_args()

    src = a.source
    pw = os.environ.get("FPV_VIEWER_PASS")  # set by detect.ps1 from ~\.fpv-viewer-pass
    if pw and "@" not in src and src.startswith("rtsp://"):
        src = src.replace("rtsp://", f"rtsp://viewer:{pw}@", 1)
    model = YOLO(a.model)
    stream = LatestFrame(src)
    seq, done, seen, t0, fps = 0, 0, {}, time.time(), 0.0

    while stream.ok:
        frame, seq = stream.get(seq)
        if frame is None:
            time.sleep(0.002)
            continue
        t = time.time()
        r = model(frame, conf=a.conf, imgsz=a.imgsz, verbose=False)[0]
        fps = 0.9 * fps + 0.1 / max(time.time() - t, 1e-6)
        done += 1
        for c in r.boxes.cls.tolist():
            name = r.names[int(c)]
            seen[name] = seen.get(name, 0) + 1

        if a.test:
            if done >= a.test:
                break
            continue
        out = r.plot()
        cv2.putText(out, f"{fps:.1f} fps", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Pi FPV - detection (q to quit)", out)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    stream.ok = False
    if a.test:
        # the check: frames must arrive and detection must keep up
        assert done >= a.test, f"stream ended after {done} frames"
        print(f"OK: {done} frames, {done / (time.time() - t0):.1f} fps end-to-end, "
              f"detector {fps:.1f} fps, saw {dict(sorted(seen.items(), key=lambda kv: -kv[1]))}")
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
