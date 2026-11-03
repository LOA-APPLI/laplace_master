# libraries
import sys
import time
import threading

from laplace_server import ServerLHC
from laplace_server.protocol import DEVICE_MOTOR
from laplace_server.get_ip import get_ip
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QDoubleSpinBox,
    QFormLayout, QSpinBox,
)
import zmq

# project
from dummy_shot_server import SHOT_SUB_ADDRESS


port_motor_1 = 5555
name_list_motor_1 = [
    "GasJetHeight", 
    "GasJetLongitudinal", 
    "GasJetTransverse",
]
my_ip = get_ip(name="Source Motor 1")
MOTOR_ADDRESS_1 = f"tcp://{my_ip}:{port_motor_1}"


class DummyMotor:
    '''Test class made to simulate a motor device.'''
    
    def __init__(self, id: int):
        '''
        Initialize a test motor.
        
        Args:
            id (int):
                the id of the motor.
        '''
        self.id = id
        self.positions = {
            0: 0.,
            1: 0.,
            2: 0.,
        }

        self.latched_positions = {
            0: 0.,
            1: 0.,
            2: 0.,
        }
        self.latched_shot_number = -1


    def set_shot_number(self, shot_number: int) -> None:
        '''Set shot number and latched the related position.'''
        self.latched_shot_number = shot_number
        self.latched_positions = self.positions.copy()


    def set_positions(self, positions: dict) -> None:
        '''Set the positions of the motor.'''
        print(f"[Motor] Moving to {positions}")
        
        for key, value in positions.items():
            key = int(key)
            try:
                self.positions[key] = float(value)
            except Exception as e:
                print(f'Exception {e}, key: {key}, value: {value}')
        
        print(f"[Motor] New positions = {self.positions}")


    def get_data(self) -> dict:
        '''Returns shot, positions and latched elements.'''
        return {
            "positions": self.positions,
            "unit": "a.u.",
            "shot_number": self.latched_shot_number,
            "shot_positions": self.latched_positions
        }


class DummyMotorWindow(QWidget):
    ''''''
    def __init__(self, id: int, port: int, name_list: list[str]):
        '''
        Initialize a window of dummy mortor.

        Args:
            id (int):
                the dummy motor id.
            
            port (int):
                the server port.
            
            name_list (list[str]):
                the list of axis names.
        '''
        super().__init__()
        self.id = id
        self.port = port
        self.ip = get_ip(name=f"Dummy Motor {id}")

        self.motor = DummyMotor(id=id)

        self.server = ServerLHC(
            address=f"tcp://{self.ip}:{self.port}",
            freedom=len(name_list),
            device=DEVICE_MOTOR,
            data=self.motor.get_data(),
            name=f"dummy_motor_{id}",
            name_list=name_list
        )
        self.server.set_on_position_changed(self.on_position_changed)

        self.setup_ui()
        self.actions()
        self.setup_zmq()
        self.server.start()


    def setup_zmq(self) -> None:
        '''Creates the ZMQ context.'''
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

 
    def setup_ui(self) -> None:
        '''Set the UI widgets.'''
        self.setWindowTitle(f"Dummy Motor {self.id}")
        self.resize(350, 200)

        layout = QVBoxLayout()

        self.sub_address = QLineEdit(SHOT_SUB_ADDRESS)
        self.sub_address.setReadOnly(True)

        layout.addWidget(QLabel("SHOT SUB"))
        layout.addWidget(self.sub_address)

        # Server address display
        layout.addWidget(QLabel("Server address:"))

        self.address_entry = QLineEdit(
            self.server.address_for_client
        )
        self.address_entry.setReadOnly(True)
        layout.addWidget(self.address_entry)

        # Motor values: create one spin box per axis
        form = QFormLayout()

        self.position_boxes = {}

        for index, name in enumerate(self.server.name_list):
            spin_box = QDoubleSpinBox()
            spin_box.setRange(-1e6, 1e6)
            spin_box.setDecimals(6)

            # Give each widget a meaningful Qt object name
            spin_box.setObjectName(
                name.lower().replace(" ", "_")
            )

            # Store it by its numerical motor-axis index
            self.position_boxes[index] = spin_box

            # Use the server's axis name as the visible label
            form.addRow(f"{name}:", spin_box)

        # Shot number
        self.shot_box = QSpinBox()
        self.shot_box.setRange(-1, 100_000)
        self.shot_box.setReadOnly(True)

        form.addRow("Motor shot number:", self.shot_box)

        layout.addLayout(form)
        self.setLayout(layout)


    def actions(self) -> None:
        '''Define the actions of the window.'''
        for index, spin_box in self.position_boxes.items():
            spin_box.valueChanged.connect(
                self.on_spin_box_changed
            )


    def on_spin_box_changed(self, value=None) -> None:
        '''Update motor positions from all spin boxes.'''
        # make the position dictionary
        positions = {
            str(index): spin_box.value()
            for index, spin_box in self.position_boxes.items()
        }
        
        self.motor.set_positions(positions)  # set the position in dummy motor

        self.server.set_data(                # update the server values
            self.motor.get_data()
        )


    def on_position_changed(self, positions: dict) -> None:
        '''Called when master sends new motor targets.'''
        self.motor.set_positions(positions)   # set the position in dummy motor

        self.server.set_data(
            self.motor.get_data()             # update the server
        )

        # Update all GUI spin boxes
        for index, spin_box in self.position_boxes.items():
            spin_box.setValue(
                self.motor.positions.get(index, 0.0)
            )


    def loop(self) -> None:
        '''
        Listen to shot server and update
        the latest completed shot number.
        '''
        print(f"[Motor {self.id}] Listening to shots...")

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
        '''Close properly the sub thread.'''
        self.running = False
        time.sleep(0.1)
        
        self.server.stop()
        self.sub.close()
        self.ctx.term()

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DummyMotorWindow(
        id=1, 
        port=port_motor_1,
        name_list=name_list_motor_1
    )
    window.show()

    sys.exit(app.exec())