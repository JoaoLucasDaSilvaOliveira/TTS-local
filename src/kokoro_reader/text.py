import html
import re
from urllib.parse import urlsplit

MAX_TEXT = 60_000


def clean_markdown(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError(f"Texto inválido ou maior que {MAX_TEXT} caracteres")
    text = text.replace("\r\n", "\n").replace("\x00", "")
    text = re.sub(r"\A\ufeff?---\s*\n.*?\n(?:---|\.\.\.)\s*(?:\n|$)", "", text, flags=re.S)

    def code(match):
        body = match.group(2).strip()
        return "\n" if len(body) > 120 or len(body.splitlines()) > 2 else "\n" + body + "\n"

    text = re.sub(r"(?m)^[ \t]*(`{3,}|~{3,})[^\n]*\n(.*?)^[ \t]*\1[`~]*[ \t]*$", code, text, flags=re.S)
    # Código indentado é reconhecido apenas em blocos separados, preservando listas.
    def indented(match):
        body = re.sub(r"(?m)^(?: {4}|\t)", "", match[0]).strip()
        return "\n" if len(body) > 120 or len(body.splitlines()) > 2 else "\n" + body + "\n"
    text = re.sub(r"(?m)(?:(?<=\n\n)|\A)(?:(?: {4}|\t)[^\n]*(?:\n|$))+", indented, text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^\n]*?\)", "", text)
    text = re.sub(r"!?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m[2] or m[1], text)
    text = re.sub(r"\[([^\]]+)\]\([^\s)]*(?:\s+\"[^\"]*\")?\)", r"\1", text)
    text = re.sub(r"(?m)^[ \t]*\[[^\]]+\]:[ \t]+\S+.*$", "", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    def url(match):
        raw = match[0]
        trimmed = raw.rstrip(".,;!?)]}")
        return (urlsplit(trimmed).hostname or "link") + raw[len(trimmed):]
    text = re.sub(r"https?://[^\s<>]+", url, text)
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    text = re.sub(r"(?m)^[ \t]*(?:#{1,6}[ \t]+|>[ \t]*|[-+*][ \t]+(?:\[[ xX]\][ \t]*)?|\d+[.)][ \t]+)", "", text)
    text = re.sub(r"(?m)^[ \t]*(?:[-*_][ \t]*){3,}$", "", text)
    text = re.sub(r"(`+)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*\*|__|~~)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\w)([*_])([^\n]+?)\1(?!\w)", r"\2", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _split_long_sentence(sentence, limit):
    """Prefer a clause boundary near the limit, then a word boundary."""
    remaining = sentence.strip()
    while len(remaining) > limit:
        prefix = remaining[:limit + 1]
        clauses = [m.end() for m in re.finditer(r"[,;](?=\s)", prefix)
                   if limit // 2 <= m.end() <= limit]
        spaces = [m.start() for m in re.finditer(r"\s+", prefix) if 0 < m.start() <= limit]
        cut = clauses[-1] if clauses else spaces[-1] if spaces else limit
        yield remaining[:cut].rstrip()
        remaining = remaining[cut:].lstrip()
    if remaining:
        yield remaining


def segment(text, limit=220, min_chars=0, first_min_chars=None):
    """Trechos curtos com IDs estáveis; não divide decimais nem siglas comuns."""
    if limit < 16:
        raise ValueError("Limite muito pequeno")
    if not 0 <= min_chars <= limit:
        raise ValueError("Tamanho mínimo inválido")
    if first_min_chars is not None and not 0 <= first_min_chars <= limit:
        raise ValueError("Tamanho mínimo inicial inválido")
    result = []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Soft line wrapping is formatting, not a speech boundary. Only blank
    # lines separate paragraphs; sentence punctuation handles the rest.
    for paragraph in re.split(r"\n[ \t]*\n(?:[ \t]*\n)*", text):
        paragraph_chunks = []
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        # Só encerra frase quando há espaço e próximo início; preserva Dr./etc.
        protected = re.sub(r"\b(?:Dr|Dra|Sr|Sra|Prof|etc)\.", lambda m: m[0][:-1] + "\ue000", paragraph)
        protected = re.sub(r"\b(?:[A-Z]\.){2,}", lambda m: m[0].replace(".", "\ue000"), protected)
        for sentence in re.split(r"(?<=[.!?…])\s+", protected):
            sentence = sentence.replace("\ue000", ".")
            for chunk in _split_long_sentence(sentence, limit):
                minimum = first_min_chars if first_min_chars is not None and not result and len(paragraph_chunks) == 1 else min_chars
                if (paragraph_chunks and len(paragraph_chunks[-1]) < minimum
                        and len(paragraph_chunks[-1]) + 1 + len(chunk) <= limit):
                    paragraph_chunks[-1] += " " + chunk
                else:
                    paragraph_chunks.append(chunk)
        # Evita uma última frase muito curta isolada quando cabe no trecho anterior.
        minimum = first_min_chars if first_min_chars is not None and not result and len(paragraph_chunks) == 2 else min_chars
        if (len(paragraph_chunks) > 1 and len(paragraph_chunks[-1]) < minimum
                and len(paragraph_chunks[-2]) + 1 + len(paragraph_chunks[-1]) <= limit):
            paragraph_chunks[-2] += " " + paragraph_chunks[-1]
            paragraph_chunks.pop()
        result.extend(paragraph_chunks)
    return result
