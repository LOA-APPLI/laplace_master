# libraries
from laplace_log import log
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, 
    QListWidget, QListWidgetItem, QGroupBox
)
from PyQt6.QtCore import pyqtSignal

# project
from interface.widgets import ServerItemWidget
from interface.widgets import ServerControlWidget
from utils.json_encoder import json_style


class ConnectionPanel(QWidget):
    '''
    Class made to display a list of server properties.
    Two kinds of lines are available: 'ServerItemWidget' and 'ServerControlWidget'.
    The first one is always added for any valid server address.
    The second one is used to control the degree of freedom of the server.
    '''
    # signal to transmit a connection changed from ServerItemWidget
    # to MasterWindow where it will be transmit to ClientManager in order
    # to  open / close the corresponding client.
    server_connection_changed = pyqtSignal(str, bool)
    motor_connection_changed = pyqtSignal(str, int, bool, float)

    def __init__(self, title: str = ""):
        '''
        Initialization of the 'ConnectionPanel' class.

            Arg:
                title: (str)
                    the title of the ConnectionPanel
        '''
        super().__init__()  # heritage from QWidget

        self.title = title  # title of the ConnectionPanel

        # dictionary of the 'ServerItemWidget's stored in the ConnectionPanel
        self.server_widgets: dict[str, ServerItemWidget] = {}

        # dictionary of the 'ServerControlWidget's stored in the ConnectionPanel
        self.server_control_widgets: dict[str, list[ServerControlWidget]] = {}

        # Internal list of server
        self.server_list_data = []

        ### Main layout
            # Main outer layout
        outer_layout = QVBoxLayout(self)

            # Group box
        self.group_box = QGroupBox(title)
        outer_layout.addWidget(self.group_box)

            # inside the group box
        main_layout = QVBoxLayout(self.group_box)

            # list container
        self.server_list_widget = QListWidget()
        main_layout.addWidget(self.server_list_widget)

            # connect / disconnect button
        self.disconnect_button = QPushButton("Connect / Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect)
        main_layout.addWidget(self.disconnect_button)
        
        log.debug(f"Connection Panel '{title}' loaded.")


    def update_server_last_msg(self, address: str):
        '''
        Helper to change the last time a message was received.
        '''
        widget = self.server_widgets.get(address)  # get the widget from the dictionary
        if widget:                                 # if there is a widget
            widget.update_last_msg()               # change the last time a message was received


    def add_server(self, 
                   address: str,
                   name: str = "Unknown") -> None:
        '''
        Add a server line in the ConnectionPanel.
        Bind the 'connection_changed' signal to the
        function 'on_server_connection_changed'.

            Args:
                address: (str)
                    the server address.

                name: (str)
                    the name of the server, default 'Unknown'.
        '''
        # widget is content of the row, item is the layout of the row (size, position, ...)
        item = QListWidgetItem(self.server_list_widget)  # create a new list item

        widget = ServerItemWidget(address=address, name=name)                   # initialize the new server line
        widget.connection_changed.connect(self.on_server_connection_changed)    # bind the signal

        item.setSizeHint(widget.sizeHint())                 # set the size of the item
        self.server_list_widget.addItem(item)               # add the new item
        self.server_list_widget.setItemWidget(item, widget) # assign widget to item

        self.server_widgets[address] = widget               # store widget


    def add_server_controls(self, 
                            address: str,
                            freedom: int,
                            name_list: list) -> None:
        '''
        Add a control line in the ConnectionPanel.

            Args:
                address: (str)
                    the server address.

                freedom: (int)
                    the server degree of freedom.
                    (number of setable elements)
                
                name_list: (list)
                    the name list of the elements
                    belonging to the server
        '''
        self.server_control_widgets[address] = []
        
        log.info(f"The server {address} controls are:\n"
                 f"{json_style(name_list)}"
        )
        
        for i in range(freedom):
            item = QListWidgetItem(self.server_list_widget)
            widget = ServerControlWidget(address, i + 1, name_list[i])  # numbering starts at 1
            widget.enable_selection(False)                # controls are NOT selectable by default
            widget.motor_connection.connect(              # when a motor connection is changed
                self.on_motor_connection_changed          # use the corresponding function
            )

            item.setSizeHint(widget.sizeHint())
            self.server_list_widget.addItem(item)
            self.server_list_widget.setItemWidget(item, widget)

            self.server_control_widgets[address].append(widget)


    def on_disconnect(self) -> None:
        '''
        Function used when the 'Connect / Disconnect' button is pressed.
        Enable the checkBox of every widget in 'server_list_widget'.
        '''
        for i in range(self.server_list_widget.count()):
            widget = self.server_list_widget.itemWidget(
                self.server_list_widget.item(i)
            )
            if isinstance(widget, (ServerItemWidget, ServerControlWidget)):
                widget.enable_selection(True)

        self._replace_buttons()


    def restore_disconnect_button(self) -> None:
        '''
        Function used to restore the 'Connect / Disconnect' button.
        '''
        parent_layout = self.cancel_button.parentWidget().layout()
        parent_layout.removeWidget(self.cancel_button)
        parent_layout.removeWidget(self.confirm_button)

        self.cancel_button.deleteLater()
        self.confirm_button.deleteLater()

        self.disconnect_button = QPushButton("Connect / Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect)
        parent_layout.addWidget(self.disconnect_button)


    def _replace_buttons(self) -> None:
        '''
        Function used to replace the 'Connect / Disconnect' button
        with 'Confirm' and 'Cancel'.
        '''
        layout = self.disconnect_button.parentWidget().layout()

        layout.removeWidget(self.disconnect_button)
        self.disconnect_button.deleteLater()

        self.cancel_button = QPushButton("Cancel")
        self.confirm_button = QPushButton("Confirm")

        self.cancel_button.clicked.connect(self.cancel_selection)
        self.confirm_button.clicked.connect(self.confirm_selection)

        layout.addWidget(self.cancel_button)
        layout.addWidget(self.confirm_button)


    def cancel_selection(self) -> None:
        '''
        Reset configuration after using the 'Cancel' button.
        '''
        for i in range(self.server_list_widget.count()):
            widget = self.server_list_widget.itemWidget(
                self.server_list_widget.item(i)
            )
            if isinstance(widget, (ServerItemWidget, ServerControlWidget)):
                widget.enable_selection(False)

        self.restore_disconnect_button()


    def confirm_selection(self) -> None:
        '''
        Apply selection after using the 'Confirm' button.
        '''
        for i in range(self.server_list_widget.count()):
            widget = self.server_list_widget.itemWidget(
                self.server_list_widget.item(i)
            )
            if isinstance(widget, (ServerItemWidget, ServerControlWidget)):
                if widget.is_selected():
                    widget.toggle_connection_state()
                widget.enable_selection(False)

        self.restore_disconnect_button()


    def on_server_connection_changed(self, 
                                     address: str,
                                     connected: bool) -> None:
        '''
        Transmit a signal from 'ServerItemWidget' to MasterWindow
        and synchronize ServerControlWidget states.
        '''
        log.info(f"[ConnectionPanel {self.title}] Server connection status changed | address={address} | connected={connected}")
        self.server_connection_changed.emit(address, connected)

        list_widgets = self.server_control_widgets.get(address)
        main_widget = self.server_widgets.get(address)

        if not list_widgets or not main_widget:
            return

        for widget in list_widgets:
            if main_widget.connected != widget.connected:
                widget.toggle_connection_state()


    def on_motor_connection_changed(self, 
                                    address: str, 
                                    motor_index: int,
                                    enabled: bool,
                                    position: float) -> None:
        '''
        Function made to transmit the signal from the ServerControlWidget
        to the MasterWindow.
        '''
        self.motor_connection_changed.emit(address, motor_index, enabled, position)


    def on_server_alive_changed(self, address: str, alive: bool) -> None:
        '''
        Indicate if a server stops answering.
        '''
        widget = self.server_widgets.get(address)
        if not widget:
            return

        if not alive and widget.connected:
            widget.toggle_connection_state()


    # def update_server_data(self,
    #                        address: str,
    #                        data: dict) -> None:
    #     '''
    #     Transmit data to ServerControlWidget.
    #     '''
    #     if data:
    #         list_widgets = self.server_control_widgets.get(address)
    #         if not list_widgets:
    #             return

    #         for i, widget in enumerate(list_widgets):
    #             try:
    #                 widget.update_positions(data["positions"][i], data["unit"])
    #             except Exception as e:
    #                 log.error(f"Exception occured in ConnectionPanel update_server_data: {e}\n"
    #                           f"The data was: {data}")

    def update_server_data(self,
                       address: str,
                       data: dict) -> None:
        '''
        Transmit data to ServerControlWidget.
        '''
        if data:
            list_widgets = self.server_control_widgets.get(address)
            if not list_widgets:
                return

            for i, widget in enumerate(list_widgets):
                try:
                    position = data["positions"][str(i)]
                    widget.update_positions(position, data["unit"])
                except Exception as e:
                    log.error(f"Exception occurred in ConnectionPanel update_server_data: {e}\n"
                            f"The data was: {data}")