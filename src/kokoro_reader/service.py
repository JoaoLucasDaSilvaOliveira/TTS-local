import asyncio
import contextlib
import fcntl
import json
import logging
import os
import shutil
import signal
import socket
import struct
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .engine import Engine
from .notify import notify
from .player import Player
from .settings import Preferences, runtime_dir, validate_speed, validate_voice
from .text import clean_markdown, segment

LOG = logging.getLogger(__name__)


@dataclass
class Session:
    texts: list[str]
    directory: Path
    voice: str
    source: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    index: int = 0
    revision: int = 0
    loaded: int = -1
    paused: bool = False
    audio: dict = field(default_factory=dict)
    started: float = field(default_factory=time.perf_counter)
    first_playback: float | None = None
    waiting_since: float | None = None
    producer: asyncio.Task | None = None


class Reader:
    def __init__(self, engine, player, root, preferences=None):
        self.engine, self.player, self.root = engine, player, root
        self.preferences = preferences or Preferences.load()
        self.session = None
        self.lock = asyncio.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kokoro-cpu")
        self.metrics = {}
        self.wakeup = asyncio.Event()

    async def stop(self):
        session, self.session = self.session, None
        try:
            await self.player.command("stop")
        finally:
            if session:
                if session.producer:
                    session.producer.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await session.producer
                shutil.rmtree(session.directory)

    async def produce(self, session):
        import soundfile as sf
        try:
            for index, text in enumerate(session.texts):
                # Limita adiantamento; retém WAVs já ouvidos para navegação anterior.
                while index > session.index + 3:
                    await asyncio.sleep(0.1)
                audio, elapsed = await asyncio.get_running_loop().run_in_executor(
                    self.executor, self.engine.synthesize, text, session.voice)
                if self.session is not session:
                    return
                path = session.directory / f"{index:05}.wav"
                sf.write(path, audio, 24000)
                session.audio[index] = path
                self.wakeup.set()
                LOG.info("synthesis index=%s seconds=%.3f audio_seconds=%.3f", index, elapsed, len(audio) / 24000)
                if index == 0:
                    self.metrics = {"first_synthesis_seconds": round(elapsed, 3), "first_audio_seconds": round(len(audio) / 24000, 3)}
                self.metrics["synthesis_total_seconds"] = round(self.metrics.get("synthesis_total_seconds", 0) + elapsed, 3)
                self.metrics["audio_total_seconds"] = round(self.metrics.get("audio_total_seconds", 0) + len(audio) / 24000, 3)
                self.metrics["synthesized_segments"] = index + 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.exception("Síntese falhou")
            notify(f"Falha na síntese: {exc}", error=True)
            async with self.lock:
                if self.session is session:
                    # Não aguarda/cancela a própria tarefa.
                    session.producer = None
                    await self.stop()

    async def tick(self):
        async with self.lock:
            s = self.session
            if not s:
                return
            if s.loaded == s.revision and not s.paused and await self.player.command("get_property", "eof-reached"):
                if s.index + 1 == len(s.texts):
                    self.metrics["session_wall_seconds"] = round(time.perf_counter() - s.started, 3)
                    LOG.info("session_complete %s", json.dumps(self.metrics))
                    await self.stop()
                    return
                s.index += 1
                s.revision += 1
                s.waiting_since = time.perf_counter()
            if s.loaded != s.revision:
                if s.index not in s.audio:
                    return
                await self.player.command("loadfile", str(s.audio[s.index]), "replace")
                await self.player.command("set_property", "speed", self.preferences.speed)
                await self.player.command("set_property", "pause", s.paused)
                s.loaded = s.revision
                if s.waiting_since is not None:
                    gap = time.perf_counter() - s.waiting_since
                    self.metrics["transition_wait_seconds"] = round(self.metrics.get("transition_wait_seconds", 0) + gap, 3)
                    s.waiting_since = None
                if s.first_playback is None:
                    s.first_playback = time.perf_counter() - s.started
                    self.metrics["first_playback_seconds"] = round(s.first_playback, 3)
                    LOG.info("first_playback seconds=%.3f", s.first_playback)
                    notify(f"Lendo {len(s.texts)} trechos com {s.voice}")
                return

    def status(self):
        s = self.session
        return {"protocol": 1, "voice": self.preferences.voice, "speed": self.preferences.speed,
                "state": "idle" if s is None else "paused" if s.paused else "playing" if s.loaded == s.revision else "buffering",
                "segment_index": s.index if s else None, "segment_count": len(s.texts) if s else 0,
                "segment_text": s.texts[s.index] if s else None, "source": s.source if s else None,
                "session_id": s.id if s else None, "segment_id": f"{s.id}:{s.index}" if s else None,
                "metrics": self.metrics}

    async def dispatch(self, request):
        async with self.lock:
            cmd = request.get("command")
            if cmd == "read":
                texts = segment(clean_markdown(request.get("text", "")), min_chars=100, first_min_chars=0)
                if not texts:
                    raise ValueError("Texto vazio após limpeza")
                source = request.get("source", {})
                if not isinstance(source, dict) or len(json.dumps(source)) > 2048:
                    raise ValueError("source inválido")
                await self.stop()
                s = Session(texts, Path(tempfile.mkdtemp(prefix="audio-", dir=self.root)), self.preferences.voice, source)
                self.session = s
                self.metrics = {}
                s.producer = asyncio.create_task(self.produce(s))
                self.wakeup.set()
            elif cmd == "stop":
                await self.stop()
            elif cmd in ("play", "pause", "toggle"):
                if self.session:
                    self.session.paused = not self.session.paused if cmd == "toggle" else cmd == "pause"
                    await self.player.command("set_property", "pause", self.session.paused)
            elif cmd in ("seek-forward", "seek-backward"):
                if self.session and self.session.loaded == self.session.revision:
                    await self.player.command("seek", 10 if cmd == "seek-forward" else -10, "relative+exact")
            elif cmd in ("previous", "next"):
                if self.session:
                    s = self.session
                    s.index = max(0, min(len(s.texts) - 1, s.index + (1 if cmd == "next" else -1)))
                    s.revision += 1
                    await self.player.command("stop")
                    self.wakeup.set()
            elif cmd in ("speed", "faster", "slower", "voice"):
                p = Preferences(self.preferences.voice, self.preferences.speed)
                if cmd == "voice":
                    p.voice = validate_voice(request.get("value"))
                elif cmd == "speed":
                    p.speed = validate_speed(request.get("value"))
                else:
                    p.speed = round(max(0.75, min(1.5, p.speed + (0.1 if cmd == "faster" else -0.1))), 2)
                p.save()
                self.preferences = p
                await self.player.command("set_property", "speed", p.speed)
            elif cmd != "status":
                raise ValueError("Comando desconhecido")
            return self.status()


