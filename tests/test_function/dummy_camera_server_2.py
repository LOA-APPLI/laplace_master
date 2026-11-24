# libraries
import sys

from laplace_server.get_ip import get_ip
from PyQt6.QtWidgets import (
    QApplication
)

# project
from dummy_camera_server import DummyCamera

# project
from dummy_motor_server_2 import MOTOR_ADDRESS_2
from dummy_shot_server import SHOT_SUB_ADDRESS
from target_function import target_function
from target_function_noisy import target_function_noisy

target = target_function  # target function to use

port_camera_2 = 5558
plottable_list_camera_2 = [
    "ElectronCountsIn",
    "ElectronCountsOut",
]
my_ip = get_ip(name="Source Camera 2")
CAMERA_ADDRESS_2 = f"tcp://{my_ip}:{port_camera_2}"



if __name__ == "__main__":
    app = QApplication(sys.argv)
    cam = DummyCamera(
        id=2,
        port=port_camera_2,
        plottable_list=plottable_list_camera_2,
        motor_address=MOTOR_ADDRESS_2,
        target_function=target,
        time_sleep_s=0.5,
    )
    cam.show()
    sys.exit(app.exec())