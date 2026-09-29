# libraries
from PyQt6.QtCore import QObject, pyqtSignal
from laplace_log import log
from laplace_server.protocol import DEVICE_GAS, DEVICE_MOTOR

# project
from client.clientManager import ClientManager
from utils.json_encoder import json_style
from utils.config_helper import get_from_config
from utils.pack_actuator_data import make_position_queue


class ScanBrain(QObject):
    '''
    Central controller of the optimization workflow.

    The Brain coordinates optimization suggestions, motor commands,
    and diagnostic measurements. It manages the evaluation queue,
    synchronizes measurements from multiple sources, and returns
    aggregated results to the optimization server.
    '''
    queue_updated = pyqtSignal(list, dict)

    def __init__(self, client_manager: ClientManager):
        '''
        Initialize the Brain.

        Arg:
            client_manager: (ClientManager)
                Communication interface used to interact with control,
                diagnostic, and optimization servers.
        '''
        super().__init__()  # heritage from QObject
        
        self.client_manager = client_manager
        self.armed = False
        self.motor_control_enabled = False  # the right to move motors
        
        self.suggestions = []  # candidates suggested by the optimizer
        self.results = []      # collected results from the diagnostics
        self.obj_spec = {}     # address of the objectives and keys associated

        self.current = None                 # Currently evaluated sample
        self.waiting: bool = False          # boolean indicating if we are in a measurement process
        self.motion_pending: bool = False   # boolean indicating if motors are moving or expected to move

        self.scan_address: str = "Unknown"        # Address of the OPT server
        self.motors: dict[str, list[dict]] = {}  # mask to determine which motor can move and what was the position when state changed
        
        self.shot_number_from_diags = {}    # the diagnostic addresses and the shot number they sent
        # self.motor_position_validated_at_shot = {}

        ### loading tolerances
        self.tolerance_gas = get_from_config(
            module="opt",
            item="tolerance_gas",
            default_value=1e-2,
            type=float
        )

        self.tolerance_motors = get_from_config(
            module="opt",
            item="tolerance_motors",
            default_value=1e-3,
            type=float
        )
        
        log.debug(f"Tolerances loaded: tolerance gas = {self.tolerance_gas}, tolerance motors = {self.tolerance_motors}")

        self.shot_number = -1                       # new shot number to come
        self.latest_shot_number = -1                # previous shot number
        self.new_shot_available = False             # boolean indicatif if there is a new shot
        self.pending_motor_addresses = set()        # addresses of the motors that are still moving
        self.expected_sources: set[str] = set()     # addresses of the diagnostics from which we are still waiting a key

        self.desync_mode = False
        self.desync_counter = 0
        self.desync_threshold = 3
        self.last_good_shot = None

        self.resync_counter = 0
        self.resync_threshold = 3


        # whether to add some logs that can be triggered often
        self.is_trig_logs = get_from_config(
            module="logs",
            item="is_trig_logs",
            default_value=False,
            type=bool
        )
        log.debug(f"Trig logs on." if self.is_trig_logs else "Trig logs off.")
        
        log.info("Brain loaded.")

    def reset_shot_system(self) -> None:
        # reset shot state
        self.shot_number = -1
        self.latest_shot_number = -1
        self.new_shot_available = False
        self.pending_motor_addresses = set()
        self.expected_sources: set[str] = set()


    def set_armed(self, armed: bool) -> None:
        self.reset_shot_system()
        log.info("System armed: starting loop")
        self.armed = armed

    
    def on_shot(self, shot_number: int) -> None:
        if not self.armed:
            return

        if self.desync_mode:
            self._handle_resync_shot(shot_number)
            return


        # strict monotonic global stream
        if shot_number <= self.latest_shot_number:
            return

        log.debug(f"[Shot] global={shot_number} expected_next={self.latest_shot_number}")

        self.latest_shot_number = shot_number

        self.new_shot_available = True
        
    def update_controls_and_diagnostics(self) -> None:
        self.client_manager.set_scan_controls()
        self.client_manager.set_scan_diagnostics()
        

    def tick(self) -> None:
        '''
        Define where is the master in the sampling procedure.
        '''
        if not self.armed:
            return
        
        if self.motion_pending:     # if the motor are moving
            return                  # let the time to the device to move

        if self.desync_mode:
            return

        if not self.waiting:                             # if we are not waiting for a diagnostic (we can start next sample)
            if self.new_shot_available:                  # if a new shot has been recorded
                self._next(self.latest_shot_number)      # start the next sample
                self.new_shot_available = False          # we considered the new shot 


        # otherwise we are waiting for a diagnostic
        if self._can_finalize():                # verify if the sample has finished since last tick           # if self._is_measurement_complete():
            log.debug("Sample finilized.")
            self._finalize_current_sample()


    def _can_finalize(self) -> bool:
        '''
        Verify if the sample is complete.
        '''
        ok = (
            self.waiting                                  # we were waiting for a diagnostic
            and not self.motion_pending                   # the motors are not moving
            and hasattr(self, "expected_sources")         # the brain has an 'expected_sources' attribute
            and len(self.expected_sources) == 0           # there is no diagnostic expected
            and len(self.pending_motor_addresses) == 0    # there is no motor expected to move
        )

        
        return ok
    
    def _enter_desync_mode(self):
        if self.desync_mode:
            return

        log.warning("DESYNC detected → freezing system")

        self.desync_mode = True
        self.waiting = False
        self.motion_pending = False

        self.expected_sources.clear()
        self.pending_motor_addresses.clear()

        self.resync_counter = 0
        self.desync_counter = 0


    def _exit_desync_mode(self):
        log.info("Resynchronization successful")

        self.desync_mode = False
        self.desync_counter = 0
        self.resync_counter = 0

        self.reset_shot_system()

        # self.last_good_shot = self.latest_shot_number


    def _observe_shot(self, shot_number: int | None, source: str):
        """
        Only validates consistency against current expected shot.
        Does NOT update any reference state.
        """

        if shot_number is None:
            return

        if self.desync_mode:
            # only monitor stability, no decisions yet
            return

        # no expected shot yet
        if self.shot_number == -1:
            return
        
        if shot_number < self.shot_number:
            return

        # STRICT MATCH REQUIRED (NO TOLERANCE)
        if shot_number > self.shot_number:  # !=
            self.desync_counter += 1

            log.warning(
                f"[DESYNC suspicion] source={source} "
                f"got={shot_number} expected={self.shot_number} "
                f"counter={self.desync_counter}"
            )

            if self.desync_counter >= self.desync_threshold:
                self._enter_desync_mode()

            return

        # correct observation → reset ONLY counter
        self.desync_counter = 0



    def _handle_resync_shot(self, shot_number: int):

        # first contact
        if self.shot_number == -1:
            self.shot_number = shot_number
            return

        # require strict monotonic global recovery
        if shot_number == self.latest_shot_number + 1:
            self.desync_counter += 1
        else:
            self.desync_counter = 0

        self.latest_shot_number = shot_number

        if self.desync_counter >= self.desync_threshold:
            self._exit_desync_mode()


    def on_scan_data(self, scan_address: str, 
                        settings: dict) -> None:
        '''
        Handles incoming settings from the scan server.

        Resets the current state, unpacks the settings dictionary into a list of samples,
        loads samples into the queue and starts the scan if possible.

        Args:
            scan_address: (str)
                Address of the scan server.

            data: (dict)
                Payload containing scan settings.
        '''
        log.info(f"Scan settings received {settings}. Updating queue")
                # reset the attributes
        self.suggestions.clear()
        self.results.clear()
        self.obj_spec.clear()
        self.scan_address = scan_address
        self.current = None
        self.waiting = False
        log.info("Previous queue cleared.")

        queue = make_position_queue(settings) 
        # add samples to the suggestions

        self.suggestions = queue

        self.queue_updated.emit(queue, dict({}))


    def _next(self, shot_number: int, next_in_queue: int | None=None) -> None:
        '''
        Start evaluation of the next suggested sample if allowed.

        A new sample is triggered only if the system is not already
        waiting for measurements and motor control is enabled
        (or explicitly forced via `next_in_queue`).
        '''
        # Do not proceed if motors are not enabled
        # unless we explicitly ask for an element in the suggestions
        if not (self.motor_control_enabled or next_in_queue is not None):
            return
        
        if shot_number < 0:
            return

        if not self.new_shot_available:
            return

        # if we are waiting for a measure 
        if self.waiting:
            if self.is_trig_logs:
                log.debug(f"The method _next was triggered while we were still waiting for a diagnostic (shotnumber {self.shot_number}).\n"
                          f"The shot number {shot_number} is then dropped from master.")
            return         # don't look for the next suggestion

        if self.motion_pending:
            if self.is_trig_logs:
                log.debug(f"The method _next was triggered while we were still moving the motors (shot number {self.shot_number}).\n"
                          f"The shot number {shot_number} is then dropped from master.")
            return
    
        if not self.suggestions:                        # if there is no suggestion
            log.info("No suggestion available.")        # send the results
            return                                      # get out of the function

        if next_in_queue is None:
            next_in_queue = 0

        self.shot_number = shot_number  # update the shot number

        self.current = self.suggestions.pop(next_in_queue)  # get the current point to sample and pop it from the suggestions
        self.queue_updated.emit(self.suggestions, self.obj_spec)
        self.waiting = True                     # we start to wait for a measure (some diagnostics)
        self.motion_pending = True              # we need to move motors
        self.current_measurements = {}          # gather the measures
        self.shot_number_from_diags = {}
        # self.motor_position_validated_at_shot = {}

        #self.pending_motor_addresses = set(self.current["inputs"].keys())  # addresses of the motors to move
        self.pending_motor_addresses = set(self.current.keys())

        self.expected_sources = set(self.client_manager.get_all_diagnostics().keys())                   # addresses of the diagnostics we are waiting for: all diagnostics
        log.info(f'Expected sources: {self.expected_sources}')

        # filter the allowed motors
        inputs = {}
        #for addr, targets in self.current["inputs"].items():
        log.info(f'self.current: {self.current}')
        for addr, targets in self.current.items():
            
            motor_list = self.motors.get(addr)
            
            if motor_list is None:
                inputs[addr] = targets
                continue

            filtered = []

            for i, t in enumerate(targets):
                if motor_list[i]["enabled"]:
                    filtered.append(t)
                else:
                    position = motor_list[i]["position"]
                    filtered.append(position)
                    log.info(f"The motor {i + 1} from {addr} is disabled.\n" 
                             f"Using the current position: {position}, rather than the suggestion: {t}")
            
            inputs[addr] = filtered
        
        log.info("Measuring inputs:\n"
                    f"{json_style(inputs)}\n"
                    f"It should be related with the next shot number to come ({self.shot_number})")

        self.client_manager.sample_point(inputs)  # send the imputs to control system servers
        self.commanded_inputs = inputs            # what was asked to the motors 

    def on_motor_position_update(self, address: str, positions: dict):
        # update the motor mask
        motor_list = self.motors.get(address)

        if motor_list:
            for i, pos in enumerate(positions.get("positions", [])):
                motor_list[i]["position"] = pos

        if not self.waiting or not self.motion_pending:
            return

        target = self.commanded_inputs

        # motor_shot = positions.get("shot_number")
        # if motor_shot is not None:
        #     self.motor_position_validated_at_shot[address] = motor_shot

        if self._motors_match_target(address, positions, target):
            self.pending_motor_addresses.discard(address)
            if not self.pending_motor_addresses:
                log.info("Motors reached target. Starting measurement phase.")
                self.motion_pending = False


    def _motors_match_target(self, address, current, target):        
        # current_positions = current.get("shot_positions", [])
        current_positions = current.get("positions", [])
        target_positions = target.get(address)
        
        # motor_shot = current.get("shot_number")
        # if motor_shot is not None:
        #     self._observe_shot(motor_shot, source="motor")
        
        # motor_shot = current.get("shot_number")
        # self._observe_shot(motor_shot, source="motor")

        if target_positions is None:
            return False

        if len(current_positions) < len(target_positions):
            return False

        for c, t in zip(current_positions, target_positions):

            if t is None:
                continue
            
            if self.client_manager.server_devices[address] == DEVICE_GAS:
                device = "Gas"
                if abs(c - t) > self.tolerance_gas:
                    return False
            
            elif self.client_manager.server_devices[address] == DEVICE_MOTOR:
                device = "Motor"
                if abs(c - t) > self.tolerance_motors:
                    return False
        
        log.debug(f"{device} tolerance passed, for address {address}.")
        
        return True


    def on_measurement(self, 
                       address: str, 
                       data: dict) -> None:
        '''
        Process a measurement received from a diagnostic server.

        Measurements are collected until all expected sources have
        responded for the current sample.

        Args:
            address: (str)
                Address of the diagnostic server.
            
            data: (dict)
                Measured values for the current sample.
        '''
        if not self.armed:
            return

        if not data:
            return
        
        if not self.waiting:               # if we are not waiting for a measure
            if self.is_trig_logs and data:
                log.debug(f"The method on_measurement was triggered while we were not waiting for a diagnostic (shot number {self.shot_number}).")
            return                         # we do not continue

        if self.motion_pending:
            if self.is_trig_logs and data:
                log.debug(f"The method on_measurement was triggered while we were still moving motor (shot number {self.shot_number}).\n"
                          f"The diagnostic was then dropped.")
                if "shot_number" in data.keys():
                    log.debug(f"The dropped diagnostic had shot number {data['shot_number']}")
            return


        values = data
        if not isinstance(values, dict):
            log.debug(f"The type of the data ({type(values)}) received from the diagnostic {address} is not {dict}.")
            return
        
        shot = values.get("shot_number")
        self._observe_shot(shot, source=f"diag:{address}")

        if shot is None:
            log.debug("Missing shot_number, dropping diagnostic")
            return
        
        if shot != self.shot_number:
            log.warning(f"Dropping diagnostic: expected {self.shot_number}, got {shot}")
            return

        if values:
            log.info(
                f"Measurement received from {address}:\n"
                    f"{json_style(values)}"
            )

        for key, value in values.items():
                self.current_measurements.setdefault(address, {})[key] = value

        self.expected_sources.discard(address)
        log.info(f"expected sources remaining: {self.expected_sources}")
        
        self.shot_number_from_diags[address] = values["shot_number"]


    def _finalize_current_sample(self) -> None:
        '''
        Finalize the current sample once all measurements are collected.

        The aggregated inputs and outputs are stored. If additional
        suggestions remain, evaluation continues; otherwise results
        are sent back to the optimizer.
        '''
        if not isinstance(self.current, dict):
            log.debug(f"Impossible to finalize the current sample, self.current must be a {dict}, not ({type(self.current)})")
            return
        
        # self.results.append({
        #     "inputs": self.current,
        #     "outputs": self.current_measurements,
        #     "shot_number_from_master": self.shot_number,
        #     "shot_number_from_diags": self.shot_number_from_diags,
        # })
        self.results = {
            "inputs": self.current,
            "outputs": self.current_measurements,
            "shot_number_from_master": self.shot_number,
            "shot_number_from_diags": self.shot_number_from_diags,
         }
        log.info(f'Results: {self.results}')

        for key in self.shot_number_from_diags.keys():
            if self.shot_number != self.shot_number_from_diags[key]:
                log.error("The shot number from the master and the diagnostics are different.")
        

        self.current = None
        self.waiting = False
        self.shot_number = -1
        self.shot_number_from_diags = {}

        self.queue_updated.emit(self.suggestions, self.obj_spec)
        self._send_results()
        self.current_measurements = {} # Empty current measurements dictionary 

        #if not self.suggestions:
        #    self._send_results()
            


    def _send_results(self) -> None:
        '''
        Send collected batch results to the optimization server.
        '''
        if self.scan_address is None:
            log.debug(f"The optimizer adress is {None}. Impossible to send back results.")
            return

        if self.results:
            payload = {"results": self.results}
            log.info(f"Sending results to scan manager: {self.scan_address}\n"
                    f"{json_style(payload)}")

            self.client_manager.send_scan(self.scan_address, payload)


    def set_motor_control(self, enabled: bool) -> None:
        '''
        Enable or disable motor control.

        When enabling control, the next queued sample is triggered
        if available.

        Arg:
            enabled : bool
                Whether motor movement is allowed.
        '''
        # set the motor control
        self.motor_control_enabled = enabled
        
        # if enabled:         # if motors can be drive
        #     self._next(shot_number=-1)    # get the next sample


    def set_motor_enabled(self, 
                          address: str, 
                          index: int, 
                          enabled: bool,
                          position: float) -> None:
        '''
        Define if the motor can move.
        '''
        if address not in self.motors:
            return

        self.motors[address][index - 1] = {"enabled": enabled, "position": position}


    def register_motor_server(self, address: str, freedom: int):
        '''Set the motor mask'''
        self.motors[address] = [
            {"enabled" : True, "position": None}
            for _ in range(freedom)
        ]


    def delete_suggestion(self, index: int):
        deleted = self.suggestions.pop(index)
        log.info(f"Suggestion deleted:\n"
                    f"{json_style(deleted)}")