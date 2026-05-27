"""Background worker for long-term memory extraction jobs."""

import threading
import time


class MemoryExtractionWorker(object):
    """Single-threaded polling worker for long-term memory jobs."""

    def __init__(self, memory_service, poll_interval_seconds=5):
        self.memory_service = memory_service
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, name="memory-extraction-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout=5):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run_loop(self):
        while not self._stop_event.is_set():
            self.memory_service.claim_and_process_next_job()
            self._stop_event.wait(self.poll_interval_seconds)

    def run_once(self):
        return self.memory_service.claim_and_process_next_job()
