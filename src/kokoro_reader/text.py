import html
import re
import textwrap
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
    text = re.sub(r"(?m)^\s*\[[^\]]+\]:\s+\S+.*$", "", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    def url(match):
        raw = match[0]
        trimmed = raw.rstrip(".,;!?)]}")
        return (urlsplit(trimmed).hostname or "link") + raw[len(trimmed):]
    text = re.sub(r"https?://[^\s<>]+", url, text)
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}\s+|>\s*|[-+*]\s+(?:\[[ xX]\]\s*)?|\d+[.)]\s+)", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*_]\s*){3,}$", "", text)
    text = re.sub(r"(`+)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*\*|__|~~)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\w)([*_])([^\n]+?)\1(?!\w)", r"\2", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def segment(text, limit=220, min_chars=0):
    """Trechos curtos com IDs estáveis; não divide decimais nem siglas comuns."""
    if limit < 16:
        raise ValueError("Limite muito pequeno")
    if not 0 <= min_chars <= limit:
        raise ValueError("Tamanho mínimo inválido")
    result = []
    for paragraph in re.split(r"\n+", text):
        paragraph_chunks = []
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        # Só encerra frase quando há espaço e próximo início; preserva Dr./etc.
        protected = re.sub(r"\b(?:Dr|Dra|Sr|Sra|Prof|etc)\.", lambda m: m[0][:-1] + "\ue000", paragraph)
        protected = re.sub(r"\b(?:[A-Z]\.){2,}", lambda m: m[0].replace(".", "\ue000"), protected)
        for sentence in re.split(r"(?<=[.!?…])\s+", protected):
            sentence = sentence.replace("\ue000", ".")
            for chunk in textwrap.wrap(sentence, width=limit, break_long_words=True, break_on_hyphens=False):
                if (paragraph_chunks and len(paragraph_chunks[-1]) < min_chars
                        and len(paragraph_chunks[-1]) + 1 + len(chunk) <= limit):
                    paragraph_chunks[-1] += " " + chunk
                else:
                    paragraph_chunks.append(chunk)
        # Evita uma última frase muito curta isolada quando cabe no trecho anterior.
        if (len(paragraph_chunks) > 1 and len(paragraph_chunks[-1]) < min_chars
                and len(paragraph_chunks[-2]) + 1 + len(paragraph_chunks[-1]) <= limit):
            paragraph_chunks[-2] += " " + paragraph_chunks[-1]
            paragraph_chunks.pop()
        result.extend(paragraph_chunks)
    return result
