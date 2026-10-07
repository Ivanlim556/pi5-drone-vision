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
- **Phase 3 gate passed 2026-09-28** (3 boxes as a wall): tape 50 cm → sensor 54–56 cm; tape 100 cm → **98–104 cm**. Error does not grow with distance (no scaling) — the +5 cm at 50 was most likely the tape's start point. maximum error 6 cm (+4–6 cm at 50 cm, −2/+4 cm at 1 m).
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

## 2026-10-01: sensor freeze test (100 kHz) + handover page
- Baseline at 400 kHz: 0 sensor restarts in 4 h 10 min of this boot; log `0087_*` shows ~9 distance updates/s, no stale rows.
- Trying `dtparam=i2c_arm_baudrate=100000`. Cost: the firmware upload takes ~9 s instead of ~2 s, and the grid rate may drop below 15 Hz. The watchdog's startup allowance was raised from 8 to 20 s so the slower upload can't trigger a restart loop.
- `mavlink_out.py` now accepts `device,baud` (e.g. `/dev/ttyAMA0,921600`) for the J11 UART.
- `HANDOVER.html` written for teammates (system overview, SSH login, commands, FC bench test, wiring, troubleshooting).
- After reboot at 100 kHz (15:45): sensor started fine, 0 restarts, 0 I2C errors. Update rate ≈ 6–7/s (63 distance changes in 10 s on a cup at 0.55 m), down from 15 Hz — the ~1.4 KB grid read is bus-limited. Nearest stays 0.10 m even facing a wall: something sits right in front of one edge zone (wire/box edge?) — check.
- Next: soak 1–2 days. Freezes still → speed isn't the cause, back to 400 kHz + solder wires. No freezes → try 200 kHz (~12/s).
- 2026-10-02: 100 kHz run reached ~22 h with 0 freezes, camera 0 errors. **Decision: stay at 100 kHz** (~6-7 grids/s is enough for slow indoor flight). 200 kHz is optional, before faster flights.

