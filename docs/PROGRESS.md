# Pi 5 FPV bring-up — progress

Guide: AR0234 FPV Bring-up artifact (https://claude.ai/artifact/96imF6Ymetm4gsGuj9qnUg)
Last session: 2026-09-25, office + home (hotspot)

## Status

| Stage | Status | Notes |
|---|---|---|
| 1 — Flash Pi 5 | Done | Hostname `pi5drone`, user `pi`, laptop SSH key installed (no password needed) |
| 2 — Camera works | Done | `imx708` detected · photo OK (`stage2-test-photo.jpg`) · H.264 encodes (~1.5 Mbit/s) |
| 3 — Live feed | **Done** | Picture on laptop + HDMI. **10-min soak passed** (home, hotspot, 22:27–22:37): no reboot, stream up 60/60 checks, 5.06–5.14 V, `throttled=0x0`, 53→60 °C, 3 brief decode smears. **Latency 148 ms average** (7 readings, 129–169 ms; web page / WebRTC over the 2.4 GHz hotspot, 2026-09-25) |
| Web page | Done | MediaMTX on the Pi, starts at boot: `http://pi5drone.local:8889/cam` (same WiFi/hotspot only) |
| 4 — Object detection | Laptop version works | YOLO11n on the laptop CPU from the Pi's feed, ~14 fps (`detect.ps1`). On-Pi detection waits for the Hailo |

## Open issues

1. **Pi rebooted by itself 3 times at the office** — 5 V input 4.86–4.98 V there. At home it held 5.06–5.14 V for the whole soak with no reboot, so the office supply was the cause. Keep using the home one (or the official 27 W).
2. **Some blur remains** = UDP packets lost over WiFi; clears at the next keyframe (every 0.5 s).
3. Logs are lost on each reboot. To keep them, run once on the Pi:
   `sudo mkdir -p /var/log/journal && sudo systemctl restart systemd-journald`

## Fixes found (differ from the guide)

| Problem | Fix |
|---|---|
| Laptop got no video with `ffplay udp://@:5600` | Use `udp://0.0.0.0:5600` — this Windows ffmpeg build rejects `@` |
| ~20 s delay, growing | Raw H.264 has no timestamps; ffplay assumed 25 fps vs 30 sent. Add `-f h264 -framerate 60 -sync ext` |
| Blur / delay | Laptop was on 2.4 GHz → reconnected to 5 GHz. Pi WiFi power save disabled (`802-11-wireless.powersave 2`) |
| Picture upside down | `--rotation 180` |
| Stream died when SSH dropped | Run detached (`setsid nohup`) — done inside `start-stream.sh` |

## Pi access

| | |
|---|---|
| SSH command | `ssh -4 pi@pi5drone.local` |
| Hostname | `pi5drone` |
| Username | `pi` |
| Password | the one you set in Raspberry Pi Imager (needed only for `sudo`) |
| Login key | this laptop's `C:\Users\ivan\.ssh\id_ed25519` — no password asked. On another PC, SSH asks for the Pi password instead |
| IP — office WiFi `TP-Link_C6A4` | 192.168.0.110 |
| IP — hotspot `[phone-hotspot]` | 172.20.10.2 |

If `pi5drone.local` is not found, use the IP instead: `ssh pi@172.20.10.2`. IPs can change; if both fail,
look for `pi5drone` in the phone's hotspot device list or the router's device list.

## How to run

Laptop (PowerShell, in this folder):
```
ssh -4 pi@pi5drone.local
./start-stream.sh          # on the Pi — streams to the laptop you SSH'd from
```
Then, in a second PowerShell window on the laptop:
```
.\view-stream.ps1
```
Laptop firewall rule "FPV 5600" (UDP inbound) is already added.

**Away from the office:** turn on the phone hotspot `[phone-hotspot]` and connect the laptop to it, then `ssh -4 pi@pi5drone.local` — the Pi joins
by itself (saved, autoconnect on; tested 2026-09-25). Hotspot runs on 2.4 GHz, so expect more blur than the office 5 GHz.
Add home WiFi from SSH with `sudo nmtui` → Activate a connection.

## Live web page (MediaMTX)

Open in any browser on the same WiFi / hotspot: **http://pi5drone.local:8889/cam** (or `http://172.20.10.2:8889/cam` on the hotspot).
QGroundControl / VLC: `rtsp://pi5drone.local:8554/cam`

- Installed on the Pi in `~/mediamtx/` (v1.21.1). It reads the camera itself — no `rpicam-vid`, no `start-stream.sh`.
- Settings in `~/mediamtx/cam.yml` (copy here: `mediamtx-cam.yml`): 1280×720 · 30 fps · software H.264 · 3 Mbit/s · keyframe 0.5 s · rotated 180° · focus locked at infinity.
- Only one program can use the camera: stop MediaMTX before running `start-stream.sh` or `rpicam-*`.
- Start at boot (run once on the Pi, asks for your password):
  `pkill mediamtx; sudo cp ~/mediamtx/mediamtx.service /etc/systemd/system/ && sudo systemctl enable --now mediamtx`
  Then: stop `sudo systemctl stop mediamtx` · start `sudo systemctl start mediamtx` · log `journalctl -u mediamtx -n 30`
- Next: remote viewing from anywhere with Tailscale + a password on the page.

## Object detection on the laptop (no Hailo yet)

Reads the MediaMTX feed, runs YOLO11n on the laptop CPU, draws boxes. Nothing changes on the Pi.

- Run: `.\detect.ps1` in this folder (press **q** in the window to quit). Check without a window: `.\detect.ps1 --test 100`
- First result 2026-09-25 (hotspot): detector **~14 fps** on the Ryzen 5 5600H CPU; saw person, chair.
- Python env: `C:\Users\ivan\fpv-detect\.venv` (built with `uv`; kept out of OneDrive and away from the ESP-IDF Python).
- Always processes the newest frame, so the delay does not build up when detection is slower than 30 fps.
- **2026-09-28: GPU enabled.** PyTorch `2.14.0+cu130` in the venv (NVIDIA driver 592.82, CUDA 13.1). RTX 3050: **~30 fps** (CPU was ~16), 56 MB GPU memory. YOLO picks the GPU by itself — `detect.ps1` unchanged. First frame takes ~7 s (GPU warm-up); normal.
- Model: **YOLO11n** (Ultralytics, nano, 2.6 M parameters, trained on COCO's 80 everyday classes). Bigger = more accurate, slower: n → s → m. On the GPU: **yolo11n 30 fps, yolo11s 26 fps** (2026-09-28) — `.\detect.ps1 --model yolo11s.pt` for better accuracy at almost the same speed. Model files sit in this folder; run from here, or YOLO downloads them again wherever you are.
- **Delay fixed 2026-09-28: ~1 s → ~0.19 s** (stopwatch test, 5 readings, yolo11s on GPU). Two causes in `detect.py`: FFmpeg's input buffer (turned off: `nobuffer`, `max_delay 0`, `reorder_queue_size 0`) and frame-threaded decoding holding one frame per CPU thread (now 1 decoder thread). Only ~50 ms above the plain web page — the time YOLO takes per frame.

## Object detection on the Pi (CPU, no Hailo) — works, fan fitted

**2026-09-26: fan added** (Pi fan header, ~5,400 rpm under load). At **15 fps** it holds **66–69 °C, `throttled=0x0`**. Default is now `--max-fps 15`.
Start at boot (run once on the Pi, asks for your password):
`sudo cp ~/detect/pi-detect.service /etc/systemd/system/ && sudo systemctl enable --now pi-detect`
**2026-09-26: start-at-boot switched OFF on request** (`sudo systemctl disable pi-detect`) — paused for now.
To turn it back on: `sudo systemctl enable --now pi-detect`. The service file and fan fix stay in place.
Stop `sudo systemctl stop pi-detect` · start `sudo systemctl start pi-detect` · off at boot `sudo systemctl disable pi-detect` · log `journalctl -u pi-detect -n 30`

Before the fan:

Boxed video on a web page: **http://pi5drone.local:8889/detect** (plain feed stays at `/cam`).

- Files on the Pi: `~/detect/` (`pi_detect.py`, `yolo11n-320.onnx`, `yolo11n-640.onnx`, `.venv` with onnxruntime + OpenCV, 229 MB). Copies of the script here.
- Model converted to ONNX on the laptop, so the Pi needed no PyTorch (~70 MB download instead of ~400 MB). Checked against official YOLO on the same frame: same object, boxes within ~6 px.
- Speed (Pi 5 CPU): 320 model **22 fps**, 640 model 5 fps.
- Start (not at boot yet): `cd ~/detect && setsid nohup .venv/bin/python pi_detect.py > /tmp/pi_detect.log 2>&1 &`   Stop: `pkill -f "[.]venv/bin/python pi_detect"`
- **Heat: no fan/cooler on this Pi.** Uncapped (22 fps) and 10 fps both reached 85 °C and hard-throttled (`throttled=0xe0006`). Capped at **5 fps** it held 74–82 °C. Default is now `--max-fps 5`.
  → **Buy the official Raspberry Pi Active Cooler** (clips on, ~RM25). Then try `--max-fps 15`, and only then start it at boot.
- ONNX Runtime threads busy-spin by default, so a frame cap saved no CPU until `allow_spinning=0` was set (250% → 150% CPU).
- Gotcha: `pkill -f pi_detect` also matches the SSH command running it and drops the session — use the `[.]venv` pattern above.
- Gotcha: many hung/aborted SSH sessions made the Pi refuse SSH for ~10 min (OpenSSH `PerSourcePenalties`). Wait it out; don't hammer retries.

## Hailo — hardware arriving 2026-09-28

**Raspberry Pi AI HAT+ 13 TOPS** (checked from photos 2026-09-28 — not the AI Kit): **Hailo-8L** soldered on the HAT. The AI HAT+ enables PCIe Gen 3 by itself — no `dtparam=pciex1_gen=3` needed. Models must be the **hailo8l** `.hef` builds. Fitted 2026-09-28 over the fan; PCIe ribbon pre-attached; camera ribbon through the HAT cut-out.

**Working 2026-09-28** — `/detect` now runs on the Hailo, starts at boot (`pi-detect` enabled).
- PCIe link **8.0 GT/s x1** (Gen 3) · `hailortcli fw-control identify` → `HAILO8L`, firmware 4.23.0.
- Install: `sudo apt install -y dkms hailo-all && sudo reboot` → HailoRT **4.23.0**. **Not** `hailo-h10-all` (HailoRT 5, Hailo-10H only — conflicts).
- Chip benchmark `hailortcli run /usr/share/hailo-models/yolov8s_h8l.hef`: **58.8 fps**.
- `pi_detect.py` picks the model by file: `.hef` → Hailo (default when `/dev/hailo0` exists), `.onnx` → CPU. Hailo model YOLOv8s 640 px, NMS on the chip. Cap 30 fps (camera rate).
- Live: **~30 fps**, detection process 50–70 % CPU (was 150–250 %), **52–54 °C**, fan ~2,250 rpm, `throttled=0x0`.
- Cross-check on `bus.jpg` vs official YOLOv8s on the laptop: same 5 objects, scores within 0.02, boxes within a few px.
- The venv needs `include-system-site-packages = true` in `~/detect/.venv/pyvenv.cfg` (python3-hailort is a system package). Its own numpy 2.5 works with HailoRT.
- Gotcha fixed: Hailo objects left to Python's teardown closed in the wrong order → segfault at exit (code 139, and piped output lost). `HailoDetector.close()` via `atexit` fixes it.
- Also applied the laptop's delay fixes to the Pi reader (no FFmpeg input buffer, 1 decoder thread).
- **Phase 1 gate passed 2026-09-28 (15:38–15:48):** 60/60 readings running, 0 restarts, `throttled=0x0`, 54.9–59.8 °C, fan 2,350–4,375 rpm, 5.05–5.16 V, `/detect` ~28 fps at the end.
- GPIO: the AI HAT+ passes the 40 pins through (socket strip J1 on top) → the VL53L5CX wires to the top of the HAT, pins 1/3/5/6 (+7 for INT). Pin 1 only — never 2/4 (5 V). Before fitting: 69 pending updates to install (`sudo apt full-upgrade`); bootloader already current (2026-05-26). Check the fan still clears the HAT.

## AR0234 pre-setup on card A — DONE 2026-10-01 (board not yet arrived)

Decided: same card A (not card B). Backup first: files → `C:\Users\ivan\pi5-backups\cardA-20260930-1413\` (config, services, code, ONNX models, package lists, logs) + GitHub v1.0-cm3. Full-card clone abandoned: the USB card reader dropped out mid-copy twice (`USB disconnect`, Pi power/temps fine — reader suspect).
- **Kurokesu repo added** (`/etc/apt/sources.list.d/kurokesu.sources`; script read before running: key + source only, fingerprint-checked; undo `sudo sh setup.sh --remove`).
- **Dry run finding:** Kurokesu packages carry a `1:` epoch → a plain `apt upgrade` would have replaced 11 standard camera packages (libcamera*, rpicam-apps*). **apt lock** `/etc/apt/preferences.d/kurokesu.pref`: `Pin: release o=Kurokesu` priority 90, `ar0234-rpi-dkms` 500 → 0 Kurokesu packages in the upgrade list, standard camera stack kept. (First attempt failed: a long multi-line paste got truncated in SSH — use the one-line `printf` version.)
- **Driver:** `ar0234-rpi-dkms 0.1.2` only (replaces nothing), DKMS-built for 6.18.50 rpi-2712 + v8; overlay `/boot/firmware/overlays/ar0234.dtbo` (supports `4lane`, `cam0`).
- **Power overlay** (Pi 5 version) compiled → `/boot/firmware/overlays/ar0234-gamuda-power.dtbo`; merge test with `ar0234,4lane,cam0`: OK, cam0_reg + cam1_reg = 35000 µs, ar0234@10, 4 data lanes.
- **`camera` switch** (`/usr/local/bin/camera`, source in this folder): `sudo camera cm3|ar0234` + reboot rewrites one marked block in `config.txt` (backup each time); `camera` shows the mode. Tested on a copy: 5 switches → one block, other lines untouched.
- **Pre-test (ar0234 mode, no board):** device `10-0010` (`ar0234cs`) on CAM0's I²C bus (`i2c-10` = `i2c@88000`), regulators live at 35000 µs. Driver did **not** probe by itself at boot; manual `echo 10-0010 | sudo tee /sys/bus/i2c/drivers/ar0234/bind` → `extclk 24000000Hz, link 450000000Hz, lanes 4` → `Error reading reg 0x3000: -121` → `failed to read chip id` = **PASS** (only the board missing). Power-on → first I²C read took **47 ms** = 35 ms ramp + 6.2 ms driver wait, as designed.
- **Arrival-day watch item:** if the driver again doesn't bind by itself at boot with the board connected → manual bind works; make it permanent with a small boot rule.
- Back to `camera cm3`: all normal (34 fps `/detect`).

## AR0234 — board ~1 week away (from 2026-09-28)

**Card B candidate (2026-09-29):** 128 GB microSD (shows as "Mass Storage Device", 119 GB). Held an old Pi OS (Apr 2026, WiFi "HONOR X9a 5G"), free to erase; one file was **corrupt** (`user-data`) → unsafe unplug or a failing card. Erased with Imager (now empty FAT32, drive D:). **Tested 2026-09-29: PASS** — 16 GiB of seeded random data written and read back byte-for-byte with unbuffered I/O (H2testw-style script, `cardtest.py`): **0 bad bytes**, write 16.8 MB/s, read 18.0 MB/s (likely limited by the USB card reader). The earlier corrupt file was an unsafe unplug. → **Usable as card B** for bench work; the card that flies should still be a new A2/U3 card.

- **Cable ordered:** generic FFC 0.5 mm **22P, 20 cm, "Same" side (Type A)**, 8 pcs. Right cable type; raspberrypi.com makes no 22-to-22 camera cable.
- **Still to order:** one pack of the **"Opposite" side (Type B)**, 22P 20 cm, from the same seller — which type the board needs is only known once it is in hand.
- Also ordered: 2× official Pi 5 camera cable 22→15 pin — **CM3 spares only**, will not fit the AR0234.
- Arrival day: pick the cable whose contacts face the pads at both ends → continuity pins 1–22 (guide Phase 2.2) → Kapton over contact 18 → first power-on (Phase 2.3).
- Before arrival: card B (second microSD) with the Kurokesu driver + overlays (Phase 2.1).
- **Power overlay: use the Pi 5 version in this folder** (`ar0234-gamuda-power-overlay.dts`, 2026-09-28). The handover original only set `cam1_reg` (fine on CM4, where it is the same node as `cam0_reg`); on the Pi 5 they are separate, so the Pi 5 version sets both connectors. First-ever compile done on the Pi: OK, merges onto `bcm2712-rpi-5-b.dtb`, both regulators 35 ms, `delay-us` override works.

## Problems on 2026-09-29 (all fixed)

1. **Laggy page / Pi unreachable** → weak power supply again. Swapped to a **5 A USB-C PD supply**: 5.07–5.12 V, `usb_max_current_enable=1`. **Keep this supply; the old office one causes brownouts.** (Laptop↔Pi pings still spike on busy office WiFi; the Pi's own link is fine at −48 dBm. Ethernet is the cure for bench work.)
2. **No distances**: detector log `VL53L5CX not detected on 0x29`, kernel `i2c_designware ... controller timed out`, `i2cdetect` hung. **SDA (pin 3) stuck LOW** — stayed low even with the Pi's I²C controller detached and PWREN low, went high with the SDA wire unplugged → wire badly seated / sensor frozen during the power swap. Unplug + replug of the SDA wire cleared it. Check: `pinctrl get 2,3` must show `hi` for both. (If it ever stays stuck with the wire on: 9 clock pulses on SCL + STOP, done with `pinctrl` — see chat 2026-09-29.)
3. **Hailo "Device disconnected while opening device"** (restart loop) → caused by stopping the detector with a plain `kill`: Python exits on SIGTERM without closing the Hailo; dmesg `hailo_nnc_driver_down, timeout waiting for shutdown response`. Fixed by a reboot; `pi_detect.py` now turns SIGTERM into a normal exit so `HailoDetector.close()` runs. **To restart the detector use `sudo systemctl restart pi-detect`.**

## Is YOLO good enough indoors? (started 2026-09-29)

Target: **indoor** flight. Principle: avoidance is driven by the distance sensor; YOLO only labels (so an unknown wall/pole still counts as an obstacle).
- **Current Pi model** (YOLOv8s COCO, 80 classes) knows person/chair/couch/table/TV/bottle… but **no door, wall, stairs, window, pole, shelf**.
- **Tried model A = `yolov8s-oiv7.pt`** (Open Images V7, 601 classes incl. Door/Window/Stairs/Shelf) on the laptop GPU vs COCO: office window photo → A found 3 windows, COCO none; dim room (webcam) → both found the chair, **both missed an obvious door + shelf** even at conf 0.08; A also said "House" for the whole frame. Verdict: **not good enough** — weak in dim light, low mAP (27.7), no Hailo build.
- **Plan (B + C):** fine-tune YOLOv8s on a public indoor dataset (Roboflow Universe "Indoor Objects", 1,398 images: door, opened door, window, pole, cabinet, table, chair, couch…) **+ own photos from the drone camera** (capture script, ~150–300, labelled in Roboflow) + some people images, **greyscale** (for the AR0234). Train on the RTX 3050, score against own test photos, compile for Hailo-8L, deploy. Then GitHub v1 (CM3); later v2 (AR0234).
- **Training v1 (2026-09-29/30):** Roboflow "Indoor Objects" v4 (forked + downloaded; 2,100 / 451 / 247 images, 10 classes, CC BY 4.0) → `C:\Users\ivan\fpv-detect\datasets\indoor-objects\` (files renamed short by `shorten_names.py` — Roboflow names broke Windows' 260-char path limit). YOLOv8s from COCO weights, RTX 3050, batch 8, `hsv_s=0.9` (colour-tolerant for the mono AR0234). Early-stopped at epoch 55 (best 35), 55 min. Weights: `C:\Users\ivan\fpv-detect\runs\indoor-v1\weights\best.pt`.
  - **Test set mAP50 0.33** (P 0.41, R 0.37): refrigeratorDoor 0.61, cabinetDoor 0.51, window 0.41, door 0.37, chair 0.35, pole 0.30, cabinet 0.23, couch 0.19, table 0.16, openedDoor 0.12.
  - Webcam (my room): COCO → person 0.84, bottle, chair; v1 → only a wrong "cabinetDoor" — missed the door, knows no people.
  - **Verdict: not deployed.** Causes: dataset is largely furniture/catalogue photos (domain gap vs a low, dim drone view); too many near-identical classes; no person class.
  - **Next:** own photos from the drone camera (capture script when the Pi is back; label ~200–300 in Roboflow), fewer obstacle classes (door incl. open, window, pole/pillar, furniture, person, maybe stairs/wall), keep person (mix COCO persons or start from the COCO model), then retrain. The Pi keeps the COCO model meanwhile.

## GitHub — v1.0 CM3 milestone (2026-09-30)

**Private** repo https://github.com/Ivanlim556/pi5-drone-vision · release **v1.0-cm3**. Local clone `C:\Users\ivan\pi5-drone-vision` (outside OneDrive). Layout `pi/`, `laptop/`, `training/`, `docs/` (guide + this log). Kept out: the viewer password hash (placeholder in `pi/mediamtx/cam.yml`), `.fpv-viewer-pass`, model weights, datasets, runs, logs (`.gitignore`). `.gitattributes` keeps Pi files LF. Git identity set for this repo only. v2.0 = AR0234, same repo.

## Robustness fixes 2026-09-30 (all tested on the Pi)

Found after a power-on: detection frozen for minutes while the service still said "active".
1. **Video publisher stalled → everything froze.** ffmpeg used wall-clock timestamps; the Pi's clock jumped +21 h at NTP sync (no RTC) and ffmpeg hung; the main loop blocked writing to it (thread in `anon_pipe_write`), so detection, the log **and MAVLink** stopped. Now `Publisher`: own thread, fixed-rate on a monotonic clock (frame-count timestamps), main loop never blocks, watchdog restarts ffmpeg after 5 s. Tested with a simulated hung ffmpeg.
2. **Flight log overwritten** — date-only file name repeated after reboot (clock restored to shutdown time). Now `0001_<date>.csv` run numbers, opened with `x` (never overwrite); `t_s` monotonic.
3. **Frozen sensor starved the whole program** — VL53L5CX froze again (SDA low; power-cycle releases it); its I²C calls hung ~1 s each **holding Python's GIL** (main thread in `futex`, sensor thread in `i2c_dw_xfer`). Now the sensor runs in **its own process** (shared memory), with a watchdog that kills + respawns it (power-cycling the sensor) after 3 s without data. **Test: sensor power cut 6 s → detection kept logging ~29 rows/s, distances correctly absent, reader auto-restarted, distances back.**
- Open question: why the sensor freezes at all (jumper wires, 400 kHz I²C, SATEL power). Try: solder/shorten the wires, then 100 kHz (`dtparam=i2c_arm_baudrate=100000`).
4. **Camera link drops when handled** (3× on 2026-09-30, CM3 on CAM0): libcamera `Camera frontend has timed out! ... check that your camera sensor connector is attached securely` → MediaMTX retries every 6 s but it never recovers until reseat + reboot. Happened even with a **new spare cable** → suspect the connector latches (CM3's tiny camera-end latch first). Reseat both ends + keep the camera fixed and untouched fixed it. If it drops *without* handling: 2nd spare cable, then camera without the HAT. On the drone: rigid mount + strain relief.
5. The detector restart loop during a camera outage left ~80 empty log files → the log is now created at the first processed frame; empties removed. (The `find_vma ... hailo_vdma_buffer_map` kernel WARNING appears at every detector start — harmless, not a cause.)
- Tip: avoid running `rpicam-hello --list-cameras` while MediaMTX streams.

## Pi → FC obstacle reports (MAVLink) — **live on the Pi since 2026-09-30**

**Live test:** laptop `fc_view.py` received from the Pi: `OBSTACLE_DISTANCE` 9 Hz, 8 sectors, heartbeat, alerts like `OBSTACLE object 1.0m ahead`. Fix needed: in udpin mode the Pi must *read* to learn the laptop's address (`recv_msg()` loop in `update()`).

Team FC firmware: **ArduPilot** (version + J11's SERIALn still to ask). The Pi **reports**, ArduPilot decides, the pilot overrides.
- `mavlink_out.py` (Pi): `OBSTACLE_DISTANCE` ~10 Hz (8 sectors across the sensor's 45°, middle 4 grid rows only so floor/ceiling don't count; 65535 = unknown elsewhere, 401 cm = clear), `HEARTBEAT` 1 Hz, `STATUSTEXT` like `OBSTACLE person 1.2m ahead` (max 1/s unless object/side changes). MAVLink 2, ardupilotmega dialect, component OBSTACLE_AVOIDANCE.
- `pi_detect.py --mavlink` (default `udpin:0.0.0.0:14550`; drone: `/dev/ttyAMA0,921600`; SITL: `tcp:<laptop>:5762`; `""` = off). A link problem never stops detection.
- `fc_view.ps1` (laptop): stand-in FC — radar window of what ArduPilot would receive + the alerts. Connects out to `pi5drone:14550` (no firewall rule needed).
- Tested on the laptop with `mavlink_out.py`'s simulated obstacle: 10 Hz, 8 sectors, heartbeat, alerts OK.
- **To do when the Pi is back online** (it went offline at the office 2026-09-29 — replug): copy `pi_detect.py` + `mavlink_out.py` to `~/detect/`, `pip install pymavlink` (done on the laptop; Pi attempt failed while offline), `sudo systemctl restart pi-detect`, then `.\fc_view.ps1`.
- ArduPilot params for later: `SERIALn_PROTOCOL=2`, `SERIALn_BAUD=921`, `PRX1_TYPE=2`, `AVOID_ENABLE=3`, `AVOID_MARGIN=2`, `AVOID_BEHAVE=1`.

## Flight log (2026-09-29)

`pi_detect.py` writes one CSV per run to `~/detect/logs/` (`YYYYMMDD-HHMMSS.csv`), a row per frame (~30/s, ~8 MB/h): `time,t_s,fps,nearest_m,temp_c,detections` — e.g. `11:14:00,14.54,29.9,0.10,58.4,banana 0.42 0.20m`. Trust `t_s` (no internet in the field → the date may be wrong). Copy: `scp "pi@pi5drone:detect/logs/*.csv" .` · off: `--no-log`. Checked: rows written live; restart via SIGTERM left **0** new Hailo errors (clean-shutdown fix confirmed).
Guide: new section **D.0 Bench → flight** (what changes, order of work, the log) + 3 troubleshooting rows from today.

## Remote access — Tailscale (2026-09-28)

Pi `pi5drone` = **[pi-tailscale-ip]**, laptop `[laptop]` = [laptop-tailscale-ip], account `Ivanlim556`. Works from any network once **Tailscale is ON on the laptop** (tray icon → Connect; it was found stopped).
- SSH: `ssh pi@pi5drone` (or `ssh pi@[pi-tailscale-ip]`) — same host key as `pi5drone.local`, checked.
- Pages: `http://pi5drone:8889/detect` and `/cam`. Laptop detection away from the office: `.\detect.ps1 --source rtsp://pi5drone:8554/cam` (`.local` only works on the same WiFi).
- `tailscaled` starts at boot on the Pi. **Node key expires 2027-03-27** → in the Tailscale admin console, *Disable key expiry* for pi5drone.
- The Pi still needs a WiFi to reach the internet: office WiFi, the hotspot, or home WiFi added with `sudo nmtui`.
- **Tested from home 2026-09-28** (home WiFi, Pi at the office): SSH OK, `/detect` in the browser moving (WebRTC), RTSP ~27 fps — through Tailscale's Singapore relay (`relay "sin"`, no direct path). Fallback if WebRTC ever goes black: `http://pi5drone:8888/detect` (HLS, +1–2 s delay).
- **Login on the pages since 2026-09-28:** user **`viewer`** (password: in your password manager / `C:\Users\ivan\.fpv-viewer-pass` — deliberately not written here). Covers `/cam` and `/detect` on 8889 (browser), 8888 (HLS), 8554 (RTSP: `rtsp://viewer:PASSWORD@pi5drone:8554/cam`). The Pi itself (127.0.0.1: `pi_detect.py`) needs no login. Only a `sha256:` hash is on the Pi (`authInternalUsers` in `~/mediamtx/cam.yml`; pre-login backup `cam.yml.bak-noauth`).
- Tested: no/wrong password → 401 on RTSP, browser and HLS; right password → video 28 fps; Pi detector unaffected.
- `detect.ps1` reads the password from `~\.fpv-viewer-pass` and now defaults to `rtsp://pi5drone:8554/cam` (Tailscale name — same command at home and at the office).
- Change the password: new hash `sha256:` + base64(sha256(password)) into `cam.yml` (MediaMTX reloads by itself) + update `~\.fpv-viewer-pass`.

## Distance sensor — ST VL53L5CX (SATEL breakout), after the Hailo

Multizone time-of-flight: **8×8 distance grid**, ~45°×45° view, up to ~4 m indoors (much less in sunlight), ~15 Hz at 8×8. **I²C** (0x29): 3V3, GND, SDA → Pi pin 3, SCL → pin 5, LPn → 3V3. Needs I²C enabled on the Pi.
Plan change: ArduPilot does not read it directly → **sensor → Pi → FC** (Pi sends MAVLink distances). Use with the camera: give each YOLO box a distance / draw the grid on `/detect`.

**Working 2026-09-28.** Wiring (SATEL → top of the AI HAT+): GND→6 · IOVDD→1 (3.3 V) · **AVDD→2 (5 V — the SATEL has its own regulator; correct per ST)** · PWREN→11 (GPIO17) · LPn→13 (GPIO27) · SCL→5 · SDA→3 · I2C_RST→9 (GND) · INT→7 (GPIO4).
- I²C on at **400 kHz** (`sudo raspi-config nonint do_i2c 0` + `dtparam=i2c_arm_baudrate=400000`; 1 MHz is riskier on jumper wires). `i2c-tools` installed; `i2cdetect` is in `/usr/sbin`.
- Power the sensor on without sudo: `pinctrl set 17 op dh; pinctrl set 27 op dh` (lasts until reboot). Then `/usr/sbin/i2cdetect -y 1` shows **29**.
- Driver: `vl53l5cx-ctypes` 0.0.3 (Pimoroni, wraps ST's ULD) in `~/detect/.venv`. Init + firmware upload **2.2 s**, 8×8 at **15 Hz**. Test: `~/detect/.venv/bin/python ~/detect/tof_test.py` (copy in this folder).
- First read gave 0–4 mm everywhere = **protective film still on the sensor**. Removed → real readings (18–47 cm on the bench).
- GPIO: the kit's stacking header only reached flush until the HAT was pushed fully down; now pins stand ~5–6 mm above the HAT, female jumpers hold. Solder for the drone.
- **On `/detect` since 2026-09-28** (`pi_detect.py`, Hailo + sensor): coloured 8×8 grid in cm (red near → green 2 m+), a distance on each box (`cup 0.92  0.21 m` = nearest valid zone inside the box), `nearest X m` top left. The script powers the sensor itself (PWREN/LPn via `pinctrl`); no sensor → runs with boxes only.
- Calibration knobs (defaults set from bench tests): `--tof-flip udlr` (hand test: left/right was swapped with `ud`), `--tof-fov 0.64,1.10` (sensor 45° vs CM3 66°×41°, sensor beside the camera), `--tof-min 0.10` (readings under 10 cm = desk/own frame; they had made a cup at ~25 cm read 0.05 m).
- Cup check: measured by hand ~25 cm → sensor zone 26 cm, box label 0.21 m.
- Safety: an I²C error no longer kills the reader thread, and a grid older than 0.5 s is dropped (a stale distance looks valid).
- Parallax: sensor and camera are a few cm apart, so under ~30 cm the grid is visibly offset from the picture; fine beyond that. On the drone, mount them as close together as possible.
- **Phase 3 gate passed 2026-09-28** (3 boxes as a wall): tape 50 cm → sensor 54–56 cm; tape 100 cm → **98–104 cm**. Error does not grow with distance (no scaling) — the +5 cm at 50 was most likely the tape's start point. ±5 cm.
- The script now power-cycles the sensor (PWREN low → high) at every start: after a knocked wire it answered at 0x29 but was stuck half-started (firmware upload timed out).
- Keep the desk/frame out of the sensor's view.

**Camera fault 2026-09-28 17:30** (while moving the boxes): `imx708 11-001a: Failed to write reg 0x0100. error = -5` → `Failed to start streaming: Input/output error`. Camera still detected (ID read OK) but I²C writes fail at stream start = bad contact on the camera ribbon, probably pinched/creased when the HAT was pushed down. Reseat did not fix it → **moved the same cable to CAM/DISP 0 + reboot → works** (`i2c@88000`, no errors). **The CAM1 connector is faulty** (latch or a contact).
- **Use CAM0 from now on.** MediaMTX / detection need no change (they use the first camera found).
- **AR0234 on card B: `dtoverlay=ar0234,4lane,cam0`** (the power overlay covers cam0_reg too — the Pi 5 version in this folder).
- Always power off before plugging a camera ribbon: the Pi only looks for cameras at boot, and hot-plugging can damage the connector.
- Also seen in dmesg: `WARNING ... find_vma ... hailo_vdma_buffer_map [hailo_pci]` at each detector start — a Hailo driver warning on kernel 6.18, not the cause. Watch it.

## Roadmap (written into the guide, section PLAN — 2026-09-26)

1. **Hailo** → detection off the CPU, 30 fps, same `/detect` page (swap only the detector in `pi_detect.py`).
2. **AR0234** → replaces the CM3; repeat Stage 2+3 gates; greyscale detection benchmark. Snag to expect: MediaMTX's own libcamera may not know the AR0234 → feed `/cam` from the Kurokesu `rpicam-vid` instead.
3. **LiDAR** → distance. Choose single-point (TF-Luna/TFmini) or 360° (RPLIDAR). Plan: LiDAR straight to the FC first (ArduPilot avoids on its own), Pi adds camera info as a second obstacle source.
4. **Avoidance** → Pi sends MAVLink `OBSTACLE_DISTANCE` over the J11 UART; the FC (ArduPilot/PX4 only) decides and flies. Test: simulator → props off → tethered → flight.

## Next

- [x] Stopwatch latency test — 148 ms average. Redo any time: open `latency-test.html`, point the camera at the stopwatch, screenshot (Win+Shift+S) and subtract the two numbers
- [x] 10-minute run without dropouts → Stage 3 gate
- [x] Enable MediaMTX at boot (done 2026-09-25, service `mediamtx` enabled + running)
- [ ] Remote viewing: Tailscale + page password
- [x] Object detection working on the laptop (CPU)
- [x] GPU PyTorch — laptop detection ~30 fps on the RTX 3050 (2026-09-28)
- [x] Object detection on the Pi CPU (`/detect` page) — 15 fps with the fan
- [x] Fan fitted — 66–69 °C at 15 fps, no throttling
- [ ] On-Pi detection at boot — **paused on purpose**; re-enable when object detection work resumes (`sudo systemctl enable --now pi-detect`)
- [ ] Stage 4 when the Hailo arrives (detection on the Pi itself)
