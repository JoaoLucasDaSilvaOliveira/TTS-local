"""Optional Qt document controls, independent of the panel and service."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .files import load_document


class _Result(QObject):
    done = Signal(int, object, object)


class _Load(QRunnable):
    def __init__(self, generation, path, loader):
        super().__init__()
        self.generation, self.path, self.loader = generation, path, loader
        self.result = _Result()
        self.cancelled = False

    def run(self):
        if self.cancelled:
            self.result.done.emit(self.generation, None, None)
            return
        try:
            document = self.loader(self.path)
            self.result.done.emit(self.generation, document, None)
        except Exception as exc:
            from .files import DocumentError
            message = str(exc) if isinstance(exc, DocumentError) else "Não foi possível carregar o arquivo local."
            self.result.done.emit(self.generation, None, message)


class DocumentController(QObject):
    loaded = Signal(object)  # Document: text, source, path, page_count, read_payload
    cleared = Signal()
    busy = Signal(bool)
    error = Signal(str)

    def __init__(self, parent=None, *, loader=load_document, pool=None):
        super().__init__(parent)
        self.document = None
        self.is_busy = False
        self._generation = 0
        self._jobs = {}
        self._loader = loader
        self.pool = pool if pool is not None else QThreadPool(self)
        if pool is None:
            self.pool.setMaxThreadCount(1)

    @property
    def read_payload(self):
        return self.document.read_payload if self.document else None

    @Slot(str)
    def load_path(self, path):
        for job in self._jobs.values():
            job.cancelled = True
        self._generation += 1
        self.is_busy = True
        self.busy.emit(True)
        job = _Load(self._generation, path, self._loader)
        job.result.done.connect(self._finished)
        self._jobs[self._generation] = job
        self.pool.start(job)

    @Slot(int, object, object)
    def _finished(self, generation, document, error):
        self._jobs.pop(generation, None)
        if generation != self._generation:
            return
        self.is_busy = False
        self.busy.emit(False)
        if error:
            self.error.emit(error)
        else:
            self.document = document
            self.loaded.emit(document)

    @Slot()
    def clear(self):
        for job in self._jobs.values():
            job.cancelled = True
        self._generation += 1  # Late background results must not restore a cleared file.
        self.document = None
        self.is_busy = False
        self.busy.emit(False)
        self.cleared.emit()


def document_icon(extension):
    """Native QIcons: MIME theme icons with original, distinct painted fallbacks."""
    colors = {".txt": "#2977b8", ".md": "#7955b3", ".pdf": "#c44343"}
    names = {".txt": "text-plain", ".md": "text-markdown", ".pdf": "application-pdf"}
    pixmap = QPixmap(40, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(colors[extension]))
    painter.setBrush(QColor(colors[extension]))
    painter.drawRoundedRect(3, 2, 34, 44, 4, 4)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(11)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, extension[1:].upper())
    painter.drawLine(10, 35, 30, 35)
    painter.drawLine(10, 39, 25, 39)
    painter.end()
    return QIcon.fromTheme(names[extension], QIcon(pixmap))


class _Filename(QLabel):
    def __init__(self):
        super().__init__()
        self.full_name = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_filename(self, name):
        self.full_name = name
        self.setAccessibleName(name)
        self.setToolTip(name)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self.full_name, Qt.TextElideMode.ElideMiddle, self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class FileControls(QWidget):
    """Attach to expanded input layout; load/clear never submits synthesis."""
    loaded = Signal(object)
    cleared = Signal()
    busy = Signal(bool)
    error = Signal(str)

    def __init__(self, parent=None, *, controller=None):
        super().__init__(parent)
        self.controller = controller if controller is not None else DocumentController(self)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.choose = QPushButton("Abrir arquivo…")
        self.choose.setToolTip("Arquivo local .txt, .md ou PDF pesquisável; arraste um arquivo aqui.")
        self.remove = QPushButton("Remover arquivo")
        self.remove.setEnabled(False)
        row.addWidget(self.choose)
        row.addWidget(self.remove)
        layout.addLayout(row)
        self.card = QWidget()
        card_row = QHBoxLayout(self.card)
        card_row.setContentsMargins(0, 0, 0, 0)
        self.icon = QLabel()
        self.filename = _Filename()
        self.extension = QLabel()
        card_row.addWidget(self.icon)
        card_row.addWidget(self.filename, 1)
        card_row.addWidget(self.extension)
        layout.addWidget(self.card)
        self.card.hide()
        self.message = QLabel("Arraste um .txt, .md ou .pdf pesquisável aqui.")
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.choose.clicked.connect(self.open_dialog)
        self.remove.clicked.connect(self.controller.clear)
        self.controller.loaded.connect(self._loaded)
        self.controller.cleared.connect(self._cleared)
        self.controller.busy.connect(self._busy)
        self.controller.error.connect(self._error)

    @property
    def document(self):
        return self.controller.document

    @property
    def read_payload(self):
        return self.controller.read_payload

    @Slot()
    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir documento local", "", "Documentos (*.txt *.md *.pdf *.TXT *.MD *.PDF);;Todos os arquivos (*)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        self.controller.load_path(str(path))

    def clear(self):
        self.controller.clear()

    def _loaded(self, document):
        extension = document.path.suffix.lower()
        self.icon.setPixmap(document_icon(extension).pixmap(32, 38))
        self.filename.set_filename(document.path.name)
        self.extension.setText(extension.upper())
        self.card.setToolTip(str(document.path))
        self.card.show()
        self.remove.setEnabled(True)
        self.message.setText(f"{len(document.text):,} caracteres · pronto para ler" + (f" · {document.page_count} páginas" if document.page_count is not None else ""))
        self.loaded.emit(document)

    def _cleared(self):
        self.card.hide()
        self.filename.set_filename("")
        self.extension.clear()
        self.card.setToolTip("")
        self.remove.setEnabled(False)
        self.message.setText("Seleção / clipboard ativo. Arraste um arquivo para abrir.")
        self.cleared.emit()

    def _busy(self, busy):
        self.choose.setEnabled(not busy)
        self.remove.setEnabled(busy or self.document is not None)
        if busy:
            self.message.setText("Carregando arquivo…")
        self.busy.emit(busy)

    def _error(self, message):
        self.message.setText(message)
        self.error.emit(message)

    @staticmethod
    def _local_path(event):
        urls = event.mimeData().urls()
        return urls[0].toLocalFile() if len(urls) == 1 and urls[0].isLocalFile() else None

    def dragEnterEvent(self, event):
        if self._local_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._local_path(event)
        if path:
            event.acceptProposedAction()
            self.load_path(path)
        else:
            event.ignore()
            self._error("Arraste um único arquivo local .txt, .md ou .pdf.")
