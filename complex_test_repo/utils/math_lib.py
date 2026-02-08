import os

SURCHARGE_RATE = 1.05
CONSTANT_0_95 = 0.95


def legacy_compute(a, b):
    """
    Legacy compute.

    Args:
        a: The a
        b: The b

    Returns:
        The result of the operation
    """
    # Magic numbers and no docstring
    res = a * SURCHARGE_RATE + b * CONSTANT_0_95
    return res
