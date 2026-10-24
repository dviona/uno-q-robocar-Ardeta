.DEFAULT_GOAL := help

ARDUINO_CLI ?= arduino-cli
ADB ?= adb
SERIAL ?=
ADB_DEVICE = $(if $(strip $(SERIAL)),-s "$(SERIAL)",-d)

.PHONY: help package build flash monitor logs stop devices clean

help:
	@printf '%s\n' \
	  'make package  Create build/uno-q-robocar.zip for App Lab' \
	  'make build    Compile the MCU sketch with arduino-cli' \
	  'make flash    Deploy Python and sketch, compile, upload, and start on UNO Q' \
	  'make monitor  Open the MCU serial monitor (Ctrl+C to leave)' \
	  'make logs     Follow Python app logs (Ctrl+C to leave)' \
	  'make stop     Stop this track app on UNO Q' \
	  'make devices  List connected ADB devices' \
	  'make clean    Remove the generated ZIP and sketch build' \
	  'Use SERIAL=... to select a board; otherwise use the only USB device.' \
	  'Override tool paths with ADB=... or ARDUINO_CLI=...'

package:
	@command -v zip >/dev/null || { echo 'Install zip to package an App Lab application.' >&2; exit 1; }
	mkdir -p build
	rm -f build/uno-q-robocar.zip
	zip -qr build/uno-q-robocar.zip app.yaml python sketch \
	  -x '*/__pycache__/*' '*.pyc' '*/.DS_Store' '*/.venv/*' '*/build/*'

build:
	"$(ARDUINO_CLI)" compile --fqbn arduino:zephyr:unoq --profile default \
	  --build-path "$(CURDIR)/build/sketch" sketch

# App CLI builds and uploads on the board, keeping Python and the MCU paired.
flash: package
	@set -eu; \
	  stage=$$("$(ADB)" $(ADB_DEVICE) shell -T 'mktemp -d /tmp/uno-q-flash.XXXXXX'); \
	  trap '"$(ADB)" $(ADB_DEVICE) shell -T "rm -rf -- \"$$stage\"" >/dev/null 2>&1 || :' EXIT; \
	  "$(ADB)" $(ADB_DEVICE) push build/uno-q-robocar.zip "$$stage/app.zip"; \
	  "$(ADB)" $(ADB_DEVICE) shell -T "sh -s -- \"$$stage/app.zip\"" < scripts/flash.sh

monitor:
	"$(ADB)" $(ADB_DEVICE) shell -t 'TMPDIR=/tmp arduino-app-cli monitor'

logs:
	"$(ADB)" $(ADB_DEVICE) shell -t 'TMPDIR=/tmp arduino-app-cli app logs "$$HOME/ArduinoApps/uno-q-robocar-cli" --follow'

stop:
	"$(ADB)" $(ADB_DEVICE) shell -T 'TMPDIR=/tmp arduino-app-cli app stop "$$HOME/ArduinoApps/uno-q-robocar-cli"'

devices:
	"$(ADB)" devices -l

clean:
	rm -rf build/sketch build/uno-q-robocar.zip
