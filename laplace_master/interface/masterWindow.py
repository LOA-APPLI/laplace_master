# libraries
import pathlib

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, 
    QVBoxLayout, QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import (
    QSettings, QTimer
)
from PyQt6.QtGui import QIcon
import qdarkstyle
from laplace_server.protocol import (
    DEVICE_CAMERA, DEVICE_OPT, DEVICE_SHOT,
    AVAILABLE_CONTROLS, DEVICE_SCAN
)
from laplace_log import log

# project
from interface.panels import (
    ConnectionPanel, OptimizationPanel, LaserPanel, ScanPanel
)
from interface.widgets import (
    SaveBar, ServerBar
)
from client.clientManager import ClientManager
from client.optBrain import OptBrain
from client.scanBrain import ScanBrain


class MasterWindow(QMainWindow):
    '''
    Main class of the project. Create the main window and 
    connect the interface and the server configurations. 
    '''
    
    def __init__(self, flag: str="Optimizer"):
        '''
        Initialization of the 'MasterWindow' class.
        '''
        super().__init__() # heritage from QMainWindow

        self.p = pathlib.Path(__file__)  # current path of the file
        
        # load the settings
        self.settings = QSettings(
            str(self.p.parent.parent / "config.ini"), 
            QSettings.Format.IniFormat
        )
        self.optimize = "opt" in flag.lower() # Checks whether windiw should be launched for optimization or scan
        self.set_up()  # initialize the widgets and place them in the window

        # Manager handling one client per server
        self.client_manager = ClientManager()
        # Brain organizing the queue (optimizer or scan)
        if self.optimize:
            self.brain = OptBrain(self.client_manager)
        else:
            self.brain = ScanBrain(self.client_manager)
        
        # Ping timer
        self.timer = QTimer()
        ping_time_ms = self.settings.value(
            "server/ping_time_ms", 
            defaultValue=3000, 
            type=int
        )
        self.timer.start(ping_time_ms)

        self.global_controller_timer = QTimer()
        self.global_controller_timer.timeout.connect(self.poll_optimizer)
        self.global_controller_timer.start(ping_time_ms)


        brain_time_ms = self.settings.value(
            "server/brain_time_ms", 
            defaultValue=3000, 
            type=int
        )
        self.brain_timer = QTimer()
        self.brain_timer.timeout.connect(self.brain.tick)
        self.brain_timer.start(brain_time_ms)
        
        self.actions()  # signals

    @property
    def saving_path(self) -> str:
        '''
        Property made to have a convenient access to the saving path.
        '''
        return self.save_bar.saving_path


    def set_up(self) -> None:
        '''
        Function made to initialize the widgets and 
        to place them in the 'MasterWindow'.
        '''
        # Set window title, geometry and style
        self.setWindowTitle("Master Window")
        self.setGeometry(100, 30, 1000, 700)
        self.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))
        
        # Window icon
        icon_path = self.p.parent / 'icons'    # icon path
        self.setWindowIcon(QIcon(str(icon_path / 'LOA.png')))

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main vertical layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        ### top line (saveBar and serverBar)
        top_container = QHBoxLayout()
        main_layout.addLayout(top_container)

            # pathBar
        saved_path = self.settings.value("interface/path_saving_entry", defaultValue="", type=str)
        self.save_bar = SaveBar(saved_path)

        # top_container.addStretch(3)          # add space
        top_container.addWidget(self.save_bar)
        # top_container.addStretch(2)

            # serverBar
        self.server_bar = ServerBar()
        top_container.addWidget(self.server_bar)
        # top_container.addStretch(3)

        ### 2 x 2 grid
        grid_layout = QGridLayout()
        main_layout.addLayout(grid_layout)

            # Top-left label
        self.laser_panel = LaserPanel()
        # laser_label = QLabel("laser")
        # laser_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Top-right layout for diags panel
        self.diagsConnectionPanel = ConnectionPanel("Diagnostics")

            # Bottom-left label
        self.motorsConnectionPanel = ConnectionPanel("Control systems")

            # Bottom-right label
        if self.optimize:
            self.globalControlPanel = OptimizationPanel()
        else:
            self.globalControlPanel = ScanPanel()

            # Add widgets to the grid layout
        # grid_layout.addWidget(laser_label, 0, 0)
        grid_layout.addWidget(self.laser_panel, 0, 0)
        grid_layout.addWidget(self.diagsConnectionPanel, 0, 1)
        grid_layout.addWidget(self.motorsConnectionPanel, 1, 0)
        grid_layout.addWidget(self.globalControlPanel, 1, 1)

            # Set column and row stretch
        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)


    def actions(self) -> None:
        '''
        Defines all the signals between the clients and the interface.
        '''
        # update the 'config.ini' file when the 'path saving entry' is modified
        self.save_bar.save_entry.textChanged.connect(
            lambda text: self.settings.setValue("interface/path_saving_entry", text)
        )

        # send a message to all servers when the saving path is modified
        self.save_bar.save_entry.textChanged.connect(
            self.client_manager.save_all
        )

        # when a server address is filled, use the route procedure
        self.server_bar.server_added.connect(
            self.route_server
        )
        
        # ping all servers according to the internal timer
        self.timer.timeout.connect(
            self.client_manager.ping_all
        )
        
        ### every panel actions
            # update the server state when the interface requires it
        self.diagsConnectionPanel.server_connection_changed.connect(
            lambda addr, state: self.client_manager.set_server_enabled(addr, state)
        )
        self.motorsConnectionPanel.server_connection_changed.connect(
            lambda addr, state: self.client_manager.set_server_enabled(addr, state)
        )
        self.globalControlPanel.server_connection_changed.connect(
            lambda addr, state: self.client_manager.set_server_enabled(addr, state)
        )
        self.laser_panel.server_connection_changed.connect(
            lambda addr, state: self.client_manager.set_server_enabled(addr, state)
        )
            # update the displayed time when a message is received
        self.client_manager.server_contacted.connect(
            self.diagsConnectionPanel.update_server_last_msg
        )
        self.client_manager.server_contacted.connect(
            self.motorsConnectionPanel.update_server_last_msg
        )
        self.client_manager.server_contacted.connect(
            self.globalControlPanel.update_server_last_msg
        )
        self.client_manager.server_contacted.connect(
            self.laser_panel.update_server_last_msg
        )
            # update the server state when the client lose connection
        self.client_manager.server_pinged.connect(
            self.diagsConnectionPanel.on_server_alive_changed
        )
        self.client_manager.server_pinged.connect(
            self.motorsConnectionPanel.on_server_alive_changed
        )
        self.client_manager.server_pinged.connect(
            self.globalControlPanel.on_server_alive_changed
        )
        self.client_manager.server_pinged.connect(
            self.laser_panel.on_server_alive_changed
        )

        # when data is received, route it to the correct panel
        self.client_manager.server_data_received.connect(
            self.route_server_data
        )

        ### brain actions - optimizer
            # transmit the motor control state to the brain
        if self.optimize:
            self.globalControlPanel.motor_control_changed.connect(
                self.brain.set_motor_control
            )
                # define if the brain is ready to brain
            self.globalControlPanel.arm_changed.connect(
                self.brain.set_armed
            )

            self.brain.queue_updated.connect(
                self.globalControlPanel.queue_viewer.set_queue
            )

            self.globalControlPanel.queue_viewer.delete_current.connect(
                self.brain.delete_suggestion
            )

            # when the motor is enabled / disabled, set the corresponding information in brain
            self.motorsConnectionPanel.motor_connection_changed.connect(
                self.brain.set_motor_enabled
            )

            self.laser_panel.shot_changed.connect(
                lambda shot_number: self.brain.on_shot(
                    shot_number=shot_number, 
                )
            )
        else: 

            self.globalControlPanel.load_controls_clicked.connect(
                self.brain.update_controls_and_diagnostics
            )

            self.globalControlPanel.motor_control_changed.connect(
                self.brain.set_motor_control
            )
                # define if the brain is ready to brain
            self.globalControlPanel.arm_changed.connect(
                self.brain.set_armed
            )

            self.brain.queue_updated.connect(
                self.globalControlPanel.queue_viewer.set_queue
            )

            self.globalControlPanel.queue_viewer.delete_current.connect(
                self.brain.delete_suggestion
            )

            # when the motor is enabled / disabled, set the corresponding information in brain
            self.motorsConnectionPanel.motor_connection_changed.connect(
                self.brain.set_motor_enabled
            )

            self.laser_panel.shot_changed.connect(
                lambda shot_number: self.brain.on_shot(
                    shot_number=shot_number, 
                )
            )


    def route_server(self, address: str) -> None:
        '''
        Function called when a new server address is provided.
        Probe the server and use the informations gather to create 
        the elements in the corresponding panel.

            Errors: message boxes are shown when the address is
            not conform to the ZMQ standards and when the client
            did get not answer.

            Arg:
                address: (str)
                    the address of the server in ZMQ
                    format, using REQ.
        '''
        # probe the server to gather informations
        info = self.client_manager.probe_server(address, self.saving_path)
        
        # if there is no information (an error was raised)
        if info is None:
            msg = f'The address "{address}" was not found or is invalid.'
            log.info(msg)
            
            # create a message box
            QMessageBox.warning(
                self, "Invalid address", msg,
                QMessageBox.StandardButton.Ok
            )
            return  # get out of the routing session

        # if the client did get not answer
        if info.already:
            msg = f'The server "{address}" was already reached.'
            log.info(msg)
            
            # create a message box
            QMessageBox.warning(
                self, "Server already reached", msg,
                QMessageBox.StandardButton.Ok
            )
            return  # get out of the routing session

        # if the client did get not answer
        if not info.alive:
            msg = f'The server "{address}" did not respond.'
            log.info(msg)
            
            # create a message box
            QMessageBox.warning(
                self, "Server unreachable", msg,
                QMessageBox.StandardButton.Ok
            )
            return  # get out of the routing session

        # if the device is a camera
        if info.device == DEVICE_CAMERA:
            # top right connectionPanel
            self.diagsConnectionPanel.add_server(
                address=info.address,
                name=info.name or "Unknown"
            )
            log.info(f"New diagnostic server added:")
        
        # elif the device is a 'control system'
        elif info.device in AVAILABLE_CONTROLS:# info.device == DEVICE_MOTOR or info.device == DEVICE_GAS:
            # bottom left connectionPanel
            self.motorsConnectionPanel.add_server(
                address=info.address,
                name=info.name or "Unkwon"
            )
            # create a subline per degree of freedom
            if info.freedom:
                self.brain.register_motor_server(   # register in the brain
                    info.address, 
                    info.freedom
                )
                self.motorsConnectionPanel.add_server_controls(
                    address=info.address,
                    freedom=info.freedom,
                    name_list=info.name_list
                )
            log.info(f"New control system server added:")
        
        elif info.device == DEVICE_OPT:
            self.globalControlPanel.add_server(
                address=info.address,
                name=info.name or "Optimization"
            )
            log.info(f"New optimization server added:")

        elif info.device == DEVICE_SCAN:
            self.globalControlPanel.add_server(
                address=info.address,
                name=info.name or "Scan"
            )
            log.info(f"New scan server added:")
            # Start polling timer (to update motors as well as positions)
            self.scan_timer = QTimer()
            update_scan_time = 1000 # In milliseconds
            self.scan_timer.start(update_scan_time)
            # Update scanner with current list of motors and positions
            # and diagnostics and measurement names
            self.scan_timer.timeout.connect(self.update_scanner)  
        
        elif info.device == DEVICE_SHOT:
            self.laser_panel.add_shot_number(
                address=info.address,
                name=info.name or "Shot Number"
            )
            log.info(f"New shot number server added:")
        
        log.info(f"name={info.name or 'Unknown'}, address={info.address}, freedom={info.freedom}")


    def route_server_data(self, address: str, data: dict):


        device_type = self.client_manager.server_devices.get(address)

        if device_type in AVAILABLE_CONTROLS:
            # when data is received, from motors, update the displayed motor positions
            self.motorsConnectionPanel.update_server_data(address, data)

            try:
                self.brain.on_motor_position_update(address, data)  # and brain measurement
            except Exception as e:
                log.error(f"Error: while processing motor position update.\n{e}")

        elif device_type == DEVICE_SHOT:
            self.laser_panel.set_shot_value(address, data)

        elif device_type == DEVICE_CAMERA:
            self.brain.on_measurement(address, data)

        elif device_type == DEVICE_OPT:
            self.brain.on_opt_data(address, data)

        elif device_type == DEVICE_SCAN:
            if data:
                self.brain.on_scan_data(address, data)

    def update_scanner(self):
        self.brain.update_controls_and_diagnostics()


    def poll_optimizer(self):
        for address, device in self.client_manager.server_devices.items():
            if device == DEVICE_OPT:
                data = self.client_manager.poll_optimizer(address)
                if data:
                    self.brain.on_opt_data(address, data)


    def poll_scanner(self):
        for address, device in self.client_manager.server_devices.items():
            if device == DEVICE_SCAN:
                data = self.client_manager.poll_scanner(address)
                if data:
                    self.brain.on_scan_data(address, data)


    def closeEvent(self, event) -> None:
        '''
        Function called when the window is closing.
        Close every client of client manager.
        '''
        self.client_manager.close_all()
        event.accept()