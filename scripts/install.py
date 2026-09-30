"""Instalação por usuário, sem sudo; preserva e avisa sobre arquivos conflitantes."""
import argparse
import os
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


def install_kwin_dock(source, data_root=None):
    """Install only our package and enable only its named plugin key (Plasma 6)."""
    data_root = data_root or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    target = data_root / "kwin/scripts/kokoro-reader-dock"
    for path in source.rglob("*"):
        if path.is_file():
            install_file(path, target / path.relative_to(source))
    writer = shutil.which("kwriteconfig6")
    dbus = shutil.which("qdbus6") or shutil.which("qdbus")
    if writer and dbus:
        subprocess.run([writer, "--file", "kwinrc", "--group", "Plugins",
                        "--key", "kokoro-reader-dockEnabled", "true"], check=True)
        subprocess.run([dbus, "org.kde.KWin", "/KWin", "reconfigure"], check=True)
        subprocess.run([dbus, "org.kde.KWin", "/Scripting", "start"], check=True)
        print("KWin: posicionamento superior habilitado apenas para Kokoro Reader.")
    else:
        print("KWin: pacote instalado; habilite 'Kokoro Reader top dock' em Configurações > Scripts do KWin.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-sync", action="store_true", help="somente copia; rode uv sync na instalação depois")
    parser.add_argument("--without-gui", action="store_true", help="instala somente serviço e cliente de terminal")
    parser.add_argument("--without-kwin", action="store_true", help="não instala o posicionamento do dock no KDE")
    args = parser.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    if SOURCE != TARGET:
        for name in ("pyproject.toml", "uv.lock", "README.md"):
            install_file(SOURCE / name, TARGET / name)
        for folder in ("src", "scripts", "systemd", "tests", "docs", "desktop", "kwin"):
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
        command = ["uv", "sync", "--python", "3.12", "--locked"]
        if not args.without_gui:
            command += ["--extra", "gui"]
        subprocess.run(command, cwd=TARGET, check=True)
    binary = Path.home() / ".local/bin"
    binary.mkdir(parents=True, exist_ok=True)
    for name in ("kokoro-reader", "kokoro-readerctl", "kokoro-reader-panel"):
        launcher = binary / name
        expected = f'#!/bin/sh\nexec "{TARGET}/.venv/bin/{name}" "$@"\n'
        if launcher.exists() and launcher.read_text() != expected:
            raise RuntimeError(f"Launcher existente preservado; resolva: {launcher}")
        launcher.write_text(expected)
        launcher.chmod(0o755)
    install_file(TARGET / "systemd/kokoro-reader.service", Path.home() / ".config/systemd/user/kokoro-reader.service")
    if not args.without_gui:
        template = (TARGET / "desktop/kokoro-reader.desktop").read_text()
        desktop = TARGET / "desktop/kokoro-reader-installed.desktop"
        desktop.write_text(template.replace("@PANEL@", str(binary / "kokoro-reader-panel")))
        install_file(desktop, Path.home() / ".local/share/applications/kokoro-reader.desktop")
        if not args.without_kwin and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
            install_kwin_dock(TARGET / "kwin/kokoro-reader-dock")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    print(f"Instalado em {TARGET}. Baixe os pesos e habilite o serviço conforme README.")


if __name__ == "__main__":
    main()