async def serve():
    os.umask(0o077)
    root = runtime_dir()
    lock = (root / "service.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError("Serviço já está em execução") from exc
    # Restos somente dos diretórios de áudio criados por este serviço.
    for path in root.glob("audio-*"):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
    started = time.perf_counter()
    engine = await asyncio.to_thread(Engine)
    await asyncio.to_thread(engine.warmup, Preferences.load().voice)
    LOG.info("model_load seconds=%.3f", time.perf_counter() - started)
    player = Player(root)
    reader = None
    path = root / "control.sock"
    server = None
    shutdown = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, shutdown.set)
    try:
        await player.start()
        reader = Reader(engine, player, root)

        async def client(stream, writer):
            try:
                peer = writer.get_extra_info("socket")
                _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    raise PermissionError("Usuário não autorizado")
                raw = await asyncio.wait_for(stream.readline(), 5)
                request = json.loads(raw)
                if not isinstance(request, dict) or request.get("protocol", 1) != 1:
                    raise ValueError("Protocolo inválido")
                result = {"ok": True, **await reader.dispatch(request)}
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            try:
                writer.write((json.dumps(result, ensure_ascii=False) + "\n").encode())
                await writer.drain()
            except (ConnectionError, BrokenPipeError):
                pass
            finally:
                writer.close()
                with contextlib.suppress(ConnectionError, BrokenPipeError):
                    await writer.wait_closed()

        path.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(client, str(path), limit=400_000)
        path.chmod(0o600)
        LOG.info("ready socket=%s", path)
        while not shutdown.is_set():
            reader.wakeup.clear()
            await reader.tick()
            try:
                await asyncio.wait_for(reader.wakeup.wait(), 0.02)
            except TimeoutError:
                pass
    finally:
        if server:
            server.close()
            await server.wait_closed()
        if reader:
            try:
                await reader.stop()
            except Exception:
                LOG.exception("Erro ao parar mpv; áudio temporário removido")
            finally:
                reader.executor.shutdown(wait=True, cancel_futures=True)
        try:
            await player.close()
        finally:
            path.unlink(missing_ok=True)
            lock.close()
