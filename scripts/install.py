"""Instalação por usuário, sem sudo; preserva e avisa sobre arquivos conflitantes."""
import argparse
import shutil
import subprocess
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
TARGET = Path.home() / ".local/share/kokoro-reader"


def install_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and source.read_bytes() != target.read_bytes():
        backup = target.with_name(target.name + ".before-install")
        if backup.exists():
            backup = target.with_name(target.name + f".before-install.{time.time_ns()}")
        shutil.copy2(target, backup)
        print(f"Preservado: {backup}")
    shutil.copy2(source, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-sync", action="store_true", help="somente copia; rode uv sync na instalação depois")
    args = parser.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    if SOURCE != TARGET:
        for name in ("pyproject.toml", "uv.lock", "README.md"):
            install_file(SOURCE / name, TARGET / name)
        for folder in ("src", "scripts", "systemd", "tests", "docs"):
            for path in (SOURCE / folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    install_file(path, TARGET / path.relative_to(SOURCE))
    config = Path.home() / ".config/kokoro-reader"
    config.mkdir(parents=True, mode=0o700, exist_ok=True)
    preferences = config / "preferences.json"
    if not preferences.exists():
        preferences.write_text('{"voice": "pf_dora", "speed": 1.0}\n')
        preferences.chmod(0o600)
    if not args.skip_sync:
        subprocess.run(["uv", "sync", "--python", "3.12", "--locked"], cwd=TARGET, check=True)
    binary = Path.home() / ".local/bin"
    binary.mkdir(parents=True, exist_ok=True)
    for name in ("kokoro-reader", "kokoro-readerctl"):
        launcher = binary / name
        expected = f'#!/bin/sh\nexec "{TARGET}/.venv/bin/{name}" "$@"\n'
        if launcher.exists() and launcher.read_text() != expected:
            raise RuntimeError(f"Launcher existente preservado; resolva: {launcher}")
        launcher.write_text(expected)
        launcher.chmod(0o755)
    install_file(TARGET / "systemd/kokoro-reader.service", Path.home() / ".config/systemd/user/kokoro-reader.service")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    print(f"Instalado em {TARGET}. Baixe os pesos e habilite o serviço conforme README.")


if __name__ == "__main__":
    main()
