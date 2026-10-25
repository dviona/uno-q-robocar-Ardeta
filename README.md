# Ardeta — UNO Q Robocar

Vision-guided ball approach and goal-push attempts on Arduino UNO Q and the Hiwonder miniAuto chassis. Built by **Arja Sadhukhan (@coding-jedi-ninja), Tavish Hookoom (@tavishh), and Debbie Viona (@dviona)**.

This branch preserves the application exported from the event robot on October 24, 2026, including its calibrated runtime settings and both Edge Impulse model versions. Application source matches the export; generated Python bytecode is excluded. `export-manifest.json` records the source-file Git blob hashes. No scoring success or model accuracy is asserted by this source import.

## Application layout

```text
app.yaml
python/
  main.py             App Lab entry point and BOOT-controlled lifecycle
  autonomy.py         MJPEG reader, HSV / Edge Impulse detection, decision loop
  config.json         exported mode, model, direction mapping and tuning
  robot_client.py     Bridge motor/sensor client
  requirements.txt    exported Python dependencies
  *.eim               v1 and v2 Linux aarch64 executable model exports
sketch/
  sketch.ino          MCU motor control, sensors, button and timed stops
  sketch.yaml         exported sketch build profile
camera/               separately flashed ESP32-S3 camera firmware
scripts/flash.sh       terminal deployment helper
Makefile
```

The camera, packaging/deployment helpers and starter reference documents are retained from this repository's existing main branch. The application files and models come from the final App Lab export. The camera firmware is a supplied reference, not a readback of the event camera.

## Run on UNO Q

1. Raise the wheels and keep physical motor-power disconnection accessible. Connect UNO Q to your computer by USB.
2. Run `make package` from the repository root. Import `build/uno-q-robocar.zip` through Apps / My Apps in Arduino App Lab and select UNO Q.
3. Run while UNO Q still has Internet to install `python/requirements.txt`. The export declares `edge-impulse-linux`; image decoding also imports OpenCV (`cv2`) and NumPy, which must be available in the app environment. Resolve missing packages before switching Wi-Fi.
4. Connect **UNO Q Linux itself** to the camera access point using the supplied credentials. Keep USB connected: the camera network has no Internet. Stream URL is `http://192.168.5.1:81/stream`, 320×240. Close any browser preview before Python opens the single-client stream.
5. Start the application in App Lab. A short press/release of the camera BOOT button starts the routine after countdown; another short press stops it. App Lab Run launches the application but does not itself start driving.

**Exported default mode is `score`.** For a new kit, change `mode` to `observe` before pressing BOOT for stationary vision checks, then use `motion` for one-pulse direction checks. Verify the exported calibration against the actual chassis before returning to `score`.

Optional terminal deployment: `make devices`, `make flash`, `make logs`, and `make stop`. Use `SERIAL=...` with multiple boards. Flash replaces the terminal-managed Python and sketch source folders; save board-only edits first.

## Exported configuration

| Setting | Event export value |
| --- | --- |
| Detector / selected model | `edge_impulse` / v2 `.eim` |
| Confidence threshold | 0.5 |
| Run limit | 120 seconds |
| Approach / near speed | 140 / 120 |
| Approach or lateral pulse | 220 ms |
| Push pulse / maximum pushes | 250 ms / 5 |
| Center band | 0.10 normalized image width |
| FOMO close-ball cue | bottom of merged detection at normalized y ≥ 0.65 |
| Manual starting alignment | `prealigned_goal: true` |
| Unknown ultrasonic permitted | `allow_unknown_ultrasonic: true` |
| Valid-distance cutoff | 80 mm |
| Missed-detection tolerance | 8 additional observations while stationary |
| Direction calibration | logical forward↔backward and left↔right reversed |

All values are editable in `python/config.json`. Edit the imported copy in App Lab and restart, or repackage/deploy local changes. Imported apps are copies of the ZIP, not live links to this checkout.

## Perception and actions

The background reader continuously drains MJPEG and retains one decoded frame. After a short movement, the next decision requires a frame arriving after the settling interval. The Edge Impulse adapter loads the configured Linux aarch64 `.eim`, uses the Studio preprocessing helper, and maps `soccerball` and `goal` labels. It joins nearby FOMO cells into detections and rejects multiple qualifying blobs as ambiguous. Proximity uses the ball's vertical image position; the alternative HSV detector uses apparent width.

The loop laterally centers a detected ball, approaches with bounded forward pulses, and pushes when close. It does **not** search by rotating or plan a path around the ball. With manual alignment enabled, place the robot behind the ball in a clear lane into the goal. With manual alignment disabled, a goal detection and a compatible horizontal alignment are required. Missing ball detections cause stationary retries up to the configured limit; exhausted retries, camera errors, expired arrivals, valid insufficient-clearance readings, BOOT stop, run limit or push limit end the run.

## Models and limitations

Both model versions are included as executable Linux aarch64 binaries; v2 is selected. They are not runnable on macOS. The original training project, labeled dataset, and evaluation report were not included in the export, so these binaries reproduce inference but not training. Do not infer training-data provenance or accuracy from the filenames.

A completed attempt is not automatic proof of a goal. Unknown ultrasonic readings are allowed in the exported settings, and a forward sensor does not protect sideways motion. Camera arrival timestamps do not establish image capture freshness. The MCU timer bounds motor output only while its loop is serviced; BOOT is a software stop. Keep a physical disconnect available.

## Validation and credits

Source import validation: ZIP integrity, Python syntax, JSON parsing, configured model presence, source/model blob hashes, executable modes and App Lab package layout. No physical robot or camera was available for this import; the aarch64 models were not executed on the development Mac.

Starter code, motor client, MCU firmware and camera firmware: hackout organizers / [uno-q-hackout](https://github.com/aaishikasb/uno-q-hackout). Model inference: Edge Impulse Linux SDK; images: OpenCV and NumPy. Controller development included OpenAI Codex assistance. See `STARTER_README.md` for the supplied hardware and API reference.
