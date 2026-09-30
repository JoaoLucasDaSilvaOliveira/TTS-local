"""Probe Qt dock lifetime on the chosen QPA backend; no service or desktop writes.

Run with PYTHONPATH=src and QT_QPA_PLATFORM=wayland for native verification.
The initial show and final close are excluded from transition event counts.
"""
import json
import sys

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QLabel

from kokoro_reader.dock import DockShell


class LifetimeProbe(QObject):
    def __init__(self, dock):
        super().__init__()
        self.dock = dock
        self.events = []

    def eventFilter(self, target, event):
        if target is self.dock or isinstance(target, QWindow):
            kind = None
            if event.type() == QEvent.Type.PlatformSurface:
                kind = event.surfaceEventType().name
            elif event.type() in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Close):
                kind = event.type().name
            if kind:
                self.events.append({"target": "widget" if target is self.dock else "window", "event": kind})
        return False


def main():
    app = QApplication(sys.argv)
    app.setDesktopFileName("kokoro-reader")
    dock = DockShell()
    dock.setWindowTitle("Kokoro Reader")
    content = QLabel("Verificação da mesma superfície nativa\n" * 12)
    dock.body_layout.addWidget(content)
    probe = LifetimeProbe(dock)
    app.installEventFilter(probe)
    dock.show()
    baseline = {}
    samples = []
    steps = iter([True, False] * 10 + [True, False, True])

    def sample():
        samples.append({"same_window": dock.windowHandle() is baseline["window"],
                        "same_win_id": dock.winId() == baseline["id"],
                        "same_flags": dock.windowFlags() == baseline["flags"],
                        "visible": dock.isVisible() and dock.windowHandle().isVisible()})

    def finish():
        sample()
        events = list(probe.events)
        ok = all(all(item.values()) for item in samples) and not events
        print(json.dumps({"platform": app.platformName(), "transitions": len(samples) - 1,
                          "stable": ok, "initial_events": baseline["events"],
                          "transition_events": events, "samples": samples}, indent=2))
        app.removeEventFilter(probe)
        dock.close()
        app.exit(0 if ok else 1)

    def step():
        try:
            expanded = next(steps)
        except StopIteration:
            QTimer.singleShot(250, finish)
            return
        dock.set_expanded(expanded)
        sample()
        QTimer.singleShot(40, step)

    def begin():
        baseline.update(window=dock.windowHandle(), id=dock.winId(), flags=dock.windowFlags(),
                        events=list(probe.events))
        probe.events.clear()
        step()

    QTimer.singleShot(300, begin)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
