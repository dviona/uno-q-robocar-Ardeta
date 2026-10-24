Qualcomm Hackathon project: a vision-guided soccer robot on Arduino UNO Q. Finds the ball, lines up with the goal, and pushes. Built by Arja, Debbie, Tavish

# UNO Q Robocar

A vision-guided robot car built on the **Arduino UNO Q** and a **Hiwonder miniAuto** chassis. Press the camera's BOOT button and the robot searches for a ball, centers it, approaches, and pushes it toward the goal.

**Team:** [names]  
**Event:** [hackathon name, date]

## How it works

```
ESP32-S3 camera --MJPEG over Wi-Fi--> UNO Q Python (MPU): detect + decide
                                              |
                                        Arduino Bridge
                                              v
                                   UNO Q sketch (MCU): motors, sensors, timed stops
```

- **Camera:** streams 320x240 MJPEG at `http://192.168.5.1:81/stream`.
- **Python (Linux MPU):** reads frames, detects the ball (and goal), and picks the next move.
- **Arduino sketch (MCU):** drives the motors and enforces timed stops.
- **Bridge:** carries commands such as `drive`, `stop` and `read_sensors` between the two.

### Behavior (`python/main.py`)

Each cycle: take a fresh frame, choose one short action, look again.

| State | What it does |
| --- | --- |
| SEARCH | Short rotation pulses until the ball is seen; gives up after a bounded number of pulses |
| ALIGN | Rotates toward the ball until it is inside the center dead band |
| APPROACH | Short forward pulses until the ball is close (image position, size, or ultrasonic) |
| PUSH | Forward pulses toward the goal, bounded by a pulse limit; optional strafing to line the ball up with the goal |

Safety behavior: a stalled camera feed, a ball that is never found, the run time limit, or the BOOT button all end the run.

## Repository layout

```
robocar/
  app.yaml
  Makefile
  scripts/flash.sh
  python/
    main.py            state machine (our code)
    detector.py        HSV colour detector + optional Edge Impulse model (our code)
    camera.py          background MJPEG reader that keeps only the newest frame (our code)
    snap.py            saves frames + detections for tuning (our code)
    robot_client.py    motor/sensor API over Bridge (starter)
    requirements.txt
    *.eim              Edge Impulse model, if used (not committed; see below)
  sketch/
    sketch.ino         motor control, sensors, button, timed stops (starter)
    sketch.yaml
  camera/HiwonderCamStream/HiwonderCamStream.ino   camera firmware (starter, flashed separately)
```

## Setup

You need Arduino App Lab, GNU Make, `zip`, and Android Platform-Tools (`adb`), plus a data-capable USB-C cable.

1. Connect the UNO Q by USB and complete the App Lab board setup.
2. **While the board still has internet**, install the Python dependencies (`python/requirements.txt`). The camera network has no internet.
3. Join the camera's Wi-Fi **from the UNO Q's Linux side**. SSID and password are supplied with the robot.
4. Keep the motor-power disconnect within reach and the wheels raised while testing.

## Run

```sh
make devices     # confirm the board is visible
make flash       # package, deploy, compile, upload, start
make logs        # follow Python output
make monitor     # MCU serial monitor
make stop        # stop the app
```

Short-press the camera **BOOT** button to start a run, and short-press it again to stop. `make flash` replaces `python/` and `sketch/` on the board, so edit locally and re-flash instead of editing in App Lab.

## Tuning

Calibrate with the wheels raised first, then on the floor. Values are at the top of `python/main.py` (`TUNING` block) and `python/detector.py`.

| Setting | What to check |
| --- | --- |
| `HSV_RANGES` (`detector.py`) | Ball colour under the venue lighting; use `snap.py` frames |
| `ROTATE_RIGHT_IS_CLOCKWISE` | Flip if turns go the wrong way |
| `TURN_SPEED`, `FWD_SPEED`, `PUSH_SPEED` | Lowest speeds that move reliably on this floor and battery |
| `*_MS` pulse lengths | Distance/angle produced by one pulse |
| `CLOSE_CY`, `CLOSE_SIZE`, `CLOSE_MM` | When "close enough to push" triggers |
| `ALIGN_GOAL`, `GOAL_TOL_PX` | Goal alignment (needs the trained model) |

**Calibrated values for our robot:** [fill in after testing: speeds, pulse lengths, turn direction, HSV range, battery condition]

Tune the detector with the robot stationary:

```sh
python3 snap.py   # saves annotated frames to data/frames/
```

## Edge Impulse model (optional)

Train a FOMO object detector with classes `soccerball` and `goal` (96x96 input), deploy with target **Arduino UNO Q**, and place the downloaded `.eim` in `python/`. `detector.py` uses it automatically when present and falls back to the colour detector otherwise. The `.eim` is generated from our own project, so it is shared outside git.

## Status

- [ ] Starter runs; BOOT starts and stops the 200 ms test pulse
- [ ] Camera stream read from the UNO Q
- [ ] Motor directions and speeds calibrated
- [ ] Ball detected reliably (left, center, right, near, far, absent)
- [ ] Approach working end to end
- [ ] Push / goal attempt working
- [ ] Backup video recorded

## Safety

The BOOT button is a software stop, not a power cutoff. Keep the physical motor-power disconnect accessible, keep movements bounded (never use duration `0` from Python), and do not enable the inherited `F|1|&` obstacle-avoidance demo.

## Credits

- Starter code, firmware, and track guide: hackathon organizers (Arduino UNO Q robocar track)
- Detection, camera reader, and state machine: [team names]
- Edge Impulse project/data: [credit the source if you cloned the public project]
