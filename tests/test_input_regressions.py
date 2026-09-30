import pytest
from kokoro_reader.clipboard import SelectionCache, preview_text
from kokoro_reader.text import clean_markdown, segment
from kokoro_reader.player import Player


def test_single_newline_always_separates_segments():
    assert segment(clean_markdown("Este é um trecho.\nEste é outro trecho."), min_chars=100) == [
        "Este é um trecho.", "Este é outro trecho."]
    assert segment("Uma frase\r\nOutra frase", min_chars=100) == ["Uma frase", "Outra frase"]


def test_cache_ignores_app_selection_and_supports_repeat():
    cache = SelectionCache()
    cache.update("Texto selecionado para estudar.", "Clipboard antigo")
    first = cache.text
    cache.update("0", "Clipboard antigo", owns_primary=True)
    assert cache.text == first and cache.source == "primary"
    cache.update("", "Clipboard novo", owns_primary=True)
    assert cache.text == "Clipboard novo" and cache.source == "clipboard"
    cache.update("Outro texto externo", "Clipboard novo")
    assert cache.text == "Outro texto externo"


def test_external_zero_is_valid_and_preview_does_not_truncate_input():
    cache = SelectionCache()
    cache.update("0", "")
    assert cache.text == "0"
    cache.update("Frase longa. " * 100, "")
    assert len(preview_text(cache.text)) <= 180
    assert preview_text(cache.text).endswith("…")
    assert len(cache.text) > 1000


async def test_player_close_handles_reset_from_mpv(tmp_path):
    class Writer:
        def close(self):
            pass
        async def wait_closed(self):
            raise ConnectionResetError(104, "Connection reset by peer")
    player = Player(tmp_path)
    player.writer = Writer()
    await player.close()
