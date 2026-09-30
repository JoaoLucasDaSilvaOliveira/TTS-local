import argparse
import asyncio
import json
import logging
import socket
import sys
import time
from pathlib import Path

from .clipboard import read_selection
from .notify import notify
from .settings import VOICES, runtime_dir

SAMPLE_TEXT = "Olá! Esta é uma revisão de português brasileiro: ação, coração e ciência. Em 2026, estudamos 25 minutos."


def send(request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect(str(runtime_dir() / "control.sock"))
        client.sendall((json.dumps({"protocol": 1, **request}, ensure_ascii=False) + "\n").encode())
        with client.makefile("r", encoding="utf-8") as stream:
            result = json.loads(stream.readline(400_000))
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Erro desconhecido"))
    return result


def samples(output, text):
    from .engine import Engine
    import soundfile as sf
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    engine = Engine()
    report = {"text": text, "device": "cpu", "model_load_seconds": round(time.perf_counter() - started, 3), "voices": {}}
    for voice in VOICES:
        audio, elapsed = engine.synthesize(text, voice)
        path = output / f"{voice}.wav"
        sf.write(path, audio, 24000)
        report["voices"][voice] = {"synthesis_seconds": round(elapsed, 3), "audio_seconds": round(len(audio) / 24000, 3),
                                    "real_time_factor": round(elapsed / (len(audio) / 24000), 3)}
    (output / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Leitor Kokoro offline, português brasileiro, CPU")
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("read", help="seleção primária; fallback clipboard")
    group = read.add_mutually_exclusive_group()
    group.add_argument("--text", help="texto explícito; não consulta clipboard")
    group.add_argument("--stdin", action="store_true", help="texto vindo de stdin")
    for command in ("toggle", "stop", "previous", "next", "faster", "slower", "status", "serve", "download"):
        commands.add_parser(command)
    commands.add_parser("voice").add_argument("value", choices=VOICES)
    commands.add_parser("speed").add_argument("value", type=float)
    sample = commands.add_parser("samples")
    sample.add_argument("--output", type=Path, default=Path("samples"))
    sample.add_argument("--text", default=SAMPLE_TEXT)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from .service import serve
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
            asyncio.run(serve())
            return
        if args.command == "download":
            from .engine import download
            print(download())
            return
        if args.command == "samples":
            samples(args.output, args.text)
            return
        request = {"command": args.command}
        if args.command == "read":
            text = sys.stdin.read(60_001) if args.stdin else args.text if args.text is not None else read_selection()
            if not text.strip():
                raise ValueError("Seleção e clipboard vazios")
            request.update(text=text, source={"kind": "stdin" if args.stdin else "text" if args.text is not None else "wayland"})
        if hasattr(args, "value"):
            request["value"] = args.value
        print(json.dumps(send(request), ensure_ascii=False, indent=2))
    except Exception as exc:
        message = str(exc)
        if isinstance(exc, (FileNotFoundError, ConnectionRefusedError)) and args.command not in ("serve", "download", "samples"):
            message = "Serviço indisponível ou carregando. Consulte: systemctl --user status kokoro-reader"
        notify(message, error=True)
        print(f"Kokoro Reader: {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
