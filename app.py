# VoqTask - Voice To-Do Task App (Streamlit)
# Run: streamlit run app.py

import streamlit as st
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import sys
import hashlib
import html
import io
import re
import numpy as np
import soundfile as sf

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

# Ensure package is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from taskwhisper.storage import (
    init_db,
    save_task,
    get_tasks,
    get_task_by_id,
    update_task_status,
    update_task,
    delete_task,
)
from taskwhisper import storage as storage_module
from taskwhisper.models import Task, TaskStatus, Priority, now_iso, ConversationTurn
from taskwhisper.nlu import parse_task_from_text, is_task_creation
from taskwhisper.voice import transcribe_audio
from taskwhisper.jarvis import get_proactive_suggestion, reply_to_user
from taskwhisper import config
from taskwhisper import sync_supabase

reward_task_completion = getattr(storage_module, "reward_task_completion", None)
get_user_rewards_summary = getattr(storage_module, "get_user_rewards_summary", None)

if reward_task_completion is None:
    def reward_task_completion(task_id: str, user_id: str = "default") -> dict:
        return {"awarded": False, "points_awarded": 0, "level": 1, "streak_days": 0}

if get_user_rewards_summary is None:
    def get_user_rewards_summary(user_id: str = "default") -> dict:
        return {
            "points": 0,
            "tasks_completed": 0,
            "streak_days": 0,
            "level": 1,
            "points_in_level": 0,
            "needed_for_next": 100,
            "level_progress": 0.0,
        }

