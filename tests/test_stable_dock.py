"""Native-window lifetime and keyboard regressions, independent of the service."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from kokoro_reader.dock import DockShell


class SurfaceEvents(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.events = []
        widget.installEventFilter(self)
        widget.windowHandle().installEventFilter(self)

    def eventFilter(self, target, event):
        if event.type() in (QEvent.Type.Hide, QEvent.Type.Show, QEvent.Type.Close):
            self.events.append((target, event.type()))
        if event.type() == QEvent.Type.PlatformSurface:
            self.events.append((target, event.surfaceEventType()))
        return False


@pytest.fixture
def dock(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("KOKORO_REDUCED_MOTION", raising=False)
    widget = DockShell()
    widget.editor = QLineEdit()
    widget.body_layout.addWidget(widget.editor)
    widget.show()
    app.processEvents()
    yield widget
    widget.transition.stop()
    widget.close()
    widget.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("animate", [False, True])
def test_transitions_keep_window_surface_and_top_level_visible(dock, animate):
    window, native_id, flags = dock.windowHandle(), dock.winId(), dock.windowFlags()
    observed = SurfaceEvents(dock)
    for expanded in [True, False, True, False, True, False]:
        dock.set_expanded(expanded, animate=animate)
        QTest.qWait(25)
        assert dock.windowHandle() is window
        assert dock.winId() == native_id
        assert dock.windowFlags() == flags
        assert dock.isVisible() and window.isVisible()
        assert dock.details.isEnabled() == expanded
    QTest.qWait(230)
    assert dock.size() == dock.compact_size()
    assert not dock.details.isVisible()
    assert observed.events == []  # includes native surface destruction/creation


def test_expanded_keyboard_input_tab_and_escape(dock):
    dock.set_expanded(True, animate=False)
    assert not dock.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert all(button.focusPolicy() == Qt.FocusPolicy.StrongFocus for button in dock.header_controls)
    QTest.keyClick(dock.header, Qt.Key.Key_Tab)
    assert dock.compact_play.hasFocus()
    dock.editor.setFocus()
    QTest.keyClicks(dock.editor, "chapter")
    assert dock.editor.text() == "chapter"
    QTest.keyClick(dock.editor, Qt.Key.Key_Escape)
    QTest.qWait(230)
    assert not dock.expanded and not dock.details.isVisible()
    assert all(button.focusPolicy() == Qt.FocusPolicy.NoFocus for button in dock.header_controls)
    assert not dock.editor.hasFocus()


def test_compact_clicks_do_not_request_widget_focus_or_recreate_surface(dock):
    observed = SurfaceEvents(dock)
    calls = []
    dock.compact_play.clicked.connect(lambda: calls.append("read"))
    QTest.mouseClick(dock.compact_play, Qt.MouseButton.LeftButton)
    assert calls == ["read"]
    assert not dock.compact_play.hasFocus()
    assert dock.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert observed.events == []


def test_reduced_motion_and_reversal_finish_at_current_target(dock):
    observed = SurfaceEvents(dock)
    dock.set_expanded(True)
    QTest.qWait(30)
    dock.set_expanded(False)
    QTest.qWait(30)
    dock.set_expanded(True)
    dock.set_reduced_motion(True)
    QApplication.processEvents()
    assert dock.size() == dock.target_size()
    assert dock.details.isVisible() and dock.details.isEnabled()
    dock.set_expanded(False)
    assert dock.size() == dock.compact_size()
    assert not dock.details.isVisible()
    assert observed.events == []
