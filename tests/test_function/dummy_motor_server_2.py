# libraries
import sys

from laplace_server.get_ip import get_ip
from PyQt6.QtWidgets import (
    QApplication
)

# project
from dummy_motor_server import DummyMotorWindow


port_motor_2 = 5556
name_list_motor_2 = [
    "GasPressure", 
    "LaserEnergy", 
]
my_ip = get_ip(name="Source Motor 2")
MOTOR_ADDRESS_2 = f"tcp://{my_ip}:{port_motor_2}"

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DummyMotorWindow(
        id=2, 
        port=port_motor_2,
        name_list=name_list_motor_2
    )
    window.show()

    sys.exit(app.exec())