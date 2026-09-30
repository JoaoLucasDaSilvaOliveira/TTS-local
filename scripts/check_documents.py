"""Opt-in real CPU/audio check with generated, non-private document fixtures."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from kokoro_reader.cli import send
from kokoro_reader.settings import runtime_dir


def make_pdf(path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 200 Td (Estudo local: leitura de PDF pesquisavel.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/kokoro-reader-documents-results.json"))
    args = parser.parse_args()
    if send({"command": "status"})["state"] != "idle":
        raise RuntimeError("Pare a leitura atual antes de rodar este teste com áudio.")
    results = []
    with tempfile.TemporaryDirectory(prefix="kokoro-documents-") as directory:
        root = Path(directory)
        fixtures = {".txt": "Ação, ciência e revisão: 123 números.\nOutro trecho com CPU e URL https://example.com/estudo.",
                    ".md": "---\ntitle: metadata\n---\n# Estudos\n**Ação** e ciência: 42 números e uma [referência](https://example.com)."}
        for extension, text in fixtures.items():
            (root / f"estudo{extension}").write_text(text, encoding="utf-8")
        make_pdf(root / "estudo.pdf")
        try:
            for extension in (".txt", ".md", ".pdf"):
                path = root / f"estudo{extension}"
                began = time.monotonic()
                response = json.loads(subprocess.check_output(
                    [sys.executable, "-m", "kokoro_reader.cli", "read", "--file", str(path)], text=True))
                assert response["source"]["name"] == path.name
                assert response["source"]["extension"] == extension
                session = response["session_id"]
                deadline = began + 30
                while time.monotonic() < deadline:
                    current = send({"command": "status"})
                    if current["state"] == "playing" and current["session_id"] == session:
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError(f"Áudio não começou em 30 s para {extension}")
                assert current["source"]["kind"] == "file"
                result = {"extension": extension, "segments": current["segment_count"],
                          "seconds_until_playing": round(time.monotonic() - began, 3),
                          "metrics": current["metrics"]}
                paused = send({"command": "pause"})
                assert paused["state"] == "paused"
                resumed = send({"command": "play"})
                assert resumed["state"] in ("playing", "buffering")
                send({"command": "stop"})
                assert not list(runtime_dir().glob("audio-*"))
                results.append(result)
        finally:
            send({"command": "stop"})
    args.output.write_text(json.dumps({"ok": True, "documents": results}, indent=2) + "\n")
    print(json.dumps({"ok": True, "documents": results}, indent=2))


if __name__ == "__main__":
    main()
