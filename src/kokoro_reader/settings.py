import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

VOICES = ("pf_dora", "pm_alex", "pm_santa")
SPEED_STEPS = (0.75, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30, 1.40, 1.50)


def config_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kokoro-reader"


def runtime_dir():
    root = os.environ.get("XDG_RUNTIME_DIR")
    if not root:
        raise RuntimeError("XDG_RUNTIME_DIR ausente; execute na sessão do usuário.")
    path = Path(root) / "kokoro-reader"
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise RuntimeError("Diretório de execução inseguro")
    path.chmod(0o700)
    return path


def validate_voice(value):
    if value not in VOICES:
        raise ValueError("Voz inválida; use " + ", ".join(VOICES))
    return value


def validate_speed(value):
    if isinstance(value, bool):
        raise ValueError("Velocidade inválida")
    value = float(value)
    if not math.isfinite(value) or not 0.75 <= value <= 1.5:
        raise ValueError("Velocidade deve estar entre 0.75 e 1.50")
    return round(value, 2)


def step_speed(value, direction):
    """Move along a fixed grid anchored at 1.00, including the 0.75 endpoint.

    Explicit/custom speeds remain valid; +/- moves to the next grid neighbor.
    """
    value = validate_speed(value)
    if direction not in (-1, 1):
        raise ValueError("Direção de velocidade inválida")
    steps = SPEED_STEPS if direction == 1 else reversed(SPEED_STEPS)
    for speed in steps:
        if (speed > value if direction == 1 else speed < value):
            return speed
    return SPEED_STEPS[-1] if direction == 1 else SPEED_STEPS[0]


@dataclass
class Preferences:
    voice: str = "pf_dora"
    speed: float = 1.0

    @classmethod
    def load(cls, path=None):
        path = path or config_dir() / "preferences.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(validate_voice(data["voice"]), validate_speed(data["speed"]))

    def save(self, path=None):
        validate_voice(self.voice)
        validate_speed(self.speed)
        path = path or config_dir() / "preferences.json"
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".preferences-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(asdict(self), stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
