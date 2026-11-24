import torch


def target_function(
    positions: dict,
    n_objectives: int = 3,) -> torch.Tensor:
    '''
    Test function supporting up to five dimensions and 1–3 objectives.

    Args:
        positions: Dictionary mapping zero-based axis indices to values.
        n_objectives: Number of objectives to return (1, 2, or 3).

    Returns:
        Tensor with shape [N, n_objectives], or [1, n_objectives]
        for a single point.
    '''
    if not positions:
        raise ValueError("At least one coordinate must be provided.")

    if n_objectives not in (1, 2, 3):
        raise ValueError("n_objectives must be 1, 2, or 3.")

    # Normalize keys and values.
    coords = {
        int(key): torch.as_tensor(value)
        for key, value in positions.items()
    }

    if any(i < 0 or i >= 5 for i in coords):
        raise ValueError("Axis indices must be between 0 and 4.")

    # Use the same dtype and device for all coordinates.
    first = next(iter(coords.values()))

    if not first.is_floating_point():
        first = first.to(torch.get_default_dtype())

    device, dtype = first.device, first.dtype

    coords = {
        i: value.to(device=device, dtype=dtype)
        for i, value in coords.items()
    }

    # Support scalar and broadcast-compatible batched coordinates.
    keys = list(coords)
    broadcast = torch.broadcast_tensors(*(coords[i] for i in keys))
    coords = dict(zip(keys, broadcast))

    center_1 = [2, 4, 0, 0, 0]
    width_1  = [1, 1, 4, 4, 4]

    center_2 = [6, 3, 0, 0, 0]
    width_2  = [10, 4, 6, 6, 6]

    center_3 = [3, 7, 0, 0, 0]
    width_3  = [8, 6, 6, 6, 6]

    center_4 = [4, 5, 0, 0, 0]
    width_4  = [6, 3, 6, 6, 6]

    # Only supplied axes contribute.
    def gaussian_exponent(center, width):
        return sum(
            (x - center[i]) ** 2 / width[i]
            for i, x in coords.items()
        )

    gaussian_1 = torch.exp(
        -gaussian_exponent(center_1, width_1)
    )
    gaussian_2 = torch.exp(
        -gaussian_exponent(center_2, width_2)
    )
    gaussian_3 = torch.exp(
        -gaussian_exponent(center_3, width_3)
    )

    denominator_1 = 1 + sum(
        x ** 2 for x in coords.values()
    )

    denominator_2 = 1 + sum(
        x ** (4 if i == 0 else 2)
        for i, x in coords.items()
    )

    result_1 = (
        gaussian_1
        + gaussian_2
        + 1 / denominator_1
    )

    result_2 = (
        -gaussian_1
        + 1 / denominator_2
        - gaussian_3
    )

    objectives = [result_1, result_2]

    if n_objectives >= 3:
        gaussian_4 = torch.exp(
            -gaussian_exponent(center_4, width_4)
        )

        result_3 = gaussian_4 + 1 / denominator_1
        objectives.append(result_3)

    result = torch.stack(objectives[:n_objectives], dim=-1)

    if result.ndim == 1:
        result = result.unsqueeze(0)

    return result