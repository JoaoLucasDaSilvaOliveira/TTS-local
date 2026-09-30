"""Valida o painel contra o serviço real e salva uma captura da própria janela."""
import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from kokoro_reader.panel import Panel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", default="/tmp/kokoro-reader-panel.png")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    panel = Panel()
    panel.show()
    result = {"ok": False}

    def check():
        if not panel.connected:
            return
        assert panel.voice.currentData() == panel.status["voice"]
        assert panel.speed.text() == f"{panel.status['speed']:.2f} ×".replace(".", ",")
        assert panel.read.isEnabled()
        assert panel.grab().save(args.screenshot)
        print(f"connected state={panel.status['state']} platform={app.platformName()} screenshot={args.screenshot}")
        result["ok"] = True
        panel.quit_panel()

    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(200)
    QTimer.singleShot(15_000, panel.quit_panel)
    app.exec()
    panel.pool.waitForDone(20_000)
    if not result["ok"]:
        raise RuntimeError("Painel não conectou ao serviço em 15 s")


if __name__ == "__main__":
    main()
