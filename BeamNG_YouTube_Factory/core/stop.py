"""Токен остановки процесса (кнопка STOP)."""
import threading


class StopRequested(Exception):
    """Пользователь нажал STOP."""


class CancelToken:
    def __init__(self):
        self._ev = threading.Event()

    def cancel(self):
        self._ev.set()

    def reset(self):
        self._ev.clear()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()

    def check(self):
        if self._ev.is_set():
            raise StopRequested()

    def sleep(self, seconds: float):
        """Прерываемый sleep."""
        if self._ev.wait(seconds):
            raise StopRequested()
