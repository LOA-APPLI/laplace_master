
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

def make_position_queue(settings: dict) -> list[dict]:
    """
    Convert scan settings into a queue of motor positions.

    A motor that is not present in the scan settings gets None as
    its position, meaning that motor should not be moved.

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
        A list of dictionaries containing one position list per address.
    """

    dimensions = []
    address_motor_count = {}

    for address, motors in settings.items():

        if motors:
            # The total number of motors is explicitly provided.
            address_motor_count[address] = motors[0][1]['motor count']
        else:
            address_motor_count[address] = 0

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
        generate_values(
            dimension['start'],
            dimension['stop'],
            dimension['step']
        )
        for dimension in dimensions
    ]

    combinations = product(*value_lists)

    queue = []

    for combination in combinations:

        # Create a position for EVERY motor.
        # Motors not present in dimensions remain None.
        positions = {
            address: [None] * count
            for address, count in address_motor_count.items()
        }

        # Fill in the motors that are actually being scanned.
        for dimension, value in zip(dimensions, combination):
            address = dimension['address']
            index = dimension['index']

            positions[address][index] = value

        queue.append(positions)

    return queue

if __name__ == "__main__":
    data =  {'positions': [0.0, 0.0], 'moving': False, 'unit': 'a.u.', 'shot_number': -1, 'shot_positions': [0.0, 0.0]}