
from itertools import product
from laplace_log import log

# def pack_actuator_data(motor_names, motor_state):
#     controls = {}

#     for address, names in motor_names.items():
#         state = motor_state[address]

#         controls[address] = {
#             "moving": state["moving"],
#             "unit": state["unit"],
#             "shot_number": state["shot_number"],
#             "motors": [
#                 {
#                     "name": name,
#                     "position": position,
#                     "shot_position": shot_position,
#                 }
#                 for name, position, shot_position
#                 in zip(names, state["positions"], state["shot_positions"])
#             ],
#         }

#     return controls
def pack_actuator_data(motor_names, motor_state):
    controls = {}

    for address, names in motor_names.items():
        state = motor_state[address]

        controls[address] = {
            "moving": state.get("moving", False),
            "unit": state["unit"],
            "shot_number": state["shot_number"],
            "motors": {
                str(i): {
                    "name": name,
                    "position": state["positions"][str(i)],
                    "shot_position": state["shot_positions"][str(i)],
                }
                for i, name in enumerate(names)
            },
        }

    return controls

from itertools import product


def make_position_queue(settings: dict) -> list[dict]:
    """
    Convert scan settings into a queue of motor positions.

    Each queue entry maps an address to a dictionary of target positions,
    keyed by motor 'index'. 

    Parameters
    ----------
    settings : dict
        Dictionary of the form:
        {
            address: [
                [motor_name, {
                    'current': float,
                    'start': float,
                    'stop': float,
                    'step': float,
                    'rank': int,
                    'index': int,
                    'motor count': int
                }],
                ...
            ]
        }

    Returns
    -------
    list[dict]
        One dictionary per scan point, of the form
        {address: {index: target_position, ...}}.
    """
    log.info(f'Settings received by make_position_queue: {settings}')
    dimensions = []

    for address, motors in settings.items():
        for motor_name, motor_settings in motors:
            dimensions.append({
                'address': address,
                'name': motor_name,
                'index': motor_settings['index'],
                'start': motor_settings['start'],
                'stop': motor_settings['stop'],
                'step': motor_settings['step'],
                'rank': motor_settings['rank'],
            })

    # Rank 0 is the outermost loop.
    dimensions.sort(key=lambda d: d['rank'])

    def generate_values(start, stop, step):
        values = []
        value = start

        if step > 0:
            while value <= stop:
                values.append(value)
                value += step
        elif step < 0:
            while value >= stop:
                values.append(value)
                value += step
        else:
            raise ValueError("Step cannot be zero")

        return values

    value_lists = [
        generate_values(d['start'], d['stop'], d['step'])
        for d in dimensions
    ]

    queue = []

    for combination in product(*value_lists):
        # Every address gets an entry, even if nothing is scanned on it.
        positions = {address: {} for address in settings}

        for dimension, value in zip(dimensions, combination):
            positions[dimension['address']][str(dimension['index'])] = value

        queue.append(positions)

    log.info(f'Queue: {queue}')

    return queue

