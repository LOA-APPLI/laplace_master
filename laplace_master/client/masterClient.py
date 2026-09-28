# libraries
import zmq
import time
from PyQt6.QtCore import pyqtSignal

from laplace_log import log
from laplace_server.protocol import (
    make_ping, make_info_request, make_opt_update, make_scan_update,
    make_get_request, make_save_request, make_set_request, 
    make_set_actuators, make_scan_act_position_update, 
    make_set_diagnostics
)

# project
from utils.helper_address import normalize_address



class MasterClient:
    '''
    Client responsible for communicating with a remote server via ZeroMQ (REQ/REP).

    This class wraps common protocol requests such as ping, info,
    get, set, save, and optimization updates. It handles socket creation,
    timeouts, reconnection logic, and basic reply validation.
    '''

    def __init__(self, address: str, timeout_ms: int = 2000):
        '''
        Initialize the MasterClient and connect to a server.

        Args:
            address: (str)
                The server address (e.g., "tcp://127.0.0.1:5555").
            
            timeout_ms: (int)
                Send and receive timeout in milliseconds. Defaults to 2000.
        '''
        self.address = normalize_address(address)   # be sure that the address start by the protocol ('tcp://')
        self.context = zmq.Context.instance()       # create zmq context
        self.connected = True                       # flag indicating if the client is running
        self.timeout_ms = timeout_ms

        try:
            self.socket = self.context.socket(zmq.REQ)        # create the socket
            self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)  # set the timeout (received)
            self.socket.setsockopt(zmq.SNDTIMEO, timeout_ms)  # set the timeout (sent)
            self.socket.connect(self.address)                 # connect to the address
        
        except zmq.ZMQError as e: 
            raise ValueError(f"Invalid server address: {address}") from e

        self.last_contact_time = 0.0
        self.enabled = True
        self.ready = False # True according to server criteria
        self.server_name = "Unknown"
        self.server_device = "Unknown"
        self.server_freedom = 0


    def set_connected(self, enabled: bool) -> None:
        '''
        Enable or disable the client connection.

        When enabling, the ZeroMQ socket is recreated.
        When disabling, the socket is closed.

        Args:
            enabled: (bool)
                True to enable communication, False to disable it.
        '''
        if self.connected == enabled:  # if the state is already the right one
            return                     # do nothing
        
        self.connected = enabled       # else set the new state

        if enabled:  # recreate the socket if it was disconnected
            try:
                self.socket.close(linger=0)
            except Exception:
                pass

            self.socket = self.context.socket(zmq.REQ)
            self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
            self.socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
            self.socket.connect(self.address)
        
        else:       # else disable the socket
            try:
                self.socket.close(linger=0)
            except Exception:
                pass


    def send_message(self, message: dict) -> dict | None:
        '''
        Send a JSON message to the server and wait for a reply.

        Args:
            message: (dict)
                The protocol message to send.

        Returns:
            dict | str | None:
                The server reply if successful,
                None if the client is disconnected or a timeout/error occurs.
        '''
        if not self.connected:  # if the client is not connecter
            return None         # ignore it (by returning None)
        
        try:                                     # try to send the message
            self.socket.send_json(message)
            reply = self.socket.recv_json()
            self.last_contact_time = time.time() # update the last time a message was received
            
            return reply    # return the response
        
        except (zmq.error.Again, zmq.ZMQError):  # if there was an error
            try:
                # On timeout or invalid socket
                self.socket.close(linger=0) # close the connection
            except Exception:
                pass
            return None


    def ping(self) -> bool:
        '''
        Send a ping request to the server.

        Returns:
            bool:
                True if the server replies with a valid PONG response,
                False otherwise.
        '''
        if not self.connected:      # if the client is not connected
            return False            # the server is not alive

        reply = self.send_message(
            make_ping("Master", self.server_name)
        )

        if not self._is_valid_reply(reply):  # if the response is not valid
            return False                     # the server is not alive

        if reply is not None:                       # if there is a response        
            payload: dict = reply.get("payload", {})
            return payload.get("PING") == "PONG"    # the server is alive is answering PONG
        
        return False    # else the server is not alive


    def info(self) -> dict | None:
        '''
        Request server information.

        Returns:
            dict | None:
                The server payload containing metadata (e.g., name, device),
                or None if the request fails.
        '''
        if not self.connected:  # if the client is not connected
            return None         # there is no information

        reply = self.send_message(
            make_info_request("Master", self.server_name)
        )

        if not self._is_valid_reply(reply): # if the response is not valid
            return None                     # there is no information

        if reply is not None:
            payload: dict = reply.get("payload", {})
            self.server_name = payload.get("name", "Unknown")
            self.server_device = payload.get("device", "Unknown")
            self.server_freedom = int(payload.get("freedom", 0))

            return payload


    def get(self) -> dict | None:
        '''
        Request current data from the server.

        Returns:
            dict | None:
                The full server reply if successful,
                None otherwise.
        '''
        if not self.connected:  # if the client is not connected
            return None         # there is no value

        reply = self.send_message(
            make_get_request("Master", self.server_name)
        )

        if not self._is_valid_reply(reply):  # if the response is not valid
            return None                      # there is no value

        return reply  # return the data received from the server

    
    def save(self, new_path: str):
        '''
        Send a save request to the server.

        Args:
            new_path: (str)
                The path where the server should store data.

        Returns:
            dict | None:
                The server reply if successful,
                None otherwise.
        '''
        if not self.connected:  # if the server is not connected
            return None         # there is no response

        reply = self.send_message(
            make_save_request("Master", self.server_name, path=new_path)
        )

        if not self._is_valid_reply(reply):  # if the response is not valid
            return None                      # there is no response

        return reply    # return the server response
    

    def set(self, positions: dict):
        '''
        '''
        reply = self.send_message(
            make_set_request("Master", self.server_name, positions=positions)
        )
        
        if not self._is_valid_reply(reply):
            return None
        
        return reply

    def set_actuators(self, controls: dict):
        '''
        '''
        reply = self.send_message(
            make_set_actuators("Master", self.server_name, controls)
        )

        if not self._is_valid_reply(reply):
            return None
        
        return reply

    def set_diagnostics(self, diagnostics: dict): 
        '''
        '''
        reply = self.send_message(
            make_set_diagnostics("Master", self.server_name, diagnostics)
        )

        if not self._is_valid_reply(reply):
            return None
        
        return reply

    def opt_update(self, data: dict) -> dict | None:
        '''
        Send an optimization configuration update to the server.

        Args:
            data: (dict)
                Dictionary containing configuration parameters.

        Returns:
            dict | None:
                The server reply if successful,
                None otherwise.
        '''
        reply = self.send_message(
            make_opt_update("Master", self.server_name, data=data)
        )
        
        if not self._is_valid_reply(reply):  # if the response is not valid
            return None                      # ignore it
        
        return reply   # return the server dictionary

    def scan_update(self, data: dict) -> dict | None:
        '''
        Sends scan data update to the server.

        Args:
            data: (dict)
                Dictionary containing scan data.

        Returns:
            dict | None:
                The server reply if successful,
                None otherwise.
        '''
        reply = self.send_message(
            make_scan_update("Master", self.server_name, data=data)
        )
        
        if not self._is_valid_reply(reply):  # if the response is not valid
            return None                      # ignore it
        
        return reply   # return the server dictionary        

    
    def scan_act_position_update(self, data: dict) -> dict | None:
        '''
        Send the current actuator positions to the server.

        Args:
            data: (dict)
                Dictionary containing motor positions

        Returns:
            dict | None:
                The server reply if successful,
                None otherwise.
        '''
        if self.ready:
            reply = self.send_message(
                make_scan_act_position_update("Master", self.server_name, data=data)
            )
        else :
            return None
        
        if not self._is_valid_reply(reply):  # if the response is not valid
            return None                      # ignore it
        
        return reply   # return the server dictionary
    
    def close(self) -> None:
        '''Close the underlying ZeroMQ socket immediately.'''
        self.socket.close(linger=0)


    def set_enabled(self, enabled: bool) -> None:
        '''
        Enable or disable the client at a higher level.

        When disabled, the socket is closed.
        When re-enabled, the socket is recreated.

        Args:
            enabled: (bool)
                True to enable communication, False to disable it.
        '''
        self.enabled = enabled
        if not enabled:
            try:
                self.socket.close(linger=0)
            except Exception:
                pass
        else:
            self._reset_socket()  # recreate the socket when enabling


    def _reset_socket(self) -> None:
        '''
        Recreate the ZeroMQ REQ socket with default timeouts
        and reconnect to the server address.
        '''
        try:
            self.socket.close(linger=0)
        except Exception:
            pass

        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, 2000)
        self.socket.setsockopt(zmq.SNDTIMEO, 2000)
        self.socket.connect(self.address)


    def _is_valid_reply(self, reply: dict | None) -> bool:
        '''
        Validate a server reply.

        Args:
            reply (dict | None):
                The received reply.

        Returns:
            bool:
                True if the reply exists and contains no error message,
                False otherwise.
        '''
        if reply is None:
            return False
        
        elif reply.get("error_msg") is not None:
            return False
        
        return True