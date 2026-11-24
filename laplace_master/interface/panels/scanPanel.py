# libraries
from laplace_log import log
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, 
    QListWidgetItem, QPushButton, QGroupBox, 
    QCheckBox, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal

# project
from interface.widgets import ServerItemWidget
from interface.widgets import ScanQueueViewerWidget

class ScanPanel(QWidget):
    '''
    Panel to manage optimization server(s).
    Displays ServerItemWidget(s) in a list with a motor control checkbox.
    Only one server can be connected at a time.
    '''
    server_connection_changed = pyqtSignal(str, bool)
    motor_control_changed = pyqtSignal(bool)
    next_sample_clicked = pyqtSignal(int)
    #load_controls_clicked = pyqtSignal(str)
    arm_changed = pyqtSignal(bool)

    def __init__(self, title="Scan"):
        super().__init__()

        self.server_widgets: dict[str, ServerItemWidget] = {}

        # Main layout
        outer_layout = QVBoxLayout(self)

        # Group box
        self.group_box = QGroupBox(title)
        outer_layout.addWidget(self.group_box)

        # inside the group box
        self.main_layout = QVBoxLayout(self.group_box)

        # List of servers
        self.server_list_widget = QListWidget()
        self.main_layout.addWidget(self.server_list_widget)

        # QueueViewerWidget
        self.queue_viewer = ScanQueueViewerWidget()
        self.main_layout.addWidget(self.queue_viewer)

        # hbox for control system
        self.hbox = QHBoxLayout()

        # Motor control checkbox
        self.motor_checkbox = QCheckBox("Allow scan to drive motors")
        self.motor_checkbox.setEnabled(False)
        self.motor_checkbox.toggled.connect(
            lambda enabled: log.info("Scan driving motors enabled.") if enabled else log.info("Scan driving motors disabled.") 
        )
        self.motor_checkbox.toggled.connect(self.motor_control_changed)
        self.hbox.addWidget(self.motor_checkbox)

        self.arm_checkbox = QCheckBox("Brain armed")
        self.arm_checkbox.setEnabled(False)
        self.arm_checkbox.toggled.connect(
            lambda enabled: log.info("Brain armed.") if enabled else log.info("Brain unarmed.") 
        )
        self.arm_checkbox.toggled.connect(self.arm_changed)
        self.hbox.addWidget(self.arm_checkbox)

        # Next in queue button
        self.next_sample_button = QPushButton("Next sample")
        self.next_sample_button.setEnabled(False)
        self.next_sample_button.clicked.connect(self.on_next_sample)
        self.hbox.addWidget(self.next_sample_button)



        self.main_layout.addLayout(self.hbox)

        # Connect / Disconnect button
        self.disconnect_button = QPushButton("Connect / Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect)
        self.main_layout.addWidget(self.disconnect_button)

        log.debug("Scan Panel loaded.")


    def add_server(self, address: str, name: str) -> None:
        '''
        Add a server line in the Scan panel.
        '''
        widget = ServerItemWidget(address, name)
        widget.enable_selection(False)  # initially not selectable
        widget.connection_changed.connect(self._on_server_connection_changed)
        self.server_widgets[address] = widget

        # Add to QListWidget
        item = QListWidgetItem(self.server_list_widget)
        item.setSizeHint(widget.sizeHint())
        self.server_list_widget.addItem(item)
        self.server_list_widget.setItemWidget(item, widget)

        # Since a server exists, enable the motor checkbox immediately
        self.motor_checkbox.setEnabled(True)
        self.arm_checkbox.setEnabled(True)



    def on_next_sample(self) -> None:
        '''Emit a signal when the 'Next in Queue' button is clicked.'''
        current_index = self.queue_viewer.current_index
        log.debug(f"Next sample button clicked. Current index = {current_index}")
        self.next_sample_clicked.emit(current_index)



    def on_disconnect(self) -> None:
        '''
        Enables checkboxes to select server(s) to connect/disconnect.
        '''
        for widget in self.server_widgets.values():
            widget.enable_selection(True)

        # Replace connect button with confirm/cancel
        layout = self.disconnect_button.parentWidget().layout()
        layout.removeWidget(self.disconnect_button)
        self.disconnect_button.deleteLater()

        self.confirm_button = QPushButton("Confirm")
        self.cancel_button = QPushButton("Cancel")
        self.confirm_button.clicked.connect(self.confirm_selection)
        self.cancel_button.clicked.connect(self.cancel_selection)

        layout.addWidget(self.cancel_button)
        layout.addWidget(self.confirm_button)


    def cancel_selection(self) -> None:
        '''
        Cancel selection and restore the connect/disconnect button.
        '''
        for widget in self.server_widgets.values():
            widget.enable_selection(False)
        self._restore_disconnect_button()


    def confirm_selection(self) -> None:
        '''
        Confirm selection, toggle connection state, emit signal, and restore button.
        '''
        for widget in self.server_widgets.values():
            if widget.is_selected():
                widget.toggle_connection_state()  # this triggers widget.connection_changed
            widget.enable_selection(False)
        self._enforce_single_connection()
        self._restore_disconnect_button()


    def _restore_disconnect_button(self) -> None:
        layout = self.cancel_button.parentWidget().layout()
        self.cancel_button.deleteLater()
        self.confirm_button.deleteLater()

        self.disconnect_button = QPushButton("Connect / Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect)
        layout.addWidget(self.disconnect_button)


    def _on_server_connection_changed(self, 
                                      address: str, 
                                      connected: bool) -> None:
        '''
        Emit the signal exactly like ConnectionPanel.
        Enforce single connection and update motor checkbox.
        '''
        log.info(f"[OptimizationPanel] Server connection status changed | address={address} | connected={connected}")
        self.server_connection_changed.emit(address, connected)
        self._enforce_single_connection()


    def _enforce_single_connection(self) -> None:
        '''
        Disconnect all other servers except the one currently connected.
        '''
        active_server = None
        for addr, widget in self.server_widgets.items():
            if widget.connected:
                if active_server is None:
                    active_server = addr
                else:
                    widget.toggle_connection_state()  # this emits server_connection_changed

        # Update motor checkbox
        self.motor_checkbox.setEnabled(active_server is not None)
        self.arm_checkbox.setEnabled(active_server is not None)
        self.next_sample_button.setEnabled(active_server is not None)
        if active_server is None:
            self.motor_checkbox.setChecked(False)
            self.arm_checkbox.setChecked(False)


    def update_server_last_msg(self, address: str) -> None:
        '''
        Helper to change the last time a message was received from a server.
        '''
        widget = self.server_widgets.get(address)
        if widget:
            widget.update_last_msg()


    def on_server_alive_changed(self, address: str, alive: bool) -> None:
        '''
        Indicate if a server stops answering.
        '''
        widget = self.server_widgets.get(address)
        if not widget:
            return

        if not alive and widget.connected:
            widget.toggle_connection_state()