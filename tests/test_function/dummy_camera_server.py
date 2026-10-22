# libraries
from typing import Callable
import time
import sys
import threading

from laplace_server import ServerLHC
from laplace_server.get_ip import get_ip
from laplace_server.protocol import (
    DEVICE_CAMERA, make_get_request
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, 
    QVBoxLayout, QLineEdit, QFormLayout,
)
from PyQt6.QtCore import pyqtSignal, pyqtSlot
import zmq

# project
from dummy_motor_server import MOTOR_ADDRESS_1
from dummy_shot_server import SHOT_SUB_ADDRESS
from target_function import target_function
from target_function_noisy import target_function_noisy

target = target_function  # target function to use

port_camera_1 = 5557
plottable_list_camera_1 = [
    "ElectronCharge",
    "ElectronEnergyMean",
    "ElectronEnergyStd",
]
my_ip = get_ip(name="Source Camera 1")
CAMERA_ADDRESS_1 = f"tcp://{my_ip}:{port_camera_1}"


class DummyCamera(QWidget):
    '''Test class made to simulate the behavior of camera.'''

    measurement_ready = pyqtSignal(object)
    
    def __init__(self, 
                 id: int, 
                 port: int, 
                 plottable_list: list[str],
                 motor_address: str,
                 target_function: Callable,
                 time_sleep_s=0.5):
        '''
        Create a demon thread to simulate 
        the camera behavrior.

        Args:
            id (int):
                the camera id.
            
            port (int):
                the camera port.
            
            plottable_list (list[str]):
                the list of objective names.
            
            motor_address (str):
                the address of the motor used by
                this camera.
        '''
        super().__init__()
        self.id = id
        self.name = f"dummy_camera_{id}"
        self.port = port
        self.ip = get_ip(name=f"Dummy Camera {id}")
        self.plottable_list = plottable_list
        self.motor_address = motor_address
        self.target_function = target_function
        self.time_sleep_s = time_sleep_s

        self.last_shot = -1
        self.last_result = ""

        self.server = ServerLHC(
            address=f"tcp://{self.ip}:{self.port}",
            freedom=0,
            device=DEVICE_CAMERA,
            data={},
            name=self.name,
            empty_data_after_get=True,
            plottables_list = plottable_list
        )

        self.setup_ui()
        self.measurement_ready.connect(self.update_ui)

        self.setup_zmq()
        self.server.start()

        self.running = True
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()


    def setup_ui(self) -> None:
        '''Set the UI widgets.'''
        self.setWindowTitle(f"Dummy Camera {self.id}")
        self.resize(360, 220)

        layout = QVBoxLayout()

        # Addresses
        self.sub_address = QLineEdit(SHOT_SUB_ADDRESS)
        self.sub_address.setReadOnly(True)

        self.motor_address_entry = QLineEdit(self.motor_address)
        self.motor_address_entry.setReadOnly(True)

        self.lhc_address = QLineEdit(
            self.server.address_for_client
        )
        self.lhc_address.setReadOnly(True)

        layout.addWidget(QLabel("SHOT SUB"))
        layout.addWidget(self.sub_address)

        layout.addWidget(QLabel("MOTOR"))
        layout.addWidget(self.motor_address_entry)

        layout.addWidget(QLabel("CAMERA"))
        layout.addWidget(self.lhc_address)

        # Dynamic objective names
        layout.addWidget(QLabel("Objective names"))

        objective_form = QFormLayout()
        self.objective_names = {}

        for name in self.plottable_list:
            entry = QLineEdit(name)
            entry.setReadOnly(True)
            entry.setObjectName(
                f"objective_{name.lower()}"
            )

            self.objective_names[name] = entry
            objective_form.addRow(f"{name}:", entry)

        layout.addLayout(objective_form)

        # Live values
        self.shot_label = QLabel("Shot: -")
        self.motor_label = QLabel("Motor: -")
        self.value_label = QLabel("Values: -")
        self.time_label = QLabel("Time: -")

        layout.addWidget(self.shot_label)
        layout.addWidget(self.motor_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.time_label)

        self.setLayout(layout)



    @pyqtSlot(object)
    def update_ui(self, data: dict) -> None:
        """Update all GUI labels from a measurement."""

        self.shot_label.setText(
            f"Shot: {data['shot_number']}"
        )

        self.motor_label.setText(
            f"Motor: {data['motor']}"
        )

        self.time_label.setText(
            f"Time: {data['time']}"
        )

        # Display only the configured objective values.
        values = {
            name: data[name]
            for name in self.plottable_list
            if name in data
        }

        self.value_label.setText(f"Values: {values}")


    ### ZMQ
    def setup_zmq(self) -> None:
        '''Creates the ZMQ context.'''
        self.ctx = zmq.Context()

        # sub to shot server
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.connect(SHOT_SUB_ADDRESS)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "SHOOT")


    ### Motor
    def get_motor(self) -> dict:
        '''Get the motor value.'''
        sock = self.ctx.socket(zmq.REQ)
        try:
            sock.connect(self.motor_address)

            sock.send_json(
                make_get_request(
                    sender=self.name, 
                    target="dummy_motor"
                    )
                )
            reply = sock.recv_json()
            data = reply["payload"]["data"]
            
            motor_shot = data["shot_number"]
            
            return data["shot_positions"]
        
        finally:
            sock.close()

    ### compute test function
    def measure(self, shot: int) -> dict:
        '''Evaluate the target function for a completed shot.'''

        motor_positions = self.get_motor()

        result = self.target_function(
            positions=motor_positions, 
            n_objectives=len(self.plottable_list)
        )

        # One measurement at a time: shape [1, n_objectives].
        values = result[0]

        objective_names = [
            entry.text()
            for entry in self.objective_names.values()
        ]

        if len(objective_names) != values.numel():
            raise ValueError(
                f"Target returned {values.numel()} objectives, "
                f"but {len(objective_names)} names were configured."
            )

        data = {
            "shot_number": shot,
            "motor": motor_positions,
            "time": time.strftime("%H:%M:%S"),
        }

        for name, value in zip(objective_names, values):
            data[name] = value.item()

        return data


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

                time.sleep(self.time_sleep_s)  # camera processing

                data = self.measure(completed_shot)    # compute the test function
                self.server.set_data(data)             # set the values in the LHC server

                # Send the measurement to the GUI thread safely.
                self.measurement_ready.emit(data)

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
    cam = DummyCamera(
        id=1,
        port=port_camera_1,
        plottable_list=plottable_list_camera_1,
        motor_address=MOTOR_ADDRESS_1,
        target_function=target,
        time_sleep_s=0.5,
    )
    cam.show()
    sys.exit(app.exec())