import sys
import threading
import time

import zmq
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QDoubleSpinBox,
    QFormLayout, QSpinBox
)

from laplace_server.server_lhc import ServerLHC
from laplace_server.protocol import DEVICE_MOTOR
from laplace_log import log


MOTOR_ADDRESS = "tcp://*:5557"
SHOT_SUB_ADDRESS = "tcp://147.250.140.85:6009"


class DummyMotor:
    def __init__(self):
        self.positions = [0.0, 0.0]
        self.moving = False

        self.latched_positions = [0.0, 0.0]
        self.latched_shot_number = -1
    
    def set_shot_number(self, shot_number: int):
        self.latched_shot_number = shot_number
        self.latched_positions = self.positions.copy()

    def set_positions(self, positions):
        print(f"[Motor] Moving to {positions}")
        
        for key, value in positions.items():
            key = int(key)
            try:
                self.positions[key] = float(value)
            except Exception as e:
                log.info(f'Exception {e}, key: {key}')
        
        print(f"[Motor] New positions = {self.positions}")


    def get_data(self):
        return {
            "positions": self.positions,
            "moving": self.moving,
            "unit": "a.u.",
            "shot_number": self.latched_shot_number,
            "shot_positions": self.latched_positions
        }


class DummyMotorWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Dummy Motor")

        self.motor = DummyMotor()

        self.server = ServerLHC(
            address=MOTOR_ADDRESS,
            freedom=2,
            device=DEVICE_MOTOR,
            data=self.motor.get_data(),
            name="dummy_motor_copy"
        )

        self.server.set_name_list(["Direction z", "Direction a"])
        self.server.set_on_position_changed(self.on_position_changed)

        self.init_ui()
        self.actions()
        self.setup_zmq()
        self.server.start()


    def setup_zmq(self):
        """
        Creates the ZMQ context
        """
        self.ctx = zmq.Context()

        # sub to shot server
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.connect(SHOT_SUB_ADDRESS)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "SHOOT")

        self.running = True
        self.thread = threading.Thread(
            target=self.loop,
            daemon=True
        )
        self.thread.start()



    def init_ui(self):
        layout = QVBoxLayout()

        self.sub_address = QLineEdit(SHOT_SUB_ADDRESS)
        self.sub_address.setReadOnly(True)

        layout.addWidget(QLabel("SHOT SUB"))
        layout.addWidget(self.sub_address)

        # Address display
        layout.addWidget(QLabel("Server address:"))

        self.address_entry = QLineEdit(
            self.server.address_for_client
        )
        self.address_entry.setReadOnly(True)

        layout.addWidget(self.address_entry)

        # Motor values
        form = QFormLayout()

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-1e6, 1e6)
        self.spin_x.setDecimals(6)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-1e6, 1e6)
        self.spin_y.setDecimals(6)

        form.addRow("Direction x:", self.spin_x)
        form.addRow("Direction y:", self.spin_y)

        self.shot_box = QSpinBox()
        self.shot_box.setRange(-1, 100000)
        self.shot_box.setReadOnly(True)
        form.addRow("Motor shot number:", self.shot_box)

        layout.addLayout(form)

        self.setLayout(layout)


    def actions(self):
        self.spin_x.valueChanged.connect(
            lambda: self.motor.set_positions(
                {"0": self.spin_x.value(), "1": self.spin_y.value()}
            )
        )
        self.spin_y.valueChanged.connect(
            lambda: self.motor.set_positions(
                {"0": self.spin_x.value(), "1": self.spin_y.value()}
            )
        )


    def on_position_changed(self, positions):
        """
        Called when master sends new motor targets.
        """
        log.info(f'Dummy motor copy at address {MOTOR_ADDRESS} moving to {positions}')
        self.motor.set_positions(positions)

        self.server.set_data(
            self.motor.get_data()
        )

        # Update GUI
        self.spin_x.setValue(
            self.motor.positions[0]
        )
        self.spin_y.setValue(
            self.motor.positions[1]
        )


    def loop(self):
        """
        Listen to shot server and update
        the latest completed shot number.
        """
        print("[Motor] Listening to shots...")

        while self.running:
            try:
                topic = self.sub.recv_string()
                event = self.sub.recv_json()

                next_shot = event["number"]
                completed_shot = next_shot - 1

                self.motor.set_shot_number(completed_shot)

                self.server.set_data(
                    self.motor.get_data()
                )

                self.shot_box.setValue(completed_shot)

                print(
                    f"[Motor] Shot updated -> {completed_shot}"
                )

            except Exception as e:
                if self.running:
                    print("[Motor] loop error:", e)

    def closeEvent(self, event):
        self.running = False
        time.sleep(0.1)
        
        self.server.stop()
        self.sub.close()
        self.ctx.term()

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DummyMotorWindow()
    window.resize(350, 150)
    window.show()

    sys.exit(app.exec())