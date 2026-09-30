"""IPC mpv persistente; somente arquivos locais e socket Unix."""
import asyncio
import json
import contextlib

IPC_TIMEOUT = 3


class Player:
    def __init__(self, root):
        self.path = root / "mpv.sock"
        self.lock = asyncio.Lock()
        self.sequence = 0

    async def start(self):
        self.path.unlink(missing_ok=True)
        self.process = await asyncio.create_subprocess_exec(
            "mpv", "--no-config", "--idle=yes", "--no-terminal", "--no-video",
            "--keep-open=yes", "--audio-pitch-correction=yes", "--ao=pipewire,pulse,alsa",
            "--ytdl=no", f"--input-ipc-server={self.path}",
            stdout=asyncio.subprocess.DEVNULL,
        )
        for _ in range(100):
            if self.process.returncode is not None:
                raise RuntimeError("mpv não iniciou")
            try:
                self.reader, self.writer = await asyncio.open_unix_connection(str(self.path))
                return
            except (FileNotFoundError, ConnectionRefusedError):
                await asyncio.sleep(0.05)
        raise RuntimeError("mpv não criou o socket IPC")

    async def command(self, *args):
        async with self.lock:
            self.sequence += 1
            request = self.sequence
            self.writer.write((json.dumps({"command": args, "request_id": request}) + "\n").encode())
            await self.writer.drain()
            loading = args[0] == "loadfile"
            acknowledged, file_loaded, data = False, False, None
            # A loadfile ACK does not mean the new decoder is ready: EOF may
            # still describe the previous file. Hold the command lock until
            # both ACK and file-loaded arrive, in either event ordering.
            async with asyncio.timeout(IPC_TIMEOUT):
                while True:
                    line = await self.reader.readline()
                    if not line:
                        raise RuntimeError("mpv desconectou")
                    reply = json.loads(line)
                    if reply.get("request_id") == request:
                        if reply.get("error") != "success":
                            raise RuntimeError(f"mpv: {reply.get('error')}")
                        acknowledged, data = True, reply.get("data")
                    elif loading and reply.get("event") == "file-loaded":
                        file_loaded = True
                    elif loading and reply.get("event") == "end-file" and reply.get("reason") == "error":
                        raise RuntimeError(f"mpv: file load failed: {reply.get('file_error', 'error')}")
                    if acknowledged and (not loading or file_loaded):
                        return data

    async def close(self):
        if hasattr(self, "writer"):
            self.writer.close()
            with contextlib.suppress(ConnectionError, BrokenPipeError):
                await self.writer.wait_closed()
        if hasattr(self, "process") and self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()
        self.path.unlink(missing_ok=True)
