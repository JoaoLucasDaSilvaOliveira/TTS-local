"""Painel Qt opcional: nenhum modelo ou áudio carregado neste processo."""
import subprocess
import sys
import os
import time

from PySide6.QtCore import QLockFile, QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
    QMenu, QProgressBar, QPushButton, QStyle, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .cli import send
from .clipboard import read_selection, read_sources, SelectionCache, preview_text
from .notify import notify
from .file_controls import FileControls
from .settings import VOICES, runtime_dir
from .dock import DockShell, icon as dock_icon


class Result(QObject):
    done = Signal(object, object, bool)


class Request(QRunnable):
    def __init__(self, command, user_action=False):
        super().__init__()
        self.command = command
        self.user_action = user_action
        self.result = Result()

    @Slot()
    def run(self):
        local = {}
        try:
            request = dict(self.command)
            if request["command"] == "status":
                try:
                    local["_selection"] = read_sources()
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if request["command"] == "read" and "text" not in request:
                text = read_selection()
                if not text.strip():
                    raise ValueError("Seleção e clipboard vazios")
                request.update(text=text, source={"kind": "wayland"})
            if request["command"] == "start-service":
                subprocess.run(["systemctl", "--user", "start", "kokoro-reader.service"], check=True, timeout=15,
                               capture_output=True)
                request = {"command": "status"}
            response = send(request, timeout=3)
            response.update(local)
            self.result.done.emit(response, None, self.user_action)
        except Exception as exc:
            self.result.done.emit(local or None, exc, self.user_action)


