# Speech-to-text using Whisper (offline-capable) with fallback
import io
import tempfile
from pathlib import Path
from typing import Optional

from . import config


def transcribe_audio(audio_bytes: bytes, language: Optional[str] = None) -> str:
    """Transcribe audio to text. Prefer Whisper; fallback to SpeechRecognition if needed."""
    try:
        return _whisper_transcribe(audio_bytes, language)
    except Exception as e:
        try:
            return _sr_transcribe(audio_bytes, language)
        except Exception:
            raise e


def _whisper_transcribe(audio_bytes: bytes, language: Optional[str] = None) -> str:
    import whisper
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        model = whisper.load_model(config.WHISPER_MODEL, download_root=str(config.AUDIO_CACHE_DIR))
        result = model.transcribe(path, language=language or None, fp16=False)
        return (result.get("text") or "").strip()
    finally:
        Path(path).unlink(missing_ok=True)


def _sr_transcribe(audio_bytes: bytes, language: Optional[str] = None) -> str:
    import speech_recognition as sr
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        r = sr.Recognizer()
        with sr.AudioFile(path) as source:
            audio = r.record(source)
        # Prefer Google Web API (free, no key for short audio) or use default
        try:
            return r.recognize_google(audio, language=(language or "en-US").split("-")[0] + "-" + (language or "en-US").upper()[:2] if language else None) or ""
        except Exception:
            return r.recognize_google(audio) or ""
    finally:
        Path(path).unlink(missing_ok=True)
