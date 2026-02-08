from core.engine import ProcessingEngine
from data.processor import process_batch
from utils.math_lib import legacy_compute

THRESHOLD_10 = 10
THRESHOLD_20 = 20
CONSTANT_3 = 3


def run():
    """
    Run.
    """
    engine = ProcessingEngine()
    val = legacy_compute(THRESHOLD_10, THRESHOLD_20)
    print(f"Result: {val}")
    engine.execute("ls")

    data = [1, 2, CONSTANT_3]
    processed = process_batch(data)
    print(f"Processed: {processed}")


if __name__ == "__main__":
    run()
