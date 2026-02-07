
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
    '''Refactored version using early returns (guard clauses).'''
    # Check invalid conditions first and return early
    if not a:
        return default_value

    # Each subsequent check is at the same level - no deep nesting
    if not meets_requirement_1():
        return early_result_1

    if not meets_requirement_2():
        return early_result_2

    # Main logic is at top level - easy to read
    result = perform_main_operation()
    return result
