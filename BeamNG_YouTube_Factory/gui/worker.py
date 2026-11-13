from PySide6.QtCore import QThread, Signal

from core.stop import StopRequested


class PipelineWorker(QThread):
    progress = Signal(float, str, str)
    log = Signal(str, str)
    done = Signal(bool, object)       # ok, result|error text

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            res = self.fn()
            self.done.emit(True, res)
        except StopRequested:
            self.done.emit(False, "Остановлено пользователем")
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, str(e))
