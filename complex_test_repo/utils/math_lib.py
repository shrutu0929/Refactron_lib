
import os

def legacy_compute(a, b):
    '''
    Legacy compute.
    
    Args:
        a: The a
        b: The b
    
    Returns:
        The result of the operation
    '''
    # Magic numbers and no docstring
    res = a * 1.05 + b * 0.95
    return res
