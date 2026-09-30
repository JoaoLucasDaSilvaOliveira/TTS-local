"""Verificação Qt em offscreen, sem controlar janelas de outras aplicações."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from kokoro_reader.panel import Panel


@pytest.fixture
def panel(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(Panel, "poll", lambda self: None)
    widget = Panel()
    widget.timer.stop()
    yield widget
    widget.quitting = True
    widget.tray.hide()
    widget.close()
    widget.deleteLater()
    app.processEvents()


def status(state="idle", **values):
    return {"state": state, "segment_count": 0 if state == "idle" else 2,
            "segment_index": None if state == "idle" else 0, "speed": 1.0,
            "voice": "pf_dora", "segment_text": "Texto.", **values}


def test_buttons_follow_service_state(panel):
    panel.receive(status(), None, False)
    assert panel.read.isEnabled() and not panel.stop.isEnabled()
    panel.receive(status("playing"), None, False)
    assert panel.pause.isEnabled() and not panel.play.isEnabled()
    panel.receive(status("paused"), None, False)
    assert panel.play.isEnabled() and not panel.pause.isEnabled()
    assert panel.next.isEnabled() and panel.backward.isEnabled()
    panel.receive(None, "offline", False)
    assert not panel.read.isEnabled() and not panel.stop.isEnabled()


def test_speed_poll_does_not_send_command(panel, monkeypatch):
    commands = []
    monkeypatch.setattr(panel, "submit", lambda command, **kw: commands.append((command, kw)))
    panel.receive(status(speed=1.25, voice="pm_alex"), None, False)
    assert panel.speed.text() == "1,25 ×" and panel.voice.currentData() == "pm_alex"
    assert commands == []


def test_read_label_stays_consistent_after_poll_and_file_clear(panel, tmp_path):
    from kokoro_reader.files import load_document
    panel.receive(status(_selection=("Texto selecionado.", "")), None, False)
    assert panel.read.text() == "Iniciar leitura"
    assert panel.compact_play.toolTip() == panel.compact_play.accessibleName() == "Iniciar leitura"
    labels = [action.text() for action in panel.tray.contextMenu().actions()]
    assert "Iniciar leitura" in labels and "Ler seleção / clipboard" not in labels
    panel.receive(status("paused"), None, False)
    assert panel.compact_play.toolTip() == "Retomar"
    path = tmp_path / "estudo.txt"
    path.write_text("Texto do arquivo.")
    document = load_document(path)
    panel.files.controller.document = document
    panel.files._loaded(document)
    assert panel.read.text() == "Ler arquivo"
    panel.files.clear()
    panel.receive(status(), None, False)
    assert panel.read.text() == panel.compact_play.toolTip() == "Iniciar leitura"


def test_commands_clicked_during_poll_are_queued(panel):
    from kokoro_reader.panel import Request
    panel.pending = Request({"command": "status"})
    panel.submit("stop")
    assert panel.queued == [("stop", {})]


def test_buttons_send_explicit_commands(panel, monkeypatch):
    commands = []
    monkeypatch.setattr(panel, "submit", lambda command, **kw: commands.append(command))
    panel.receive(status("playing"), None, False)
    panel.pause.click()
    panel.forward.click()
    panel.backward.click()
    panel.next.click()
    panel.previous.click()
    panel.stop.click()
    panel.receive(status("paused"), None, False)
    panel.play.click()
    assert commands == ["pause", "seek-forward", "seek-backward", "next", "previous", "stop", "play"]


def test_read_uses_preview_text_even_after_completion(panel, monkeypatch):
    from kokoro_reader.panel import Request
    captured = []
    monkeypatch.setattr(panel.pool, "start", lambda task: captured.append(task.command))
    panel.selection.update("Texto selecionado para repetir.", "")
    panel.receive(status(), None, False)
    panel.submit("read")
    panel.receive(status(), None, False)  # EOF e retorno ao estado idle
    panel.submit("read")
    assert captured[0]["text"] == captured[1]["text"] == panel.selection.text
    assert captured[1]["source"]["selection"] == "primary"


def test_repeated_connection_error_notifications_are_limited(panel, monkeypatch):
    notices = []
    monkeypatch.setattr("kokoro_reader.panel.notify", lambda *args, **kw: notices.append(args))
    error = ConnectionResetError(104, "Connection reset by peer")
    panel.receive(None, error, True)
    panel.receive(None, error, True)
    panel.receive(None, error, False)
    assert len(notices) == 1
    assert "104" not in panel.state.text()
