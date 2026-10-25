"""Visual control for a calibrated robot in a clear, initially aligned lane."""
import contextlib
from dataclasses import dataclass
import json
import math
from pathlib import Path
import threading
import time
from urllib.request import urlopen


@dataclass(frozen=True)
class Detection:
    x: float
    width: float
    quality: float
    y: float = 0.0


def load_config():
    config = json.loads(Path(__file__).with_name("config.json").read_text())
    if config["mode"] not in {"observe", "motion", "score"}:
        raise ValueError("mode must be observe, motion, or score")
    for key, low, high in (
        ("run_seconds", 1, 120), ("frame_timeout", 0.1, 3),
        ("max_frame_age", 0.05, 1), ("settle_seconds", 0.05, 1),
        ("speed", 1, 180), ("near_speed", 1, 180),
        ("pulse_ms", 20, 250), ("push_ms", 20, 250),
        ("max_pushes", 1, 5), ("center_band", 0.01, 0.3),
        ("goal_tolerance", 0.01, 0.3), ("close_ball_width", 0.05, 0.8),
        ("minimum_clearance_mm", 20, 500), ("close_ball_y", 0.1, 1),
        ("max_missed_frames", 0, 20),
    ):
        value = config[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be {low}..{high}")
    for key in ("pulse_ms", "push_ms", "max_pushes", "speed", "near_speed", "max_missed_frames"):
        if type(config[key]) is not int:
            raise ValueError(f"{key} must be an integer")
    for key in ("motion_calibrated", "allow_unknown_ultrasonic", "prealigned_goal"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} must be true or false")
    if config["mode"] == "score" and not config["motion_calibrated"]:
        raise ValueError("Verify physical motion first, then set motion_calibrated true")
    if config["motion_direction"] not in {"forward", "backward", "left", "right", "rotate_left", "rotate_right"}:
        raise ValueError("Unknown motion_direction")
    directions = {"forward", "backward", "left", "right", "rotate_left", "rotate_right"}
    if not isinstance(config["direction_map"], dict) or not all(
            k in directions and v in directions for k, v in config["direction_map"].items()):
        raise ValueError("direction_map must map direction names to direction names")
    if config["detector"] not in {"opencv", "edge_impulse"}:
        raise ValueError("detector must be opencv or edge_impulse")
    if config["detector"] == "edge_impulse":
        if not isinstance(config["model_path"], str) or not config["model_path"]:
            raise ValueError("edge_impulse detector needs model_path")
        if type(config["min_confidence"]) not in (int, float) or not 0 < config["min_confidence"] <= 1:
            raise ValueError("min_confidence must be 0..1")
    for name in ("ball", "goal"):
        settings = config[name]
        if not settings["ranges"]:
            raise ValueError(f"{name}: at least one HSV range required")
        for lower, upper in settings["ranges"]:
            if len(lower) != 3 or len(upper) != 3:
                raise ValueError(f"{name}: HSV bounds need three channels")
            for lo, hi, maximum in zip(lower, upper, (179, 255, 255)):
                if type(lo) is not int or type(hi) is not int or not 0 <= lo <= hi <= maximum:
                    raise ValueError(f"{name}: invalid HSV range")
        if not 1 <= settings["min_area"] <= 76800:
            raise ValueError(f"{name}: invalid min_area")
        for key in ("min_circularity", "min_fill"):
            if not 0 <= settings[key] <= 1:
                raise ValueError(f"{name}: invalid {key}")
    return config


def detect(frame, settings):
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for lower, upper in settings["ranges"]:
        mask |= cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        x, _, width, height = cv2.boundingRect(contour)
        circularity = 4 * math.pi * area / max(perimeter * perimeter, 1)
        fill = area / (width * height)
        if (area >= settings["min_area"] and circularity >= settings["min_circularity"]
                and fill >= settings["min_fill"]):
            candidates.append(Detection((x + width / 2) / frame.shape[1],
                                        width / frame.shape[1], min(circularity, fill)))
    # Never guess between two qualifying targets.
    return candidates[0] if len(candidates) == 1 else None


def merge_cells(cells, size):
    """FOMO emits one box per grid cell; join cells at most one cell apart into blobs."""
    blobs = []  # [x0, y0, x1, y1, [values]]
    for cell in cells:
        gap = min(cell["width"], cell["height"])
        merged = [cell["x"], cell["y"], cell["x"] + cell["width"], cell["y"] + cell["height"], [cell["value"]]]
        rest = []
        for blob in blobs:
            if (blob[0] - gap <= merged[2] and merged[0] - gap <= blob[2]
                    and blob[1] - gap <= merged[3] and merged[1] - gap <= blob[3]):
                merged = [min(blob[0], merged[0]), min(blob[1], merged[1]),
                          max(blob[2], merged[2]), max(blob[3], merged[3]), blob[4] + merged[4]]
            else:
                rest.append(blob)
        blobs = rest + [merged]
    return [Detection((x0 + x1) / 2 / size[0], (x1 - x0) / size[0], sum(v) / len(v), y1 / size[1])
            for x0, _, x1, y1, v in blobs]


class EdgeImpulseDetector:
    """FOMO .eim model; labels must be soccerball and goal."""
    LABELS = {"soccerball": "ball", "goal": "goal"}

    def __init__(self, config):
        self.config = config
        self.runner = None

    def __enter__(self):
        from edge_impulse_linux.image import ImageImpulseRunner
        path = Path(__file__).with_name(self.config["model_path"])
        self.runner = ImageImpulseRunner(str(path))
        params = self.runner.init()["model_parameters"]
        self.size = (params["image_input_width"], params["image_input_height"])
        return self

    def detect(self, frame):
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Studio trained with squash; the plain helper would crop the frame to a square.
        features, _ = self.runner.get_features_from_image_auto_studio_settings(rgb)
        boxes = self.runner.classify(features)["result"].get("bounding_boxes", [])
        self.last_raw = sorted(boxes, key=lambda b: -b["value"])[:6]
        found = {"ball": [], "goal": []}
        for box in boxes:
            name = self.LABELS.get(box["label"])
            if name and box["value"] >= self.config["min_confidence"]:
                found[name].append(box)
        # Never guess between two qualifying targets.
        blobs = {name: merge_cells(cells, self.size) for name, cells in found.items()}
        return tuple(blobs[n][0] if len(blobs[n]) == 1 else None for n in ("ball", "goal"))

    def __exit__(self, *args):
        if self.runner:
            self.runner.stop()


class LatestCamera:
    """Drain continuously and keep one frame. Arrival time is NOT capture time."""
    def __init__(self, config):
        self.config = config
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.error = None
        self.thread = threading.Thread(target=self._read, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def _read(self):
        try:
            import cv2
            import numpy as np
            with urlopen(self.config["camera_url"], timeout=self.config["frame_timeout"]) as response:
                if response.headers.get_content_type() != "multipart/x-mixed-replace":
                    raise RuntimeError("Expected camera MJPEG response")
                buffer = b""
                while not self.closed.is_set():
                    chunk = response.read1(8192)
                    if not chunk:
                        raise RuntimeError("Camera disconnected")
                    buffer += chunk
                    if len(buffer) > 2_000_000:
                        raise RuntimeError("Oversized/malformed MJPEG frame")
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        end = buffer.find(b"\xff\xd9", max(start, 0))
                        if start < 0 or end < 0:
                            break
                        jpeg, buffer = buffer[start:end + 2], buffer[end + 2:]
                        arrived = time.monotonic()
                        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is None or frame.shape[:2] != (240, 320):
                            raise RuntimeError("Expected valid 320x240 camera frame")
                        with self.lock:
                            self.latest = (arrived, frame)
        except Exception as exc:
            with self.lock:
                self.error = exc

    def next_frame(self, after, robot, deadline):
        from robot_client import ProgramStopped
        until = min(deadline, time.monotonic() + self.config["frame_timeout"])
        while time.monotonic() < until:
            if not robot.is_running():
                raise ProgramStopped
            with self.lock:
                latest, error = self.latest, self.error
            if error:
                raise RuntimeError(f"Camera failed: {error}") from error
            if latest and latest[0] > after and time.monotonic() - latest[0] <= self.config["max_frame_age"]:
                return latest
            time.sleep(0.02)
        raise RuntimeError("No fresh frame before camera timeout/run deadline")

    def __exit__(self, *args):
        self.closed.set()
        self.thread.join(timeout=self.config["frame_timeout"] + 0.1)
        # Stop/restart only after reader relinquishes the single-client camera.
        if self.thread.is_alive():
            raise RuntimeError("Camera reader did not exit; stop/restart the app")


def physical(direction, config):
    """Map a logical direction to the one the chassis actually performs (see direction_map)."""
    return config["direction_map"].get(direction, direction)


def is_close(ball, config, factor=1.0):
    # FOMO boxes are one grid cell wide, so the model's proximity cue is how low the ball sits in the frame.
    if config["detector"] == "edge_impulse":
        return ball.y >= config["close_ball_y"] * (1 - (1 - factor) / 2)
    return ball.width >= config["close_ball_width"] * factor


def choose_action(ball, goal, config):
    if ball is None:
        return "stop", "ball absent or ambiguous"
    if not config["prealigned_goal"]:
        if goal is None:
            return "stop", "goal marker absent or ambiguous"
        if abs(ball.x - goal.x) > config["goal_tolerance"]:
            return "stop", "ball/goal misaligned: reposition behind ball"
    if abs(ball.x - 0.5) > config["center_band"]:
        return ("left" if ball.x < 0.5 else "right"), "center ball laterally"
    if is_close(ball, config):
        return "push", "ball close and lane aligned"
    return "forward", "approach ball"


def summarize(samples):
    found = [s for s in samples if s]
    if not found:
        return f"SUMMARY: ball found in 0/{len(samples)} frames"
    med = lambda values: sorted(values)[len(values) // 2]
    return (f"SUMMARY: ball found in {len(found)}/{len(samples)} frames ({100 * len(found) // len(samples)}%), "
            f"median x={med([s.x for s in found]):.2f} y={med([s.y for s in found]):.2f} "
            f"width={med([s.width for s in found]):.2f} quality={med([s.quality for s in found]):.2f}")


def run_attempt(robot, config):
    samples = []
    try:
        if config["mode"] == "score" and not config["motion_calibrated"]:
            raise ValueError("Scoring requires verified motion calibration")
        if config["mode"] == "motion":
            robot.drive(physical(config["motion_direction"], config), config["speed"], config["pulse_ms"])
            return
        deadline = time.monotonic() + config["run_seconds"]
        pushes = 0
        misses = 0
        with LatestCamera(config) as camera, contextlib.ExitStack() as stack:
            ei = stack.enter_context(EdgeImpulseDetector(config)) if config["detector"] == "edge_impulse" else None
            after = time.monotonic() + config["settle_seconds"]
            while time.monotonic() < deadline:
                arrived, frame = camera.next_frame(after, robot, deadline)
                if ei:
                    ball, goal = ei.detect(frame)
                else:
                    ball = detect(frame, config["ball"])
                    goal = detect(frame, config["goal"])
                action, reason = choose_action(ball, goal, config)
                print(f"ball={ball} goal={goal} action={action}: {reason}", flush=True)
                if config["mode"] == "observe":
                    samples.append(ball)
                    if ei:
                        print("raw:", [(b["label"], round(b["value"], 2), b["x"], b["y"], b["width"], b["height"])
                                       for b in ei.last_raw], flush=True)
                        after = time.monotonic() + 0.15
                        continue
                    import cv2
                    import numpy as np
                    patch = cv2.cvtColor(frame[110:130, 150:170], cv2.COLOR_BGR2HSV)
                    lo, hi = np.percentile(patch.reshape(-1, 3), [5, 95], axis=0)
                    print(f"Center 20x20 patch HSV 5..95 percentiles: {lo.round()} .. {hi.round()}", flush=True)
                    after = time.monotonic() + 0.15
                    continue
                if ball is None and misses < config["max_missed_frames"]:
                    # The model drops the ball in some frames; wait for another instead of ending the run.
                    misses += 1
                    after = time.monotonic() + 0.05
                    continue
                misses = 0
                if action == "stop":
                    return
                distance = robot.read_sensors().get("ultrasonic_mm", -1)
                if type(distance) not in (int, float) or not math.isfinite(distance):
                    raise RuntimeError("Invalid ultrasonic reading")
                if distance < 0 and not config["allow_unknown_ultrasonic"]:
                    raise RuntimeError("Ultrasonic unknown; check sensor")
                if 0 <= distance < config["minimum_clearance_mm"]:
                    raise RuntimeError("Clearance limit reached; may be the ball")
                if time.monotonic() - arrived > config["max_frame_age"]:
                    raise RuntimeError("Observation expired during processing")
                if time.monotonic() >= deadline:
                    return
                near = is_close(ball, config, 0.7)
                robot.drive(physical("forward" if action == "push" else action, config),
                            config["near_speed"] if near else config["speed"],
                            config["push_ms"] if action == "push" else config["pulse_ms"])
                if action == "push":
                    pushes += 1
                    if pushes >= config["max_pushes"]:
                        print("Bounded attempt complete. Visually check whether it scored.")
                        return
                after = time.monotonic() + config["settle_seconds"]
            print("Run time limit reached")
    finally:
        robot.stop()
        if samples:
            print(summarize(samples), flush=True)
