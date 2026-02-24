# VoqTask - Configuration
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("TASKWHISPER_DATA", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "tasks.db"
AUDIO_CACHE_DIR = DATA_DIR / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

DEFAULT_SPEECH_RATE = 1.0
# Keep focused options for hackathon demo reliability and local language support.
SUPPORTED_LANGUAGES = ["en", "ta", "te", "hi"]
OFFLINE_MODE = os.environ.get("OFFLINE_MODE", "0") == "1"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
