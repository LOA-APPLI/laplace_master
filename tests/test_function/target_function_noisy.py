import torch

from target_function import target_function

noise_factor = 0.1


def target_function_noisy(
    positions: dict,
    n_objectives: int = 3,
    noise: float = noise_factor,) -> torch.Tensor:
    '''
    Evaluate the target function with independent multiplicative noise.

    Args:
        positions: Dictionary of motor-axis indices and values.
        n_objectives: Number of objectives to return (1, 2, or 3).
        noise: Maximum relative noise amplitude.

    Returns:
        Tensor with shape [N, n_objectives], or [1, n_objectives]
        for a single point.
    '''
    # Compute the noiseless objectives.
    values = target_function(
        positions=positions,
        n_objectives=n_objectives,
    )

    # Independent uniform noise for every point and objective.
    epsilon = noise * values.abs() * (
        2 * torch.rand_like(values) - 1
    )

    return values + epsilon