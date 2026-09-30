"""Teste real opt-in: fala, controla mpv, valida limpeza e registra métricas."""
import argparse
import hashlib
import json
import socket
import subprocess
import time
from pathlib import Path

from kokoro_reader.cli import send
from kokoro_reader.settings import runtime_dir


def mpv(*command):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect(str(runtime_dir() / "mpv.sock"))
        connection.sendall((json.dumps({"command": command, "request_id": 1}) + "\n").encode())
        with connection.makefile() as stream:
            for line in stream:
                reply = json.loads(line)
                if reply.get("request_id") == 1:
                    if reply.get("error") == "property unavailable":
                        return None
                    assert reply["error"] == "success", reply
                    return reply.get("data")


def wait(predicate, timeout=60):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        status = send({"command": "status"})
        if predicate(status):
            return status
        time.sleep(0.1)
    raise RuntimeError("Timeout: " + json.dumps(status))


def clipboard_hash():
    value = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=3)
    return hashlib.sha256(value.stdout).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("docs/smoke-results.json"))
    args = parser.parse_args()
    original = send({"command": "status"})
    before = clipboard_hash()
    report = {"device": "cpu", "checks": []}
    try:
        send({"command": "voice", "value": "pf_dora"})
        send({"command": "speed", "value": 1.0})
        send({"command": "read", "text": "Ação e coração: revisão de ciência. Em 2026, são 25 minutos e R$ 12,50. CPU, INSS e TTS. Veja https://example.com/estudo.\n\nSegundo parágrafo: pausa, retomada, anterior e próximo."})
        status = wait(lambda s: s["state"] == "playing")
        report["initial_metrics"] = status["metrics"]
        report["audio_output"] = mpv("get_property", "current-ao")
        send({"command": "pause"})
        send({"command": "pause"})
        assert mpv("get_property", "pause") is True
        pos1 = mpv("get_property", "time-pos")
        time.sleep(0.35)
        pos2 = mpv("get_property", "time-pos")
        assert abs(pos2 - pos1) < 0.1
        report["checks"].append("pause preserves mpv time-pos")
        send({"command": "next"})
        wait(lambda s: s["state"] == "paused" and s["segment_index"] == 1)
        # Estado paused durante buffering; aguarde arquivo ser carregado no mpv.
        for _ in range(200):
            path = mpv("get_property", "path")
            if path and path.endswith("00001.wav"):
                break
            time.sleep(0.1)
        assert path.endswith("00001.wav")
        assert mpv("get_property", "pause") is True
        send({"command": "previous"})
        for _ in range(100):
            path = mpv("get_property", "path")
            if path and path.endswith("00000.wav"):
                break
            time.sleep(0.1)
        assert path.endswith("00000.wav")
        report["checks"].append("next/previous load correct WAV while paused")
        send({"command": "seek-forward"})
        time.sleep(0.2)
        assert mpv("get_property", "pause") is True
        send({"command": "seek-backward"})
        time.sleep(0.2)
        assert mpv("get_property", "time-pos") < 0.5
        report["checks"].append("seek +10/-10 seconds works and preserves pause")
        send({"command": "faster"})
        assert mpv("get_property", "speed") == 1.1
        send({"command": "slower"})
        assert mpv("get_property", "speed") == 1.0
        send({"command": "speed", "value": 0.75})
        assert mpv("get_property", "speed") == 0.75
        send({"command": "speed", "value": 1.5})
        assert mpv("get_property", "speed") == 1.5
        send({"command": "speed", "value": 1.0})
        report["checks"].append("speed changes immediately, including 0.75 and 1.50")
        send({"command": "play"})
        send({"command": "play"})
        assert mpv("get_property", "pause") is False
        wait(lambda s: s["state"] == "idle")
        assert not list(runtime_dir().glob("audio-*"))
        report["checks"].append("resume, automatic EOF progression and WAV cleanup")
        # Sessão nova e contínua, sem controles, modelo já quente.
        send({"command": "read", "text": "A leitura é local e usa apenas a CPU. Estudar com calma ajuda a compreender.\n\nMais um trecho para testar a fila. A revisão terminou."})
        status = wait(lambda s: s["state"] == "idle")
        report["continuous_metrics"] = status["metrics"]
        send({"command": "read", "text": "Texto para parar antes da conclusão."})
        send({"command": "stop"})
        assert not list(runtime_dir().glob("audio-*"))
        report["checks"].append("stop during synthesis cleans files")
        assert before == clipboard_hash()
        report["checks"].append("clipboard unchanged")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        send({"command": "stop"})
        send({"command": "voice", "value": original["voice"]})
        send({"command": "speed", "value": original["speed"]})


if __name__ == "__main__":
    main()
