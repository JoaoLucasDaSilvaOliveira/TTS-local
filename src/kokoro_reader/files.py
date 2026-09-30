"""Bounded, offline document ingestion; this module never accesses the clipboard."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import logging
import stat

from .text import MAX_TEXT, clean_markdown

SUPPORTED_EXTENSIONS = frozenset({".txt", ".md", ".pdf"})
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_FILE_BYTES = MAX_TEXT * 4 + 3  # UTF-8, including BOM
MAX_PDF_PAGES = 500
MAX_PDF_STREAM_BYTES = 2 * 1024 * 1024


class DocumentError(ValueError):
    """A safe user-facing error, never containing extracted document contents."""


@dataclass(frozen=True)
class Document:
    path: Path
    text: str
    page_count: int | None = None

    @property
    def source(self):
        source = {"kind": "file", "name": self.path.name, "extension": self.path.suffix.lower()}
        if self.page_count is not None:
            source["page_count"] = self.page_count
        return source

    @property
    def read_payload(self):
        return {"text": self.text, "source": self.source}


def load_document(path: str | Path) -> Document:
    path = Path(path).expanduser().absolute()
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentError("Formato não suportado. Escolha um arquivo .txt, .md ou .pdf.")
    limit = MAX_FILE_BYTES if extension == ".pdf" else MAX_TEXT_FILE_BYTES
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise DocumentError("Escolha um arquivo local regular.")
        if path.stat().st_size > limit:
            raise DocumentError(f"Arquivo muito grande (limite: {limit:,} bytes).")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as exc:
        raise DocumentError("Não foi possível abrir o arquivo local. Verifique se existe e pode ser lido.") from exc
    if len(data) > limit:
        raise DocumentError(f"Arquivo muito grande (limite: {limit:,} bytes).")
    page_count = None
    if extension == ".pdf":
        text, page_count = _pdf_text(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Codificação não suportada. Salve o arquivo como UTF-8 (BOM permitido).") from exc
        if "\x00" in text:
            raise DocumentError("Arquivo não é texto UTF-8 válido; bytes nulos não são aceitos.")
    if len(text) > MAX_TEXT:
        raise DocumentError(f"Texto excede o limite de {MAX_TEXT:,} caracteres. Divida o documento.")
    if not text.strip() or not clean_markdown(text):
        raise DocumentError("Arquivo vazio ou sem texto para leitura.")
    return Document(path, text, page_count)


def _pdf_text(data):
    from pypdf import PdfReader

    # Parser diagnostics can quote document data. Keep them out of app logs;
    # callers receive only the fixed, user-facing errors below.
    parser_logger = logging.getLogger("pypdf")
    if not parser_logger.handlers:
        parser_logger.addHandler(logging.NullHandler())
    parser_logger.propagate = False
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise DocumentError("PDF criptografado não é suportado. Use uma cópia sem proteção.")
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise DocumentError(f"PDF excede o limite de {MAX_PDF_PAGES} páginas. Divida o documento.")
        parts, count = [], 0
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_PDF_STREAM_BYTES:
                raise DocumentError("Página de PDF muito complexa para leitura local. Divida ou simplifique o PDF.")
            part = (page.extract_text() or "").strip()
            count += len(part) + (2 if parts else 0)
            if count > MAX_TEXT:
                raise DocumentError(f"Texto excede o limite de {MAX_TEXT:,} caracteres. Divida o documento.")
            parts.append(part)
        text = "\n\n".join(parts)
        if not text.strip():
            raise DocumentError("PDF sem texto pesquisável (vazio ou digitalizado). OCR não é realizado.")
        return text, page_count
    except DocumentError:
        raise
    except Exception as exc:
        # Parser exceptions can quote content; expose only our fixed message.
        raise DocumentError("PDF danificado ou inválido; não foi possível extrair o texto.") from exc
