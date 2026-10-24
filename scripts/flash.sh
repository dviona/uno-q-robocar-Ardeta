#!/bin/sh
# Runs on UNO Q through ADB; the local checkout owns these three source paths.
set -eu
export TMPDIR=/tmp
app="$HOME/ArduinoApps/uno-q-robocar-cli"

command -v arduino-app-cli >/dev/null || {
    echo 'Arduino App CLI is missing. Complete the UNO Q App Lab setup first.' >&2
    exit 1
}
command -v python3 >/dev/null || {
    echo 'Python 3 is missing from UNO Q Linux. Restore the prepared board software.' >&2
    exit 1
}
if [ -L "$app" ] || { [ -e "$app" ] && [ ! -f "$app/.make-managed" ]; }; then
    echo "Refusing to replace an existing app at $app. Move it aside first." >&2
    exit 1
fi

stage=$(mktemp -d /tmp/uno-q-robocar.XXXXXX)
trap 'rm -rf "$stage"' EXIT
python3 -m zipfile -e "$1" "$stage"
test -f "$stage/app.yaml"
test -f "$stage/python/main.py"
test -f "$stage/sketch/sketch.ino"
test -f "$stage/sketch/sketch.yaml"

if [ -f "$app/app.yaml" ]; then
    arduino-app-cli app stop "$app"
fi
mkdir -p "$app"
touch "$app/.make-managed"
# Replace source directories so deleted local files cannot linger on the board.
rm -rf "$app/python" "$app/sketch"
mv "$stage/app.yaml" "$app/app.yaml"
mv "$stage/python" "$stage/sketch" "$app/"
arduino-app-cli app start "$app"
