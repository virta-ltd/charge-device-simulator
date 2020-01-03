class FrequentFlowOptions:
    def __init__(self, delay_seconds: int, count: int):
        self.delay_seconds = delay_seconds
        self.count = count

    run_last_time = -1
    run_counter = 0
