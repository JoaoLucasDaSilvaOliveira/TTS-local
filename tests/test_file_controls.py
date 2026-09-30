import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from kokoro_reader.file_controls import DocumentController, FileControls, document_icon
from kokoro_reader.files import load_document


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def test_threaded_load_clear_and_failure_retention(app, tmp_path):
    path = tmp_path / "note.md"
    path.write_text("# Preview only")
    thread_ids, events, errors = [], [], []
    def loader(path):
        thread_ids.append(threading.get_ident())
        return load_document(path)
    controller = DocumentController(loader=loader)
    widget = FileControls(controller=controller)
    widget.loaded.connect(events.append)
    widget.error.connect(errors.append)
    clipboard = QApplication.clipboard()
    clipboard.setText("Clipboard unchanged")
    widget.load_path(path)
    wait_for(app, lambda: len(events) == 1)
    assert thread_ids[0] != threading.get_ident()
    assert widget.read_payload["text"] == "# Preview only"
    assert widget.filename.full_name == "note.md"
    assert widget.extension.text() == ".MD"
    assert widget.card.toolTip() == str(path)
    assert clipboard.text() == "Clipboard unchanged"
    widget.load_path(tmp_path / "missing.txt")
    wait_for(app, lambda: bool(errors))
    assert widget.document is events[0]
    assert widget.filename.full_name == "note.md"
    widget.clear()
    assert widget.read_payload is None and widget.card.isHidden()
    assert widget.card.toolTip() == ""
    assert clipboard.text() == "Clipboard unchanged"


class DeferredPool:
    def __init__(self):
        self.jobs = []
    def start(self, job):
        self.jobs.append(job)


def test_clear_and_newer_load_ignore_late_results(app, tmp_path):
    path = tmp_path / "first.txt"
    path.write_text("first")
    second = tmp_path / "second.txt"
    second.write_text("second")
    pool = DeferredPool()
    controller = DocumentController(pool=pool)
    events = []
    controller.loaded.connect(events.append)
    controller.load_path(str(path))
    controller.clear()
    pool.jobs[0].run()
    assert controller.document is None and not events
    controller.load_path(str(path))
    controller.load_path(str(second))
    pool.jobs[2].run()
    pool.jobs[1].run()
    assert controller.document.text == "second" and len(events) == 1


def drop(urls):
    mime = QMimeData()
    mime.setUrls(urls)
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    event._keep_mime_alive = mime  # Qt event borrows, rather than owns, QMimeData.
    return event


def test_drop_local_only_single_file(app, tmp_path):
    pool = DeferredPool()
    widget = FileControls(controller=DocumentController(pool=pool))
    path = tmp_path / "drop.TXT"
    path.write_text("drop text")
    widget.dropEvent(drop([QUrl.fromLocalFile(str(path))]))
    assert len(pool.jobs) == 1
    pool.jobs[0].run()
    assert widget.document.text == "drop text"
    widget.dropEvent(drop([QUrl("https://example.com/document.pdf")]))
    widget.dropEvent(drop([QUrl.fromLocalFile(str(path)), QUrl.fromLocalFile(str(path))]))
    assert len(pool.jobs) == 1 and "único arquivo local" in widget.message.text()


def test_dialog_cancel_and_path(app, tmp_path, monkeypatch):
    pool = DeferredPool()
    widget = FileControls(controller=DocumentController(pool=pool))
    monkeypatch.setattr("kokoro_reader.file_controls.QFileDialog.getOpenFileName", lambda *args: ("", ""))
    widget.open_dialog()
    assert not pool.jobs
    path = tmp_path / "dialog.txt"
    path.write_text("dialog")
    monkeypatch.setattr("kokoro_reader.file_controls.QFileDialog.getOpenFileName", lambda *args: (str(path), ""))
    widget.open_dialog()
    assert len(pool.jobs) == 1


def test_native_distinct_icons_and_elision(app, tmp_path, monkeypatch):
    # Force original native fallbacks regardless of desktop icon theme.
    monkeypatch.setattr("kokoro_reader.file_controls.QIcon.fromTheme", lambda name, fallback: fallback)
    icons = [document_icon(extension).pixmap(40, 48).toImage() for extension in (".txt", ".md", ".pdf")]
    assert all(not image.isNull() for image in icons)
    assert icons[0] != icons[1] and icons[1] != icons[2] and icons[0] != icons[2]
    widget = FileControls()
    widget.filename.resize(80, 25)
    widget.filename.set_filename("very long document name that needs elision.txt")
    assert "…" in widget.filename.text()
