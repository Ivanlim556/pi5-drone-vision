# Distance sensor (VL53L5CX "LiDAR") — how it is connected, how it works, how the numbers are made

The camera + YOLO say **what** something is and **where in the picture**; this sensor says **how far** it is.
Avoidance runs on the distances — an object YOLO doesn't know (a wall, a box) is still an obstacle.

## 1. The sensor

| | |
|---|---|
| Part | **ST VL53L5CX** on the **VL53L5CX-SATEL** breakout board |
| Principle | multizone time-of-flight: a 940 nm infrared laser (VCSEL) flashes, the sensor times the light coming back per zone |
| Zones | **8 × 8 = 64**, each its own distance |
| Field of view | **45° × 45°** (63° diagonal) — each zone ≈ **5.6° × 5.6°** (≈ 10 cm at 1 m, 20 cm at 2 m, 40 cm at 4 m) |
| Range | ~2 cm to **~4 m** indoors on a white target; shorter on dark surfaces and **much shorter in bright sunlight** |
| Rate | set to 15 Hz; **~6–7 grids/s in practice** (the I²C bus at 100 kHz can't move a full grid faster) |
| Bus | I²C, address **0x29** |

## 2. Wiring (SATEL → Raspberry Pi 5 GPIO header, on top of the AI HAT+)

| SATEL pin | Pi pin | What |
|---|---|---|
| GND | 6 | ground |
| IOVDD | 1 | 3.3 V for the I²C / logic side |
| AVDD | 2 | 5 V — the SATEL has its own regulator for the sensor |
| SCL | 5 | I²C clock (GPIO3) |
| SDA | 3 | I²C data (GPIO2) |
| PWREN | 11 | GPIO17 — powers the sensor on/off (the software uses it to reset a frozen sensor) |
| LPn | 13 | GPIO27 — low-power pin, held high = active |
| I2C_RST | 9 | tied to GND (not used) |
| INT | 7 | not used (the software polls) |

Boot config: `dtparam=i2c_arm=on`, `dtparam=i2c_arm_baudrate=100000` — **100 kHz, not 400 kHz**: at 400 kHz the
sensor froze now and then (SDA held low); at 100 kHz it ran 77 h with 0 freezes.

**Mounting (AR0234 rig):** the sensor stands **9.5 cm beside the camera lens**, both **upright and facing straight
ahead, parallel**. The sensor board is **turned 90°** relative to the camera. Keep the whole rig on one rigid base
and strain-relieve the jumper wires (they came loose three times when the rig was carried) — or solder them.

## 3. From light to a distance grid (`pi/pi_detect.py`, `_tof_worker` + `ToF`)

```
 power-cycle (PWREN low→high) → upload sensor firmware (~84 KB, ~9 s at 100 kHz) → 8×8 mode, 15 Hz → ranging
   every grid:
     distance_mm[64] + target_status[64]
       → keep zones with status 5 or 9 (= valid target), others → no value (NaN)
       → drop readings closer than 10 cm (--tof-min 0.10: the desk / the drone's own frame)
       → mm → metres
       → re-orient to match the camera picture (--tof-flip: AR0234 rig "lrt" = flip + swap rows/cols, CM3 "udlr")
       → shared memory, with a timestamp
```

- The reader runs in **its own process**: if the sensor freezes, only its readings stop — detection, video, the
  flight log and MAVLink carry on.
- **Watchdog:** no fresh grid for **3 s** → the reader is killed, the sensor power-cycled, reading restarts
  (allowing 20 s for the firmware upload after each start).
- **Freshness:** a grid older than **0.5 s** is thrown away — a stale distance looks valid and is worse than none.

## 4. Matching the grid to the camera picture

**Field of view.** The sensor sees 45°; the AR0234 with its 70° lens sees ~71.5° × 48.5°. So the 8×8 grid covers
only the **middle part** of the picture:

```
fraction across = tan(22.5°) / tan(71.5°/2) = 0.58      fraction up/down = tan(22.5°) / tan(48.5°/2) = 0.92
```
(`--tof-fov 0.58,0.92` for the AR0234 rig, `0.64,1.10` for the CM3). The outer ~20 % on each side of the picture
never gets a distance — that is the sensor's view, not a fault.

**Parallax.** Sensor and lens are 9.5 cm apart, so they see a near object from slightly different places. Each
zone is shifted sideways in the picture by

```
shift (pixels) = f × baseline / d          f = (picture width / 2) × 0.58 / tan(22.5°) ≈ 896 px,  baseline = 0.095 m
```
using **that zone's own distance d** — like a stereo camera: 170 px at 0.5 m, 85 px at 1 m, 43 px at 2 m, 21 px at
4 m (`--tof-baseline 0.095`; 0 = off). Without it, a box 50 cm away picked up the wall's distance; with it, its own.

**Distance of a detected object.** For each YOLO box: the **nearest valid zone whose (shifted) centre lies inside
the box** → `person 0.80  48 cm` on `/detect`, and in the flight log.

**On `/detect`:** each zone with a value is drawn as a square with its distance in cm — **red = near, green = 2 m
or more**; no square = no valid reading. `nearest X cm` (top left) is the closest zone in the whole grid.

## 5. What the flight controller gets (`pi/mavlink_out.py`)

The FC does not see the picture — only directions and distances. About **10 times a second**:

```
8×8 grid → keep the middle 4 rows (rows 2–5 ≈ ±11° up/down: the floor and ceiling don't count as obstacles)
         → per column: the nearest distance → 8 values, left → right
         → OBSTACLE_DISTANCE (MAVLink 2), body frame (FRD)
```

| Field | Value |
|---|---|
| `distances[0..7]` | the 8 columns, **left → right**, in cm (10–400) |
| `distances[8..71]` | **65535 = no information** (no sensor there — sides and back) |
| a column with no valid zone | **401 = "clear to max range"** |
| `increment_f` / `angle_offset` | 5.625° per slice; first slice centred at −19.69° (left of the nose) |
| `min_distance` / `max_distance` | 10 / 400 cm |
| also | `HEARTBEAT` 1 Hz (companion computer alive), `STATUSTEXT` when something is within 1.5 m, e.g. `OBSTACLE person 64cm left` (at most once a second unless the object or side changes) |

The Pi **reports, it never commands**: the FC's own avoidance (ArduPilot `PRX1_TYPE=2`, `AVOID_*`) decides how to
react, and the pilot always overrides. See it on a laptop with `laptop\fc_view.ps1` (radar of exactly these messages).

## 6. Accuracy and tests

- **Tape measure, against a wall of boxes (2026-09-28):** 50 cm → 54–56 cm, 100 cm → 98–104 cm → **maximum error 6 cm**.
- **Stability at 100 kHz:** 22 h and 77 h runs with 0 freezes; one overnight run 99.99 % of frames had a distance.
- **Alignment:** camera vs grid checked with a hand / bottle / arm at 0.5–1 m (`lrt`, `0.58,0.92`, `0.095`).

## 7. Limits — know these before relying on it

- **Only 45° forward.** Nothing to the sides or behind — on the FC those directions are "no information".
- **No reading is reported as "clear" (401).** Correct for open space beyond 4 m, but **glass, mirrors and very dark
  or steeply angled surfaces may return nothing and look clear too**. Also in strong sunlight the range drops.
- **Small things far away:** a hand at 1 m is smaller than one zone (~10 cm) and may not register.
- **Below 10 cm** everything is ignored on purpose.
- **Parallax / tilt:** move or tilt the sensor and the squares no longer sit on the right objects — re-set
  `--tof-baseline` and stand it upright (a ~10° backward lean put the readings ~2 rows low).

## 8. Troubleshooting

| Symptom | Check / fix |
|---|---|
| No distances at all | `pinctrl get 2,3` — both should read `hi`. A line stuck `lo` = a wire off or a frozen sensor: power off, re-seat the jumpers (pins 1, 2, 3, 5, 6, 9, 11, 13) |
| Distances come and go, `VL53L5CX reader restarted` in `journalctl -u pi-detect` | a loose jumper (usually after the rig was moved) — re-seat, tape the bundle |
| Every zone reads 0–4 mm | the protective film is still on the sensor |
| Box shows the wall's distance, squares off to one side or too high/low | sensor moved or leaning: upright, parallel to the lens, gap as in `--tof-baseline` |
| Test it on its own | stop detection (`sudo systemctl stop pi-detect`), then `~/detect/.venv/bin/python ~/detect/tof_test.py` prints the 8×8 grid |
