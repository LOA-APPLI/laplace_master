# libraries
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal
from laplace_log import log
from laplace_server.protocol import DEVICE_OPT, DEVICE_SCAN, DEVICE_MOTOR

from utils.pack_actuator_data import pack_actuator_data


# project
from client.masterClient import MasterClient


@dataclass
class ServerInfo:
    '''Class made to define the information received from the server.'''
    address: str
    alive: bool
    already: bool
    name: str | None
    device: str | None
    freedom : int
    name_list: list


class ClientManager(QObject):
    '''
    Class made to organize the clients and send messages to the servers.
    '''
    server_pinged = pyqtSignal(str, bool)           # address, alive
    server_contacted = pyqtSignal(str)              # address
    server_data_received = pyqtSignal(str, dict)    # address, raw data

    def __init__(self):
        '''
        Initialize the ClientManager.

        Creates internal storage for active clients and associated
        server device types. No connections are established at
        initialization time.
        '''
        super().__init__()
        self.clients: dict[str, MasterClient] = {}  # {address: MasterClient}
        self.server_devices: dict[str, str] = {}    # {address: kind of device}


    def probe_server(self,
                     address: str,
                     saving_path: str) -> ServerInfo | None:
        '''
        Probe a server and attempt to establish communication.

        This method:
            1. Creates a MasterClient for the given address.
            2. Sends a ping to verify availability.
            3. If alive, stores the client and requests server info.
            4. Returns a structured ServerInfo object.

        Args:
            address: (str)
                Server address (e.g., "tcp://127.0.0.1:5555").
            
            saving_path: (str)
                Path transmitted to the server for saving operations.

        Returns:
            ServerInfo | None:
                - ServerInfo with alive=True if the server responds.
                - ServerInfo with alive=False if unreachable.
                - None if the address format is invalid.
        '''
        if address in self.clients.keys():       # if the client already exist
            client = self.clients[address]
            return ServerInfo(                   # return the corresponding informations
                address=address,
                alive=client.enabled,
                already=True,
                name=client.server_name,
                device=client.server_device,
                freedom=client.server_freedom,
                name_list=[]
            )
        
        log.info(f"Probing the server: {address}")
        # try to connect to the server
        try:
            client = MasterClient(address)
        except ValueError:
            return None      # if there is an error, (wrong address format) return None

        # try to contact the server
        alive = client.ping()
        if not alive:                   # if not answering
            client.close()              # close the client
            return ServerInfo(          # inform that server is not alive
                address=address,
                alive=False,
                already=False,
                name=None,
                device=None,
                freedom=0,
                name_list=[]
            )
        
        self.clients[address] = client  # add the client in the dictionary
        client.save(saving_path)        # transmit the saving path to the server

        # get the server informations
        info_dict = client.info()
        if info_dict is not None:                            # if the server responded
            name = info_dict.get("name", "Unknown")          # get the name
            device = info_dict.get("device", "Unknown")      # the device
            name_list = info_dict.get("name_list", [])
            try:                                             # the freedom (int format)
                freedom = int(info_dict.get("freedom", 0))
            except (TypeError, ValueError):
                freedom = 0

            self.server_devices[address] = device  # store the server device
            log.info(f'Device: {device}')
            
            return ServerInfo(     # return the structured informations
                address=address, 
                alive=True,
                already=False,
                name=name, 
                device=device, 
                freedom=freedom,
                name_list=name_list
            )

        # else there is a problem
        client.close()              # close the client
        self.clients.pop(address)   # pop the client from the dict
        return ServerInfo(          # return not alive
            address=address, 
            alive=False,
            already=False,
            name=None, 
            device=None, 
            freedom=0,
            name_list=[]
        )


    def remove_server(self, address: str) -> None:
        '''
        Remove a server from management and close its connection.

        Args:
            address (str):
                The server address.
        '''
        client = self.clients.pop(address, None)
        if client:
            client.close()


    def ping_all(self) -> None:
        '''
        Ping all connected servers and emit corresponding signals.

        For each connected client:
            - Sends a ping.
            - Emits `server_pinged`.
            - If alive, emits `server_contacted`.
            - Retrieves available data and emits `server_data_received`.

        Signals Emitted:
            - server_pinged(address, alive)
            - server_contacted(address)
            - server_data_received(address, data, device)
        '''
        # for each client
        for address, client in self.clients.items():
            
            if not client.connected:  # if the client is not connected
                continue              # ignore it

            alive = client.ping()                   # ping the client
            self.server_pinged.emit(address, alive) # emit a signal to update the server state

            if not alive:  # if the server die
                continue   # ignore it
            
            self.server_contacted.emit(address)    # update the last time the server responded
            

            reply = client.get()                   # get the data stored in the server
            if reply is not None:                  # if the data is received
                data = reply.get("payload", {}).get("data", {}) # extract the data from the reply
                self.server_data_received.emit(address, data)   # transmit it to the control system panel

    def get_all_controls(self) -> dict | None:
        controls = dict({})
        for address, client in self.clients.items():
            info = client.info()
            if info is None:
                return controls
            
            elif info.get('device') == 'MOTOR':
                motor_names = {address: info.get('name_list')}
                motor_state = {address: client.get()['payload']['data']}
                controls.update(pack_actuator_data(motor_names, motor_state))
                log.debug(f'Controls: {controls}')
        return controls


    def get_all_diagnostics(self) -> dict | None:
        diagnostics = dict({})
        for address, client in self.clients.items():
            info = client.info()
            if info is None:
                return diagnostics
            
            elif info.get('device') == 'CAMERA':
                camera_name = info.get('name')
                #camera_data = client.get()['payload']['data']
                camera_plottables_list = info.get('plottables_list')
                diagnostics[address] = {'name': camera_name, 'plottables_list': camera_plottables_list}
        return diagnostics

    
    def get_all_scanners(self) -> dict | None:
        scanners = dict({})
        for address, client in self.clients.items():
            info = client.info()
            if info is None:
                return scanners
            elif info.get('device') == 'SCAN':
                name_list = info.get('name_list')
                scanners[address] = name_list
        return scanners


    def set_scan_controls(self) -> None:
        controls = self.get_all_controls()
        scanners = self.get_all_scanners()
        log.debug(f'Controls: {controls}, scanners: {scanners}')
        for address, _ in scanners.items():
            client = self.clients[address]
            client.set_actuators(controls)

    def set_scan_diagnostics(self) -> None:
        diagnostics = self.get_all_diagnostics()
        scanners = self.get_all_scanners()
        log.debug(f'Diagnostics: {diagnostics}, scanners: {scanners}')
        for address, _ in scanners.items():
            client = self.clients[address]
            client.set_diagnostics(diagnostics)
    
    def poll_optimizer(self, address: str) -> dict | None:
        client = self.clients.get(address)
        if not client or not client.connected:
            return None

        if self.server_devices[address] != DEVICE_OPT:
            return None

        reply = client.get()
        if reply is None:
            return None

        return reply.get("payload", {}).get("data", {})

    def poll_scanner(self, address: str) -> dict | None:
        client = self.clients.get(address)
        if not client or not client.connected:
            return None

        if self.server_devices[address] != DEVICE_SCAN:
            return None

        reply = client.get()
        if reply is None:
            return None

        return reply.get("payload", {}).get("data", {})


    def save_all(self, new_path: str) -> None:
        '''
        Send a save path update to all connected servers.
        Only connected clients receive the update.

        Args:
            new_path: (str)
                The new saving path to transmit to each server.
        '''
        for address, client in self.clients.items():
            if not client.connected:
                continue
            client.save(new_path)


    def close_all(self) -> None:
        '''
        Close all active client connections and clear storage.
        '''
        for client in self.clients.values():
            client.close()
        self.clients.clear()


    def set_server_enabled(self, 
                           address: str, 
                           enabled: bool) -> None:
        '''
        Enable or disable communication with a specific server.

        Args:
            address: (str)
                The server address.
            
            enabled: (bool)
                True to allow communication, False to disable it.
        '''
        client = self.clients.get(address)
        if client:
            client.set_connected(enabled)

    
    def sample_point(self, inputs: dict) -> None:
        '''
        Send position updates to multiple servers.

        Args:
            inputs: (dict)
                Dictionary mapping:
                    {address (str): list[float | None]}
                Each list index represents a position index.
                None values are ignored.

        Behavior:
            - Filters out disconnected clients.
            - Builds a positions dictionary with explicit indices.
            - Sends a SET request to each relevant server.
        '''
        for addr, values in inputs.items():     # for each of the input addresses
            client = self.clients.get(addr)     # get the corresponding client

            if not client or not client.connected:  # if the client does not exist or is not connected
                continue                            # ignore it

            # Build positions payload with explicit indices
            positions = {}

            for position_index, value in enumerate(values):
                # print(f"position_index = {position_index}, value = {value}")
                if value is None:   # ignore the None values
                    continue

                positions[position_index] = value   # set the positions values

            # if there is no position for this address
            if not positions:
                continue      # ignore it
            print(f"positions send = {positions}")
            client.set(positions)   # send the positions to the server


    def send_opt(self, 
                 address: str, 
                 payload: dict) -> None:
        '''
        Send the result to the optimizing server.

        Args:
            address: (str)
                The server address.
            
            payload: (dict)
                Dictionary containing command parameters.
        '''
        client = self.clients.get(address)
        if not client or not client.connected:
            return

        if not self.server_devices[address] == DEVICE_OPT:
            return

        client.opt_update(data=payload)

    def send_scan(self, address: str, payload: dict)->None:
        client = self.clients.get(address)
        if not client or not client.connected:
            return

        if not self.server_devices[address] == DEVICE_SCAN:
            return

        client.scan_update(data=payload)


    def send_actuators_positions(self, 
                              address: str,
                              payload: dict) -> None:
        '''Send the current actuator positions
        to all scan devices
        
        Args:
            address: (str) Server address
            payload: (dict) Dict formatted as:
        '''
        client = self.clients[address]
        scanners = self.get_all_scanners()
        for scanner_address, _ in scanners.items():
            client = self.clients[scanner_address]
            client.scan_act_position_update(data=payload)


            

            

