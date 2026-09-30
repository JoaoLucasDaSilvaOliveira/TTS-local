"""Opt-in live first-playback measurement; uses public text, leaves clipboard intact.

Run once before and once after installing/restarting the service to compare.
"""
import argparse
import json
import time
from pathlib import Path

from kokoro_reader.cli import send

TEXT = ("A leitura em português ajuda a revisar conceitos importantes e organizar o estudo com calma, "
        "permitindo compreender os detalhes antes de continuar a próxima etapa e preparar uma revisão cuidadosa.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = send({"command": "status"})
    if original["state"] != "idle":
        raise RuntimeError("Pare a leitura atual antes de medir.")
    results = []
    try:
        send({"command": "voice", "value": "pf_dora"})
        send({"command": "speed", "value": 1.0})
        for _ in range(2):
            send({"command": "read", "text": TEXT, "source": {"kind": "benchmark"}})
            deadline = time.monotonic() + 60
            first = None
            while time.monotonic() < deadline:
                status = send({"command": "status"})
                if first is None and status["state"] == "playing":
                    first = {"first_chars": len(status["segment_text"]), "segments": status["segment_count"],
                             "start_metrics": dict(status["metrics"])}
                if first is not None and status["state"] == "idle":
                    first["complete_metrics"] = status["metrics"]
                    results.append(first)
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("Timeout na reprodução do benchmark")
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))
    finally:
        send({"command": "stop"})
        send({"command": "voice", "value": original["voice"]})
        send({"command": "speed", "value": original["speed"]})


if __name__ == "__main__":
    main()
