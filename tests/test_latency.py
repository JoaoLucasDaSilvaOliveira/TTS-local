import asyncio
import json

import numpy as np
import pytest

from kokoro_reader.latency import AudioCache
from kokoro_reader.player import Player
from kokoro_reader.service import Reader, Session
from kokoro_reader.settings import Preferences
from kokoro_reader.text import clean_markdown, segment


def test_first_sentence_preserves_paragraphs_and_following_grouping():
    text = "Olá! Tudo bem? Vamos estudar.\n\nOutro parágrafo."
    chunks = segment(clean_markdown(text), min_chars=100, first_min_chars=0)
    assert chunks == ["Olá!", "Tudo bem? Vamos estudar.", "Outro parágrafo."]
    assert " ".join(chunks) == text.replace("\n\n", " ")
    assert segment("Dr. Silva tem 3.14 reais. Olá!", min_chars=100, first_min_chars=0) == [
        "Dr. Silva tem 3.14 reais.", "Olá!"]
    with pytest.raises(ValueError):
        segment(text, first_min_chars=-1)


def test_cache_has_byte_and_entry_bounds_and_voice_isolation():
    cache = AudioCache(max_bytes=24, max_entries=2)
    a = np.zeros(3, dtype=np.float32)
    cache.put(("pf_dora", "Texto."), a)
    assert cache.get(("pm_alex", "Texto.")) is None
    assert not a.flags.writeable
    cache.put(("pm_alex", "Texto."), a.copy())
    cache.get(("pf_dora", "Texto."))
    cache.put(("pm_santa", "Texto."), a.copy())
    assert cache.get(("pm_alex", "Texto.")) is None
    assert cache.bytes == 24 and len(cache.entries) == 2
    cache.put("oversized", np.zeros(7, dtype=np.float32))
    assert cache.get("oversized") is None
    cache.put(("pf_dora", "Texto."), np.zeros(1, dtype=np.float32))
    assert cache.bytes == 16


async def test_next_audio_loads_in_same_tick_and_producer_wakes_reader(tmp_path, monkeypatch):
    class Engine:
        def synthesize(self, text, voice):
            return np.zeros(240, dtype=np.float32), 0.01

    class Player:
        eof = False
        commands = []
        async def command(self, *args):
            self.commands.append(args)
            if args[0] == "loadfile":
                self.eof = False
            if args == ("get_property", "eof-reached"):
                return self.eof

    monkeypatch.setattr("kokoro_reader.service.notify", lambda *a, **kw: None)
    reader = Reader(Engine(), Player(), tmp_path, Preferences())
    try:
        await reader.dispatch({"command": "read", "text": "Primeiro.\nSegundo."})
        reader.wakeup.clear()
        await asyncio.wait_for(reader.wakeup.wait(), 2)
        await reader.session.producer
        await reader.tick()
        reader.player.eof = True
        await reader.tick()
        assert reader.session.index == 1
        assert reader.session.loaded == reader.session.revision
        assert reader.player.commands[-3][0] == "loadfile"
    finally:
        await reader.stop()
        reader.executor.shutdown(wait=True)


def ipc_player(tmp_path):
    class Writer:
        def write(self, data):
            pass
        async def drain(self):
            pass

    player = Player(tmp_path)
    player.reader = asyncio.StreamReader()
    player.writer = Writer()
    return player


def ipc_feed(player, *replies):
    for reply in replies:
        player.reader.feed_data((json.dumps(reply) + "\n").encode())


@pytest.mark.parametrize("event_first", [True, False])
async def test_loadfile_waits_for_ack_and_ready_event_in_either_order(tmp_path, event_first):
    player = ipc_player(tmp_path)
    task = asyncio.create_task(player.command("loadfile", "/local.wav", "replace"))
    ack = {"request_id": 1, "error": "success", "data": "acknowledged"}
    event = {"event": "file-loaded"}
    ipc_feed(player, event if event_first else ack)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not task.done()
    ipc_feed(player, {"event": "end-file", "reason": "eof"}, ack if event_first else event)
    assert await task == "acknowledged"


async def test_eof_command_cannot_overtake_pending_load(tmp_path):
    player = ipc_player(tmp_path)
    load = asyncio.create_task(player.command("loadfile", "/local.wav", "replace"))
    ipc_feed(player, {"request_id": 1, "error": "success"})
    await asyncio.sleep(0)
    eof = asyncio.create_task(player.command("get_property", "eof-reached"))
    await asyncio.sleep(0)
    assert player.sequence == 1 and not eof.done()
    ipc_feed(player, {"event": "file-loaded"}, {"request_id": 2, "error": "success", "data": False})
    await load
    assert await eof is False


@pytest.mark.parametrize("reply", [
    {"request_id": 1, "error": "command failed"},
    {"event": "end-file", "reason": "error", "file_error": "loading failed"},
])
async def test_loadfile_propagates_ack_and_decode_errors(tmp_path, reply):
    player = ipc_player(tmp_path)
    ipc_feed(player, reply)
    with pytest.raises(RuntimeError, match="mpv:"):
        await player.command("loadfile", "/local.wav", "replace")


async def test_loadfile_event_wait_is_bounded_and_disconnect_propagates(tmp_path, monkeypatch):
    monkeypatch.setattr("kokoro_reader.player.IPC_TIMEOUT", 0.01)
    player = ipc_player(tmp_path)
    ipc_feed(player, {"request_id": 1, "error": "success"})
    with pytest.raises(TimeoutError):
        await player.command("loadfile", "/local.wav", "replace")
    player = ipc_player(tmp_path)
    player.reader.feed_eof()
    with pytest.raises(RuntimeError, match="mpv desconectou"):
        await player.command("loadfile", "/local.wav", "replace")


@pytest.mark.parametrize("error", ["mpv: property unavailable", "mpv desconectou", "mpv: command failed"])
async def test_eof_property_loading_transient_only_is_retried(tmp_path, monkeypatch, error):
    class Player:
        loaded = False
        pending_error = None
        eof = False

        async def command(self, *args):
            if args[0] == "loadfile":
                self.loaded = True
                self.pending_error = error
            if args == ("get_property", "eof-reached"):
                assert self.loaded
                if self.pending_error is not None:
                    pending, self.pending_error = self.pending_error, None
                    raise RuntimeError(pending)
                return self.eof

    monkeypatch.setattr("kokoro_reader.service.notify", lambda *a, **kw: None)
    reader = Reader(None, Player(), tmp_path, Preferences())
    directory = tmp_path / "audio-transient"
    directory.mkdir()
    session = Session(["Primeiro."], directory, "pf_dora", {})
    session.audio[0] = directory / "00000.wav"
    reader.session = session
    try:
        await reader.tick()  # loadfile ACK; properties are not yet available.
        if error != "mpv: property unavailable":
            with pytest.raises(RuntimeError, match=error):
                await reader.tick()
            return
        await reader.tick()  # The known transient must not kill the service.
        assert reader.session is session and session.index == 0
        await reader.tick()  # Decoder ready, EOF false.
        assert reader.session is session
        reader.player.eof = True
        await reader.tick()
        assert reader.session is None and not directory.exists()
    finally:
        await reader.stop()
        reader.executor.shutdown(wait=True)
