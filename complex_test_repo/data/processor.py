
import time

def process_batch(data_list):
    '''
    Process batch.
    
    Args:
        data_list: Data to process
    
    Returns:
        The result of the operation
    '''
    # Performance issue: N+1 pattern or inefficient iteration
    results = []
    for item in data_list:
        # Simulating sub-query or heavy processing in loop
        detail = get_item_detail(item)
        results.append(detail)
    return results

def get_item_detail(item):
    '''
    Get item detail.
    
    Args:
        item: The item
    
    Returns:
        The requested item detail
    '''
    return {"id": item, "details": "example"}

def deep_nesting_example(a, b, c, d):
    '''
    Deep nesting example.
    
    Args:
        a: The a
        b: The b
        c: The c
        d: The d
    '''
    # Complexity issue: Deep nesting
    if a:
        if b:
            for i in range(10):
                if c:
                    while d:
                        print(i)
                        break
