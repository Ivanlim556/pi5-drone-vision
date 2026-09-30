# Run on the laptop (PowerShell): .\view-stream.ps1
# -framerate 60 makes ffplay read faster than the Pi sends, so frames never pile up (fixed the 20 s delay).
# udp://0.0.0.0 not udp://@ -- this Windows ffmpeg build rejects the @ form.
$ff = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffplay.exe"
& $ff -fflags nobuffer -flags low_delay -framedrop -probesize 32 -analyzeduration 0 -sync ext -f h264 -framerate 60 -window_title "Pi FPV" udp://0.0.0.0:5600
