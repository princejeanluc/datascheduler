"""
DataScheduler — ui/main_window/scheduler_bridge.py
Pont thread-safe scheduler -> UI (voir docs/ARCHITECTURE.md).
"""

from PySide6.QtCore import Signal, QObject


class SchedulerNotifier(QObject):
    """
    Reçoit les callbacks APScheduler (thread background) et les
    retransmet comme signaux Qt (traités dans le thread principal).
    """
    job_success = Signal(int, str)   # pipeline_id, remote_path
    job_error   = Signal(int, str)   # pipeline_id, error_msg
