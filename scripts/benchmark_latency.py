"""Offline CPU timing; run with PYTHONPATH=src python scripts/benchmark_latency.py."""
import argparse
import json
import time

from kokoro_reader.engine import Engine
from kokoro_reader.text import segment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", choices=["pf_dora", "pm_alex", "pm_santa"], default="pf_dora")
    args = parser.parse_args()
    text = "Este é um teste de leitura em português. O leitor deve começar rapidamente e continuar sem interrupções entre as frases."
    started = time.perf_counter()
    engine = Engine()
    print(json.dumps({"model_load_seconds": time.perf_counter() - started}), flush=True)
    started = time.perf_counter()
    engine.warmup(args.voice)
    print(json.dumps({"warmup_seconds": time.perf_counter() - started}), flush=True)
    first = segment(text, min_chars=100, first_min_chars=0)[0]
    for label, sample in [("first_sentence", first), ("full_segment", text), ("repeated_segment", text)]:
        audio, elapsed = engine.synthesize(sample, args.voice)
        print(json.dumps({"sample": label, "voice": args.voice, "chars": len(sample),
                          "seconds": elapsed, "audio_seconds": len(audio) / 24000}), flush=True)


if __name__ == "__main__":
    main()
