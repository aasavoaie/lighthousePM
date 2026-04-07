_started = False


def start_scheduler() -> None:
    global _started
    _started = True


def stop_scheduler() -> None:
    global _started
    _started = False
