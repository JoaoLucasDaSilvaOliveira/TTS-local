import asyncio

import numpy as np
import pytest

from kokoro_reader.latency import AudioCache
from kokoro_reader.service import Reader
from kokoro_reader.settings import Preferences
from kokoro_reader.text import clean_markdown, segment


def test_first_sentence_preserves_lines_and_following_grouping():
    text = "Olá! Tudo bem? Vamos estudar.\nOutro parágrafo."
    chunks = segment(clean_markdown(text), min_chars=100, first_min_chars=0)
    assert chunks == ["Olá!", "Tudo bem? Vamos estudar.", "Outro parágrafo."]
    assert " ".join(chunks) == text.replace("\n", " ")
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
