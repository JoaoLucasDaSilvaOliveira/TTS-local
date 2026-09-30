"""Bounded process-local audio reuse; never persists selected text."""
from collections import OrderedDict


class AudioCache:
    def __init__(self, max_bytes=32 * 1024 * 1024, max_entries=64):
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.entries = OrderedDict()
        self.bytes = 0

    def get(self, key):
        audio = self.entries.get(key)
        if audio is not None:
            self.entries.move_to_end(key)
        return audio

    def put(self, key, audio):
        if audio.nbytes > self.max_bytes or self.max_entries < 1:
            return
        old = self.entries.pop(key, None)
        if old is not None:
            self.bytes -= old.nbytes
        audio.setflags(write=False)
        self.entries[key] = audio
        self.bytes += audio.nbytes
        while self.bytes > self.max_bytes or len(self.entries) > self.max_entries:
            _, removed = self.entries.popitem(last=False)
            self.bytes -= removed.nbytes
