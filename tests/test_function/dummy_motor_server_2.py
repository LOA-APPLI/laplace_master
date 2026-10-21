# libraries
import sys

from laplace_server.get_ip import get_ip
from PyQt6.QtWidgets import (
    QApplication
)

# project
from dummy_motor_server import DummyMotorWindow


port_motor_2 = 5557

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DummyMotorWindow(
        id=1, 
        port=port_motor_2,
        name_list=[
            "GasPressure", 
            "LaserEnergy", 
        ]
    )
    window.show()

    sys.exit(app.exec())