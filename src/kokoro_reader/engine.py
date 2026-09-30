import os
import time
from pathlib import Path

from .settings import VOICES, validate_voice
from .latency import AudioCache

REPO = "hexgrad/Kokoro-82M"
REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"


def model_dir():
    return Path(os.environ.get("KOKORO_READER_HOME", Path.home() / ".local/share/kokoro-reader")) / "models"


def download():
    from huggingface_hub import snapshot_download
    # Apenas pesos oficiais, configuração e três vozes brasileiras.
    return snapshot_download(REPO, revision=REVISION, local_dir=model_dir(),
                             allow_patterns=["config.json", "kokoro-v1_0.pth", *[f"voices/{v}.pt" for v in VOICES]])


class Engine:
    def __init__(self):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from kokoro import KModel, KPipeline
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
        # Misaki define uma cópia embutida; preferimos explicitamente o pacote Arch.
        EspeakWrapper.set_library("/usr/lib/libespeak-ng.so.1")
        EspeakWrapper.set_data_path("/usr/share/espeak-ng-data")
        torch.set_num_threads(int(os.environ.get("KOKORO_THREADS", "2")))
        root = model_dir()
        model = KModel(repo_id=REPO, config=str(root / "config.json"), model=str(root / "kokoro-v1_0.pth"))
        self.pipeline = KPipeline(lang_code="p", repo_id=REPO, model=model.to("cpu").eval(), device="cpu")
        for voice in VOICES:
            self.pipeline.voices[voice] = self.pipeline.load_voice(str(root / "voices" / f"{voice}.pt"))
        self.cache = AudioCache()

    def warmup(self, voice):
        """Pay lazy CPU initialization before accepting read requests."""
        self.synthesize("Olá! Vamos começar a leitura.", voice)

    def synthesize(self, text, voice):
        import numpy as np
        import torch
        validate_voice(voice)
        started = time.perf_counter()
        key = (voice, text)
        cached = self.cache.get(key)
        if cached is not None:
            return cached, time.perf_counter() - started
        # Verifica o limite real para evitar o truncamento silencioso da pipeline p.
        def generate(part):
            phonemes, _ = self.pipeline.g2p(part)
            if len(phonemes) > 500:
                if len(part) < 2:
                    raise ValueError("Token excede limite de fonemas")
                middle = part.rfind(" ", 0, len(part) // 2 + 1)
                middle = middle if middle > 0 else len(part) // 2
                return generate(part[:middle]) + generate(part[middle:])
            if not phonemes:
                return []
            return [r.audio.numpy() for r in self.pipeline.generate_from_tokens(phonemes, voice=voice, speed=1)]
        with torch.inference_mode():
            chunks = generate(text)
        if not chunks:
            raise ValueError("Trecho sem conteúdo pronunciável")
        audio = np.concatenate(chunks)
        self.cache.put(key, audio)
        return audio, time.perf_counter() - started
