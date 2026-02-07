
from utils.math_lib import legacy_compute
from core.engine import ProcessingEngine
from data.processor import process_batch

def run():
    '''
    Run.
    '''
    engine = ProcessingEngine()
    val = legacy_compute(10, 20)
    print(f"Result: {val}")
    engine.execute("ls")
    
    data = [1, 2, 3]
    processed = process_batch(data)
    print(f"Processed: {processed}")

if __name__ == "__main__":
    run()
