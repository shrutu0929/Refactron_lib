THRESHOLD_VALUE = 5
MIN_X_VALUE = 5
MAX_Y_VALUE = 10
ITERATION_LIMIT = 100
MIN_ITERATION_VALUE = 10
MAX_ITERATION_VALUE = 5
def do_something_crazy(x: int, y: int) -> int:
    """
    This function performs a series of operations based on the input values x and y.
    It checks if x is greater than the threshold value and y is less than the max y value.
    If the conditions are met, it iterates over a range of numbers and prints a message.
    Finally, it returns the sum of x and y.
    """
    if x > THRESHOLD_VALUE:
        if y < MAX_Y_VALUE:
            for i in range(ITERATION_LIMIT):
                print("doing something", x)
    return x + y
do_something_crazy(10, 5)