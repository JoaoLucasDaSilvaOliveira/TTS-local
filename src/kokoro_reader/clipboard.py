import subprocess
from dataclasses import dataclass


def read_selection(run=subprocess.run):
    errors = []
    for primary in (True, False):
        args = ["wl-paste", "--no-newline", "--type", "text"]
        if primary:
            args.append("--primary")
        try:
            result = run(args, capture_output=True, text=True, timeout=3, check=False)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            if result.returncode:
                errors.append(result.stderr.strip())
        except subprocess.TimeoutExpired:
            errors.append("Tempo esgotado ao consultar Wayland")
        except FileNotFoundError as exc:
            raise RuntimeError("Instale wl-clipboard") from exc
    if len(errors) == 2:
        raise RuntimeError("Seleção/clipboard indisponíveis: " + "; ".join(errors))
    return ""


def read_sources(run=subprocess.run):
    """Snapshot somente leitura, incluindo origem, para prévia do app."""
    values = []
    for primary in (True, False):
        args = ["wl-paste", "--no-newline", "--type", "text"]
        if primary:
            args.append("--primary")
        result = run(args, capture_output=True, text=True, timeout=2, check=False)
        values.append(result.stdout if result.returncode == 0 else "")
    return tuple(values)


@dataclass
class SelectionCache:
    text: str = ""
    source: str = ""
    clipboard: str | None = None

    def update(self, primary, clipboard, owns_primary=False):
        changed = self.clipboard is not None and clipboard != self.clipboard
        self.clipboard = clipboard
        if owns_primary and self.text and not changed:
            return  # Não substitui texto externo pela seleção de um controle do app.
        if primary.strip() and not owns_primary:
            self.text, self.source = primary, "primary"
        elif clipboard.strip():
            self.text, self.source = clipboard, "clipboard"
        elif not owns_primary:
            self.text, self.source = "", ""


def preview_text(text, limit=180):
    short = " ".join(text.split())
    return short if len(short) <= limit else short[:limit - 1].rstrip() + "…"
