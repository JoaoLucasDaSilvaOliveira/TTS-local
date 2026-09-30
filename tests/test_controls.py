import asyncio
import threading

import numpy as np
import pytest

from kokoro_reader.service import Reader
from kokoro_reader.settings import Preferences


class FakePlayer:
    def __init__(self):
        self.commands = []
        self.eof = False

    async def command(self, *args):
        self.commands.append(args)
        if args == ("get_property", "eof-reached"):
            return self.eof
        if args[0] == "loadfile":
            self.eof = False


class Engine:
    def synthesize(self, text, voice):
        return np.zeros(240, dtype=np.float32), 0.01


@pytest.fixture
async def reader(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr("kokoro_reader.service.notify", lambda *a, **kw: None)
    instance = Reader(Engine(), FakePlayer(), tmp_path, Preferences())
    yield instance
    await instance.stop()
    instance.executor.shutdown(wait=True)


async def ready(reader):
    for _ in range(100):
        if len(reader.session.audio) == len(reader.session.texts):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Producer não concluiu")


@pytest.mark.parametrize("text,expected", [
    ("Texto\nquebrado", ["Texto quebrado"]),
    ("Texto.\nquebrado", ["Texto.", "quebrado"]),
    ("Texto\n\nquebrado", ["Texto", "quebrado"]),
])
async def test_service_uses_punctuation_and_blank_lines_not_soft_wraps(reader, text, expected):
    await reader.dispatch({"command": "read", "text": text})
    await ready(reader)
    assert reader.session.texts == expected
    assert reader.status()["segment_count"] == len(expected)


async def test_pause_navigation_and_eof(reader):
    await reader.dispatch({"command": "read", "text": "Primeiro.\n\nSegundo."})
    await ready(reader)
    await reader.tick()
    assert reader.status()["state"] == "playing"
    await reader.dispatch({"command": "toggle"})
    await reader.dispatch({"command": "next"})
    await reader.tick()
    assert reader.status()["state"] == "paused"
    assert reader.status()["segment_index"] == 1
    assert ("set_property", "pause", True) in reader.player.commands
    await reader.dispatch({"command": "previous"})
    await reader.tick()
    assert reader.status()["segment_index"] == 0
    await reader.dispatch({"command": "toggle"})
    reader.player.eof = True
    await reader.tick()
    await reader.tick()
    assert reader.status()["segment_index"] == 1
    reader.player.eof = True
    directory = reader.session.directory
    await reader.tick()
    assert reader.status()["state"] == "idle"
    assert not directory.exists()


async def test_preferences_and_bounds(reader):
    for _ in range(10):
        await reader.dispatch({"command": "faster"})
    assert reader.preferences.speed == 1.5
    for _ in range(10):
        await reader.dispatch({"command": "slower"})
    assert reader.preferences.speed == 0.75
    await reader.dispatch({"command": "voice", "value": "pm_santa"})
    assert Preferences.load() == Preferences("pm_santa", 0.75)
    with pytest.raises(ValueError):
        await reader.dispatch({"command": "voice", "value": "../../x.pt"})
    with pytest.raises(ValueError):
        await reader.dispatch({"command": "speed", "value": float("nan")})


async def test_explicit_pause_play_and_seek(reader):
    await reader.dispatch({"command": "read", "text": "Uma leitura."})
    await ready(reader)
    await reader.tick()
    await reader.dispatch({"command": "pause"})
    await reader.dispatch({"command": "pause"})
    assert reader.session.paused
    await reader.dispatch({"command": "seek-forward"})
    assert ("seek", 10, "relative+exact") in reader.player.commands
    await reader.dispatch({"command": "seek-backward"})
    assert ("seek", -10, "relative+exact") in reader.player.commands
    await reader.dispatch({"command": "play"})
    await reader.dispatch({"command": "play"})
    assert not reader.session.paused


async def test_invalid_read_preserves_session(reader):
    await reader.dispatch({"command": "read", "text": "Texto original."})
    original = reader.session
    with pytest.raises(ValueError):
        await reader.dispatch({"command": "read", "text": "<!-- vazio -->"})
    assert reader.session is original
    session_id = reader.status()["session_id"]
    assert reader.status()["segment_id"] == f"{session_id}:0"
    await reader.dispatch({"command": "read", "text": "Outra leitura."})
    assert reader.status()["session_id"] != session_id


async def test_stop_during_synthesis_does_not_recreate_files(reader):
    started = threading.Event()
    release = threading.Event()
    class SlowEngine:
        def synthesize(self, text, voice):
            started.set()
            release.wait(timeout=3)
            return np.zeros(240, dtype=np.float32), 0.01
    reader.engine = SlowEngine()
    try:
        await reader.dispatch({"command": "read", "text": "Lento."})
        directory = reader.session.directory
        assert await asyncio.to_thread(started.wait, 2)
        await reader.dispatch({"command": "stop"})
        assert not directory.exists()
        release.set()
        await asyncio.get_running_loop().run_in_executor(reader.executor, lambda: None)
        assert not directory.exists() and reader.session is None
    finally:
        release.set()


async def test_first_audio_starts_without_waiting_for_second_segment(reader):
    from kokoro_reader.service import Session
    # Simula apenas o primeiro WAV disponível, segundo ainda em síntese.
    s = Session(["Primeiro.", "Segundo."], reader.root / "audio-buffer-test", "pf_dora", {})
    s.directory.mkdir()
    path = s.directory / "00000.wav"
    path.touch()
    s.audio[0] = path
    reader.session = s
    await reader.tick()
    assert s.loaded == 0 and reader.status()["state"] == "playing"
    # Releitura simulada; comando previous ignora espera inicial adicional.
    s.first_playback = None
    await reader.dispatch({"command": "previous"})
    await reader.tick()
    assert s.loaded == s.revision
