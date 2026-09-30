"""Opt-in Qt clicks against the real service; human desktop E2E is separate."""
import sys
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kokoro_reader.cli import send
from kokoro_reader.panel import Panel


def main():
    if send({"command": "status"})["state"] != "idle":
        raise RuntimeError("Pare a leitura atual antes de executar o teste com áudio.")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("kokoro-reader")
    app.setDesktopFileName("kokoro-reader")
    panel = Panel()
    panel.show()
    phase, cycle = 0, 0
    deadline = time.monotonic() + 45
    result = {"ok": False, "error": None}
    text = ("Teste dos controles da doca. A leitura deve pausar, retomar e parar "
            "sem expandir o painel. Esta frase mantém áudio suficiente para verificar os botões.")

    def check():
        nonlocal phase, cycle
        try:
            if time.monotonic() > deadline:
                raise RuntimeError(f"Timeout no ciclo {cycle}, etapa {phase}")
            if panel.pending is not None or not panel.connected:
                return
            state = panel.status.get("state")
            if phase == 0:
                if cycle:
                    panel.set_expanded(True, animate=False)
                    panel.set_expanded(False, animate=False)
                panel.submit("read", text=text, source={"kind": "test"})
                phase = 1
            elif phase == 1 and state == "playing":
                if panel.expanded or not panel.compact_pause.isEnabled():
                    raise RuntimeError(f"pause unavailable: expanded={panel.expanded}, "
                                       f"window_enabled={panel.isEnabled()}, header_enabled={panel.header_container.isEnabled()}, "
                                       f"pause_enabled={panel.compact_pause.isEnabled()}, "
                                       f"body_ancestor={panel.body.isAncestorOf(panel.compact_pause)}")
                QTest.mouseClick(panel.compact_pause, Qt.MouseButton.LeftButton)
                phase = 2
            elif phase == 2 and state == "paused":
                assert panel.compact_play.isEnabled() and panel.compact_stop.isEnabled()
                QTest.mouseClick(panel.compact_play, Qt.MouseButton.LeftButton)
                phase = 3
            elif phase == 3 and state == "playing":
                assert panel.compact_stop.isEnabled()
                QTest.mouseClick(panel.compact_stop, Qt.MouseButton.LeftButton)
                phase = 4
            elif phase == 4 and state == "idle":
                assert not panel.expanded and not panel.compact_pause.isEnabled()
                print(f"cycle={cycle} compact pause/resume/stop passed platform={app.platformName()}")
                cycle += 1
                if cycle == 2:
                    result["ok"] = True
                    timer.stop()
                    panel.quit_panel()
                else:
                    phase = 0
        except Exception as error:
            result["error"] = error
            timer.stop()
            panel.quit_panel()

    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(100)
    try:
        app.exec()
    finally:
        panel.pool.waitForDone(20_000)
        send({"command": "stop"})
    if not result["ok"]:
        raise RuntimeError("Teste de controles compactos falhou") from result["error"]


if __name__ == "__main__":
    main()