# Page config - accessibility (SDG 10)
st.set_page_config(
    page_title="VoqTask - Voice To-Do Tasks",
    page_icon="list",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Attractive UI/UX - cohesive dark theme with warm accent
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
    /* Base */
    .stApp {
        background: linear-gradient(160deg, #0c0e14 0%, #131720 35%, #0f1219 100%);
        font-family: 'Outfit', -apple-system, sans-serif;
        max-width: none;
        width: 100%;
        margin: 0;
        padding: 0 1.5rem 2rem;
    }
    .app-shell {
        max-width: 1120px;
        margin: 0 auto;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 28px;
        padding: 1.1rem 1.1rem 1.4rem;
        background: linear-gradient(155deg, rgba(15,18,28,0.75), rgba(10,13,22,0.88));
        box-shadow: 0 24px 60px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.03);
        backdrop-filter: blur(8px);
    }
    [data-testid="stAppViewContainer"] { background: transparent; }
    [data-testid="stAppViewContainer"] .main .block-container {
        max-width: 100%;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    [data-testid="stHeader"] { background: transparent; }
    .stMarkdown { font-family: 'Outfit', sans-serif; }
    h1, h2, h3 { font-family: 'Outfit', sans-serif; font-weight: 600; letter-spacing: -0.02em; }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d0f16 0%, #12151d 100%) !important;
        border-right: 1px solid rgba(255,200,100,0.08);
    }
    [data-testid="stSidebar"] .stMarkdown { color: #a0a8b8; }
    [data-testid="stSidebar"] h3 { color: #e8eaed; }
    /* Hero / Voice section */
    .hero-wrap {
        background: linear-gradient(145deg, rgba(22,25,35,0.95) 0%, rgba(18,21,30,0.98) 100%);
        border: 1px solid rgba(255,200,100,0.12);
        border-radius: 20px;
        padding: 1.75rem 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 8px 32px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.03);
    }
    .hero-wrap .voice-zone {
        background: rgba(255,200,100,0.06);
        border-radius: 14px;
        padding: 1.25rem;
        border: 1px dashed rgba(255,200,100,0.2);
    }
    .hero-wrap .text-zone {
        background: rgba(100,180,255,0.05);
        border-radius: 14px;
        padding: 1.25rem;
        border: 1px solid rgba(100,180,255,0.12);
    }
    .hero-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #ffc864;
        margin-bottom: 0.5rem;
    }
    .hero-label.text-label { color: #64b4ff; }
    /* Voice info bubbles */
    .jarvis-bubble {
        background: linear-gradient(135deg, rgba(28,32,45,0.98) 0%, rgba(22,26,36,0.98) 100%);
        color: #e2e6ed;
        padding: 1rem 1.25rem;
        border-radius: 16px;
        margin: 0.5rem 0;
        border-left: 4px solid #ffc864;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .jarvis-bubble.upcoming { border-left-color: #64b4ff; }
    .jarvis-bubble.suggestion { border-left-color: #a78bfa; }
    .chat-panel {
        background: linear-gradient(160deg, rgba(18,22,32,0.94), rgba(15,18,27,0.97));
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 18px;
        padding: 0.8rem;
        min-height: 280px;
        max-height: 430px;
        overflow-y: auto;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .chat-row { display: flex; margin: 0.38rem 0; }
    .chat-row.user { justify-content: flex-end; }
    .chat-row.ai { justify-content: flex-start; }
    .chat-msg {
        max-width: 84%;
        padding: 0.62rem 0.8rem;
        border-radius: 14px;
        font-size: 0.9rem;
        line-height: 1.35;
        border: 1px solid rgba(255,255,255,0.08);
        word-wrap: break-word;
    }
    .chat-msg.user {
        background: linear-gradient(145deg, rgba(60,105,170,0.28), rgba(58,92,150,0.22));
        color: #eaf2ff;
        border-top-right-radius: 6px;
    }
    .chat-msg.ai {
        background: linear-gradient(145deg, rgba(36,42,58,0.86), rgba(28,34,48,0.9));
        color: #e7eaf0;
        border-top-left-radius: 6px;
    }
    .task-pane {
        background: linear-gradient(160deg, rgba(18,22,32,0.88), rgba(13,16,24,0.95));
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 0.9rem 0.95rem 0.7rem;
        margin-bottom: 0.9rem;
    }
    /* Task cards */
    .task-card-wrap {
        background: linear-gradient(145deg, rgba(24,28,38,0.9) 0%, rgba(18,22,30,0.95) 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 0.9rem 1rem;
        margin: 0.4rem 0;
        box-shadow: 0 2px 12px rgba(0,0,0,0.2);
        transition: border-color 0.2s, box-shadow 0.2s;
    }
    .task-card-wrap:hover { border-color: rgba(255,200,100,0.15); box-shadow: 0 4px 20px rgba(0,0,0,0.25); }
    .task-card-wrap.urgent { border-left: 4px solid #f59e0b; }
    .task-card-wrap .task-title { font-weight: 600; color: #f0f2f5; font-size: 0.98rem; }
    .task-card-wrap .task-meta { color: #7c8594; font-size: 0.82rem; margin-top: 0.2rem; }
    .task-actions { display: flex; gap: 0.25rem; flex-wrap: wrap; }
    /* Tabs */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        background: rgba(20,24,32,0.6);
        border-radius: 12px;
        padding: 4px;
        gap: 4px;
        border: 1px solid rgba(255,255,255,0.06);
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        background: transparent;
        color: #8b92a0;
        border-radius: 10px;
        font-weight: 500;
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        background: rgba(255,200,100,0.12);
        color: #ffc864;
    }
    /* Buttons */
    .stButton > button {
        border-radius: 12px;
        font-weight: 500;
        min-height: 2.55rem;
        border: 1px solid rgba(255,255,255,0.12);
        background: rgba(20,24,32,0.86);
        transition: transform 0.15s, box-shadow 0.15s;
    }
    .stButton > button:hover { transform: translateY(-1px); }
    /* Expanders */
    [data-testid="stExpander"] {
        background: rgba(20,24,32,0.5);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
    }
    /* Stats row */
    .stats-row {
        display: flex;
        gap: 1.5rem;
        margin: 1rem 0 1.25rem;
        flex-wrap: wrap;
    }
    .stat-pill {
        background: rgba(255,200,100,0.08);
        color: #ffc864;
        padding: 0.5rem 1rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid rgba(255,200,100,0.15);
    }
    /* Title area */
    .app-title { font-size: 1.85rem; font-weight: 700; color: #f2f4f8; letter-spacing: -0.03em; margin-bottom: 0.25rem; }
    .app-tagline { color: #7c8594; font-size: 0.95rem; }
    @media (max-width: 900px) {
        .stApp { padding: 0 0.35rem 1rem; }
        [data-testid="stAppViewContainer"] .main .block-container {
            padding-left: 0.55rem;
            padding-right: 0.55rem;
        }
        .app-shell {
            max-width: 100%;
            border-radius: 20px;
            padding: 0.8rem 0.8rem 1rem;
        }
        .hero-wrap {
            padding: 1rem 0.9rem;
            border-radius: 16px;
        }
        .task-card-wrap { padding: 0.72rem 0.8rem; }
        .app-title { font-size: 1.45rem; }
        .app-tagline { font-size: 0.88rem; }
    }
    /* Divider */
    hr { border-color: rgba(255,255,255,0.06); margin: 1.5rem 0; }
    /* Success / info */
    [data-testid="stSuccess"], [data-testid="stInfo"] {
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.06);
    }
    /* Section headings */
    .section-head { font-size: 1rem; font-weight: 600; color: #a0a8b8; margin-bottom: 0.75rem; }
    /* Footer */
    .footer-note { color: #5a6274; font-size: 0.8rem; margin-top: 2rem; text-align: center; }
    /* Unified composer: mic appears inside chat input */
    .st-key-unified_composer {
        position: relative;
        margin-top: 0.3rem;
    }
    .st-key-unified_composer .st-key-main_voice_input {
        position: absolute;
        left: 0.58rem;
        top: 50%;
        transform: translateY(-50%);
        z-index: 5;
        width: 2.35rem;
        max-width: 2.35rem;
        margin: 0 !important;
    }
    .st-key-unified_composer .st-key-main_voice_input [data-testid="stWidgetLabel"] {
        display: none !important;
    }
    .st-key-unified_composer .st-key-main_voice_input > div {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
        min-height: 0 !important;
    }
    .st-key-unified_composer .st-key-main_voice_input [data-testid="stAudioInput"],
    .st-key-unified_composer .st-key-main_voice_input [data-testid="stAudioInput"] > div,
    .st-key-unified_composer .st-key-main_voice_input [data-testid="stAudioInput"] > div > div {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
        min-height: 0 !important;
    }
    .st-key-unified_composer .st-key-main_voice_input button {
        min-height: 2.05rem;
        width: 2.05rem;
        border-radius: 999px;
        padding: 0;
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        color: #b2b9c8 !important;
    }
    .st-key-unified_composer .st-key-main_voice_input button:hover {
        background: rgba(255,255,255,0.08) !important;
    }
    .st-key-unified_composer .st-key-text_task_input [data-testid="stChatInput"] {
        padding-left: 2.7rem;
    }
    .st-key-unified_composer .st-key-text_task_input [data-testid="stChatInput"] textarea,
    .st-key-unified_composer .st-key-text_task_input [data-testid="stChatInput"] input {
        padding-left: 0.2rem;
    }
</style>
""", unsafe_allow_html=True)

# Init DB and session state
init_db()

if "conversation" not in st.session_state:
    st.session_state.conversation = []
if "last_transcript" not in st.session_state:
    st.session_state.last_transcript = ""
if "speech_language" not in st.session_state:
    st.session_state.speech_language = "en"
if "speech_rate" not in st.session_state:
    st.session_state.speech_rate = config.DEFAULT_SPEECH_RATE
if "user_id" not in st.session_state:
    st.session_state.user_id = "default"
if "sync_done_once" not in st.session_state:
    st.session_state.sync_done_once = False
if "voice_authenticated" not in st.session_state:
    st.session_state.voice_authenticated = True  # default open access
if "last_audio_signature" not in st.session_state:
    st.session_state.last_audio_signature = None
if "reward_flash" not in st.session_state:
    st.session_state.reward_flash = None
if "due_alerted_task_ids" not in st.session_state:
    st.session_state.due_alerted_task_ids = []
if "voice_security_enabled" not in st.session_state:
    st.session_state.voice_security_enabled = False
if "voice_pw" not in st.session_state:
    st.session_state.voice_pw = ""
if "voiceprint_template" not in st.session_state:
    st.session_state.voiceprint_template = None
if "voice_auth_threshold" not in st.session_state:
    st.session_state.voice_auth_threshold = 0.78
if "last_voiceprint" not in st.session_state:
    st.session_state.last_voiceprint = None
if "security_enroll_audio_bytes" not in st.session_state:
    st.session_state.security_enroll_audio_bytes = None
if "audio_capture_mode" not in st.session_state:
    st.session_state.audio_capture_mode = "task"


def _now_local():
    return datetime.now().astimezone()


def _is_sensitive_task_query(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\b(list|show|display|what(?:'s| is| are)|which)\b.*\b(task|tasks|todo|to do)\b", text, re.I))


def _normalize_unlock_phrase(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _extract_voiceprint(audio_bytes: bytes):
    try:
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
    except Exception:
        return None
    if data is None:
        return None
    if isinstance(data, np.ndarray) and data.ndim > 1:
        data = np.mean(data, axis=1)
    if not isinstance(data, np.ndarray) or data.size < 2048:
        return None
    peak = np.max(np.abs(data))
    if peak <= 1e-6:
        return None
    data = data / peak
    frame_size = 1024
    hop = 512
    window = np.hanning(frame_size).astype(np.float32)
    bands = 32
    vectors = []
    for start in range(0, len(data) - frame_size + 1, hop):
        frame = data[start:start + frame_size] * window
        spectrum = np.abs(np.fft.rfft(frame))
        if spectrum.size < bands:
            continue
        spectrum = np.log1p(spectrum[:512])
        split = np.array_split(spectrum, bands)
        band_means = np.array([float(np.mean(chunk)) for chunk in split], dtype=np.float32)
        vectors.append(band_means)
    if not vectors:
        return None
    mat = np.vstack(vectors)
    feature = np.concatenate([np.mean(mat, axis=0), np.std(mat, axis=0)]).astype(np.float32)
    norm = np.linalg.norm(feature)
    if norm <= 1e-8:
        return None
    return feature / norm


def _voiceprint_similarity(vec_a, vec_b) -> float:
    if vec_a is None or vec_b is None:
        return 0.0
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    if a.shape != b.shape:
        return 0.0
    return float(np.dot(a, b))

# Cloud sync: pull once on load when configured and not offline
if sync_supabase.is_configured() and not config.OFFLINE_MODE and not st.session_state.sync_done_once:
    try:
        sync_supabase.pull_and_merge(st.session_state.user_id)
        st.session_state.sync_done_once = True
    except Exception:
        pass

# Sidebar: accessibility & settings (SDG 10)
with st.sidebar:
    st.markdown("#### Settings & accessibility")
    if config.OFFLINE_MODE or not sync_supabase.is_configured():
        st.caption("Offline / local-only mode")
    st.session_state.speech_language = st.selectbox(
        "Speech recognition language",
        options=config.SUPPORTED_LANGUAGES,
        index=0,
        help="Multi-language support (code-switching supported by Whisper)",
    )
    st.session_state.speech_rate = st.slider(
        "Speech rate (for TTS / clarity)",
        0.5, 2.0, float(st.session_state.speech_rate), 0.1,
        help="Adjustable for cognitive accessibility",
    )
    st.markdown("---")
    st.markdown("#### 🔐 Voice access")
    with st.expander("Voice sign-in (optional)", expanded=False):
        st.caption("Say 'voiceprint' (or your passkey) with your enrolled voice to unlock tasks.")
        st.text_input("Voice passkey (optional)", key="voice_pw", placeholder="e.g. 123")
        st.session_state.voice_security_enabled = st.toggle(
            "Enable voice biometrics",
            value=bool(st.session_state.voice_security_enabled),
            help="Require unlock phrase plus voice match before showing task data.",
        )
        st.session_state.voice_auth_threshold = st.slider(
            "Voice match threshold",
            0.60,
            0.95,
            float(st.session_state.voice_auth_threshold),
            0.01,
            help="Higher is stricter. 0.78 is a good demo default.",
        )
        if st.button("Capture next recording for security", key="arm_security_capture_btn"):
            st.session_state.audio_capture_mode = "security_enroll"
            st.info("Security capture armed. Record once in the main Speak recorder.")
        capture_mode_text = "security" if st.session_state.audio_capture_mode == "security_enroll" else "task"
        st.caption(f"Recorder mode: {capture_mode_text}")
        if st.button("Enroll from security recording", key="enroll_from_security_audio_btn"):
            security_audio = st.session_state.get("security_enroll_audio_bytes")
            if not security_audio:
                st.warning("Record your security voice sample first.")
            else:
                enrolled = _extract_voiceprint(security_audio)
                if enrolled is None:
                    st.error("Could not extract a stable voiceprint from security recording.")
                else:
                    st.session_state.voiceprint_template = enrolled.tolist()
                    st.success("Voiceprint enrolled from security recording.")
                    if st.session_state.voice_security_enabled:
                        st.session_state.voice_authenticated = False
        if st.button("Reset voice security", key="reset_voice_security_btn"):
            st.session_state.voiceprint_template = None
            st.session_state.voice_authenticated = not st.session_state.voice_security_enabled
            st.info("Voice security profile cleared.")
        if st.session_state.voice_security_enabled:
            if not st.session_state.voiceprint_template:
                st.warning("Enroll a voice sample to enable verification.")
            status_text = "Unlocked" if st.session_state.voice_authenticated else "Locked"
            st.caption(f"Security status: {status_text}")
    st.markdown("---")
    st.markdown("#### Cloud sync")
    if sync_supabase.is_configured() and not config.OFFLINE_MODE:
        st.success("Supabase connected")
        if st.button("Sync now"):
            try:
                merged = sync_supabase.pull_and_merge(st.session_state.user_id)
                pushed = sync_supabase.push_all_local(st.session_state.user_id)
                st.success(f"Synced: {merged} pulled, {pushed} pushed.")
            except Exception as e:
                st.error(f"Sync failed: {e}")
            st.rerun()
    else:
        st.caption("Add SUPABASE_URL and SUPABASE_ANON_KEY to .env for cloud sync.")
    st.markdown("---")
    st.markdown("#### 🎁 Rewards")
    rewards = get_user_rewards_summary(st.session_state.user_id)
    st.caption(f"Level {rewards['level']} | {rewards['points']} pts")
    r1, r2, r3 = st.columns(3)
    r1.metric("Done", rewards["tasks_completed"])
    r2.metric("🔥 Streak", f"{rewards['streak_days']}d")
    r3.metric("Next", f"{rewards['needed_for_next']} pts")
    st.progress(min(1.0, max(0.0, rewards["level_progress"])))
    st.markdown("---")
    st.caption("VoqTask | Voice-first | To-do tasks | SDG 10 aligned")

if st.session_state.voice_security_enabled and (not st.session_state.voiceprint_template):
    st.session_state.voice_authenticated = False

# Main layout: Hero + Voice/Text, then Today / Tomorrow / Later
st.markdown("<p class='app-title'>🎙️ VoqTask</p><p class='app-tagline'>Voice-first to-do task manager. Speak naturally and add tasks quickly.</p>", unsafe_allow_html=True)
if st.session_state.reward_flash:
    st.success(st.session_state.reward_flash)
    st.session_state.reward_flash = None

left_col, right_col = st.columns([1.1, 0.9], gap="large")

audio = None
typed_message = ""

# Chat layout containers (top: chat, bottom: composer)
with left_col:
    chat_top_container = st.container()
    composer_bottom_container = st.container()
    now_bottom_container = st.container()

with composer_bottom_container:
    with st.container(key="unified_composer"):
        main_audio_label = "Record security sample" if st.session_state.audio_capture_mode == "security_enroll" else "Speak"
        audio = st.audio_input(main_audio_label, key="main_voice_input", label_visibility="collapsed")
        typed_message = (st.chat_input("Message VoqTask...", key="text_task_input") or "").strip()
# Process voice input
transcript = ""
audio_signature = None
current_voiceprint = None
if audio:
    audio_bytes = audio.getvalue()
    audio_signature = hashlib.sha256(audio_bytes).hexdigest()
    if st.session_state.audio_capture_mode == "security_enroll":
        st.session_state.security_enroll_audio_bytes = audio_bytes
        st.session_state.audio_capture_mode = "task"
        st.session_state.last_audio_signature = audio_signature
        st.success("Security sample captured. Click 'Enroll from security recording' in Voice sign-in.")
        audio = None
    else:
        # Streamlit reruns can retain the same audio payload; process each recording only once.
        if audio_signature != st.session_state.last_audio_signature:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                path = f.name
            try:
                transcript = transcribe_audio(audio_bytes, language=st.session_state.speech_language)
                st.session_state.last_transcript = transcript
                voiceprint = _extract_voiceprint(audio_bytes)
                st.session_state.last_voiceprint = voiceprint.tolist() if voiceprint is not None else None
                current_voiceprint = voiceprint
                st.session_state.last_audio_signature = audio_signature
                if transcript:
                    st.success(f"Heard: \"{transcript}\"")
            except Exception as e:
                st.error(f"Transcription failed: {e}. Try again or use text input.")
            finally:
                Path(path).unlink(missing_ok=True)
        elif st.session_state.last_voiceprint is not None:
            current_voiceprint = np.asarray(st.session_state.last_voiceprint, dtype=np.float32)

# Use transcript or text input
user_message = (transcript or typed_message or "").strip()
task_created = None

if user_message:
    st.session_state.conversation.append(ConversationTurn(role="user", content=user_message, timestamp=now_iso()))
    security_reply = None
    normalized_spoken = _normalize_unlock_phrase(user_message)
    passkey_norm = _normalize_unlock_phrase(st.session_state.get("voice_pw", ""))
    unlock_aliases = {"voiceprint", "voiceprints", "voiceprintunlock"}
    is_unlock_attempt = normalized_spoken in unlock_aliases
    if passkey_norm and normalized_spoken == passkey_norm:
        is_unlock_attempt = True

    if st.session_state.voice_security_enabled and is_unlock_attempt:
        template = st.session_state.voiceprint_template
        if not template:
            security_reply = "Voice security is enabled but no voiceprint is enrolled yet."
            st.session_state.voice_authenticated = False
        elif current_voiceprint is None:
            security_reply = "I heard your unlock phrase, but I need a fresh voice sample to verify."
            st.session_state.voice_authenticated = False
        else:
            similarity = _voiceprint_similarity(current_voiceprint, np.asarray(template, dtype=np.float32))
            threshold = float(st.session_state.voice_auth_threshold)
            if similarity >= threshold:
                st.session_state.voice_authenticated = True
                security_reply = f"✅ Voice verified. Access unlocked. Match score: {similarity:.2f}."
            else:
                st.session_state.voice_authenticated = False
                security_reply = f"❌ Voice does not match enrolled voice. Match score: {similarity:.2f}. Try again."
    elif (not st.session_state.voice_security_enabled) and is_unlock_attempt:
        st.session_state.voice_authenticated = True
        security_reply = "Voice sign-in successful."

    if (
        security_reply is None
        and st.session_state.voice_security_enabled
        and not st.session_state.voice_authenticated
    ):
        security_reply = "Voice security is locked. Say 'voiceprint' or your passkey with your enrolled voice to unlock tasks."

    if (
        security_reply is None
        and st.session_state.voice_security_enabled
        and _is_sensitive_task_query(user_message)
        and not st.session_state.voice_authenticated
    ):
        security_reply = "Voice security is locked. Say 'voiceprint' or your passkey with your enrolled voice to unlock tasks."

    if security_reply is not None:
        st.session_state.conversation.append(ConversationTurn(role="app", content=security_reply, timestamp=now_iso()))
    else:
        task = parse_task_from_text(user_message)
        if task:
            task = save_task(task)
            task_created = task
            if sync_supabase.is_configured() and not config.OFFLINE_MODE:
                try:
                    sync_supabase.push_task(task, st.session_state.user_id)
                except Exception:
                    pass
            st.balloons()
            st.success(f"Task added: **{task.title}**" + (f" - {task.due_date} {task.due_time or ''}" if task.due_date else ""))

        today_str = _now_local().strftime("%Y-%m-%d")
        tomorrow_str = (_now_local() + timedelta(days=1)).strftime("%Y-%m-%d")
        tasks_today = get_tasks(due_date=today_str, status=TaskStatus.PENDING)
        tasks_tomorrow = get_tasks(due_date=tomorrow_str, status=TaskStatus.PENDING)
        reply = reply_to_user(user_message, st.session_state.conversation, tasks_today, tasks_tomorrow, task_created=task_created)
        st.session_state.conversation.append(ConversationTurn(role="app", content=reply, timestamp=now_iso()))

# Show last reply or proactive suggestion
today_str = _now_local().strftime("%Y-%m-%d")
tomorrow_str = (_now_local() + timedelta(days=1)).strftime("%Y-%m-%d")
all_pending = get_tasks(status=TaskStatus.PENDING)
all_done = get_tasks(status=TaskStatus.DONE, limit=5000)
tasks_today = [t for t in all_pending if t.due_date == today_str]
tasks_tomorrow = [t for t in all_pending if t.due_date == tomorrow_str]
tasks_later = [t for t in all_pending if (t.due_date or "") > tomorrow_str or not t.due_date]


def _parse_iso_to_local_date(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().date()
    except Exception:
        return None

# Smart reminders: upcoming tasks in next 2 hours
def _tasks_due_soon(tasks: list, within_hours: float = 2):
    now = _now_local()
    end = now + timedelta(hours=within_hours)
    out = []
    today = now.strftime("%Y-%m-%d")
    for t in tasks:
        if not t.due_time:
            continue
        due_date = t.due_date or today
        if due_date != today:
            continue
        try:
            parts = t.due_time.split(":")
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            due_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if due_dt < now:
                continue
            if due_dt <= end:
                out.append((t, t.due_time))
        except Exception:
            continue
    return sorted(out, key=lambda x: x[1])


def _tasks_due_now(tasks: list, grace_minutes: int = 2):
    now = _now_local()
    window_start = now - timedelta(minutes=grace_minutes)
    out = []
    today = now.strftime("%Y-%m-%d")
    for t in tasks:
        if t.status != TaskStatus.PENDING or not t.due_time:
            continue
        due_date = t.due_date or today
        if due_date != today:
            continue
        try:
            parts = t.due_time.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            due_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if window_start <= due_dt <= now:
                out.append(t)
        except Exception:
            continue
    return out


def _minutes_until_today_time(time_str: str):
    if not time_str:
        return None
    try:
        now = _now_local()
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        due_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return int((due_dt - now).total_seconds() // 60)
    except Exception:
        return None


def _small_ring_html(label: str, value_text: str, percent: float, color: str) -> str:
    pct = max(0.0, min(100.0, percent))
    return f"""
    <div style="display:flex; flex-direction:column; align-items:center; gap:0.4rem;">
      <div style="
        width:96px; height:96px; border-radius:50%;
        background:conic-gradient({color} {pct:.2f}%, rgba(255,255,255,0.12) 0);
        display:grid; place-items:center;
      ">
        <div style="
          width:70px; height:70px; border-radius:50%;
          background:rgba(14,18,28,0.96); border:1px solid rgba(255,255,255,0.08);
          display:flex; align-items:center; justify-content:center; color:#eef1f6; font-weight:700; font-size:0.9rem;
        ">{value_text}</div>
      </div>
      <div style="color:#a8b0bf; font-size:0.8rem;">{label}</div>
    </div>
    """

upcoming = _tasks_due_soon(tasks_today)

due_now = _tasks_due_now(all_pending)
alerted_ids = set(st.session_state.due_alerted_task_ids)
pending_ids = {t.id for t in all_pending}
alerted_ids = {task_id for task_id in alerted_ids if task_id in pending_ids}
due_now_messages = []
for task in due_now:
    if task.id in alerted_ids:
        continue
    due_now_messages.append(f"⏰ Due now: {task.title}" + (f" ({task.due_time})" if task.due_time else ""))
    alerted_ids.add(task.id)
st.session_state.due_alerted_task_ids = list(alerted_ids)

suggestion = get_proactive_suggestion(all_pending)
today_local = _now_local().date()
done_today = sum(1 for task in all_done if _parse_iso_to_local_date(task.updated_at) == today_local)
today_goal = 5
today_percent = (done_today / today_goal * 100.0) if today_goal else 0.0
with chat_top_container:
    if upcoming:
        lines = " | ".join([f"{x[0].title} ({x[1]})" for x in upcoming])
        st.markdown(f"<div class='jarvis-bubble upcoming'><strong>🔔 Upcoming:</strong> {lines}</div>", unsafe_allow_html=True)
    for msg in due_now_messages:
        st.warning(msg)
        try:
            st.toast(msg)
        except Exception:
            pass
    if suggestion:
        st.markdown(f"<div class='jarvis-bubble suggestion'><strong>💡 Tip:</strong> {suggestion}</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-head'>🤖 Assistant chat</div>", unsafe_allow_html=True)
    chat_rows = []
    if not st.session_state.conversation:
        chat_rows.append("<div class='chat-row ai'><div class='chat-msg ai'>Try: list all tasks, show necessary tasks, or remind me to call mom at 7 pm.</div></div>")
    else:
        for turn in st.session_state.conversation[-14:]:
            role_class = "user" if turn.role == "user" else "ai"
            safe_text = html.escape(turn.content or "")
            chat_rows.append(f"<div class='chat-row {role_class}'><div class='chat-msg {role_class}'>{safe_text}</div></div>")
    st.markdown("<div class='chat-panel'>" + "".join(chat_rows) + "</div>", unsafe_allow_html=True)
    if st.session_state.conversation:
        last = st.session_state.conversation[-1]
        if last.role != "user" and st.button("🔊 Read aloud", key="tts_read_aloud"):
            try:
                import pyttsx3
                engine = pyttsx3.init()
                rate = engine.getProperty("rate")
                engine.setProperty("rate", int(rate * st.session_state.speech_rate))
                engine.say(last.content)
                engine.runAndWait()
            except Exception:
                st.caption("Install pyttsx3 for read-aloud: pip install pyttsx3")

with now_bottom_container:
    st.markdown("<div class='section-head'>Now</div>", unsafe_allow_html=True)
    now_col_left, now_col_right = st.columns([1.55, 1], gap="medium")
    with now_col_left:
        st.caption("Due next 2 hours")
        if upcoming:
            for task, due_time in upcoming[:3]:
                mins_left = _minutes_until_today_time(due_time)
                eta = f"in {mins_left}m" if mins_left is not None and mins_left >= 0 else due_time
                st.markdown(
                    f"<div class='jarvis-bubble upcoming' style='margin:0.35rem 0; padding:0.65rem 0.8rem;'>"
                    f"<strong>{html.escape(task.title)}</strong><br><span style='color:#9aa3b2; font-size:0.82rem;'>{due_time} | {eta}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No upcoming items in the next 2 hours.")
    with now_col_right:
        st.markdown(
            _small_ring_html("Today focus", f"{done_today}/{today_goal}", today_percent, "#4fd1c5"),
            unsafe_allow_html=True,
        )
        st.caption("Goal: 5 tasks/day")

    qa_col1, qa_col2, qa_col3 = st.columns(3, gap="small")
    if qa_col1.button("Add focus 25m", key="qa_add_focus", use_container_width=True):
        focus_task = Task(
            id=None,
            title="Focus session (25m)",
            due_date=today_str,
            due_time=None,
            priority=Priority.MEDIUM,
            status=TaskStatus.PENDING,
            created_at=now_iso(),
            updated_at=now_iso(),
            shared_with=[],
            notes="Quick action",
            source="quick_action",
        )
        focus_task = save_task(focus_task)
        if sync_supabase.is_configured() and not config.OFFLINE_MODE:
            try:
                sync_supabase.push_task(focus_task, st.session_state.user_id)
            except Exception:
                pass
        st.success("Added focus task for today.")
        st.rerun()

    if qa_col2.button("Snooze next +15m", key="qa_snooze_next", use_container_width=True):
        now_local = _now_local()
        candidates = []
        for task in all_pending:
            if not task.due_time:
                continue
            due_date = task.due_date or today_str
            if due_date != today_str:
                continue
            try:
                hh, mm = [int(x) for x in task.due_time.split(":")[:2]]
                due_dt = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if due_dt >= now_local:
                    candidates.append((due_dt, task))
            except Exception:
                continue
        if not candidates:
            st.info("No upcoming timed task to snooze.")
        else:
            due_dt, task = sorted(candidates, key=lambda x: x[0])[0]
            task.due_time = (due_dt + timedelta(minutes=15)).strftime("%H:%M")
            task.updated_at = now_iso()
            update_task(task)
            if sync_supabase.is_configured() and not config.OFFLINE_MODE:
                try:
                    sync_supabase.push_task(task, st.session_state.user_id)
                except Exception:
                    pass
            st.success(f"Snoozed: {task.title} to {task.due_time}.")
            st.rerun()

    if qa_col3.button("Done latest", key="qa_done_latest", use_container_width=True):
        if not all_pending:
            st.info("No pending task available.")
        else:
            latest = sorted(all_pending, key=lambda t: t.created_at or "", reverse=True)[0]
            changed = update_task_status(latest.id, TaskStatus.DONE)
            if changed:
                reward_result = reward_task_completion(latest.id, st.session_state.user_id)
                if reward_result.get("awarded"):
                    st.session_state.reward_flash = (
                        f"+{reward_result['points_awarded']} pts | "
                        f"Level {reward_result['level']} | "
                        f"{reward_result['streak_days']}-day streak"
                    )
                if sync_supabase.is_configured() and not config.OFFLINE_MODE:
                    latest_ref = get_task_by_id(latest.id)
                    if latest_ref:
                        try:
                            sync_supabase.push_task(latest_ref, st.session_state.user_id)
                        except Exception:
                            pass
                st.success(f"Completed: {latest.title}")
            else:
                st.info("Could not mark latest task done.")
            st.rerun()

with right_col:
    unlocked_for_tasks = (not st.session_state.voice_security_enabled) or st.session_state.voice_authenticated
    if not unlocked_for_tasks:
        st.info("Tasks and productivity are hidden. Say 'voiceprint' to unlock.")
    else:
        # Task overview: Today | Tomorrow | Later
        st.markdown("---")
        st.markdown("### 📋 Task overview")
        # Stats pills
        st.markdown(
            f"<div class='stats-row'>"
            f"<span class='stat-pill'>Today: {len(tasks_today)}</span>"
            f"<span class='stat-pill'>Tomorrow: {len(tasks_tomorrow)}</span>"
            f"<span class='stat-pill'>Later: {len(tasks_later)}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        
        # Productivity dashboard
        st.markdown("### 📈 Productivity dashboard")
        total_open = len(all_pending)
        total_done = len(all_done)
        total_tasks = total_open + total_done
        completion_rate = (total_done / total_tasks * 100.0) if total_tasks else 0.0
        today_local = _now_local().date()
        done_today = sum(1 for task in all_done if _parse_iso_to_local_date(task.updated_at) == today_local)
        done_this_week = 0
        daily_counts = {}
        for offset in range(6, -1, -1):
            day = today_local - timedelta(days=offset)
            key = day.strftime("%a")
            daily_counts[key] = 0
        for task in all_done:
            done_date = _parse_iso_to_local_date(task.updated_at)
            if done_date is None:
                continue
            age_days = (today_local - done_date).days
            if 0 <= age_days <= 6:
                key = done_date.strftime("%a")
                daily_counts[key] = daily_counts.get(key, 0) + 1
                done_this_week += 1
        avg_done_per_day = done_this_week / 7.0
        
        dash_col1, dash_col2, dash_col3, dash_col4 = st.columns(4)
        dash_col1.metric("Completed today", done_today)
        dash_col2.metric("Completion rate", f"{completion_rate:.1f}%")
        dash_col3.metric("Done this week", done_this_week)
        dash_col4.metric("Avg/day (7d)", f"{avg_done_per_day:.1f}")
        
        def _ring_card(label: str, value_text: str, percent: float, color: str) -> str:
            pct = max(0.0, min(100.0, percent))
            return f"""
            <div style="display:flex; flex-direction:column; align-items:center; gap:0.5rem; margin:0.5rem 0 0.75rem;">
              <div style="
                width:112px; height:112px; border-radius:50%;
                background:conic-gradient({color} {pct:.2f}%, rgba(255,255,255,0.10) 0);
                display:grid; place-items:center;
              ">
                <div style="
                  width:82px; height:82px; border-radius:50%;
                  background:rgba(14,18,28,0.96); border:1px solid rgba(255,255,255,0.08);
                  display:flex; align-items:center; justify-content:center; color:#eef1f6; font-weight:700; font-size:0.95rem;
                ">{value_text}</div>
              </div>
              <div style="color:#a8b0bf; font-size:0.82rem;">{label}</div>
            </div>
            """
        
        today_goal = 5
        week_goal = 25
        today_percent = (done_today / today_goal * 100.0) if today_goal else 0.0
        week_percent = (done_this_week / week_goal * 100.0) if week_goal else 0.0
        
        ring_c1, ring_c2, ring_c3 = st.columns(3)
        with ring_c1:
            st.markdown(_ring_card("Completion rate", f"{completion_rate:.0f}%", completion_rate, "#4fd1c5"), unsafe_allow_html=True)
        with ring_c2:
            st.markdown(_ring_card("Today progress", f"{done_today}/{today_goal}", today_percent, "#f6ad55"), unsafe_allow_html=True)
        with ring_c3:
            st.markdown(_ring_card("Weekly progress", f"{done_this_week}/{week_goal}", week_percent, "#63b3ed"), unsafe_allow_html=True)
        st.caption("Trend order: " + " | ".join(daily_counts.keys()))
        
        tab_today, tab_tomorrow, tab_later = st.tabs(["Today", "Tomorrow", "Later"])
        
        def render_task_list(tasks: list, key_prefix: str):
            priority_order = {
                Priority.URGENT: 0,
                Priority.HIGH: 1,
                Priority.MEDIUM: 2,
                Priority.LOW: 3,
            }
            sorted_tasks = sorted(
                tasks,
                key=lambda task: (
                    priority_order.get(task.priority, 99),
                    task.due_date or "9999-12-31",
                    task.due_time or "23:59",
                    task.created_at or "",
                ),
            )
            priority_counts = {}
            for task in sorted_tasks:
                priority_counts[task.priority] = priority_counts.get(task.priority, 0) + 1
        
            current_priority = None
            for i, t in enumerate(sorted_tasks):
                if t.priority != current_priority:
                    current_priority = t.priority
                    st.markdown(
                        f"<div class='section-head'>{current_priority.value.replace('_', ' ').title()} ({priority_counts.get(current_priority, 0)})</div>",
                        unsafe_allow_html=True,
                    )
                urg = " urgent" if t.priority == Priority.URGENT else ""
                meta = (f"{t.due_date} {t.due_time or ''}" if t.due_date else "No date")
                notes_preview = (f" | {t.notes[:28]}..." if t.notes and len(t.notes) > 28 else (f" | {t.notes}" if t.notes else ""))
                with st.container():
                    col_a, col_b = st.columns([4, 1])
                    with col_a:
                        st.markdown(
                            f"<div class='task-card-wrap{urg}'><div class='task-title'>{t.title}</div><div class='task-meta'>{meta}{notes_preview}</div></div>",
                            unsafe_allow_html=True,
                        )
                    with col_b:
                        if st.button("Done", key=f"{key_prefix}_done_{t.id}", help="Mark done"):
                            status_changed = update_task_status(t.id, TaskStatus.DONE)
                            if status_changed:
                                reward_result = reward_task_completion(t.id, st.session_state.user_id)
                                if reward_result.get("awarded"):
                                    st.session_state.reward_flash = (
                                        f"🎉 +{reward_result['points_awarded']} pts | "
                                        f"Level {reward_result['level']} | "
                                        f"🔥 {reward_result['streak_days']}-day streak"
                                    )
                                if sync_supabase.is_configured() and not config.OFFLINE_MODE:
                                    tt = get_task_by_id(t.id)
                                    if tt:
                                        tt.status = TaskStatus.DONE
                                        try:
                                            sync_supabase.push_task(tt, st.session_state.user_id)
                                        except Exception:
                                            pass
                            st.rerun()
                        if st.button("View", key=f"{key_prefix}_view_{t.id}", help="View details"):
                            st.session_state[f"viewing_{t.id}"] = not st.session_state.get(f"viewing_{t.id}", False)
                            st.rerun()
                        if st.button("Edit", key=f"{key_prefix}_edit_{t.id}", help="Edit"):
                            st.session_state[f"editing_{t.id}"] = True
                            st.rerun()
                        if st.button("Delete", key=f"{key_prefix}_del_{t.id}", help="Delete"):
                            delete_task(t.id)
                            if sync_supabase.is_configured() and not config.OFFLINE_MODE:
                                try:
                                    sync_supabase.delete_remote(t.id, st.session_state.user_id)
                                except Exception:
                                    pass
                            st.rerun()
        
                # Read: view details (expander)
                if st.session_state.get(f"viewing_{t.id}"):
                    with st.expander("Task details", expanded=True):
                        st.markdown(f"**Title:** {t.title}")
                        st.markdown(f"**Due:** {t.due_date or '-'} {t.due_time or ''}")
                        st.markdown(f"**Priority:** {t.priority.value} | **Status:** {t.status.value}")
                        if t.notes:
                            st.markdown(f"**Notes:** {t.notes}")
                        if t.shared_with:
                            st.markdown(f"**Shared with:** {', '.join(t.shared_with)}")
                        st.caption(f"Created {t.created_at} | Updated {t.updated_at}")
                        # Task sharing: copy to share
                        share_text = f"Task: {t.title}\nDue: {t.due_date or '-'} {t.due_time or ''}\nPriority: {t.priority.value}\n" + (f"Notes: {t.notes}\n" if t.notes else "") + (f"Shared with: {', '.join(t.shared_with)}" if t.shared_with else "")
                        st.code(share_text, language=None)
                        if st.button("Copy to share", key=f"copy_share_{t.id}"):
                            st.session_state[f"clipboard_{t.id}"] = share_text
                            st.info("Copy the text above (select and Ctrl+C) to share via email or chat.")
                        if st.button("Close", key=f"close_view_{t.id}"):
                            del st.session_state[f"viewing_{t.id}"]
                            st.rerun()
        
                # Update: edit form (expander when this task is being edited)
                if st.session_state.get(f"editing_{t.id}"):
                    with st.expander(f"Edit: {t.title[:40]}...", expanded=True):
                        with st.form(key=f"edit_form_{key_prefix}_{t.id}"):
                            new_title = st.text_input("Title", value=t.title, key=f"edit_title_{t.id}")
                            c1, c2 = st.columns(2)
                            with c1:
                                new_due_date = st.text_input("Due date (YYYY-MM-DD)", value=t.due_date or "", key=f"edit_date_{t.id}")
                            with c2:
                                new_due_time = st.text_input("Due time (HH:MM)", value=t.due_time or "", key=f"edit_time_{t.id}")
                            new_priority = st.selectbox(
                                "Priority",
                                options=[p.value for p in Priority],
                                index=[p.value for p in Priority].index(t.priority.value),
                                key=f"edit_priority_{t.id}",
                            )
                            new_notes = st.text_area("Notes", value=t.notes or "", key=f"edit_notes_{t.id}")
                            new_shared = st.text_input("Shared with (comma-separated)", value=", ".join(t.shared_with) if t.shared_with else "", key=f"edit_shared_{t.id}")
                            sub_col1, sub_col2, _ = st.columns(3)
                            with sub_col1:
                                submitted = st.form_submit_button("Save")
                            with sub_col2:
                                cancel = st.form_submit_button("Cancel")
                            if submitted:
                                t.title = new_title.strip() or t.title
                                t.due_date = new_due_date.strip() or None
                                t.due_time = new_due_time.strip() or None
                                t.priority = Priority(new_priority)
                                t.notes = new_notes.strip()
                                t.shared_with = [x.strip() for x in new_shared.split(",") if x.strip()]
                                update_task(t)
                                if sync_supabase.is_configured() and not config.OFFLINE_MODE:
                                    try:
                                        sync_supabase.push_task(t, st.session_state.user_id)
                                    except Exception:
                                        pass
                                if f"editing_{t.id}" in st.session_state:
                                    del st.session_state[f"editing_{t.id}"]
                                st.rerun()
                            if cancel:
                                if f"editing_{t.id}" in st.session_state:
                                    del st.session_state[f"editing_{t.id}"]
                                st.rerun()
        
        with tab_today:
            st.markdown("<div class='section-head'>Due today</div>", unsafe_allow_html=True)
            if not tasks_today:
                st.info("Nothing due today. Add a task by voice or text.")
            else:
                render_task_list(tasks_today, "today")
        
        with tab_tomorrow:
            st.markdown("<div class='section-head'>Due tomorrow</div>", unsafe_allow_html=True)
            if not tasks_tomorrow:
                st.info("Nothing due tomorrow.")
            else:
                render_task_list(tasks_tomorrow, "tomorrow")
        
        with tab_later:
            st.markdown("<div class='section-head'>Later / No date</div>", unsafe_allow_html=True)
            if not tasks_later:
                st.info("No tasks scheduled for later.")
            else:
                render_task_list(tasks_later, "later")
        
# Smart reminders & sharing
with st.expander("Smart reminders & Sharing", expanded=False):
    st.caption("Tasks with a due date/time appear under Today or Tomorrow. Open the app to see what's due. For push notifications, allow browser notifications or use a PWA.")


# Footer
st.markdown("---")
st.markdown("<p class='footer-note'>VoqTask | Open-source | No in-app purchases | SDG 10: Reduced Inequalities</p>", unsafe_allow_html=True)

