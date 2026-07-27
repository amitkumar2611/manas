"""Voice pipeline: STT/TTS behind protocols; command parsing is pure logic.

Backends (all optional, local-first):
  STT: faster-whisper  (pip install faster-whisper; model downloads on first use)
  TTS: pyttsx3         (pip install pyttsx3; uses OS speech engine)
The pipeline logic (wake word, command extraction) is backend-free and tested.
"""
from typing import Protocol

from manas.kernel.config import settings
from manas.kernel.errors import ManasError
from manas.kernel.registry import tools


class STT(Protocol):
    def transcribe(self, audio_path: str) -> str: ...


class TTS(Protocol):
    def speak(self, text: str) -> None: ...


class WhisperSTT:
    def transcribe(self, audio_path: str) -> str:
        try:
            from faster_whisper import WhisperModel  # optional dep
        except ImportError as e:
            raise ManasError("STT needs: pip install faster-whisper") from e
        model = WhisperModel(settings.stt_model, device="auto")
        segments, _ = model.transcribe(audio_path)
        return " ".join(s.text.strip() for s in segments)


class Pyttsx3TTS:
    def speak(self, text: str) -> None:
        try:
            import pyttsx3  # optional dep
        except ImportError as e:
            raise ManasError("TTS needs: pip install pyttsx3") from e
        eng = pyttsx3.init()
        eng.say(text)
        eng.runAndWait()


def extract_command(transcript: str, wake_word: str | None = None) -> str | None:
    """Pure logic: find the wake word, return everything after it.
    Returns None when the wake word is absent (i.e. not addressed to us)."""
    wake = (wake_word or settings.wake_word).lower().strip()
    words = transcript.lower()
    idx = words.find(wake)
    if idx < 0:
        return None
    cmd = transcript[idx + len(wake):].lstrip(" ,.:;!?")
    return cmd.strip() or None


@tools.register("transcribe")
class Transcribe:
    """Audio file -> text via the configured STT backend."""
    risk_level = "SAFE"

    def __init__(self, stt: STT | None = None) -> None:
        self.stt = stt or WhisperSTT()

    async def __call__(self, audio_path: str) -> dict:
        text = self.stt.transcribe(audio_path)
        return {"transcript": text,
                "command": extract_command(text)}
