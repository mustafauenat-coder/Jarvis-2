"""Piper synthesis never accesses the network or downloads models implicitly."""
import io
import threading
import wave
from pathlib import Path

from app.openai_login import AppError

VOICE = "de_DE-thorsten-high"


class LocalVoice:
    def __init__(self, root):
        self.model = Path(root) / "voices" / (VOICE + ".onnx")
        self.voice = None
        self.lock = threading.Lock()

    def ready(self):
        return self.model.is_file() and Path(str(self.model) + ".json").is_file()

    def synthesize(self, text):
        if not self.ready():
            raise AppError("Piper-Stimme fehlt. Zuerst python -m scripts.download_voice ausführen.", 503)
        with self.lock:
            if self.voice is None:
                from piper import PiperVoice
                self.voice = PiperVoice.load(str(self.model), use_cuda=False)
            output = io.BytesIO()
            with wave.open(output, "wb") as wav:
                self.voice.synthesize_wav(text, wav)
            return output.getvalue()
