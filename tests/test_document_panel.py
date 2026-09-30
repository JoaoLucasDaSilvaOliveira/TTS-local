"""The two independently developed features work together without clipboard writes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication
from kokoro_reader.files import load_document
from kokoro_reader.panel import Panel, Request


@pytest.fixture
def panel(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(Panel, "poll", lambda self: None)
    widget = Panel()
    widget.timer.stop()
    widget.set_reduced_motion(True)
    yield widget
    widget.files.controller.pool.waitForDone(5000)
    widget.quitting = True
    widget.tray.hide()
    widget.close()
    widget.deleteLater()
    app.processEvents()


def status(**values):
    return {"state": "idle", "segment_count": 0, "segment_index": None,
            "speed": 1.0, "voice": "pf_dora", "segment_text": None, **values}


def attach(panel, path):
    document = load_document(path)
    panel.files.controller.document = document
    panel.files._loaded(document)
    return document


def test_file_preview_survives_clipboard_poll_and_rereads_full_text(panel, tmp_path, monkeypatch):
    path = tmp_path / "estudo.md"
    path.write_text("# Ação\n" + "Leitura completa. " * 100)
    document = attach(panel, path)
    panel.receive(status(_selection=("Outra seleção", "Clipboard")), None, False)
    assert "Prévia do arquivo" in panel.preview_title.text()
    assert panel.files.filename.full_name == "estudo.md"
    assert len(panel.preview.text()) < len(document.text)
    calls = []
    monkeypatch.setattr(panel.pool, "start", lambda task: calls.append(task.command))
    for _ in range(2):
        panel.submit("read")
        panel.receive(status(), None, False)
    assert len(calls) == 2
    assert all(call["text"] == document.text and call["source"] == document.source for call in calls)
    panel.files.clear()
    panel.submit("read")
    assert calls[-1]["text"] == "Outra seleção"
    assert calls[-1]["source"]["kind"] == "wayland"


def test_loading_disables_read_but_not_stop_and_cannot_queue_stale_file(panel, monkeypatch):
    panel.receive(status(state="playing", segment_count=2, segment_index=0), None, False)
    panel.files.controller.is_busy = True
    panel.update_controls()
    assert not panel.read.isEnabled() and panel.stop.isEnabled()
    panel.pending = Request({"command": "status"})
    panel.submit("read")
    assert not panel.queued
    panel.submit("stop")
    assert panel.queued == [("stop", {})]


def test_compact_file_drop_expands_without_autoplay(panel, tmp_path, monkeypatch):
    path = tmp_path / "drop.txt"
    path.write_text("Documento para prévia.")
    loaded, submitted = [], []
    monkeypatch.setattr(panel.files, "load_path", loaded.append)
    monkeypatch.setattr(panel, "submit", lambda *args, **kw: submitted.append(args))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(QPointF(12, 12), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    panel.dropEvent(event)
    assert event.isAccepted() and panel.expanded
    assert loaded == [str(path)] and not submitted


def test_file_read_snapshot_is_queued_during_status_poll(panel, tmp_path):
    path = tmp_path / "fila.txt"
    path.write_text("Snapshot de arquivo.")
    document = attach(panel, path)
    panel.pending = Request({"command": "status"})
    panel.submit("read")
    panel.files.clear()
    assert panel.queued == [("read", document.read_payload)]


def test_file_failure_is_local_and_keeps_source(panel, tmp_path, monkeypatch):
    path = tmp_path / "anterior.txt"
    path.write_text("Não perde o arquivo anterior.")
    document = attach(panel, path)
    notices = []
    monkeypatch.setattr("kokoro_reader.panel.notify", lambda *args, **kw: notices.append(args))
    panel.files._error("PDF sem texto pesquisável. OCR não é realizado.")
    assert panel.files.document is document
    assert "PDF sem texto" in panel.state.text()
    assert notices == []


def test_long_filename_does_not_widen_dock(panel, tmp_path):
    path = tmp_path / ("capítulo " * 20 + ".md")
    path.write_text("Texto para prévia.")
    attach(panel, path)
    panel.show()
    panel.set_expanded(True, animate=False)
    QApplication.processEvents()
    assert panel.width() <= 480
    assert panel.body.minimumSizeHint().width() <= panel.details.viewport().width()
    assert "…" in panel.files.filename.text()
