from arduino.app_utils import App
from robot_client import MiniAutoRobot, ProgramStopped
from autonomy import load_config, run_attempt

robot = MiniAutoRobot()


def routine():
    try:
        run_attempt(robot, load_config())
    except ProgramStopped:
        raise
    except Exception as exc:
        robot.stop()
        print(f"[STOP] {type(exc).__name__}: {exc}", flush=True)


try:
    robot.stop()
    config = load_config()
    print(f"health  : {robot.health()}")
    print(f"sensors : {robot.read_sensors()}")
    print(f"Mode: {config['mode']}. Short-press camera BOOT to start/stop.")
    App.run(user_loop=lambda: robot.run_program(routine))
finally:
    robot.stop()
