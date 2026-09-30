"""Native dock presentation; no service, audio or selection ownership here."""
import os
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .settings import config_dir


ASSETS = Path(__file__).with_name("assets")
COMPACT_SIZE = QSize(302, 60)
EXPANDED_WIDTH = 480
TOP_GAP = 12

# An ink-blue reading surface, lavender bookmark and cool paper text. Contrast
# and focus are explicit rather than inherited from a desktop's light theme.
STYLE = """
QWidget#dock { background: #202a3b; border: 1px solid #53627b; border-radius: 18px; }
QWidget { color: #edf2fc; }
QWidget#body, QScrollArea { background: transparent; border: none; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #b8c5da; }
QLabel#preview { background: #29364b; border-radius: 8px; padding: 10px; }
QPushButton { background: #35445d; border: 1px solid transparent; border-radius: 8px;
              padding: 7px 9px; min-height: 20px; }
QPushButton:hover { background: #435575; }
QPushButton:pressed { background: #526689; }
QPushButton:focus, QComboBox:focus, QCheckBox:focus { border: 2px solid #b7b0ff; }
QPushButton:disabled { color: #93a0b5; background: #283448; }
QPushButton#header { background: transparent; text-align: left; font-weight: 600; }
QPushButton#read { background: #b7b0ff; color: #202a3b; font-weight: 600; }
QPushButton#read:hover { background: #cac5ff; }
QPushButton#read:focus { border: 2px solid #edf2fc; }
QComboBox { background: #35445d; border: 1px solid #53627b; border-radius: 6px; padding: 6px; }
QComboBox QAbstractItemView { background: #29364b; color: #edf2fc; selection-background-color: #526689; }
QCheckBox { spacing: 7px; background: transparent; border: 2px solid transparent; }
QProgressBar { border: none; background: #35445d; border-radius: 5px; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #686898; border-radius: 5px; }
QScrollBar:vertical { background: #29364b; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #53627b; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def icon(name):
    return QIcon(str(ASSETS / f"{name}.svg"))


class DockShell(QWidget):
    """Compact controls stay nonactivating; expanded content accepts keyboard focus.

    `body_layout` is the expanded surface. Panel exposes a smaller `input_layout`
    within it as the stable attachment point for optional text/file sources.
    """

    def __init__(self):
        super().__init__()
        self.setObjectName("dock")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(STYLE)
        self.expanded = False
        self.dock_settings = QSettings(str(config_dir() / "dock.ini"), QSettings.Format.IniFormat)
        self.reduced_motion = (os.environ.get("KOKORO_REDUCED_MOTION") == "1"
                               or self.dock_settings.value("reducedMotion", False, type=bool))
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(10, 8, 10, 8)
        self.root_layout.setSpacing(0)
        self.root_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.header = QPushButton(icon("kokoro"), "Kokoro  ▾")
        self.header.setObjectName("header")
        self.header.setIconSize(QSize(29, 29))
        header_font = self.font()
        header_font.setPointSizeF(header_font.pointSizeF() + 1)
        self.header.setFont(header_font)
        self.header.setAccessibleName("Expandir controles do Kokoro Reader")
        self.header.setToolTip("Abrir controles • Escape recolhe")
        self.header.clicked.connect(lambda: self.set_expanded(not self.expanded))
        row.addWidget(self.header, 1)
        self.compact_play = self.icon_button("play", "Ler seleção / clipboard")
        self.compact_pause = self.icon_button("pause", "Pausar")
        self.compact_stop = self.icon_button("stop", "Parar")
        for button in (self.compact_play, self.compact_pause, self.compact_stop):
            row.addWidget(button)
        header.setFixedHeight(max(42, self.header.sizeHint().height()))
        self.header_container = header
        self.root_layout.addWidget(header)
        self.body = QWidget()
        self.body.setObjectName("body")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 12, 8, 8)
        self.body_layout.setSpacing(10)
        self.details = QScrollArea()
        self.details.setWidgetResizable(True)
        self.details.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.details.setWidget(self.body)
        self.details.hide()
        self.root_layout.addWidget(self.details, 1)
        self.transition = QPropertyAnimation(self, b"size", self)
        self.transition.setDuration(180)
        self.transition.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.transition.valueChanged.connect(lambda _: self.position_dock())
        self.transition.finished.connect(self._finish_transition)
        self.escape = QShortcut(QKeySequence("Escape"), self)
        self.escape.activated.connect(lambda: self.set_expanded(False))
        self.resize(self.compact_size())

    def icon_button(self, name, label):
        button = QPushButton(icon(name), "")
        button.setFixedSize(36, 36)
        button.setIconSize(QSize(18, 18))
        button.setToolTip(label)
        button.setAccessibleName(label)
        return button

    def set_reduced_motion(self, checked):
        self.reduced_motion = checked
        self.dock_settings.setValue("reducedMotion", checked)
        if checked and self.transition.state() == QPropertyAnimation.State.Running:
            self.transition.stop()
            self.resize(self.target_size())
            self._finish_transition()

    def target_size(self):
        if not self.expanded:
            return self.compact_size()
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry()
        height = self.body.sizeHint().height() + self.compact_size().height() + 10
        return QSize(min(EXPANDED_WIDTH, available.width() - 24),
                     min(height, max(200, available.height() - TOP_GAP * 2)))

    def compact_size(self):
        return QSize(max(COMPACT_SIZE.width(), self.header.sizeHint().width() + 140),
                     self.header_container.height() + 18)

    def set_expanded(self, expanded, animate=True):
        if self.expanded == expanded:
            return
        self.transition.stop()
        self.expanded = expanded
        self.header.setText("Kokoro  ▴" if expanded else "Kokoro  ▾")
        self.header.setAccessibleName("Recolher controles" if expanded else "Expandir controles do Kokoro Reader")
        # Only deliberate expansion makes the dock an interactive window. Media
        # clicks in compact mode keep the external app's PRIMARY selection intact.
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, not expanded)
        self.show()
        if expanded:
            self.details.show()
            self.details.setEnabled(True)
            self.body_layout.activate()
            self.activateWindow()
            self.header.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.details.setEnabled(False)
        target = self.target_size()
        if animate and not self.reduced_motion:
            self.transition.setStartValue(self.size())
            self.transition.setEndValue(target)
            self.transition.start()
        else:
            self.resize(target)
            self._finish_transition()

    def _finish_transition(self):
        self.details.setVisible(self.expanded)
        self.details.setEnabled(self.expanded)
        self.position_dock()

    def position_dock(self):
        """Best effort X11/non-KWin fallback; Wayland placement belongs to KWin."""
        area = self.screen().availableGeometry()
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + TOP_GAP)

    def showEvent(self, event):
        super().showEvent(event)
        self.position_dock()

    def paintEvent(self, event):
        # A QWidget subclass needs explicit painting for a translucent top-level
        # surface; relying on QSS background alone leaves the backing store clear.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#202a3b"))
        painter.setPen(QPen(QColor("#53627b"), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 18, 18)
