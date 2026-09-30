import sys

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from kokoro_reader.files import DocumentError, MAX_FILE_BYTES, MAX_TEXT, load_document
from kokoro_reader.text import clean_markdown


def write_pdf(path, texts=(), *, encrypted=False, image=False):
    writer = PdfWriter()
    for text in texts or (None,):
        page = writer.add_blank_page(width=300, height=300)
        if text is not None:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 200 Td (" + text.encode("ascii") + b") Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        if image:
            # Inline pixel image, intentionally no text layer.
            stream = DecodedStreamObject()
            stream.set_data(b"q 100 0 0 100 0 0 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\xff\xff EI Q")
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    writer.write(path)


@pytest.mark.parametrize("suffix", [".txt", ".TXT", ".md", ".Md"])
def test_utf8_bom_markdown_and_metadata(tmp_path, suffix):
    path = tmp_path / f"guia{suffix}"
    path.write_bytes("\ufeff# Ação\n\n**Texto** para ouvir.".encode())
    document = load_document(path)
    assert document.text == "# Ação\n\n**Texto** para ouvir."
    assert clean_markdown(document.text) == "Ação\n\nTexto para ouvir."
    assert document.source == {"kind": "file", "name": path.name, "extension": suffix.lower()}
    assert "path" not in document.source


def test_searchable_pdf_pages(tmp_path):
    path = tmp_path / "book.PDF"
    write_pdf(path, ["First page.", "Second page."])
    document = load_document(path)
    assert document.text == "First page.\n\nSecond page."
    assert document.source["page_count"] == 2


@pytest.mark.parametrize("image", [False, True])
def test_no_pdf_text(tmp_path, image):
    path = tmp_path / "blank.pdf"
    write_pdf(path, image=image)
    with pytest.raises(DocumentError, match="sem texto pesquisável"):
        load_document(path)


def test_encrypted_pdf(tmp_path):
    path = tmp_path / "locked.pdf"
    write_pdf(path, ["Secret"], encrypted=True)
    with pytest.raises(DocumentError, match="criptografado"):
        load_document(path)


def test_damaged_pdf_safe_error(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"private document contents")
    with pytest.raises(DocumentError, match="danificado") as error:
        load_document(path)
    assert "private" not in str(error.value)


def test_parser_diagnostics_do_not_log_contents(tmp_path, monkeypatch, caplog):
    import logging
    from pypdf import PageObject
    path = tmp_path / "diagnostic.pdf"
    write_pdf(path, ["Public text"])
    def broken_extract(self):
        logging.getLogger("pypdf._page").warning("private document contents")
        raise RuntimeError("private document contents")
    monkeypatch.setattr(PageObject, "extract_text", broken_extract)
    with pytest.raises(DocumentError) as error:
        load_document(path)
    assert "private" not in str(error.value)
    assert "private" not in caplog.text


@pytest.mark.parametrize("value", [b"", b" \n\t", b"<!-- hidden -->", b"\xff", b"a\x00b", b"\xff\xfeA\x00"])
def test_empty_or_unsupported_encoding(tmp_path, value):
    path = tmp_path / "input.txt"
    path.write_bytes(value)
    with pytest.raises(DocumentError):
        load_document(path)


def test_missing_directory_unsupported_and_file_limit(tmp_path):
    with pytest.raises(DocumentError, match="abrir"):
        load_document(tmp_path / "missing.txt")
    directory = tmp_path / "directory.txt"
    directory.mkdir()
    with pytest.raises(DocumentError, match="regular"):
        load_document(directory)
    with pytest.raises(DocumentError, match="Formato"):
        load_document(tmp_path / "file.docx")
    path = tmp_path / "large.pdf"
    with path.open("wb") as stream:
        stream.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises(DocumentError, match="muito grande"):
        load_document(path)


def test_text_limit_no_truncation(tmp_path):
    path = tmp_path / "limit.txt"
    path.write_text("é" * MAX_TEXT)
    assert len(load_document(path).text) == MAX_TEXT
    path.write_text("a" * (MAX_TEXT + 1))
    with pytest.raises(DocumentError, match="Texto excede"):
        load_document(path)
    path.write_bytes(b"a" * (MAX_TEXT * 4 + 4))
    with pytest.raises(DocumentError, match="muito grande"):
        load_document(path)


def test_pdf_text_and_stream_limits(tmp_path, monkeypatch):
    path = tmp_path / "limit.pdf"
    write_pdf(path, ["a" * (MAX_TEXT + 1)])
    with pytest.raises(DocumentError, match="Texto excede"):
        load_document(path)
    monkeypatch.setattr("kokoro_reader.files.MAX_PDF_STREAM_BYTES", 10)
    with pytest.raises(DocumentError, match="complexa"):
        load_document(path)
    monkeypatch.setattr("kokoro_reader.files.MAX_PDF_PAGES", 0)
    with pytest.raises(DocumentError, match="páginas"):
        load_document(path)


def test_cli_file_no_clipboard(tmp_path, monkeypatch, capsys):
    from kokoro_reader import cli
    path = tmp_path / "cli.md"
    path.write_text("# Texto explícito.")
    calls = []
    monkeypatch.setattr(sys, "argv", ["kokoro-reader", "read", "--file", str(path)])
    monkeypatch.setattr(cli, "read_selection", lambda: pytest.fail("clipboard read"))
    monkeypatch.setattr(cli, "send", lambda request: calls.append(request) or {"ok": True})
    cli.main()
    assert calls == [{"command": "read", "text": "# Texto explícito.", "source": {"kind": "file", "name": "cli.md", "extension": ".md"}}]


def test_cli_missing_file_preserves_file_error(tmp_path, monkeypatch, capsys):
    from kokoro_reader import cli
    monkeypatch.setattr(sys, "argv", ["kokoro-reader", "read", "--file", str(tmp_path / "missing.txt")])
    monkeypatch.setattr(cli, "notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "send", lambda request: pytest.fail("must not submit"))
    with pytest.raises(SystemExit):
        cli.main()
    assert "abrir o arquivo" in capsys.readouterr().err