class Panel(DockShell):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kokoro Reader")
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.pending = None
        self.queued = []
        self.status = {}
        self.connected = False
        self.quitting = False
        self.selection = SelectionCache()
        self.last_error = None
        self.last_notice = 0.0
        self.controls = []
        layout = self.body_layout
        self.compact_play.clicked.connect(self.compact_read_or_resume)
        self.compact_pause.clicked.connect(lambda: self.submit("pause"))
        self.compact_stop.clicked.connect(lambda: self.submit("stop"))
        # One set of playback controls lives outside the collapsible body.
        self.pause = self.compact_pause
        self.play = self.compact_play
        self.stop = self.compact_stop
        self.state = QLabel("Conectando ao leitor…")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        # Stable attachment point for optional FileControls, before preview/read.
        self.input_layout = QVBoxLayout()
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.input_layout)
        self.files = FileControls(self)
        self.input_layout.addWidget(self.files)
        self.files.loaded.connect(self.show_file_preview)
        self.files.cleared.connect(self.show_selection_preview)
        self.files.busy.connect(lambda _: self.update_controls())
        self.files.error.connect(self.file_error)
        self.setAcceptDrops(True)
        self.preview_title = QLabel("Prévia da seleção / clipboard")
        self.preview_title.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_title.setObjectName("muted")
        layout.addWidget(self.preview_title)
        self.preview = QLabel("Selecione ou copie um texto para ver a prévia.")
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(45)
        self.preview.setObjectName("preview")
        layout.addWidget(self.preview)
        self.read = self.button("Iniciar leitura", "read", QStyle.StandardPixmap.SP_MediaPlay)
        self.read.setObjectName("read")
        self.read.setToolTip("Selecione no Obsidian/Zed ou copie com Ctrl+C. O clipboard não é alterado.")
        layout.addWidget(self.read)
        row = QHBoxLayout()
        self.previous = self.button("Anterior", "previous", QStyle.StandardPixmap.SP_MediaSkipBackward)
        self.next = self.button("Próximo", "next", QStyle.StandardPixmap.SP_MediaSkipForward)
        for button in (self.previous, self.next):
            button.setToolTip(button.text())
            button.setText("")
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.backward = self.button("−10 s", "seek-backward", QStyle.StandardPixmap.SP_MediaSeekBackward)
        self.forward = self.button("+10 s", "seek-forward", QStyle.StandardPixmap.SP_MediaSeekForward)
        row.addWidget(self.backward)
        row.addWidget(self.forward)
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Nenhuma leitura")
        layout.addWidget(self.progress)
        self.text = QLabel("Selecione ou copie um texto para começar.")
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setWordWrap(True)
        self.text.setMinimumHeight(55)
        layout.addWidget(self.text)
        row = QHBoxLayout()
        row.addWidget(QLabel("Velocidade"))
        self.slower = self.button("−", "slower", QStyle.StandardPixmap.SP_MediaSeekBackward)
        self.speed = QLabel("1,00 ×")
        self.faster = self.button("+", "faster", QStyle.StandardPixmap.SP_MediaSeekForward)
        row.addWidget(self.slower)
        row.addWidget(self.speed)
        row.addWidget(self.faster)
        row.addStretch()
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Voz"))
        self.voice = QComboBox()
        for label, voice in zip(("Dora", "Alex", "Santa"), VOICES):
            self.voice.addItem(label, voice)
        self.voice.setToolTip("A voz escolhida vale para a próxima leitura.")
        self.voice.setAccessibleName("Voz para a próxima leitura")
        self.voice.activated.connect(lambda _: self.submit("voice", value=self.voice.currentData()))
        row.addWidget(self.voice)
        row.addStretch()
        layout.addLayout(row)
        self.top = QCheckBox("Manter janela por cima")
        self.top.setChecked(True)
        self.top.hide()  # compatibility attribute; KWin owns the dock's stacking
        self.start = QPushButton("Iniciar serviço")
        self.start.clicked.connect(lambda: self.submit("start-service"))
        self.start.hide()
        layout.addWidget(self.start)
        icon = dock_icon("kokoro")
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Kokoro Reader")
        menu = QMenu(self)
        action = menu.addAction("Abrir painel")
        action.triggered.connect(self.show_panel)
        for label, command in (("Iniciar leitura", "read"), ("Pausar", "pause"),
                               ("Retomar", "play"), ("Anterior", "previous"),
                               ("Próximo", "next"), ("Parar", "stop")):
            action = QAction(label, menu)
            action.triggered.connect(lambda checked=False, cmd=command: self.submit(cmd))
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction("Sair do painel").triggered.connect(self.quit_panel)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_panel() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.update_controls()
        QTimer.singleShot(0, self.poll)

    def button(self, title, command, icon):
        media = {"pause": "pause", "play": "play", "stop": "stop", "previous": "previous",
                 "next": "next", "seek-backward": "backward", "seek-forward": "forward"}
        image = (dock_icon(media[command]) if command in media else QIcon() if command in ("slower", "faster")
                 else self.style().standardIcon(icon))
        button = QPushButton(image, title)
        button.setAccessibleName(title)
        button.clicked.connect(lambda: self.submit(command))
        self.controls.append(button)
        return button

    def compact_read_or_resume(self):
        self.submit("play" if self.status.get("state") == "paused" else "read")

    def submit(self, command, **kwargs):
        if command == "read" and "text" not in kwargs:
            if self.files.controller.is_busy:
                self.state.setText("Aguarde o carregamento do arquivo antes de ler.")
                return
            if self.files.read_payload is not None:
                kwargs.update(self.files.read_payload)
        if command == "read" and "text" not in kwargs and self.selection.text:
            kwargs.update(text=self.selection.text, source={"kind": "wayland", "selection": self.selection.source})
        if self.pending is not None:
            if command != "status" and len(self.queued) < 16:
                self.queued.append((command, kwargs))
            return
        task = Request({"command": command, **kwargs}, command != "status")
        task.result.done.connect(self.receive)
        self.pending = task
        self.update_controls()
        self.pool.start(task)

    def poll(self):
        self.submit("status")

    @Slot(object, object, bool)
    def receive(self, response, error, user_action):
        self.pending = None
        if response and "_selection" in response:
            self.selection.update(*response.pop("_selection"), owns_primary=QApplication.clipboard().ownsSelection())
            if self.files.document is None:
                self.show_selection_preview()
        if error:
            message = str(error)
            if isinstance(error, (ConnectionError, OSError, TimeoutError)):
                self.connected = False
                message = "Conexão com o leitor interrompida. O app tentará reconectar automaticamente."
            if user_action:
                self.state.setText(message)
                now = time.monotonic()
                if message != self.last_error or now - self.last_notice > 30:
                    notify(message, error=True)
                    self.last_error, self.last_notice = message, now
            else:
                self.connected = False
                self.state.setText("Serviço indisponível ou carregando. Aguarde ou clique em Iniciar serviço.")
        else:
            self.connected = True
            self.status = response
            state = response["state"]
            self.state.setText({"idle": "Pronto para ler", "playing": "Lendo", "paused": "Pausado",
                                "buffering": "Preparando áudio…"}.get(state, state))
            count = response["segment_count"]
            self.progress.setRange(0, max(count, 1))
            self.progress.setValue((response["segment_index"] or 0) + 1 if count else 0)
            self.progress.setFormat("Trecho %v de %m" if count else "Nenhuma leitura")
            self.text.setText(preview_text(response.get("segment_text") or "") or "Nenhuma leitura em andamento.")
            self.speed.setText(f"{response['speed']:.2f} ×".replace(".", ","))
            self.voice.setCurrentIndex(self.voice.findData(response["voice"]))
            self.tray.setToolTip(f"Kokoro Reader — {self.state.text()}")
        self.update_controls()
        if self.queued:
            command, kwargs = self.queued.pop(0)
            self.submit(command, **kwargs)

    def update_controls(self):
        busy = self.pending is not None and self.pending.command["command"] != "status"
        state = self.status.get("state")
        active = self.connected and state in ("playing", "paused", "buffering")
        for button in self.controls:
            button.setEnabled(self.connected and not busy)
        for button in (self.previous, self.next, self.stop):
            button.setEnabled(active and not busy)
        self.compact_pause.setEnabled(active and state != "paused" and not busy)
        for button in (self.backward, self.forward):
            button.setEnabled(active and self.status.get("state") in ("playing", "paused") and not busy)
        self.speed.setEnabled(self.connected and not busy)
        self.voice.setEnabled(self.connected and not busy)
        self.start.setVisible(not self.connected)
        self.start.setEnabled(not busy)
        self.compact_play.setEnabled(self.connected and not busy and self.status.get("state") in ("idle", "paused"))
        label = "Retomar" if self.status.get("state") == "paused" else "Iniciar leitura"
        self.compact_play.setToolTip(label)
        self.compact_play.setAccessibleName(label)
        if self.files.document is not None and self.status.get("state") == "idle":
            self.compact_play.setToolTip("Ler arquivo")
            self.compact_play.setAccessibleName("Ler arquivo")
        if self.files.controller.is_busy:
            self.read.setEnabled(False)
            if self.status.get("state") == "idle":
                self.compact_play.setEnabled(False)
        self.header.setToolTip(f"{self.state.text()} • Abrir controles • Escape recolhe")

    def refresh_input_size(self):
        if self.expanded:
            self.body_layout.activate()
            target = self.target_size()
            if self.transition.state() == self.transition.State.Running:
                self.transition.setEndValue(target)
            elif self.size() != target:
                self.resize(target)
                self._finish_transition()

    def show_file_preview(self, document):
        self.preview_title.setText(f"Prévia do arquivo ({len(document.text)} caracteres)")
        self.preview.setText(preview_text(document.text))
        self.read.setText("Ler arquivo")
        self.read.setToolTip("Lê o documento completo. Abrir o arquivo apenas prepara a prévia.")
        self.refresh_input_size()
        self.update_controls()

    def show_selection_preview(self):
        self.preview.setText(preview_text(self.selection.text) or "Selecione ou copie um texto para ver a prévia.")
        source = "seleção" if self.selection.source == "primary" else "clipboard"
        self.preview_title.setText(f"Prévia: {source} ({len(self.selection.text)} caracteres)" if self.selection.text else "Prévia da seleção / clipboard")
        self.read.setText("Iniciar leitura")
        self.read.setToolTip("Selecione no Obsidian/Zed ou copie com Ctrl+C. O clipboard não é alterado.")
        self.refresh_input_size()
        self.update_controls()

    def file_error(self, message):
        self.state.setText(message)
        notify(message, error=True)
        self.refresh_input_size()

    def dragEnterEvent(self, event):
        if FileControls._local_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = FileControls._local_path(event)
        if path:
            event.acceptProposedAction()
            self.set_expanded(True)
            self.files.load_path(path)
        else:
            event.ignore()
            self.file_error("Arraste um único arquivo local .txt, .md ou .pdf.")

    def keep_on_top(self, checked):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def show_panel(self):
        self.showNormal()
        self.raise_()
        self.set_expanded(True)
        self.activateWindow()

    def quit_panel(self):
        self.quitting = True
        self.timer.stop()
        self.tray.hide()
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if not self.quitting and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.timer.stop()
            event.accept()


def main():
    os.umask(0o077)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("kokoro-reader")
    app.setDesktopFileName("kokoro-reader")
    root = runtime_dir()
    path = str(root / "panel.sock")
    existing = QLocalSocket()
    existing.connectToServer(path)
    if existing.waitForConnected(200):
        existing.write(b"show")
        existing.waitForBytesWritten(200)
        return
    lock = QLockFile(str(root / "panel.lock"))
    if not lock.tryLock(0):
        notify("O painel já está iniciando. Aguarde um instante.")
        return
    QLocalServer.removeServer(path)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(path):
        raise RuntimeError("Não foi possível abrir o socket privado do painel")
    panel = Panel()
    def activate():
        connection = server.nextPendingConnection()
        panel.show_panel()
        connection.close()
        connection.deleteLater()
    server.newConnection.connect(activate)
    panel.show()
    try:
        app.exec()
    finally:
        panel.pool.waitForDone(20_000)
        panel.files.controller.pool.waitForDone(20_000)
        server.close()
        QLocalServer.removeServer(path)
        lock.unlock()
