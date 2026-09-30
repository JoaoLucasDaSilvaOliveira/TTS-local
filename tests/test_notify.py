"""No desktop notifications, for playback, empty text or errors."""
import subprocess

import pytest

from kokoro_reader.notify import notify


@pytest.mark.parametrize("message,error", [
    ("Lendo 1 trechos com pf_dora", False),
    ("Seleção e clipboard vazios", True),
    ("Falha na síntese", True),
    ("O painel já está iniciando", False),
])
def test_notifications_never_spawn_desktop_process(monkeypatch, message, error):
    def forbidden(*args, **kwargs):
        pytest.fail("Desktop notification process must not be started")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert notify(message, error=error) is None
