import json
import stat
import subprocess

import pytest

from kokoro_reader.clipboard import read_selection
from kokoro_reader.settings import Preferences, validate_voice, validate_speed
from kokoro_reader.text import clean_markdown, segment


def test_markdown():
    source = '---\ntags: segredo\n---\n# Ação\n\n**Texto** e [guia](https://example.com/a).\n[[Nota|apelido]]\n- [x] coração\n`CPU`\nhttps://site.com/a?chave=privada\n'
    result = clean_markdown(source)
    assert "segredo" not in result and "privada" not in result
    assert all(word in result for word in ("Ação", "Texto", "guia", "apelido", "coração", "CPU", "site.com"))


def test_code_and_metadata():
    assert "longo" not in clean_markdown("antes\n```python\nlongo\nx\ny\n```\ndepois")
    assert "x = 1" in clean_markdown("```python\nx = 1\n```")
    assert clean_markdown("<!-- segredo --> ![imagem](a.png)") == ""
    assert "segredo" not in clean_markdown("antes\n\n    segredo\n    b\n    c\n\ndepois")
    assert "segredo" not in clean_markdown("```python\nsegredo\nb\nc\n````")


def test_conservative():
    assert clean_markdown("ação_civil 3.14 e A/B; R$ 25,00") == "ação_civil 3.14 e A/B; R$ 25,00"
    assert segment(clean_markdown("Veja https://example.com/segredo. Depois.")) == ["Veja example.com.", "Depois."]


def test_segment():
    assert segment("Dr. Silva tem 3.14 reais. Olá!\n\nCPU e U.S.A. também.") == ["Dr. Silva tem 3.14 reais.", "Olá!", "CPU e U.S.A. também."]
    text = "Estudo " * 100
    chunks = segment(text)
    assert len(chunks) > 1 and max(map(len, chunks)) <= 220
    assert " ".join(chunks) == text.strip()
    assert segment("") == []
    assert max(map(len, segment("x" * 1000))) <= 220


def test_bundle_short_sentences_preserves_paragraphs_and_content():
    assert segment("Olá! Tudo bem? Vamos estudar.\n\nOutro parágrafo.", min_chars=100) == [
        "Olá! Tudo bem? Vamos estudar.", "Outro parágrafo."]
    text = "Esta frase é curta. " * 50
    chunks = segment(text, min_chars=100)
    assert " ".join(chunks) == text.strip()
    assert max(map(len, chunks)) <= 220
    first = "Uma frase longa " * 7 + "."
    assert segment(first + " Fim.", min_chars=100) == [first + " Fim."]
    with pytest.raises(ValueError):
        segment(text, min_chars=221)


def test_primary_preferred():
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "seleção", "")
    assert read_selection(run) == "seleção"
    assert len(calls) == 1 and "--primary" in calls[0]
    assert all("wl-copy" not in c for c in calls)


@pytest.mark.parametrize("returncode", [0, 1])
def test_clipboard_fallback(returncode):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode if "--primary" in args else 0, "" if "--primary" in args else "copiado", "")
    assert read_selection(run) == "copiado"
    assert "--primary" not in calls[-1]


def test_clipboard_empty_and_missing():
    assert read_selection(lambda args, **kw: subprocess.CompletedProcess(args, 0, "  ", "")) == ""
    with pytest.raises(RuntimeError):
        read_selection(lambda args, **kw: subprocess.CompletedProcess(args, 1, "", "Wayland indisponível"))


@pytest.mark.parametrize("voice", ["pf_dora", "pm_alex", "pm_santa"])
def test_voice(voice):
    assert validate_voice(voice) == voice


@pytest.mark.parametrize("voice", ["af_heart", "../../voz.pt", "", None])
def test_bad_voice(voice):
    with pytest.raises(ValueError):
        validate_voice(voice)


@pytest.mark.parametrize("speed", [0.7, 1.6, float("nan"), float("inf"), True])
def test_bad_speed(speed):
    with pytest.raises(ValueError):
        validate_speed(speed)


def test_preferences(tmp_path):
    path = tmp_path / "config/preferences.json"
    assert Preferences.load(path) == Preferences()
    prefs = Preferences("pm_alex", 1.25)
    prefs.save(path)
    assert Preferences.load(path) == prefs
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    prefs.voice = "pm_santa"
    prefs.save(path)
    assert Preferences.load(path).voice == "pm_santa"
    assert not list(path.parent.glob(".preferences-*"))
    path.write_text(json.dumps({"voice": "evil", "speed": 1}))
    with pytest.raises(ValueError):
        Preferences.load(path)
