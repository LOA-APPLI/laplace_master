import time
import threading
import zmq
import torch
import sys

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, 
    QVBoxLayout, QLineEdit
)

from laplace_server.server_lhc import ServerLHC
from laplace_server.protocol import DEVICE_CAMERA, make_get_request
from target_function import target_function
from target_function_noisy import target_function_noisy

target = target_function  # target function to use

CAMERA_ADDRESS = "tcp://*:5558"
MOTOR_ADDRESS = "tcp://147.250.140.85:5557"
SHOT_SUB_ADDRESS = "tcp://147.250.140.85:6009"


class DummyCamera(QWidget):
    def __init__(self):
        super().__init__()
        self.name = "dummy_camera_copy"
        self.setWindowTitle("Dummy Camera")
        self.resize(300, 120)

        self.last_shot = -1
        self.last_result = ""

        self.setup_zmq()
        self.setup_lhc()
        self.setup_ui()

        self.running = True
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()


    def setup_ui(self) -> None:
        """
        Set the ui widgets.
        """
        self.setWindowTitle("Dummy Camera")
        self.resize(360, 220)

        ### Addresses
        self.sub_address = QLineEdit(SHOT_SUB_ADDRESS)
        self.sub_address.setReadOnly(True)

        self.motor_address = QLineEdit(MOTOR_ADDRESS)
        self.motor_address.setReadOnly(True)

        self.lhc_address = QLineEdit(self.server.address_for_client)
        self.lhc_address.setReadOnly(True)

        ### Objective names
        self.obj1_name = QLineEdit("electron_charge")
        self.obj2_name = QLineEdit("electron_energy_mean")

        self.obj1_name.setPlaceholderText("obj1 key")
        self.obj2_name.setPlaceholderText("obj2 key")

        ### Live values
        self.shot_label = QLabel("Shot: -")
        self.motor_label = QLabel("Motor: -")
        self.value_label = QLabel("Values: -")
        self.time_label = QLabel("Time: -")

        # font size
        self.setStyleSheet("""
            QLabel {
                font-size: 13px;
            }
        """)

        ### Layout
        layout = QVBoxLayout()

        layout.addWidget(QLabel("SHOT SUB"))
        layout.addWidget(self.sub_address)

        layout.addWidget(QLabel("MOTOR"))
        layout.addWidget(self.motor_address)

        layout.addWidget(QLabel("CAMERA"))
        layout.addWidget(self.lhc_address)

        layout.addSpacing(10)

        layout.addWidget(QLabel("Objective names"))
        layout.addWidget(self.obj1_name)
        layout.addWidget(self.obj2_name)

        layout.addSpacing(10)

        layout.addWidget(self.shot_label)
        layout.addWidget(self.motor_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.time_label)

        self.setLayout(layout)

    def update_ui(self, shot, motor, timestamp):
        self.shot_label.setText(f"Shot: {shot}")
        self.motor_label.setText(f"Motor: {motor}")
        self.time_label.setText(f"Time: {timestamp}")

    ### ZMQ
    def setup_zmq(self):
        """
        Creates the ZMQ context
        """
        self.ctx = zmq.Context()

        # sub to shot server
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.connect(SHOT_SUB_ADDRESS)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "SHOOT")

    ### LHC
    def setup_lhc(self):
        """
        Create the LHC server (request / reply)
        """
        self.server = ServerLHC(
            address=CAMERA_ADDRESS,
            freedom=0,
            device=DEVICE_CAMERA,
            data={},
            name=self.name,
            empty_data_after_get=True,
            plottables_list = ['Charge', 'Energy mean']
        )
        self.server.start()

    ### Motor
    def get_motor(self) -> list:
        """
        Get the motor value.
        """
        sock = self.ctx.socket(zmq.REQ)
        sock.connect(MOTOR_ADDRESS)

        sock.send_json(make_get_request(sender=self.name, target="dummy_motor"))
        reply = sock.recv_json()

        sock.close()
        
        data = reply["payload"]["data"]
        positions = data["shot_positions"]
        motor_shot = data["shot_number"]

        return positions

    ### compute test function
    def measure(self, shot: int):
        """
        Sample the test function.
        """
        x1, x2 = self.get_motor()  # get the motor positions
        print(f'Get motor pos. {(x1, x2)}')

        x1 = torch.tensor(x1)
        x2 = torch.tensor(x2)

        r = target(x1, x2)  # get the test function value
        print(f'Get target {r}')
        self.value_label.setText(f"Value: {r[:, 0].item()} charge | {r[:, 1].item()} energy")

        return {
            "shot_number": shot, # completed shot
            "motor": [x1.item(), x2.item()],
            self.obj1_name.text(): r[:, 0].item(),
            self.obj2_name.text(): r[:, 1].item(),
            "time": time.strftime("%H:%M:%S"),
        }

    ### Loop
    def loop(self):
        print("Camera listening...")

        while self.running:
            try:
                print("Loop running")
                topic = self.sub.recv_string()
                event = self.sub.recv_json()

                shot = event["number"]                  # next shot to come
                completed_shot = shot - 1               # shot that just been completed
                self.last_shot = completed_shot         # store last completed shot

                time.sleep(2)  # camera processing

                data = self.measure(completed_shot)    # compute the test function
                self.server.set_data(data)             # set the values in the LHC server

                self.update_ui(                        # update the interface
                    completed_shot,
                    data["motor"],
                    data["time"]
                )

                print("Camera triggered:", completed_shot)

            except Exception as e:
                if self.running:                # if the thread is still running
                    print("camera error:", e)   # print the error


    def closeEvent(self, event):
        self.running = False
        time.sleep(0.1)       # let the thread the time to close
        
        self.server.stop()    # close each thread
        self.sub.close()
        self.ctx.term()
        
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    cam = DummyCamera()
    cam.show()
    sys.exit(app.exec())