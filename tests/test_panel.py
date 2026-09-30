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
    assert panel.speed.value() == 1.25 and panel.voice.currentData() == "pm_alex"
    assert commands == []


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
