"""Opt-in real-model test: JARVIS_TEST_VOICE_ROOT points to external runtime data."""
import io
import os
import socket
import wave

import pytest

from app.voice import LocalVoice


@pytest.mark.skipif(not os.environ.get("JARVIS_TEST_VOICE_ROOT"), reason="External voice model not configured")
def test_real_piper_without_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline synthesis attempted network access")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    audio = LocalVoice(os.environ["JARVIS_TEST_VOICE_ROOT"]).synthesize("Jarvis ist online.")
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.getframerate() == 22050
        assert wav.getnchannels() == 1
        assert wav.getnframes() > 10000
