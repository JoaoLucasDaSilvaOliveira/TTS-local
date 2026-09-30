import pytest
from kokoro_reader.clipboard import SelectionCache, preview_text
from kokoro_reader.text import clean_markdown, segment
from kokoro_reader.player import Player


def test_soft_newlines_are_spaces_and_blank_lines_separate_paragraphs():
    assert segment(clean_markdown("Este é um trecho.\nEste é outro trecho."), min_chars=100) == [
        "Este é um trecho. Este é outro trecho."]
    assert segment("Uma frase\r\nOutra frase", min_chars=100) == ["Uma frase Outra frase"]
    assert segment("Uma frase\n \t\nOutra frase", min_chars=100) == ["Uma frase", "Outra frase"]
    assert segment("Uma frase\r\n\r\nOutra frase", min_chars=100) == ["Uma frase", "Outra frase"]


def test_soft_wrap_preserves_numbers_abbreviations_and_initial_sentence():
    text = "Dr. Silva tem\nR$ 12,50 e 3.14 reais em U.S.A. hoje.\nVamos estudar juntos."
    chunks = segment(text, min_chars=100, first_min_chars=0)
    assert chunks == ["Dr. Silva tem R$ 12,50 e 3.14 reais em U.S.A. hoje.", "Vamos estudar juntos."]


@pytest.mark.parametrize("marker", ["# ", "- ", "> ", "1. "])
def test_markdown_cleanup_keeps_blank_paragraph_boundary(marker):
    cleaned = clean_markdown("Primeiro parágrafo\n\n" + marker + "Segundo parágrafo")
    assert segment(cleaned, min_chars=100) == ["Primeiro parágrafo", "Segundo parágrafo"]


@pytest.mark.parametrize("punctuation", [",", ";"])
def test_long_sentence_prefers_clause_boundary_without_losing_text(punctuation):
    prefix = "Estudar com calma ajuda a compreender os conceitos" + punctuation
    text = prefix + " e permite revisar os detalhes antes de continuar a próxima etapa do estudo"
    chunks = segment(text, limit=80)
    assert chunks[0] == prefix
    assert " ".join(chunks) == text
    assert max(map(len, chunks)) <= 80


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