## AR0234 lens chosen (2026-10-02)
- Kit (box sheet photos in `cmos camera\`): lenses labelled by HFOV on a 1/2.8" cam: 20=M2516ZH01 16 mm, 25=M2512ZH03 12 mm, 40=M2508ZH02 8 mm, 55=M2506ZH04 6 mm, 70=M2504ZH05S 4 mm, 80/90 ~2.8 mm (M25..H06S / M2728..M07S), 125=M27210H08 2.1 mm, 150 ~1.9 mm, 180=M25170H12 1.7 mm (80-180 mapped by focal order).
- **Using the 70° lens (M2504ZH05S, 4 mm, 1/2.5")**: ~70° across on the AR0234, like the CM3 (66°), low distortion. Backup: 55° (6 mm, ~53°). Focus at 3-5 m and lock (ad12); re-check `--tof-fov` by hand test (CM3 value 0.64,1.10 should be close).

## 2026-10-05: AR0234 arrival day
- Board arrived (designed by Ivan; M12 holder + 70° lens fitted). In CAM0.
- First tries: `failed to read chip id` (-121), nothing on i2c-10 even with EN_RAW forced high (`pinctrl set 34 op dh` = camera power on without sudo). Meter: **0 V across C24 (+3V3)** → no power reaching the board. Two cables failed the same way. **Cause: cable direction** — flipped it → works. (Rule: blue stiffener = no-contact side; at J1 the contacts face the board.)
- Easy test points (from the netlist): 10 µF caps C24 = +3V3, C21 = +2V8, C22 = +1V8, C23 = +1V2; GND at J2 pin 3.
- **13:07 `Success reading chip id: 0xa56`**, `Using sensor ar0234 10-0010 for capture`. Driver probes at boot by itself (the earlier "didn't bind" was really a failed probe).
- **0x0A56 = COLOUR AR0234** per the driver (0x1A56 = mono); bus format SGRBG10 (Bayer). The BOM orders AR0234CSSM00SUKA0-CP (mono) → the fitted part may be colour — confirm with the first picture, tell the team. Colour is fine (better) for YOLO.
- Stock libcamera: `Could not create camera helper for ar0234` → `rpicam-hello` "No cameras available"; MediaMTX's bundled libcamera fails the same way. Kurokesu libcamera is the same base (0.7.2+rpt20260817) + AR0234 support; simulated install: 5 packages upgraded, **0 removed** (rpicam-apps left stock — swapping those would drop rpicam-apps-hailo-postprocess/-lite).
- **Sensor is MONO** (as the BOM says) although it reports 0x0A56: raw frame Gr/R/B/Gb = 234.9/234.9/239.0/238.9 (equal; a colour part would read R,B ≈ half of G). The driver took it as colour → purple-tinted picture.
- Fix: `ar0234-force-mono.patch` (this folder) adds `force_mono` to the Kurokesu driver; applied to `/usr/src/ar0234-rpi-dkms-0.1.2`, rebuilt with dkms, enabled by `/etc/modprobe.d/ar0234.conf` = `options ar0234 force_mono=1`. Now `Y10`, `[1920x1200 10-bit MONO]`, libcamera uses `ar0234_mono.json`, clean grey picture. Undo: delete the modprobe file + reboot. (A Kurokesu driver update would drop the patch — re-apply.)
- Installed Kurokesu libcamera (5 pkgs, `1:0.7.2+rpt20260817+krks4-1`). Undo: same packages with `V=0.7.2+rpt20260817-1 --allow-downgrades`.
- Sensor modes: 960x600 @236 (binned, full view), 1280x720 @198 (**centre crop** — narrows the view), 1920x1080 @133, 1920x1200 @120.
- **/cam now fed by rpicam-vid** via MediaMTX `runOnInit` (MediaMTX's own libcamera can't open the AR0234): full 1920x1200 sensor → 1280x800, 30 fps, H.264 3 Mbit/s. Config copy: `mediamtx-cam-ar0234.yml`; CM3 version on the Pi `~/mediamtx/cam.yml.bak-cm3`. `/detect` works unchanged: 29.9 fps, 52 °C, throttled=0x0.
- Passed: ad7, ad9, ad10, ad11, ad14 (stream). The ad2 short check and ad4 cable beep test were not reported — the board powers and runs normally, but do them before soldering/flying. Next: ad12 focus, ad13 orientation, `--tof-fov` re-check, ad15 latency, ad16 10-min run, ad17 cold boots.
- 17:12: `--ev 0.5` added to the /cam rpicam-vid line (brighter auto-exposure). Frame mean ~100 (was ~48 in the same room earlier). Undo: remove `--ev 0.5` from `~/mediamtx/cam.yml`. For flight later: `--exposure sport` or `--shutter 4000 --gain 4` against motion blur.
- **ad13 passed** (text reads normally, no flip). **ad16 passed** 17:14–17:24: detection 29.9 fps every 30 s, 63–65 °C, throttled=0x0, 0 camera restarts, 0 camera-link (rp1-cfe/ar0234) errors, 0 sensor restarts.
- `pi_detect.py`: `--tof-fov` default now follows the `camera` setting (`default_tof_fov()`): AR0234 + 4 mm lens 0.58,0.92 (71.5°x48.5°), CM3 0.64,1.10. Deployed; takes effect after `sudo systemctl restart pi-detect`, then hand test.
- **Sensor alignment for AR0234 done** (sensor right of the camera, turned 90°): `--tof-flip` default now `lrt` with the AR0234 (flips run before the transpose), `--tof-fov` 0.58,0.92. Tested 17:48–17:50 at ~1 m: torso/arm 102–129 cm where the camera sees them, background 250–314 cm above. Took 3 tries: udlr (sideways), udlrt (mirrored), t (upside down), lrt OK. CM3 keeps udlr / 0.64,1.10. A hand alone at 1 m is too small to fill a zone (45°/8 = 5.6° per zone ≈ 10 cm at 1 m).
- **ad15 latency: ~180 ms** (screenshots 17:55: 135.262−135.08x, 147.588−147.40x, 157.685−157.?98), vs CM3 148 ms. Extra ~35 ms = the rpicam-vid → ffmpeg → MediaMTX hop (ffmpeg also ~40% CPU). Accepted for now. Possible fix if needed: rpicam-vid `--libav-format rtsp -o rtsp://127.0.0.1:8554/cam` directly (drops ffmpeg). `latency-test.html` now points at `pi5drone` (Tailscale name).
- **ad17 cold boots: accepted provisionally** — ~10 rounds (poweroff, unplug 10 s, replug). Recorder `~/bootcheck.sh` (user crontab `@reboot`, writes `~/bootcheck.log` 60 s after boot: chip ID via `journalctl -k -b`, /cam via ffprobe) caught only 2 boots (rounds were shorter than its 60 s wait): both `Success reading chip id: 0xa56`, /cam 1280x800, throttled=0x0. Flight logs 0096–0103 (18:00–18:11) all have video frames → no failed camera seen. **Redo properly (2 min per round, 10/10 in bootcheck.log) before flight tests.** Note: `journalctl --list-boots` only lists the current boot on this Pi, and dmesg loses the chip-ID line within minutes (Hailo warning spam) → use `journalctl -k -b`.
- **ad18:** mono does not hurt detection (not like-for-like scenes): person 0.80 (CM3 0.70), chair 0.56 (0.45), tv 0.50 (0.47), laptop 0.73; a few stock-model false positives (umbrella 0.45, airplane 0.54).
- `camera` script updated (this folder): also copies `~/mediamtx/cam-<camera>.yml` → `cam.yml` (both files now on the Pi; tested on copies). **To install (sudo):** `sudo install -m 755 ~/camera.new /usr/local/bin/camera`.
- **Paused 18:2x (hotspot leaving). Still to do:** install `camera.new`; guide update with arrival-day results (tick ad3, ad7–ad16, ad18; ad17 provisional); GitHub commit (pi_detect.py, camera, ar0234-force-mono.patch, bootcheck.sh, cam-ar0234.yml with the hash replaced by the placeholder, latency-test.html, PROGRESS) + pre-release v2.0-ar0234; ad19 fan demo; ad2/ad4; HANDOVER.html: add the AR0234 notes.
- **Done 20:4x:** guide v42 (arrival-day results, ticks, 2.6 as run); GitHub `f3bb571` + pre-release **v2.0-ar0234** (README "AR0234 setup", placeholder hash only); HANDOVER.html AR0234 notes (cable direction, mono patch, troubleshooting). Still open: install `~/camera.new` (sudo), ad17 retest, ad2/ad4, ad19 fan demo.
- 2026-10-05: **ad17 full 10/10 retest skipped by decision** — stays at 2/2 recorded + no failures seen; the boot recorder stays installed if it is ever wanted.
- 21:09: new `camera` switch installed in /usr/local/bin (identical to `camera.new`); `sudo camera cm3|ar0234` now swaps cam.yml too.
- **Scope (2026-10-05):** auto-avoidance in ArduPilot (AVOID_*/OA_* tuning, SITL, flight behaviour) is the **FC teammates'** job. Ivan's part ends at the Pi → FC interface: correct OBSTACLE_DISTANCE/HEARTBEAT/STATUSTEXT over MAVLink (live-verified 2026-10-05: 51 obstacle msgs in 6 s, 8 slices, frame 12).

## 2026-10-05 evening: v2.0 final, handover
- Cold-boot retest **cleared** (not needed). Drone mounting will most likely not be done within the internship → handed over to the team.
- GitHub: v2.0-ar0234 made the final/latest release; README "Status and handover"; hardware/ar0234-board/ with schematic, Gerbers, BOM, CPL, photos; AR0234 /detect picture + FC radar picture (`fc_view.py --test 4 --save`).
- HANDOVER.html 9 rewritten: done / left for the team (FC bench test → J11 → avoidance (FC team) → mounting) / before Ivan leaves (GitHub collaborators or transfer, passwords, Tailscale).
- GitHub: docs/HANDOVER.html (password-free copy) added + linked; description and topics updated. Collaborators: none added by choice — Ivan may switch the repo to public later (needs clearance: in-house designs; public would also show WiFi names/IPs in PROGRESS and the work email in commit authors).

## 2026-10-06
- Office WiFi very jittery this morning (ping laptop→Pi 2–220 ms, Pi→router max 100 ms; Pi signal 68 %, 2 viewers open) → stream delay + smear. Pi itself fine (29.8 fps, 5.12 V, throttled=0x0).
- VL53L5CX: 147 restarts in 14 min after carrying the Pi back to the office → jumpers re-seated → 0 restarts/min, 93 % rows with distance. Tape/solder the wires.
- Drone power plan: **Matek BEC12S-PRO** (9–55 V in, default 5.2 V, 5 A cont/9 A peak, NO reverse-input protection) → USB-C pigtail → Pi power port; then `PSU_MAX_CURRENT=5000`. Added to guide D.2 (v45) and HANDOVER.
- Drone battery: **6S LiPo 10000 mAh 60C (JMP Leopard)** — 25.2 V full / 22.2 V nominal, inside the BEC12S-PRO 9–55 V range (UBEC DUO max 26 V would be too tight). Noted in guide D.2.
- 15:09 AR0234 stream died: `Camera frontend has timed out! check that your camera sensor connector is attached securely` every second (rpicam-vid retrying) → ribbon contact disturbed (handling during BEC work). Power off + reseat both ends (same direction, slack loop) → 16:52 back: /cam 1280x800@30, detect 29.9 fps, distances 300/300. Two loose-contact faults today (sensor jumpers, camera ribbon) → strain-relieve the ribbon and tape/solder the jumpers before moving the rig.

## 2026-10-07
- **Second AR0234 board (board 2) works**: swapped onto the same ribbon/CAM0 (same direction) → `Success reading chip id: 0xa56` (same ID as board 1 → force_mono covers it), /cam 1280x800@30, mono (B/G/R 103/105/105, no tint), 0 errors, 60 °C. No software change. Lens still to focus (sharpness 3.6). → design proven on 2 boards.
- Board 2 with board 1's holder + 70° lens (focus untouched): chip ID 0xa56, 0 errors, **sharp picture (sharpness 24.6)** — board-to-board sensor height is close enough that a pre-focused holder+lens carries over. The first holder tried on board 2 was the wrong type (could not reach focus).
- Lens vs pixel-array centre: datasheet note 12 — optical centre = package centre + (−1.271, −0.148) mm (toward A1). This board: U1 package centre 1.042 mm from the holder-hole midpoint → array ≈0.23 mm (≈3°) or ≈2.3 mm (≈30°) off depending on A1 orientation; camera-vs-ToF tests within 1–2 zones (mostly parallax, sensor right of camera) → small case. Ivan plans a better design: GitHub hardware README now has "Further improvements (next revision)" (optical centring, ribbon-direction silkscreen, test pads, TRIGGER/MIPI/FLASH, VL53L5CX on the camera board, mechanics).
- **Board 3 works**: chip ID 0xa56, /cam 1280x800@30, 0 camera errors, mono (B/G/R 92/94/94), 44 °C, throttled=0x0, sensor 0 restarts. Picture recognisable, slightly soft (near subject ~0.6 m vs lens focused for 3–5 m). **Tally: 3 of 3 boards working.**
- **14:01 Hailo stall:** `HAILO_VDMA_LAUNCH_TRANSFER failed due to invalid address` → det() blocked forever; service still "active", /detect + log + MAVLink dead (CPU 0 %). Likely the hailo_pci/kernel 6.18 VMA issue behind the `find_vma` warnings. **Fixes in pi_detect.py:** (1) faulthandler stall watchdog — no frame for 15 s → stack dump + exit(1) → systemd restart (C-level timer, works even if the stuck call holds the GIL; tested on the Pi); (2) Hailo fails to open → fall back to CPU yolo11n-320.onnx at 15 fps (seen working at 14:07); (3) Hailo close limited to 5 s (the wedged close made systemd wait 90 s then SIGKILL). Power cycle reset the Hailo → back to 29.9 fps.
- **Board 4 works**: chip ID 0xa56, /cam 1280x800@30, 0 camera errors, mono (B/G/R 86/88/88), 51 °C, throttled=0x0, Hailo present. Picture recognisable, soft at ~0.5 m (lens set for 3–5 m). **Tally: 4 of 4 boards working.**
- **Board 5 works**: chip ID 0xa56, /cam 1280x800@30, 0 camera errors, mono (B/G/R 111/113/113), 56 °C, throttled=0x0. Picture clear (room, shelf, boxes). **Tally: 5 of 5 boards working.** (14:15 earlier: board 4 lost ribbon contact while being handled → reseat fixed; 14:2x office WiFi 300–600 ms ping → lag, not the Pi.)
- 14:5x **Board 1 stopped answering** (`failed to read chip id`, nothing on i2c-10 with EN_RAW forced) right after its holder/lens was swapped for the 80° lens. Re-seat, then a new cable: still fails. **Board 2 on the same new cable + Pi: works** (chip ID 0xa56, 1280x800@30) → the cable and the Pi CAM0 are fine; **board 1 is the problem** (damaged or disturbed during the holder swap). To do: measure C24/C21/C22/C23 on board 1, inspect J1 latch/contacts and around U1/U5 under a magnifier.
- 16:01 board 1 on CAM0 with the cable that just worked on board 2 (board 2 ran 27 min, 1 self-recovered dropout): **still failed to read chip id** → board 1 confirmed faulty (not cable/Pi). Suspect J1 (pressed into the table while the holder was screwed on — J1 is on the opposite side) or a disturbed part. Next: C24 measurement + magnifier on J1/U1/U5.
