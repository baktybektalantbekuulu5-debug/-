"""Журнал событий: файл + консоль + подписчики (GUI)."""
import logging
import logging.handlers
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_listeners = []


class _CallbackHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        for cb in list(_listeners):
            try:
                cb(record.levelname, msg)
            except Exception:
                pass


def add_listener(cb):
    _listeners.append(cb)


def remove_listener(cb):
    if cb in _listeners:
        _listeners.remove(cb)


def setup_logging(level=logging.INFO) -> logging.Logger:
    log = logging.getLogger("factory")
    if log.handlers:
        return log
    log.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    logdir = ROOT / "logs"
    logdir.mkdir(exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(logdir / "factory.log", maxBytes=2_000_000,
                                              backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    cb = _CallbackHandler()
    cb.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    for h in (fh, ch, cb):
        log.addHandler(h)
    return log


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger("factory." + name)
