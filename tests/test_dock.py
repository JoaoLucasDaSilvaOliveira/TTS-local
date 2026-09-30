"""Dock interaction regressions, without changing the desktop or service."""
import importlib.util
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from kokoro_reader.panel import Panel


@pytest.fixture
def panel(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(Panel, "poll", lambda self: None)
    widget = Panel()
    widget.timer.stop()
    widget.show()
    app.processEvents()
    yield widget
    widget.transition.stop()
    widget.quitting = True
    widget.tray.hide()
    widget.close()
    widget.deleteLater()
    app.processEvents()


def receive(panel, state):
    panel.receive({"state": state, "segment_count": 0 if state == "idle" else 2,
                   "segment_index": None if state == "idle" else 0,
                   "speed": 1.0, "voice": "pf_dora", "segment_text": "Texto."}, None, False)


def test_compact_play_reads_or_resumes_without_accepting_window_focus(panel, monkeypatch):
    commands = []
    monkeypatch.setattr(panel, "submit", lambda cmd, **kw: commands.append(cmd))
    assert not panel.expanded and not panel.details.isVisible()
    assert panel.top.isChecked() and not panel.top.isVisible()
    assert panel.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    for state, command in (("idle", "read"), ("paused", "play")):
        receive(panel, state)
        panel.compact_play.click()
        assert commands[-1] == command
        assert panel.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert panel.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    receive(panel, "playing")
    assert not panel.compact_play.isEnabled()
    panel.compact_pause.click()
    panel.compact_stop.click()
    assert commands == ["read", "play", "pause", "stop"]
    panel.receive(None, ConnectionError(), False)
    assert not panel.compact_pause.isEnabled() and not panel.compact_stop.isEnabled()


def test_header_controls_work_after_collapse_and_during_transition(panel, monkeypatch):
    commands = []
    monkeypatch.setattr(panel, "submit", lambda cmd, **kw: commands.append(cmd))
    for animate in (False, True):
        panel.set_expanded(True, animate=False)
        receive(panel, "playing")
        panel.set_expanded(False, animate=animate)
        # The hidden/disabled body must never disable the persistent header.
        receive(panel, "playing")
        assert panel.compact_pause.isEnabled() and panel.compact_stop.isEnabled()
        QTest.mouseClick(panel.compact_pause, Qt.MouseButton.LeftButton)
        receive(panel, "paused")
        assert panel.compact_play.isEnabled() and panel.compact_stop.isEnabled()
        QTest.mouseClick(panel.compact_play, Qt.MouseButton.LeftButton)
        receive(panel, "playing")
        QTest.mouseClick(panel.compact_stop, Qt.MouseButton.LeftButton)
        receive(panel, "idle")
        assert not panel.compact_stop.isEnabled() and not panel.compact_pause.isEnabled()
    assert commands == ["pause", "play", "stop"] * 2


def test_playback_controls_are_single_header_instances(panel):
    assert panel.pause is panel.compact_pause
    assert panel.play is panel.compact_play
    assert panel.stop is panel.compact_stop
    for control in (panel.pause, panel.play, panel.stop):
        assert not panel.body.isAncestorOf(control)


def test_reduce_motion_option_is_not_exposed(panel):
    from PySide6.QtWidgets import QCheckBox
    assert not hasattr(panel, "motion")
    assert all(control.text() != "Reduzir movimento" for control in panel.findChildren(QCheckBox))


def test_expansion_escape_and_interrupted_motion_preserve_cache(panel):
    panel.selection.update("Texto selecionado", "")
    panel.set_expanded(True)
    assert not panel.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    panel.set_expanded(False)
    panel.set_expanded(True)
    assert panel.details.isEnabled()  # no 180ms lockout after a quick reversal
    QTest.qWait(220)
    assert panel.transition.state() == QAbstractAnimation.State.Stopped
    assert panel.details.isVisible()
    QTest.keyClick(panel.header, Qt.Key.Key_Escape)
    QTest.qWait(220)
    assert not panel.expanded and not panel.details.isVisible()
    assert panel.selection.text == "Texto selecionado"


def test_reduced_motion_and_input_attachment(panel):
    panel.set_reduced_motion(True)
    file_row = QLabel("Arquivo: capítulo.txt")
    file_row.setMinimumHeight(100)
    panel.input_layout.addWidget(file_row)
    panel.set_expanded(True)
    QApplication.processEvents()
    assert file_row.isVisible() and panel.details.isEnabled()
    assert panel.transition.state() == QAbstractAnimation.State.Stopped
    assert panel.size() == panel.target_size()
    assert panel.width() <= panel.screen().availableGeometry().width()
    assert panel.body.minimumSizeHint().width() <= panel.details.viewport().width()
    assert panel.height() < panel.screen().availableGeometry().height()
    panel.set_expanded(False)
    assert panel.size() == panel.compact_size()
    assert panel.dock_settings.value("reducedMotion", type=bool)


def test_system_font_scaling_keeps_controls_scrollable(panel):
    app = QApplication.instance()
    previous = app.font()
    large = QFont(previous)
    large.setPointSize(18)
    scaled = None
    try:
        app.setFont(large)
        scaled = Panel()
        scaled.timer.stop()
        scaled.set_expanded(True, animate=False)
        scaled.resize(480, 320)  # low available height with enlarged desktop text
        QApplication.processEvents()
        assert scaled.body.minimumSizeHint().width() <= scaled.details.viewport().width()
        assert scaled.details.verticalScrollBar().maximum() > 0
        for control in (scaled.read, scaled.voice):
            assert control.font().pointSize() == 18
    finally:
        if scaled:
            scaled.quitting = True
            scaled.tray.hide()
            scaled.close()
            scaled.deleteLater()
        app.setFont(previous)


def test_kwin_install_is_scoped_and_preserves_existing_package(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/install.py"
    spec = importlib.util.spec_from_file_location("dock_installer", script)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    calls = []
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(installer.subprocess, "run", lambda argv, **kw: calls.append(argv))
    source = script.parents[1] / "kwin/kokoro-reader-dock"
    destination = tmp_path / "kwin/scripts/kokoro-reader-dock/metadata.json"
    destination.parent.mkdir(parents=True)
    destination.write_text("previous package")
    installer.install_kwin_dock(source, tmp_path)
    assert destination.with_name("metadata.json.before-install").read_text() == "previous package"
    assert calls[0] == ["/tools/kwriteconfig6", "--file", "kwinrc", "--group", "Plugins",
                        "--key", "kokoro-reader-dockEnabled", "true"]
    assert calls[1:] == [["/tools/qdbus6", "org.kde.KWin", "/Scripting", "unloadScript", "kokoro-reader-dock"],
                         ["/tools/qdbus6", "org.kde.KWin", "/KWin", "reconfigure"],
                         ["/tools/qdbus6", "org.kde.KWin", "/Scripting", "start"]]


def test_kwin_script_places_and_resizes_without_window_shown_signal(panel):
    # Exercise the actual helper using Qt's JS engine, matching the Plasma 6
    # window shape observed at runtime: frameGeometryChanged, no windowShown.
    from PySide6.QtQml import QJSEngine
    engine = QJSEngine()
    setup = engine.evaluate("""
        function signal() {
            return {connect: function(callback) { this.callback = callback; }};
        }
        var reader = {
            desktopFileName: 'kokoro-reader', resourceClass: 'kokoro-reader',
            caption: 'Kokoro Reader',
            keepAbove: false,
            frameGeometry: {x: 0, y: 0, width: 302, height: 60},
            frameGeometryChanged: signal()
        };
        var unrelated = {
            desktopFileName: 'editor', caption: 'Kokoro Reader',
            keepAbove: false,
            frameGeometry: {x: 7, y: 8, width: 800, height: 600},
            frameGeometryChanged: signal()
        };
        var KWin = {MaximizeArea: 1};
        var workspace = {
            windowAdded: signal(), stackingOrder: [reader, unrelated],
            clientArea: function(option, window) {
                if (option !== KWin.MaximizeArea || window !== reader)
                    throw new Error('unexpected positioning target');
                return {x: 100, y: 42, width: 1920, height: 1020};
            }
        };
    """)
    assert not setup.isError(), setup.toString()
    script = Path(__file__).resolve().parents[1] / "kwin/kokoro-reader-dock/contents/code/main.js"
    result = engine.evaluate(script.read_text(), str(script))
    assert not result.isError(), result.toString()
    assert engine.evaluate("reader.frameGeometry.x === 909 && reader.frameGeometry.y === 54 && reader.keepAbove").toBool()
    result = engine.evaluate("""
        reader.frameGeometry.width = 480;
        reader.frameGeometryChanged.callback();
        workspace.windowAdded.callback(unrelated);
        reader.frameGeometry.x === 820 && reader.frameGeometry.y === 54
            && unrelated.frameGeometry.x === 7 && unrelated.frameGeometry.y === 8
            && reader.keepAbove && !unrelated.keepAbove
            && unrelated.frameGeometryChanged.callback === undefined;
    """)
    assert not result.isError(), result.toString()
    assert result.toBool()
