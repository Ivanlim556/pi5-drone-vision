import time, numpy as np
import vl53l5cx_ctypes as vl53l5cx
t = time.time()
s = vl53l5cx.VL53L5CX()           # uploads the ~84 KB firmware
print(f"init {time.time()-t:.1f} s, alive: {s.is_alive()}")
s.set_resolution(8 * 8); s.set_ranging_frequency_hz(15); s.start_ranging()
n, t = 0, time.time()
while n < 30:
    if s.data_ready():
        d = s.get_data(); n += 1
        dist = np.array(d.distance_mm[0][:64]).reshape(8, 8)
        stat = np.array(d.target_status[0][:64]).reshape(8, 8)
print(f"{n} frames in {time.time()-t:.1f} s")
print("last frame, distance in cm (x = no valid target, status not 5/9):")
for r in range(8):
    print(" ".join(f"{dist[r,c]/10:5.0f}" if stat[r,c] in (5, 9) else "    x" for c in range(8)))
s.stop_ranging()
