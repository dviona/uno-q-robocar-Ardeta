from arduino.app_utils import App
from robot_client import MiniAutoRobot

robot = MiniAutoRobot()


def motion_check() -> None:
    # Start with raised wheels; calibrate this short pulse on each chassis.
    robot.drive("forward", speed=100, ms=200)


try:
    robot.stop()
    print(f"health  : {robot.health()}")
    print(f"sensors : {robot.read_sensors()}")
    print("Raise the wheels, then short-press the camera BOOT button for one motion check.")
    App.run(user_loop=lambda: robot.run_program(motion_check))
finally:
    robot.stop()
