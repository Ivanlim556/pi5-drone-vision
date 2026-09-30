# Laptop: live object detection on the Pi's stream. Extra args pass through, e.g. .\detect.ps1 --test 100
# Python env lives outside OneDrive (C:\Users\ivan\fpv-detect\.venv) so OneDrive doesn't sync 1 GB of packages.
# The stream needs the 'viewer' login: the password is read from ~\.fpv-viewer-pass (outside OneDrive, not synced).
$pw = Join-Path $HOME ".fpv-viewer-pass"
if (Test-Path $pw) { $env:FPV_VIEWER_PASS = (Get-Content $pw -Raw).Trim() }
& "C:\Users\ivan\fpv-detect\.venv\Scripts\python.exe" "$PSScriptRoot\detect.py" @args
