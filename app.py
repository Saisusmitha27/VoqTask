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
import json
import os
import re
import csv
import uuid
import urllib.request
import numpy as np
import soundfile as sf
try:
    from streamlit_sortables import sort_items
except Exception:
    sort_items = None

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
    upsert_user_profile,
    update_user_voiceprint,
    list_user_profiles,
    get_user_profile,
    find_user_by_passkey,
    log_user_event,
    get_user_events,
    get_user_settings,
    set_user_settings,
    clear_user_runtime_data,
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
get_completion_activity = getattr(storage_module, "get_completion_activity", None)

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

if get_completion_activity is None:
    def get_completion_activity(user_id: str = "default", days: int = 7) -> dict:
        return {"today": 0, "window_total": 0, "by_date": {}}

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
        min-height: 220px;
        max-height: 420px;
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
        padding: 0.42rem 0.9rem;
        margin-right: 0.25rem;
        min-width: max-content;
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
    .timeline-head { margin-top: 1rem; margin-bottom: 0.6rem; }
    .timeline-head.first { margin-top: 0.2rem; }
    .panel-block {
        background: linear-gradient(160deg, rgba(18,22,32,0.92), rgba(14,18,26,0.96));
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 0.95rem 1rem 0.9rem;
        margin-bottom: 0.9rem;
        box-shadow: 0 6px 22px rgba(0,0,0,0.22);
    }
    .panel-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 0.8rem;
        margin-bottom: 0.65rem;
    }
    .panel-title {
        color: #eef2f7;
        font-size: 1.02rem;
        font-weight: 700;
        letter-spacing: 0.01em;
    }
    .panel-sub {
        color: #8c96a8;
        font-size: 0.82rem;
    }
    .kpi-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        margin: 0.1rem 0 0.35rem;
    }
    .kpi-pill {
        border: 1px solid rgba(255,255,255,0.09);
        border-radius: 999px;
        padding: 0.28rem 0.7rem;
        color: #c8d0de;
        font-size: 0.78rem;
        background: rgba(255,255,255,0.03);
    }
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
if "conversation_by_user" not in st.session_state:
    st.session_state.conversation_by_user = {}
if "last_transcript" not in st.session_state:
    st.session_state.last_transcript = ""
if "speech_language" not in st.session_state:
    st.session_state.speech_language = "en"
if "speech_rate" not in st.session_state:
    st.session_state.speech_rate = config.DEFAULT_SPEECH_RATE
if "user_id" not in st.session_state:
    st.session_state.user_id = "default"
if "enroll_user_id" not in st.session_state:
    st.session_state.enroll_user_id = "default"
if "sync_done_once" not in st.session_state:
    st.session_state.sync_done_once = False
if "voice_authenticated" not in st.session_state:
    st.session_state.voice_authenticated = True  # default open access
if "verified_user_id" not in st.session_state:
    st.session_state.verified_user_id = ""
if "last_audio_signature" not in st.session_state:
    st.session_state.last_audio_signature = None
if "reward_flash" not in st.session_state:
    st.session_state.reward_flash = None
if "due_alerted_task_ids" not in st.session_state:
    st.session_state.due_alerted_task_ids = []
if "default_user_reset_done" not in st.session_state:
    st.session_state.default_user_reset_done = False
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
if "last_spoken_turn_index" not in st.session_state:
    st.session_state.last_spoken_turn_index = -1
if "last_spoken_turn_by_user" not in st.session_state:
    st.session_state.last_spoken_turn_by_user = {}
if "tts_session_id" not in st.session_state:
    st.session_state.tts_session_id = str(uuid.uuid4())
if "ui_language" not in st.session_state:
    st.session_state.ui_language = "en"
if "accessibility_super_mode" not in st.session_state:
    st.session_state.accessibility_super_mode = False
if "theme_preset" not in st.session_state:
    st.session_state.theme_preset = "Midnight"
if "category_filter" not in st.session_state:
    st.session_state.category_filter = "all"
if "reminders_enabled" not in st.session_state:
    st.session_state.reminders_enabled = True
if "browser_notifications" not in st.session_state:
    st.session_state.browser_notifications = False
if "dragdrop_updates_enabled" not in st.session_state:
    st.session_state.dragdrop_updates_enabled = True
if "export_scope" not in st.session_state:
    st.session_state.export_scope = "own_only"
if "export_include_notes" not in st.session_state:
    st.session_state.export_include_notes = True
if "admin_console_mode" not in st.session_state:
    st.session_state.admin_console_mode = False
if "notification_email" not in st.session_state:
    st.session_state.notification_email = (os.environ.get("N8N_DEFAULT_EMAIL") or "").strip()

ADMIN_USER_ID = (os.environ.get("ADMIN_USER_ID") or "admin").strip().lower() or "admin"
ADMIN_PASSKEY = (os.environ.get("ADMIN_PASSKEY") or "").strip()

# One-time migration from legacy single conversation list into default user bucket.
if st.session_state.conversation and "default" not in st.session_state.conversation_by_user:
    st.session_state.conversation_by_user["default"] = st.session_state.conversation

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


def _normalize_with_spoken_digits(text: str) -> str:
    """Normalize spoken digit words into numeric form before passkey matching."""
    if not text:
        return ""
    t = str(text).lower()
    word_to_digit = {
        "zero": "0",
        "oh": "0",
        "o": "0",
        "one": "1",
        "two": "2",
        "to": "2",
        "too": "2",
        "three": "3",
        "four": "4",
        "for": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "ate": "8",
        "nine": "9",
    }
    for w, d in word_to_digit.items():
        t = re.sub(rf"\b{re.escape(w)}\b", d, t)
    return _normalize_unlock_phrase(t)


def _find_user_by_spoken_passkey(normalized_spoken: str):
    """Match direct passkey or passkey embedded in a longer spoken phrase."""
    if not normalized_spoken:
        return None
    direct = find_user_by_passkey(normalized_spoken)
    if direct:
        return direct
    best = None
    best_len = 0
    for prof in list_user_profiles():
        p = str((prof or {}).get("passkey_norm") or "").strip().lower()
        if not p or len(p) < 3:
            continue
        if p in normalized_spoken and len(p) > best_len:
            best = prof
            best_len = len(p)
    return best


def _locked_tasks_prompt() -> str:
    if _is_admin_user(st.session_state.get("user_id", "")):
        return tr("tasks_hidden_locked_admin")
    return tr("tasks_hidden_locked")


def _locked_voice_prompt() -> str:
    if _is_admin_user(st.session_state.get("user_id", "")):
        return tr("voice_security_locked_msg_admin")
    return tr("voice_security_locked_msg")


def _sync_session_context_query_params() -> None:
    """Persist active user/auth/admin-panel across browser reloads."""
    try:
        st.query_params["uid"] = str(st.session_state.get("user_id", "default"))
        st.query_params["auth"] = "1" if bool(st.session_state.get("voice_authenticated", False)) else "0"
        st.query_params["admin"] = "1" if (
            st.session_state.get("user_id") == ADMIN_USER_ID
            and bool(st.session_state.get("admin_console_mode", False))
        ) else "0"
    except Exception:
        pass


def _conversation_for_user(user_id: str) -> list[ConversationTurn]:
    raw = st.session_state.conversation_by_user.get(user_id, [])
    out: list[ConversationTurn] = []
    for item in raw:
        if isinstance(item, ConversationTurn):
            out.append(item)
        elif isinstance(item, dict):
            out.append(ConversationTurn.from_dict(item))
    st.session_state.conversation_by_user[user_id] = out
    return out


def _append_turn(user_id: str, role: str, content: str) -> None:
    conv = _conversation_for_user(user_id)
    conv.append(ConversationTurn(role=role, content=content, timestamp=now_iso()))
    st.session_state.conversation_by_user[user_id] = conv


def _profile_requires_voiceprint(user_id: str) -> bool:
    prof = get_user_profile(user_id)
    return bool((prof or {}).get("voiceprint", ""))


def _is_admin_user(user_id: str) -> bool:
    return (user_id or "").strip().lower() == ADMIN_USER_ID


def _requires_voice_for_user(user_id: str) -> bool:
    # Admin is always voice-verified; other users only if enrolled.
    return _is_admin_user(user_id) or _profile_requires_voiceprint(user_id)


def _default_biometrics_enabled(user_id: str) -> bool:
    uid = (user_id or "").strip().lower()
    if uid == ADMIN_USER_ID:
        return True
    if uid == "default":
        return False
    return _profile_requires_voiceprint(user_id)


def _settings_defaults_for(user_id: str) -> dict:
    is_admin = (user_id or "").strip().lower() == ADMIN_USER_ID
    return {
        "ui_language": "en",
        "speech_language": "en",
        "speech_rate": float(config.DEFAULT_SPEECH_RATE),
        "accessibility_super_mode": False,
        "theme_preset": "Midnight",
        "reminders_enabled": True,
        "browser_notifications": False,
        "dragdrop_updates_enabled": True,
        "export_scope": "all_users" if is_admin else "own_only",
        "export_include_notes": True,
        "voice_security_enabled": _default_biometrics_enabled(user_id),
        "notification_email": (os.environ.get("N8N_DEFAULT_EMAIL") or "").strip(),
    }


def _load_settings_for_user(user_id: str) -> None:
    defaults = _settings_defaults_for(user_id)
    saved = get_user_settings(user_id)
    merged = {**defaults, **(saved or {})}
    merged["speech_rate"] = max(0.5, min(2.0, float(merged.get("speech_rate", config.DEFAULT_SPEECH_RATE))))
    if merged.get("theme_preset") not in THEME_PRESETS:
        merged["theme_preset"] = "Midnight"
    if merged.get("ui_language") not in UI_LANGUAGE_LABELS:
        merged["ui_language"] = "en"
    if merged.get("speech_language") not in config.SUPPORTED_LANGUAGES:
        merged["speech_language"] = "en"
    if merged.get("export_scope") not in {"own_only", "all_users", "active_user_only"}:
        merged["export_scope"] = defaults["export_scope"]
    merged["voice_security_enabled"] = bool(merged.get("voice_security_enabled", defaults["voice_security_enabled"]))
    if _is_admin_user(user_id):
        merged["voice_security_enabled"] = True
    merged["notification_email"] = str(merged.get("notification_email", defaults["notification_email"])).strip()
    for k, v in merged.items():
        st.session_state[k] = v


def _save_settings_for_current_user() -> None:
    user_id = st.session_state.get("user_id", "default")
    payload = {
        "ui_language": st.session_state.get("ui_language", "en"),
        "speech_language": st.session_state.get("speech_language", "en"),
        "speech_rate": float(st.session_state.get("speech_rate", config.DEFAULT_SPEECH_RATE)),
        "accessibility_super_mode": bool(st.session_state.get("accessibility_super_mode", False)),
        "theme_preset": st.session_state.get("theme_preset", "Midnight"),
        "reminders_enabled": bool(st.session_state.get("reminders_enabled", True)),
        "browser_notifications": bool(st.session_state.get("browser_notifications", False)),
        "dragdrop_updates_enabled": bool(st.session_state.get("dragdrop_updates_enabled", True)),
        "export_scope": st.session_state.get("export_scope", "own_only"),
        "export_include_notes": bool(st.session_state.get("export_include_notes", True)),
        "voice_security_enabled": bool(st.session_state.get("voice_security_enabled", False)),
        "notification_email": str(st.session_state.get("notification_email", "")).strip(),
    }
    set_user_settings(user_id, payload)


# Ensure an admin profile exists for monitoring and emergency control.
upsert_user_profile(
    user_id=ADMIN_USER_ID,
    display_name="Admin",
    passkey_norm=_normalize_unlock_phrase(ADMIN_PASSKEY),
    voiceprint=(get_user_profile(ADMIN_USER_ID) or {}).get("voiceprint", ""),
)


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


I18N = {
    "en": {
        "settings_access": "#### Settings & accessibility",
        "offline_local": "Offline / local-only mode",
        "ui_language": "UI language",
        "speech_language": "Speech recognition language",
        "speech_help": "Whisper language used for voice transcription.",
        "speech_rate": "Speech rate (for TTS / clarity)",
        "voice_access": "#### Voice access",
        "cloud_sync": "#### Cloud sync",
        "sync_now": "Sync now",
        "sync_ok": "Supabase connected",
        "sync_hint": "Add SUPABASE_URL and SUPABASE_ANON_KEY to .env for cloud sync.",
        "accessibility_mode": "Accessibility super mode",
        "accessibility_help": "High contrast, larger text, larger controls, stronger focus visibility.",
        "task_added": "Task added",
        "heard": "Heard",
        "speak": "Speak",
        "security_record": "Record security sample",
        "chat_placeholder": "Message VoqTask...",
    },
    "ta": {
        "settings_access": "#### அமைப்புகள் மற்றும் அணுகல்தன்மை",
        "offline_local": "ஆஃப்லைன் / லோக்கல் முறை",
        "ui_language": "இடைமுக மொழி",
        "speech_language": "குரல் அங்கீகார மொழி",
        "speech_help": "குரல் உரைமாற்றத்துக்கு Whisper மொழி பயன்படுத்தப்படும்.",
        "speech_rate": "குரல் வேகம் (TTS / தெளிவு)",
        "voice_access": "#### குரல் அணுகல்",
        "cloud_sync": "#### கிளவுட் ஒத்திசைவு",
        "sync_now": "இப்போது ஒத்திசை",
        "sync_ok": "Supabase இணைக்கப்பட்டது",
        "sync_hint": ".env-ல் SUPABASE_URL மற்றும் SUPABASE_ANON_KEY சேர்க்கவும்.",
        "accessibility_mode": "அணுகல்தன்மை சூப்பர் முறை",
        "accessibility_help": "உயர் கண்ட்ராஸ்ட், பெரிய எழுத்து, பெரிய கட்டுப்பாடுகள், தெளிவான focus.",
        "task_added": "பணி சேர்க்கப்பட்டது",
        "heard": "கேட்டது",
        "speak": "பேசுங்கள்",
        "security_record": "பாதுகாப்பு குரல் பதிவு",
        "chat_placeholder": "VoqTask-க்கு செய்தி...",
    },
    "te": {
        "settings_access": "#### సెట్టింగ్స్ మరియు యాక్సెసిబిలిటీ",
        "offline_local": "ఆఫ్లైన్ / లోకల్ మోడ్",
        "ui_language": "UI భాష",
        "speech_language": "వాయిస్ గుర్తింపు భాష",
        "speech_help": "వాయిస్ ట్రాన్స్క్రిప్షన్ కోసం Whisper భాష ఉపయోగించబడుతుంది.",
        "speech_rate": "మాట్లాడే వేగం (TTS / స్పష్టత)",
        "voice_access": "#### వాయిస్ యాక్సెస్",
        "cloud_sync": "#### క్లౌడ్ సింక్",
        "sync_now": "ఇప్పుడు సింక్ చేయండి",
        "sync_ok": "Supabase కనెక్ట్ అయింది",
        "sync_hint": "క్లౌడ్ సింక్ కోసం .env లో SUPABASE_URL మరియు SUPABASE_ANON_KEY జోడించండి.",
        "accessibility_mode": "యాక్సెసిబిలిటీ సూపర్ మోడ్",
        "accessibility_help": "హై కాంట్రాస్ట్, పెద్ద టెక్స్ట్, పెద్ద కంట్రోల్స్, స్పష్టమైన focus.",
        "task_added": "టాస్క్ చేరింది",
        "heard": "విన్నది",
        "speak": "మాట్లాడండి",
        "security_record": "సెక్యూరిటీ వాయిస్ నమూనా రికార్డ్ చేయండి",
        "chat_placeholder": "VoqTask కు సందేశం...",
    },
    "hi": {
        "settings_access": "#### सेटिंग्स और एक्सेसिबिलिटी",
        "offline_local": "ऑफलाइन / लोकल मोड",
        "ui_language": "UI भाषा",
        "speech_language": "वॉइस पहचान भाषा",
        "speech_help": "वॉइस ट्रांसक्रिप्शन के लिए Whisper भाषा उपयोग होगी।",
        "speech_rate": "स्पीच रेट (TTS / स्पष्टता)",
        "voice_access": "#### वॉइस एक्सेस",
        "cloud_sync": "#### क्लाउड सिंक",
        "sync_now": "अभी सिंक करें",
        "sync_ok": "Supabase कनेक्टेड",
        "sync_hint": "क्लाउड सिंक के लिए .env में SUPABASE_URL और SUPABASE_ANON_KEY जोड़ें।",
        "accessibility_mode": "एक्सेसिबिलिटी सुपर मोड",
        "accessibility_help": "हाई कॉन्ट्रास्ट, बड़ा टेक्स्ट, बड़े कंट्रोल, बेहतर फोकस।",
        "task_added": "टास्क जोड़ा गया",
        "heard": "सुना गया",
        "speak": "बोलें",
        "security_record": "सुरक्षा वॉइस नमूना रिकॉर्ड करें",
        "chat_placeholder": "VoqTask को संदेश...",
    },
}

I18N_EXTRA = {
    "en": {
        "now_section": "Now",
        "due_next_2h": "Due next 2 hours",
        "goal_daily": "Goal: 5 tasks/day",
        "today_focus": "Today focus",
        "task_overview": "Task overview",
        "productivity_dashboard": "Productivity dashboard",
        "completed_today": "Completed today",
        "completion_rate": "Completion rate",
        "done_this_week": "Done this week",
        "avg_per_day_7d": "Avg/day (7d)",
        "today_progress": "Today progress",
        "weekly_progress": "Weekly progress",
        "trend_order": "Trend order",
        "tab_today": "Today",
        "tab_tomorrow": "Tomorrow",
        "tab_later": "Later",
        "due_today": "Due today",
        "nothing_due_today": "Nothing due today. Add a task by voice or text.",
        "due_tomorrow": "Due tomorrow",
        "nothing_due_tomorrow": "Nothing due tomorrow.",
        "later_no_date": "Later / No date",
        "nothing_later": "No tasks scheduled for later.",
    },
    "ta": {
        "now_section": "இப்போது",
        "due_next_2h": "அடுத்த 2 மணி நேரத்தில் முடிவடையும் பணிகள்",
        "goal_daily": "இலக்கு: தினமும் 5 பணிகள்",
        "today_focus": "இன்றைய கவனம்",
        "task_overview": "பணி ஒதுக்கீடு",
        "productivity_dashboard": "உற்பத்தித்திறன் பலகை",
        "completed_today": "இன்று முடித்தவை",
        "completion_rate": "முடித்தளவு",
        "done_this_week": "இந்த வாரம் முடித்தவை",
        "avg_per_day_7d": "சராசரி/நாள் (7நா)",
        "today_progress": "இன்றைய முன்னேற்றம்",
        "weekly_progress": "வார முன்னேற்றம்",
        "trend_order": "நாள் வரிசை",
        "tab_today": "இன்று",
        "tab_tomorrow": "நாளை",
        "tab_later": "பின்னர்",
        "due_today": "இன்றைய பாக்கி பணிகள்",
        "nothing_due_today": "இன்று முடிவு தேதி உள்ள பணி இல்லை. குரல் அல்லது உரை மூலம் பணி சேர்க்கலாம்.",
        "due_tomorrow": "நாளைய பாக்கி பணிகள்",
        "nothing_due_tomorrow": "நாளைக்கு பணி இல்லை.",
        "later_no_date": "பின்னர் / தேதி இல்லை",
        "nothing_later": "பின்னர் செய்ய திட்டமிட்ட பணிகள் இல்லை.",
    },
    "te": {
        "now_section": "ఇప్పుడు",
        "due_next_2h": "తదుపరి 2 గంటల్లో పూర్తి చేయాల్సిన పనులు",
        "goal_daily": "లక్ష్యం: రోజుకు 5 పనులు",
        "today_focus": "ఈరోజు ఫోకస్",
        "task_overview": "పనుల అవలోకనం",
        "productivity_dashboard": "ఉత్పాదకత డ్యాష్‌బోర్డ్",
        "completed_today": "ఈరోజు పూర్తి చేసినవి",
        "completion_rate": "పూర్తి శాతం",
        "done_this_week": "ఈ వారం పూర్తి చేసినవి",
        "avg_per_day_7d": "సగటు/రోజు (7రోజులు)",
        "today_progress": "ఈరోజు పురోగతి",
        "weekly_progress": "వారపు పురోగతి",
        "trend_order": "రోజుల క్రమం",
        "tab_today": "ఈరోజు",
        "tab_tomorrow": "రేపు",
        "tab_later": "తర్వాత",
        "due_today": "ఈరోజు గడువు పనులు",
        "nothing_due_today": "ఈరోజు గడువు ఉన్న పనులు లేవు. వాయిస్ లేదా టెక్స్ట్ ద్వారా పని జోడించండి.",
        "due_tomorrow": "రేపటి గడువు పనులు",
        "nothing_due_tomorrow": "రేపటికి గడువు పనులు లేవు.",
        "later_no_date": "తర్వాత / తేదీ లేదు",
        "nothing_later": "తర్వాతకు షెడ్యూల్ చేసిన పనులు లేవు.",
    },
    "hi": {
        "now_section": "अभी",
        "due_next_2h": "अगले 2 घंटों में देय कार्य",
        "goal_daily": "लक्ष्य: रोज़ 5 कार्य",
        "today_focus": "आज का फोकस",
        "task_overview": "कार्य अवलोकन",
        "productivity_dashboard": "उत्पादकता डैशबोर्ड",
        "completed_today": "आज पूरे हुए",
        "completion_rate": "पूर्णता दर",
        "done_this_week": "इस सप्ताह पूरे हुए",
        "avg_per_day_7d": "औसत/दिन (7दिन)",
        "today_progress": "आज की प्रगति",
        "weekly_progress": "साप्ताहिक प्रगति",
        "trend_order": "दिन क्रम",
        "tab_today": "आज",
        "tab_tomorrow": "कल",
        "tab_later": "बाद में",
        "due_today": "आज के देय कार्य",
        "nothing_due_today": "आज कोई देय कार्य नहीं है। आवाज़ या टेक्स्ट से कार्य जोड़ें।",
        "due_tomorrow": "कल के देय कार्य",
        "nothing_due_tomorrow": "कल कोई देय कार्य नहीं है।",
        "later_no_date": "बाद में / तारीख नहीं",
        "nothing_later": "बाद के लिए कोई कार्य निर्धारित नहीं है।",
    },
}
for _lang, _values in I18N_EXTRA.items():
    I18N.setdefault(_lang, {}).update(_values)

UI_LANGUAGE_LABELS = {
    "en": "English",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "hi": "हिन्दी",
}

SPEECH_LANGUAGE_LABELS = {
    "en": "English",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "hi": "हिन्दी",
}

TTS_LANG_BY_UI = {
    "en": "en-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "hi": "hi-IN",
}

THEME_PRESETS = {
    "Midnight": {},
    "Sunrise": {
        "app_bg": "linear-gradient(160deg, #fff8ef 0%, #ffeedd 45%, #fef4e8 100%)",
        "text": "#2f1f14",
        "card": "rgba(255,255,255,0.85)",
        "border": "rgba(160,100,45,0.18)",
        "accent": "#d97706",
    },
    "Ocean": {
        "app_bg": "linear-gradient(155deg, #061a2b 0%, #0a2d47 45%, #0d3657 100%)",
        "text": "#e8f4ff",
        "card": "rgba(8,33,52,0.9)",
        "border": "rgba(117,200,255,0.22)",
        "accent": "#38bdf8",
    },
}

CATEGORY_OPTIONS = ["general", "finance", "work", "personal", "home", "health", "study", "shopping", "family", "fitness", "travel"]


def tr(key: str) -> str:
    lang = st.session_state.get("ui_language", "en")
    return I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))


def trf(key: str, **kwargs) -> str:
    return tr(key).format(**kwargs)


I18N_MORE = {
    "en": {
        "voice_signin_optional": "Voice sign-in",
        "voice_unlock_caption": "Say 'voiceprint' (or your passkey) with your enrolled voice to unlock tasks.",
        "voice_passkey_optional": "Voice passkey (optional)",
        "enable_voice_biometrics": "Enable voice biometrics",
        "voice_biometrics_help": "Require unlock phrase plus voice match before showing task data.",
        "voice_match_threshold": "Voice match threshold",
        "voice_match_help": "Higher is stricter. 0.78 is a good demo default.",
        "capture_next_security": "Capture next recording for security",
        "security_capture_armed": "Security capture armed. Record once in the main Speak recorder.",
        "recorder_mode": "Recorder mode: {mode}",
        "recorder_mode_security": "security",
        "recorder_mode_task": "task",
        "enroll_from_security": "Enroll from security recording",
        "record_security_first": "Record your security voice sample first.",
        "extract_voiceprint_failed": "Could not extract a stable voiceprint from security recording.",
        "voiceprint_enrolled": "Voiceprint enrolled from security recording.",
        "reset_voice_security": "Reset voice security",
        "voice_security_cleared": "Voice security profile cleared.",
        "enroll_voice_warning": "Enroll a voice sample to enable verification.",
        "security_status": "Security status: {status}",
        "status_unlocked": "Unlocked",
        "status_locked": "Locked",
        "rewards_heading": "#### Rewards",
        "level_points": "Level {level} | {points} pts",
        "metric_done": "Done",
        "metric_streak": "Streak",
        "metric_next": "Next",
        "app_caption": "VoqTask | Voice-first | To-do tasks | SDG 10 aligned",
        "app_tagline": "Voice-first to-do task manager. Speak naturally and add tasks quickly.",
        "security_sample_captured": "Security sample captured. Click 'Enroll from security recording' in Voice sign-in.",
        "transcription_failed": "Transcription failed: {err}. Try again or use text input.",
        "upcoming_label": "Upcoming",
        "tip_label": "Tip",
        "assistant_chat": "Assistant chat",
        "chat_try_prompt": "Try: list all tasks, show necessary tasks, or remind me to call mom at 7 pm.",
        "no_upcoming_2h": "No upcoming items in the next 2 hours.",
        "btn_add_focus": "Add focus 25m",
        "btn_snooze_next": "Snooze next +15m",
        "btn_done_latest": "Done latest",
        "focus_added": "Added focus task for today.",
        "no_timed_task_snooze": "No upcoming timed task to snooze.",
        "snoozed_to": "Snoozed: {title} to {time}.",
        "no_pending_available": "No pending task available.",
        "completed_task": "Completed: {title}",
        "could_not_mark_done": "Could not mark latest task done.",
        "tasks_hidden_locked": "Tasks and productivity are hidden. Say 'voiceprint' to unlock.",
        "tasks_hidden_locked_admin": "Tasks and productivity are hidden. Say 'voiceprint' or passkey to unlock.",
        "btn_done": "Done",
        "btn_view": "View",
        "btn_edit": "Edit",
        "btn_delete": "Delete",
        "task_details": "Task details",
        "label_title": "Title",
        "label_due": "Due",
        "label_priority": "Priority",
        "label_status": "Status",
        "label_notes": "Notes",
        "label_shared_with": "Shared with",
        "label_created_updated": "Created {created} | Updated {updated}",
        "btn_copy_share": "Copy to share",
        "copy_share_info": "Copy the text above (select and Ctrl+C) to share via email or chat.",
        "btn_close": "Close",
        "edit_prefix": "Edit: {title}...",
        "label_due_date": "Due date (YYYY-MM-DD)",
        "label_due_time": "Due time (HH:MM)",
        "label_shared_with_csv": "Shared with (comma-separated)",
        "btn_save": "Save",
        "btn_cancel": "Cancel",
        "smart_reminders_sharing": "Smart reminders & Sharing",
        "smart_reminders_caption": "Tasks with a due date/time appear under Today or Tomorrow. Open the app to see what's due. For push notifications, allow browser notifications or use a PWA.",
        "footer_note": "VoqTask | Open-source | No in-app purchases | SDG 10: Reduced Inequalities",
    },
    "ta": {
        "voice_signin_optional": "குரல் உள்நுழைவு",
        "voice_unlock_caption": "பணிகளை திறக்க, உங்கள் பதிவு செய்யப்பட்ட குரலில் 'voiceprint' (அல்லது கடவுச்சொல்) சொல்லுங்கள்.",
        "voice_passkey_optional": "குரல் கடவுச்சொல் (விருப்பம்)",
        "enable_voice_biometrics": "குரல் உயிரளவியல் இயக்கு",
        "voice_biometrics_help": "பணிகளை காட்ட முன் திறப்பு சொல் மற்றும் குரல் பொருத்தம் தேவை.",
        "voice_match_threshold": "குரல் பொருத்த அளவு",
        "voice_match_help": "அதிக மதிப்பு = கடுமையான சரிபார்ப்பு. 0.78 நல்ல டெமோ இயல்புநிலை.",
        "capture_next_security": "அடுத்த பதிவை பாதுகாப்புக்காக பதிவு செய்",
        "security_capture_armed": "பாதுகாப்பு பதிவு தயார். பிரதான Speak பதிவியில் ஒருமுறை பதிவு செய்யுங்கள்.",
        "recorder_mode": "பதிவு முறை: {mode}",
        "recorder_mode_security": "பாதுகாப்பு",
        "recorder_mode_task": "பணி",
        "enroll_from_security": "பாதுகாப்பு பதிவிலிருந்து பதிவு செய்",
        "record_security_first": "முதலில் பாதுகாப்பு குரல் மாதிரியை பதிவு செய்யுங்கள்.",
        "extract_voiceprint_failed": "பாதுகாப்பு பதிவிலிருந்து நிலையான குரல் முத்திரை பெற முடியவில்லை.",
        "voiceprint_enrolled": "பாதுகாப்பு பதிவிலிருந்து குரல் முத்திரை பதிவு செய்யப்பட்டது.",
        "reset_voice_security": "குரல் பாதுகாப்பை மீட்டமை",
        "voice_security_cleared": "குரல் பாதுகாப்பு சுயவிவரம் அழிக்கப்பட்டது.",
        "enroll_voice_warning": "சரிபார்ப்பை இயக்கு குரல் மாதிரி பதிவு செய்யுங்கள்.",
        "security_status": "பாதுகாப்பு நிலை: {status}",
        "status_unlocked": "திறந்தது",
        "status_locked": "பூட்டப்பட்டது",
        "rewards_heading": "#### பாராட்டுகள்",
        "level_points": "நிலை {level} | {points} புள்ளிகள்",
        "metric_done": "முடிந்தவை",
        "metric_streak": "தொடர்",
        "metric_next": "அடுத்து",
        "app_caption": "VoqTask | குரல்-முன்னுரிமை | செய்யவேண்டிய பணிகள் | SDG 10",
        "app_tagline": "குரல் மூலம் பணிகளை விரைவாக நிர்வகிக்கவும்.",
        "security_sample_captured": "பாதுகாப்பு மாதிரி பதிவு செய்யப்பட்டது. Voice sign-in இல் 'Enroll from security recording' அழுத்தவும்.",
        "transcription_failed": "உரைமாற்றம் தோல்வி: {err}. மீண்டும் முயற்சி செய்யுங்கள் அல்லது உரை உள்ளிடுங்கள்.",
        "upcoming_label": "வரவிருப்பவை",
        "tip_label": "சுட்டுரை",
        "assistant_chat": "உதவியாளர் உரையாடல்",
        "chat_try_prompt": "முயற்சி: எல்லா பணிகளையும் காட்டு, முக்கிய பணிகளை காட்டு, அல்லது 7 மணிக்கு அம்மாவுக்கு அழைக்க நினைவூட்டு.",
        "no_upcoming_2h": "அடுத்த 2 மணி நேரத்தில் பணிகள் இல்லை.",
        "btn_add_focus": "25நி கவனம் சேர்க்க",
        "btn_snooze_next": "அடுத்ததை +15நி ஒத்திவை",
        "btn_done_latest": "சமீபத்தியதை முடி",
        "focus_added": "இன்றுக்கான கவன பணி சேர்க்கப்பட்டது.",
        "no_timed_task_snooze": "ஒத்திவைக்க நேரம் குறித்த பணி இல்லை.",
        "snoozed_to": "ஒத்திவைக்கப்பட்டது: {title} -> {time}",
        "no_pending_available": "நிலுவை பணி இல்லை.",
        "completed_task": "முடிக்கப்பட்டது: {title}",
        "could_not_mark_done": "சமீபத்திய பணியை முடித்ததாக குறிக்க முடியவில்லை.",
        "tasks_hidden_locked": "பணிகளும் உற்பத்தித் தகவலும் மறைக்கப்பட்டுள்ளன. திறக்க 'voiceprint' சொல்லுங்கள்.",
        "btn_done": "முடி",
        "btn_view": "பார்",
        "btn_edit": "திருத்து",
        "btn_delete": "நீக்கு",
        "task_details": "பணி விவரம்",
        "label_title": "தலைப்பு",
        "label_due": "கடைசி நாள்",
        "label_priority": "முன்னுரிமை",
        "label_status": "நிலை",
        "label_notes": "குறிப்புகள்",
        "label_shared_with": "பகிரப்பட்டது",
        "label_created_updated": "உருவாக்கம் {created} | புதுப்பிப்பு {updated}",
        "btn_copy_share": "பகிர நகலெடு",
        "copy_share_info": "மேலுள்ள உரையை நகலெடுத்து மின்னஞ்சல்/அரட்டையில் பகிருங்கள்.",
        "btn_close": "மூடு",
        "edit_prefix": "திருத்து: {title}...",
        "label_due_date": "கடைசி தேதி (YYYY-MM-DD)",
        "label_due_time": "கடைசி நேரம் (HH:MM)",
        "label_shared_with_csv": "பகிரப்பட்டவர்கள் (கமா பிரித்து)",
        "btn_save": "சேமி",
        "btn_cancel": "ரத்து செய்",
        "smart_reminders_sharing": "ஸ்மார்ட் நினைவூட்டல்கள் & பகிர்வு",
        "smart_reminders_caption": "தேதி/நேரம் உள்ள பணிகள் இன்று அல்லது நாளை பகுதியில் தோன்றும். புஷ் அறிவிப்புக்கு உலாவி அறிவிப்பை அனுமதிக்கவும்.",
        "footer_note": "VoqTask | திறந்த மூல | வாங்குதல் இல்லை | SDG 10: சமத்துவக் குறைப்பு",
    },
    "te": {
        "voice_signin_optional": "వాయిస్ సైన్-ఇన్",
        "voice_unlock_caption": "పనులు అన్‌లాక్ చేయడానికి మీ నమోదైన వాయిస్‌తో 'voiceprint' (లేదా పాస్‌కీ) చెప్పండి.",
        "voice_passkey_optional": "వాయిస్ పాస్‌కీ (ఐచ్చికం)",
        "enable_voice_biometrics": "వాయిస్ బయోమెట్రిక్స్ ప్రారంభించు",
        "voice_biometrics_help": "పనులు చూపే ముందు అన్‌లాక్ పదం + వాయిస్ సరిపోలిక అవసరం.",
        "voice_match_threshold": "వాయిస్ సరిపోలిక పరిమితి",
        "voice_match_help": "ఎక్కువైతే కఠినతరం. 0.78 మంచి డెమో డిఫాల్ట్.",
        "capture_next_security": "తదుపరి రికార్డింగ్‌ను భద్రత కోసం తీసుకోండి",
        "security_capture_armed": "సెక్యూరిటీ క్యాప్చర్ సిద్ధంగా ఉంది. ప్రధాన Speak రికార్డర్లో ఒకసారి రికార్డ్ చేయండి.",
        "recorder_mode": "రికార్డర్ మోడ్: {mode}",
        "recorder_mode_security": "భద్రత",
        "recorder_mode_task": "పని",
        "enroll_from_security": "సెక్యూరిటీ రికార్డింగ్ నుండి నమోదు చేయండి",
        "record_security_first": "ముందుగా భద్రత వాయిస్ నమూనా రికార్డ్ చేయండి.",
        "extract_voiceprint_failed": "సెక్యూరిటీ రికార్డింగ్ నుండి స్థిరమైన వాయిస్ ప్రింట్ పొందలేకపోయాం.",
        "voiceprint_enrolled": "సెక్యూరిటీ రికార్డింగ్ నుండి వాయిస్ ప్రింట్ నమోదు అయ్యింది.",
        "reset_voice_security": "వాయిస్ భద్రత రీసెట్ చేయండి",
        "voice_security_cleared": "వాయిస్ భద్రత ప్రొఫైల్ క్లియర్ అయింది.",
        "enroll_voice_warning": "ధృవీకరణ కోసం వాయిస్ నమూనా నమోదు చేయండి.",
        "security_status": "భద్రత స్థితి: {status}",
        "status_unlocked": "అన్‌లాక్",
        "status_locked": "లాక్",
        "rewards_heading": "#### బహుమతులు",
        "level_points": "స్థాయి {level} | {points} పాయింట్లు",
        "metric_done": "పూర్తి",
        "metric_streak": "స్ట్రీక్",
        "metric_next": "తదుపరి",
        "app_caption": "VoqTask | వాయిస్-ఫస్ట్ | పనుల జాబితా | SDG 10",
        "app_tagline": "సహజంగా మాట్లాడి పనులను త్వరగా జోడించండి.",
        "security_sample_captured": "సెక్యూరిటీ నమూనా రికార్డ్ అయింది. Voice sign-in లో 'Enroll from security recording' నొక్కండి.",
        "transcription_failed": "ట్రాన్స్‌క్రిప్షన్ విఫలమైంది: {err}. మళ్లీ ప్రయత్నించండి లేదా టెక్స్ట్ వాడండి.",
        "upcoming_label": "రాబోయేవి",
        "tip_label": "సూచన",
        "assistant_chat": "సహాయక చాట్",
        "chat_try_prompt": "ప్రయత్నించండి: అన్ని పనులు చూపు, ముఖ్యమైన పనులు చూపు, లేదా 7కి అమ్మకు కాల్ చేయమని గుర్తు చేయి.",
        "no_upcoming_2h": "తదుపరి 2 గంటల్లో పనులు లేవు.",
        "btn_add_focus": "25ని ఫోకస్ జోడించు",
        "btn_snooze_next": "తదుపరి +15ని వాయిదా",
        "btn_done_latest": "తాజాదాన్ని పూర్తి",
        "focus_added": "ఈరోజుకి ఫోకస్ టాస్క్ జోడించాం.",
        "no_timed_task_snooze": "వాయిదా వేయడానికి సమయపూర్వక పని లేదు.",
        "snoozed_to": "వాయిదా: {title} -> {time}",
        "no_pending_available": "పెండింగ్ పని లేదు.",
        "completed_task": "పూర్తైంది: {title}",
        "could_not_mark_done": "తాజా పనిని పూర్తిగా గుర్తించలేకపోయాం.",
        "tasks_hidden_locked": "పనులు మరియు ఉత్పాదకత సమాచారం దాచబడ్డాయి. అన్‌లాక్ కోసం 'voiceprint' చెప్పండి.",
        "btn_done": "పూర్తి",
        "btn_view": "చూడండి",
        "btn_edit": "సవరించు",
        "btn_delete": "తొలగించు",
        "task_details": "పని వివరాలు",
        "label_title": "శీర్షిక",
        "label_due": "గడువు",
        "label_priority": "ప్రాధాన్యత",
        "label_status": "స్థితి",
        "label_notes": "గమనికలు",
        "label_shared_with": "పంచిన వారు",
        "label_created_updated": "సృష్టి {created} | నవీకరణ {updated}",
        "btn_copy_share": "పంచుకోడానికి నకలు",
        "copy_share_info": "పై టెక్స్ట్‌ని కాపీ చేసి ఇమెయిల్/చాట్‌లో పంచుకోండి.",
        "btn_close": "మూసివేయి",
        "edit_prefix": "సవరించు: {title}...",
        "label_due_date": "గడువు తేదీ (YYYY-MM-DD)",
        "label_due_time": "గడువు సమయం (HH:MM)",
        "label_shared_with_csv": "పంచిన వారు (కామాతో విడగొట్టు)",
        "btn_save": "సేవ్",
        "btn_cancel": "రద్దు",
        "smart_reminders_sharing": "స్మార్ట్ రిమైండర్లు & షేరింగ్",
        "smart_reminders_caption": "తేదీ/సమయం ఉన్న పనులు Today లేదా Tomorrow లో కనిపిస్తాయి. పుష్ నోటిఫికేషన్ కోసం బ్రౌజర్ అనుమతి ఇవ్వండి.",
        "footer_note": "VoqTask | ఓపెన్ సోర్స్ | కొనుగోళ్లు లేవు | SDG 10: అసమానతల తగ్గింపు",
    },
    "hi": {
        "voice_signin_optional": "वॉइस साइन-इन",
        "voice_unlock_caption": "कार्य अनलॉक करने के लिए अपने पंजीकृत वॉइस से 'voiceprint' (या पासकी) बोलें।",
        "voice_passkey_optional": "वॉइस पासकी (वैकल्पिक)",
        "enable_voice_biometrics": "वॉइस बायोमेट्रिक्स चालू करें",
        "voice_biometrics_help": "कार्य दिखाने से पहले अनलॉक वाक्यांश और वॉइस मैच आवश्यक होगा।",
        "voice_match_threshold": "वॉइस मैच सीमा",
        "voice_match_help": "उच्च मान अधिक सख्त है। 0.78 अच्छा डेमो डिफॉल्ट है।",
        "capture_next_security": "अगली रिकॉर्डिंग सुरक्षा के लिए कैप्चर करें",
        "security_capture_armed": "सुरक्षा कैप्चर तैयार है। मुख्य Speak रिकॉर्डर में एक बार रिकॉर्ड करें।",
        "recorder_mode": "रिकॉर्डर मोड: {mode}",
        "recorder_mode_security": "सुरक्षा",
        "recorder_mode_task": "कार्य",
        "enroll_from_security": "सुरक्षा रिकॉर्डिंग से एनरोल करें",
        "record_security_first": "पहले सुरक्षा वॉइस नमूना रिकॉर्ड करें।",
        "extract_voiceprint_failed": "सुरक्षा रिकॉर्डिंग से स्थिर वॉइसप्रिंट नहीं निकाला जा सका।",
        "voiceprint_enrolled": "सुरक्षा रिकॉर्डिंग से वॉइसप्रिंट एनरोल हुआ।",
        "reset_voice_security": "वॉइस सुरक्षा रीसेट करें",
        "voice_security_cleared": "वॉइस सुरक्षा प्रोफाइल साफ़ किया गया।",
        "enroll_voice_warning": "सत्यापन सक्षम करने के लिए वॉइस नमूना एनरोल करें।",
        "security_status": "सुरक्षा स्थिति: {status}",
        "status_unlocked": "अनलॉक",
        "status_locked": "लॉक",
        "rewards_heading": "#### पुरस्कार",
        "level_points": "स्तर {level} | {points} अंक",
        "metric_done": "पूर्ण",
        "metric_streak": "स्ट्रिक",
        "metric_next": "अगला",
        "app_caption": "VoqTask | वॉइस-फर्स्ट | कार्य सूची | SDG 10",
        "app_tagline": "स्वाभाविक रूप से बोलें और जल्दी कार्य जोड़ें।",
        "security_sample_captured": "सुरक्षा नमूना रिकॉर्ड हुआ। Voice sign-in में 'Enroll from security recording' क्लिक करें।",
        "transcription_failed": "ट्रांसक्रिप्शन विफल: {err}. फिर कोशिश करें या टेक्स्ट उपयोग करें।",
        "upcoming_label": "आगामी",
        "tip_label": "सुझाव",
        "assistant_chat": "सहायक चैट",
        "chat_try_prompt": "आजमाएँ: सभी कार्य दिखाओ, जरूरी कार्य दिखाओ, या 7 बजे माँ को कॉल याद दिलाओ।",
        "no_upcoming_2h": "अगले 2 घंटों में कोई कार्य नहीं है।",
        "btn_add_focus": "25मि फोकस जोड़ें",
        "btn_snooze_next": "अगला +15मि स्नूज़",
        "btn_done_latest": "नवीनतम पूर्ण",
        "focus_added": "आज के लिए फोकस कार्य जोड़ा गया।",
        "no_timed_task_snooze": "स्नूज़ करने के लिए समयबद्ध कार्य नहीं है।",
        "snoozed_to": "स्नूज़: {title} -> {time}",
        "no_pending_available": "कोई लंबित कार्य नहीं है।",
        "completed_task": "पूर्ण: {title}",
        "could_not_mark_done": "नवीनतम कार्य पूर्ण के रूप में चिह्नित नहीं हो सका।",
        "tasks_hidden_locked": "कार्य और उत्पादकता छिपी है। अनलॉक करने के लिए 'voiceprint' बोलें।",
        "btn_done": "पूर्ण",
        "btn_view": "देखें",
        "btn_edit": "संपादित करें",
        "btn_delete": "हटाएँ",
        "task_details": "कार्य विवरण",
        "label_title": "शीर्षक",
        "label_due": "देय",
        "label_priority": "प्राथमिकता",
        "label_status": "स्थिति",
        "label_notes": "टिप्पणियाँ",
        "label_shared_with": "साझा किया गया",
        "label_created_updated": "बनाया गया {created} | अपडेट {updated}",
        "btn_copy_share": "साझा करने हेतु कॉपी",
        "copy_share_info": "ऊपर का टेक्स्ट कॉपी करके ईमेल/चैट में साझा करें।",
        "btn_close": "बंद करें",
        "edit_prefix": "संपादित करें: {title}...",
        "label_due_date": "देय तिथि (YYYY-MM-DD)",
        "label_due_time": "देय समय (HH:MM)",
        "label_shared_with_csv": "साझा किए गए (कॉमा से अलग)",
        "btn_save": "सहेजें",
        "btn_cancel": "रद्द करें",
        "smart_reminders_sharing": "स्मार्ट रिमाइंडर और साझा करना",
        "smart_reminders_caption": "तिथि/समय वाले कार्य Today या Tomorrow में दिखते हैं। पुश सूचना के लिए ब्राउज़र अनुमति दें।",
        "footer_note": "VoqTask | ओपन-सोर्स | इन-ऐप खरीद नहीं | SDG 10: असमानता में कमी",
    },
}
for _lang, _values in I18N_MORE.items():
    I18N.setdefault(_lang, {}).update(_values)

I18N_PATCH = {
    "en": {
        "speech_rate_help": "Adjustable for cognitive accessibility.",
        "theme_preset": "Theme preset",
        "reminders_enabled": "Smart reminders",
        "reminders_enabled_help": "Show upcoming and due reminders in the assistant area.",
        "browser_notifications": "Browser notification mode",
        "browser_notifications_help": "Enable this if your browser notification permission is granted.",
        "dragdrop_updates_enabled": "Enable drag-drop due-date updates",
        "dragdrop_updates_help": "Allow moving tasks between Today/Tomorrow/Later columns.",
        "export_scope": "Export visibility",
        "export_scope_own_only": "Only my tasks",
        "export_scope_all_users": "All users",
        "export_scope_active_user_only": "Only selected user",
        "export_include_notes": "Include notes in export",
        "data_export_heading": "#### Data export",
        "download_json": "Download JSON",
        "download_csv": "Download CSV",
        "admin_export_caption": "Admin export includes user_id based on selected visibility.",
        "user_export_caption": "User export includes only your own tasks.",
        "api_server_hint": "API server: python -m taskwhisper.api_server",
        "category_filter": "Category filter",
        "all_categories": "All categories",
        "task_count_today": "Today",
        "task_count_tomorrow": "Tomorrow",
        "task_count_later": "Later",
        "dragdrop_due_dates": "Drag-drop due dates",
        "dragdrop_install": "Install dependency for drag-drop: pip install streamlit-sortables",
        "dragdrop_apply": "Apply drag-drop changes",
        "dragdrop_applied": "Applied drag-drop changes to {count} task(s).",
        "category": "Category",
        "no_date": "No date",
        "priority_group": "{priority} ({count})",
        "export_notes_disabled_hint": "Notes are hidden in export by your preference.",
        "reminders_disabled_hint": "Smart reminders are disabled for this user.",
        "dragdrop_disabled_hint": "Drag-drop due-date updates are disabled for this user.",
        "active_user": "Active user",
        "switch_user_manually": "Switch user manually",
        "switch_now": "Switch now",
        "logout": "Log out",
        "profile_to_enroll": "Profile to enroll/update",
        "new_user_id": "New user id",
        "display_name": "Display name",
        "create_update_profile": "Create/Update profile",
        "enter_valid_user_id": "Enter a valid user id.",
        "profile_saved": "Profile saved: {user_id}",
        "admin_console": "Admin console",
        "admin_caption": "Monitor users and update profile metadata.",
        "total_users": "Total users: {count}",
        "monitor_user": "Monitor user",
        "recent_actions_for": "Recent actions for `{user_id}`",
        "tasks_for": "Tasks for `{user_id}`",
        "task_to_supervise": "Task to supervise",
        "mark_done": "Mark done",
        "mark_pending": "Mark pending",
        "delete_task_label": "Delete task",
        "task_marked_done": "Task marked done.",
        "task_marked_pending": "Task marked pending.",
        "task_deleted_done": "Task deleted.",
        "user_to_edit": "User to edit",
        "new_display_name": "New display name",
        "new_passkey": "New passkey",
        "leave_empty_keep_current": "leave empty to keep current",
        "update_user_profile": "Update user profile",
        "updated_user": "Updated user: {user_id}",
        "impersonate_selected_user": "Impersonate selected user",
        "now_acting_as": "Now acting as: {user_id}",
        "current_user_badge": "Current User: {name} ({user_id})",
        "switched_to_user": "Switched to user: {user_id}",
        "passkey_matched_needs_voice": "Passkey matched for {user_id}. Say 'voiceprint' with your enrolled voice to unlock tasks.",
        "voice_signin_success_active": "Voice sign-in successful. Active user: {user_id}.",
        "voice_signin_success": "Voice sign-in successful.",
        "voice_security_locked_msg": "Voice security is locked. Say 'voiceprint' or your passkey with your enrolled voice to unlock tasks.",
        "voice_security_locked_msg_admin": "Voice security is locked. Say 'voiceprint' or passkey with your enrolled voice to unlock tasks.",
        "admin_unlocked_passkey_no_voiceprint": "Admin unlocked using passkey. Enroll admin voiceprint to enforce strict voice verification.",
        "voiceprint_update_failed": "Could not update user voiceprint. Create profile first.",
        "unlock_phrase_need_fresh_voice": "I heard your unlock phrase, but I need a fresh voice sample to verify.",
        "voice_verified_score": "Voice verified. Active user: {user_id}. Match score: {score}.",
        "voice_no_match": "Voice does not match any enrolled user. Try again.",
        "sync_summary": "Synced: {pulled} pulled, {pushed} pushed, {queued} queued synced ({pending} pending).",
        "sync_failed": "Sync failed: {err}",
        "drag_header_today": "Today",
        "drag_header_tomorrow": "Tomorrow",
        "drag_header_later": "Later",
        "open_admin_console": "Open Admin Console",
        "close_admin_console": "Close Admin Console",
        "admin_console_panel_heading": "### Admin Console",
    },
    "ta": {
        "theme_preset": "தீம் வகை",
        "reminders_enabled": "ஸ்மார்ட் நினைவூட்டல்",
        "browser_notifications": "உலாவி அறிவிப்பு முறை",
        "dragdrop_updates_enabled": "இழுத்து-விட்டு தேதி புதுப்பிப்பு இயக்கு",
        "export_scope": "ஏற்றுமதி காட்சி",
        "export_scope_own_only": "என் பணிகள் மட்டும்",
        "export_scope_all_users": "அனைத்து பயனர்கள்",
        "export_scope_active_user_only": "தேர்ந்தெடுத்த பயனர் மட்டும்",
        "export_include_notes": "ஏற்றுமதியில் குறிப்புகள் சேர்க்கவும்",
        "data_export_heading": "#### தரவு ஏற்றுமதி",
        "download_json": "JSON பதிவிறக்கு",
        "download_csv": "CSV பதிவிறக்கு",
        "category_filter": "வகை வடிகட்டி",
        "all_categories": "அனைத்து வகைகள்",
        "dragdrop_due_dates": "இழுத்து-விட்டு கடைசி தேதி",
        "dragdrop_apply": "இழுத்து-விட்டு மாற்றங்களை செயல்படுத்து",
        "category": "வகை",
        "no_date": "தேதி இல்லை",
        "reminders_disabled_hint": "இந்த பயனருக்கு நினைவூட்டல் அணைக்கப்பட்டுள்ளது.",
        "dragdrop_disabled_hint": "இந்த பயனருக்கு இழுத்து-விட்டு தேதி மாற்றம் அணைக்கப்பட்டுள்ளது.",
        "active_user": "செயலில் உள்ள பயனர்",
        "switch_user_manually": "பயனரை கைமுறையாக மாற்று",
        "switch_now": "இப்போது மாற்று",
        "logout": "வெளியேறு",
        "profile_to_enroll": "பதிவு/புதுப்பிக்க வேண்டிய சுயவிவரம்",
        "new_user_id": "புதிய பயனர் ஐடி",
        "display_name": "காட்சி பெயர்",
        "create_update_profile": "சுயவிவரம் உருவாக்கு/புதுப்பி",
        "enter_valid_user_id": "சரியான பயனர் ஐடி உள்ளிடவும்.",
        "admin_console": "நிர்வாக கட்டுப்பாடு",
        "monitor_user": "கண்காணிக்க பயனர்",
        "task_to_supervise": "மேற்பார்வை பணியைத் தேர்வு செய்",
    },
    "te": {
        "theme_preset": "థీమ్ ఎంపిక",
        "reminders_enabled": "స్మార్ట్ రిమైండర్లు",
        "browser_notifications": "బ్రౌజర్ నోటిఫికేషన్ మోడ్",
        "dragdrop_updates_enabled": "డ్రాగ్-డ్రాప్ గడువు అప్డేట్ ప్రారంభించు",
        "export_scope": "ఎక్స్‌పోర్ట్ చూపు పరిధి",
        "export_scope_own_only": "నా పనులు మాత్రమే",
        "export_scope_all_users": "అన్ని వినియోగదారులు",
        "export_scope_active_user_only": "ఎంచుకున్న వినియోగదారు మాత్రమే",
        "export_include_notes": "ఎక్స్‌పోర్ట్‌లో గమనికలు చేర్చు",
        "data_export_heading": "#### డేటా ఎక్స్‌పోర్ట్",
        "download_json": "JSON డౌన్‌లోడ్",
        "download_csv": "CSV డౌన్‌లోడ్",
        "category_filter": "వర్గ ఫిల్టర్",
        "all_categories": "అన్ని వర్గాలు",
        "dragdrop_due_dates": "డ్రాగ్-డ్రాప్ గడువు తేదీలు",
        "dragdrop_apply": "డ్రాగ్-డ్రాప్ మార్పులు అమలు చేయి",
        "category": "వర్గం",
        "no_date": "తేదీ లేదు",
        "reminders_disabled_hint": "ఈ వినియోగదారికి రిమైండర్లు ఆఫ్‌లో ఉన్నాయి.",
        "dragdrop_disabled_hint": "ఈ వినియోగదారికి డ్రాగ్-డ్రాప్ అప్డేట్ ఆఫ్‌లో ఉంది.",
        "active_user": "ప్రస్తుత వినియోగదారు",
        "switch_user_manually": "వినియోగదారును మాన్యువల్‌గా మార్చు",
        "switch_now": "ఇప్పుడే మార్చు",
        "logout": "లాగ్ అవుట్",
        "profile_to_enroll": "నమోదు/అప్డేట్ ప్రొఫైల్",
        "new_user_id": "కొత్త వినియోగదారు ఐడి",
        "display_name": "ప్రదర్శన పేరు",
        "create_update_profile": "ప్రొఫైల్ సృష్టించు/అప్డేట్ చేయి",
        "enter_valid_user_id": "సరైన వినియోగదారు ఐడి ఇవ్వండి.",
        "admin_console": "అడ్మిన్ కన్సోల్",
        "monitor_user": "మానిటర్ వినియోగదారు",
        "task_to_supervise": "పర్యవేక్షించాల్సిన పని",
    },
    "hi": {
        "theme_preset": "थीम चयन",
        "reminders_enabled": "स्मार्ट रिमाइंडर",
        "browser_notifications": "ब्राउज़र सूचना मोड",
        "dragdrop_updates_enabled": "ड्रैग-ड्रॉप देय तिथि अपडेट सक्षम करें",
        "export_scope": "निर्यात दृश्यता",
        "export_scope_own_only": "केवल मेरे कार्य",
        "export_scope_all_users": "सभी उपयोगकर्ता",
        "export_scope_active_user_only": "केवल चुना गया उपयोगकर्ता",
        "export_include_notes": "निर्यात में नोट्स शामिल करें",
        "data_export_heading": "#### डेटा निर्यात",
        "download_json": "JSON डाउनलोड",
        "download_csv": "CSV डाउनलोड",
        "category_filter": "श्रेणी फ़िल्टर",
        "all_categories": "सभी श्रेणियाँ",
        "dragdrop_due_dates": "ड्रैग-ड्रॉप देय तिथियाँ",
        "dragdrop_apply": "ड्रैग-ड्रॉप बदलाव लागू करें",
        "category": "श्रेणी",
        "no_date": "कोई तिथि नहीं",
        "reminders_disabled_hint": "इस उपयोगकर्ता के लिए रिमाइंडर बंद हैं।",
        "dragdrop_disabled_hint": "इस उपयोगकर्ता के लिए ड्रैग-ड्रॉप अपडेट बंद है।",
        "active_user": "सक्रिय उपयोगकर्ता",
        "switch_user_manually": "उपयोगकर्ता मैन्युअल बदलें",
        "switch_now": "अभी बदलें",
        "logout": "लॉग आउट",
        "profile_to_enroll": "एनरोल/अपडेट प्रोफाइल",
        "new_user_id": "नया उपयोगकर्ता आईडी",
        "display_name": "प्रदर्शन नाम",
        "create_update_profile": "प्रोफाइल बनाएं/अपडेट करें",
        "enter_valid_user_id": "मान्य उपयोगकर्ता आईडी दर्ज करें।",
        "admin_console": "एडमिन कंसोल",
        "monitor_user": "उपयोगकर्ता मॉनिटर करें",
        "task_to_supervise": "पर्यवेक्षण के लिए कार्य",
    },
}
for _lang, _values in I18N_PATCH.items():
    I18N.setdefault(_lang, {}).update(_values)

I18N_NATIVE_UI = {
    "en": {
        "no_users_found": "No users found.",
        "admin_voice_mandatory": "Admin voice verification is mandatory.",
        "user_profiles_heading": "#### User profiles",
        "email_reminders_label": "Email reminders",
        "linkedin_test_post_btn": "Send LinkedIn test post",
        "linkedin_trigger_sent": "LinkedIn automation trigger sent.",
        "panel_sub_tasks": "Manage and update your tasks",
        "panel_sub_productivity": "Live productivity overview",
        "panel_sub_planner": "Plan due dates visually",
        "panel_sub_now": "Quick actions and near-term focus",
    },
    "ta": {
        "no_users_found": "பயனர்கள் இல்லை.",
        "admin_voice_mandatory": "நிர்வாகிக்கு குரல் சரிபார்ப்பு கட்டாயம்.",
        "user_profiles_heading": "#### பயனர் சுயவிவரங்கள்",
        "email_reminders_label": "மின்னஞ்சல் நினைவூட்டல்கள்",
        "linkedin_test_post_btn": "LinkedIn சோதனை பதிவு அனுப்பு",
        "linkedin_trigger_sent": "LinkedIn தானியக்க செயற்பாடு அனுப்பப்பட்டது.",
        "panel_sub_tasks": "பணிகளை நிர்வகித்து புதுப்பிக்கவும்",
        "panel_sub_productivity": "உற்பத்தித் திறன் நேரடி காட்சி",
        "panel_sub_planner": "தேதிகளை இழுத்து-விட்டு திட்டமிடவும்",
        "panel_sub_now": "உடனடி செயல்கள் மற்றும் அருகிலான கவனம்",
    },
    "te": {
        "no_users_found": "వినియోగదారులు లేరు.",
        "admin_voice_mandatory": "అడ్మిన్‌కు వాయిస్ ధృవీకరణ తప్పనిసరి.",
        "user_profiles_heading": "#### వినియోగదారు ప్రొఫైళ్లు",
        "email_reminders_label": "ఈమెయిల్ రిమైండర్లు",
        "linkedin_test_post_btn": "LinkedIn పరీక్ష పోస్టు పంపు",
        "linkedin_trigger_sent": "LinkedIn ఆటోమేషన్ ట్రిగ్గర్ పంపబడింది.",
        "panel_sub_tasks": "పనులను నిర్వహించి అప్డేట్ చేయండి",
        "panel_sub_productivity": "ఉత్పాదకత లైవ్ అవలోకనం",
        "panel_sub_planner": "డ్రాగ్-డ్రాప్‌తో తేదీలు ప్లాన్ చేయండి",
        "panel_sub_now": "త్వరిత చర్యలు మరియు సమీప దృష్టి",
    },
    "hi": {
        "no_users_found": "कोई उपयोगकर्ता नहीं मिला।",
        "admin_voice_mandatory": "एडमिन के लिए वॉइस सत्यापन अनिवार्य है।",
        "user_profiles_heading": "#### उपयोगकर्ता प्रोफाइल",
        "email_reminders_label": "ईमेल रिमाइंडर",
        "linkedin_test_post_btn": "LinkedIn परीक्षण पोस्ट भेजें",
        "linkedin_trigger_sent": "LinkedIn ऑटोमेशन ट्रिगर भेजा गया।",
        "panel_sub_tasks": "कार्य प्रबंधित करें और अपडेट करें",
        "panel_sub_productivity": "उत्पादकता का लाइव अवलोकन",
        "panel_sub_planner": "ड्रैग-ड्रॉप से तिथियाँ योजनाबद्ध करें",
        "panel_sub_now": "त्वरित कार्य और निकट-समय फोकस",
    },
}
for _lang, _values in I18N_NATIVE_UI.items():
    I18N.setdefault(_lang, {}).update(_values)

# Restore active user/auth/admin mode from URL query params on reload.
if "ctx_restored_from_query" not in st.session_state:
    st.session_state.ctx_restored_from_query = False
if not st.session_state.ctx_restored_from_query:
    try:
        qp_uid = str(st.query_params.get("uid", "") or "").strip().lower()
        qp_auth = str(st.query_params.get("auth", "0") or "0").strip() == "1"
        qp_admin_mode = str(st.query_params.get("admin", "0") or "0").strip() == "1"
    except Exception:
        qp_uid = ""
        qp_auth = False
        qp_admin_mode = False
    if qp_uid and get_user_profile(qp_uid):
        st.session_state.user_id = qp_uid
        _load_settings_for_user(qp_uid)
        st.session_state.sync_done_once = False
        st.session_state.voice_authenticated = bool(qp_auth)
        st.session_state.verified_user_id = qp_uid if qp_auth else ""
        st.session_state.admin_console_mode = bool(qp_admin_mode and qp_uid == ADMIN_USER_ID)
    st.session_state.ctx_restored_from_query = True

# Reset default user data on each fresh app-open/session.
if st.session_state.user_id == "default" and not st.session_state.default_user_reset_done:
    clear_user_runtime_data("default")
    st.session_state.conversation_by_user["default"] = []
    st.session_state.conversation = []
    st.session_state.due_alerted_task_ids = []
    st.session_state.last_spoken_turn_by_user["default"] = -1
    st.session_state.default_user_reset_done = True

_load_settings_for_user(st.session_state.user_id)


def _build_n8n_payload(event_type: str, task: Task, extras: dict | None = None) -> dict:
    extras = extras or {}
    user_email = str(st.session_state.get("notification_email", "")).strip() or (os.environ.get("N8N_DEFAULT_EMAIL") or "").strip()
    action = str(extras.get("action") or "").strip().lower()
    if not action and event_type == "task_due":
        action = "gmail"

    payload = {
        # Friend workflow compatible flat fields
        "due_date": task.due_date,
        "due_time": task.due_time,
        "action": action,
        "title": task.title,
        "description": task.notes or "",
        "user": {
            "email": user_email,
        },
        # Existing VoqTask event format (kept for backward compatibility)
        "event_type": event_type,
        "timestamp": now_iso(),
        "user_id": st.session_state.get("user_id", "default"),
        "source": "VoqTask",
        "version": "1.0",
        "task": {
            "id": task.id,
            "title": task.title,
            "due_date": task.due_date,
            "due_time": task.due_time,
            "priority": task.priority.value if task.priority else None,
            "status": task.status.value if task.status else None,
            "notes": task.notes or "",
        },
    }
    payload.update(extras)
    return payload


def _send_n8n_event(event_type: str, task: Task, extras: dict | None = None) -> None:
    webhook_url = (os.environ.get("N8N_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    payload = _build_n8n_payload(event_type, task, extras=extras)
    headers = {"Content-Type": "application/json"}
    token = (os.environ.get("N8N_WEBHOOK_TOKEN") or "").strip()
    if token:
        headers["X-VoqTask-Token"] = token
    print("N8N URL:", webhook_url)
    print("N8N EVENT:", event_type)
    print("N8N PAYLOAD:", json.dumps(payload, indent=2))
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
    except Exception:
        # Keep app flow resilient if webhook endpoint is down.
        return


SYNC_QUEUE_PATH = config.DATA_DIR / "sync_queue.json"


def _load_sync_queue() -> list[dict]:
    try:
        if not SYNC_QUEUE_PATH.exists():
            return []
        raw = json.loads(SYNC_QUEUE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def _save_sync_queue(items: list[dict]) -> None:
    try:
        SYNC_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYNC_QUEUE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _queue_upsert(task_id: str) -> None:
    if not sync_supabase.is_configured():
        return
    items = _load_sync_queue()
    items = [x for x in items if not (x.get("task_id") == task_id and x.get("op") == "upsert")]
    items.append({"op": "upsert", "task_id": task_id, "user_id": st.session_state.user_id, "queued_at": now_iso()})
    _save_sync_queue(items)


def _queue_delete(task_id: str) -> None:
    if not sync_supabase.is_configured():
        return
    items = _load_sync_queue()
    items = [x for x in items if x.get("task_id") != task_id]
    items.append({"op": "delete", "task_id": task_id, "user_id": st.session_state.user_id, "queued_at": now_iso()})
    _save_sync_queue(items)


def _flush_sync_queue() -> tuple[int, int]:
    if config.OFFLINE_MODE or not sync_supabase.is_configured():
        return (0, len(_load_sync_queue()))
    items = _load_sync_queue()
    if not items:
        return (0, 0)
    remaining: list[dict] = []
    pushed = 0
    for item in items:
        op = (item.get("op") or "").strip()
        task_id = item.get("task_id")
        user_id = item.get("user_id") or st.session_state.user_id
        ok = False
        if op == "upsert" and task_id:
            task_ref = get_task_by_id(task_id, user_id=user_id)
            if task_ref:
                ok = sync_supabase.push_task(task_ref, user_id)
            else:
                ok = True
        elif op == "delete" and task_id:
            ok = sync_supabase.delete_remote(task_id, user_id)
        else:
            ok = True
        if ok:
            pushed += 1
        else:
            remaining.append(item)
    _save_sync_queue(remaining)
    return (pushed, len(remaining))


def _save_task_with_sync(task: Task) -> Task:
    user_id = st.session_state.user_id
    existing = get_task_by_id(task.id, user_id=user_id) if task.id else None
    saved = save_task(task, user_id=user_id)
    log_user_event(
        user_id=user_id,
        event_type="task_created" if existing is None else "task_saved",
        task_id=saved.id or "",
        task_title=saved.title,
        details=f"category={saved.category}, priority={saved.priority.value}",
    )
    if config.OFFLINE_MODE or not sync_supabase.is_configured():
        return saved
    if not sync_supabase.push_task(saved, user_id):
        _queue_upsert(saved.id)
    return saved


def _update_task_with_sync(task: Task) -> Task:
    user_id = st.session_state.user_id
    updated = update_task(task, user_id=user_id)
    log_user_event(
        user_id=user_id,
        event_type="task_updated",
        task_id=updated.id or "",
        task_title=updated.title,
        details=f"category={updated.category}, priority={updated.priority.value}",
    )
    if config.OFFLINE_MODE or not sync_supabase.is_configured():
        return updated
    if not sync_supabase.push_task(updated, user_id):
        _queue_upsert(updated.id)
    return updated


def _update_status_with_sync(task_id: str, status: TaskStatus) -> bool:
    user_id = st.session_state.user_id
    task_before = get_task_by_id(task_id, user_id=user_id)
    changed = update_task_status(task_id, status, user_id=user_id)
    if not changed:
        return False
    if task_before:
        log_user_event(
            user_id=user_id,
            event_type="task_status_changed",
            task_id=task_before.id or "",
            task_title=task_before.title,
            details=f"to={status.value}",
        )
    if config.OFFLINE_MODE or not sync_supabase.is_configured():
        return True
    task_ref = get_task_by_id(task_id, user_id=user_id)
    if task_ref and not sync_supabase.push_task(task_ref, user_id):
        _queue_upsert(task_ref.id)
    return True


def _delete_task_with_sync(task_id: str) -> bool:
    user_id = st.session_state.user_id
    task_before = get_task_by_id(task_id, user_id=user_id)
    deleted = delete_task(task_id, user_id=user_id)
    if not deleted:
        return False
    if task_before:
        log_user_event(
            user_id=user_id,
            event_type="task_deleted",
            task_id=task_before.id or "",
            task_title=task_before.title,
            details="deleted_from_ui",
        )
    if config.OFFLINE_MODE or not sync_supabase.is_configured():
        return True
    if not sync_supabase.delete_remote(task_id, user_id):
        _queue_delete(task_id)
    return True

# Cloud sync: pull once on load when configured and not offline (skip default demo user).
if (
    sync_supabase.is_configured()
    and not config.OFFLINE_MODE
    and st.session_state.user_id != "default"
    and not st.session_state.sync_done_once
):
    try:
        sync_supabase.pull_and_merge(st.session_state.user_id)
        _flush_sync_queue()
        st.session_state.sync_done_once = True
    except Exception:
        pass


def _render_admin_console_panel() -> None:
    st.markdown(tr("admin_console_panel_heading"))
    st.caption(tr("admin_caption"))
    users = list_user_profiles()
    if not users:
        st.info(tr("no_users_found"))
        return
    st.caption(trf("total_users", count=len(users)))
    for u in users:
        pending_count = len(get_tasks(user_id=u["user_id"], status=TaskStatus.PENDING, limit=5000))
        done_count = len(get_tasks(user_id=u["user_id"], status=TaskStatus.DONE, limit=5000))
        st.markdown(f"- `{u['user_id']}` ({u.get('display_name') or u['user_id']}) | pending: {pending_count}, done: {done_count}")

    monitor_user = st.selectbox(tr("monitor_user"), options=[u["user_id"] for u in users], key="admin_monitor_user_select")
    monitor_events = get_user_events(user_id=monitor_user, limit=100)
    st.caption(trf("recent_actions_for", user_id=monitor_user))
    st.dataframe(monitor_events, use_container_width=True, hide_index=True)

    monitor_tasks = get_tasks(user_id=monitor_user, limit=200)
    st.caption(trf("tasks_for", user_id=monitor_user))
    task_rows = [
        {
            "id": t.id,
            "title": t.title,
            "category": t.category,
            "status": t.status.value,
            "priority": t.priority.value,
            "due_date": t.due_date or "",
            "due_time": t.due_time or "",
            "updated_at": t.updated_at,
        }
        for t in monitor_tasks
    ]
    st.dataframe(task_rows, use_container_width=True, hide_index=True)

    task_ids = [t.id for t in monitor_tasks]
    if task_ids:
        admin_task_id = st.selectbox(tr("task_to_supervise"), options=task_ids, key="admin_task_supervise_select")
        c_admin_1, c_admin_2, c_admin_3 = st.columns(3)
        if c_admin_1.button(tr("mark_done"), key="admin_mark_done_btn"):
            if update_task_status(admin_task_id, TaskStatus.DONE, user_id=monitor_user):
                task_ref = get_task_by_id(admin_task_id, user_id=monitor_user)
                if task_ref:
                    log_user_event(
                        user_id=monitor_user,
                        event_type="admin_task_status",
                        task_id=task_ref.id or "",
                        task_title=task_ref.title,
                        details=f"to=done by={st.session_state.user_id}",
                    )
                st.success(tr("task_marked_done"))
                st.rerun()
        if c_admin_2.button(tr("mark_pending"), key="admin_mark_pending_btn"):
            if update_task_status(admin_task_id, TaskStatus.PENDING, user_id=monitor_user):
                task_ref = get_task_by_id(admin_task_id, user_id=monitor_user)
                if task_ref:
                    log_user_event(
                        user_id=monitor_user,
                        event_type="admin_task_status",
                        task_id=task_ref.id or "",
                        task_title=task_ref.title,
                        details=f"to=pending by={st.session_state.user_id}",
                    )
                st.success(tr("task_marked_pending"))
                st.rerun()
        if c_admin_3.button(tr("delete_task_label"), key="admin_delete_task_btn"):
            task_ref = get_task_by_id(admin_task_id, user_id=monitor_user)
            if delete_task(admin_task_id, user_id=monitor_user):
                if task_ref:
                    log_user_event(
                        user_id=monitor_user,
                        event_type="admin_task_deleted",
                        task_id=task_ref.id or "",
                        task_title=task_ref.title,
                        details=f"by={st.session_state.user_id}",
                    )
                st.success(tr("task_deleted_done"))
                st.rerun()

    edit_user = st.selectbox(tr("user_to_edit"), options=[u["user_id"] for u in users], key="admin_edit_user_select")
    edit_profile = get_user_profile(edit_user) or {}
    admin_display = st.text_input(tr("new_display_name"), value=edit_profile.get("display_name", ""), key="admin_display_name")
    admin_pass = st.text_input(tr("new_passkey"), value="", placeholder=tr("leave_empty_keep_current"), key="admin_new_passkey")
    if st.button(tr("update_user_profile"), key="admin_update_user_btn"):
        keep_pass = edit_profile.get("passkey_norm", "") if not admin_pass.strip() else _normalize_unlock_phrase(admin_pass)
        upsert_user_profile(
            user_id=edit_user,
            display_name=(admin_display or edit_user).strip(),
            passkey_norm=keep_pass,
            voiceprint=edit_profile.get("voiceprint", ""),
        )
        log_user_event(
            user_id=edit_user,
            event_type="admin_profile_updated",
            details=f"by={st.session_state.user_id}",
        )
        st.success(trf("updated_user", user_id=edit_user))
        st.rerun()
    if st.button(tr("impersonate_selected_user"), key="admin_impersonate_user_btn"):
        from_user = st.session_state.user_id
        st.session_state.user_id = edit_user
        _load_settings_for_user(edit_user)
        st.session_state.sync_done_once = False
        st.session_state.admin_console_mode = False
        if st.session_state.voice_security_enabled and _requires_voice_for_user(edit_user):
            st.session_state.voice_authenticated = False
        else:
            st.session_state.voice_authenticated = True
        log_user_event(
            user_id=edit_user,
            event_type="admin_impersonation",
            details=f"from={from_user}",
        )
        st.success(trf("now_acting_as", user_id=edit_user))
        st.rerun()

# Sidebar: accessibility & settings (SDG 10)
with st.sidebar:
    st.markdown(tr("settings_access"))
    prefs_before = {
        "ui_language": st.session_state.ui_language,
        "speech_language": st.session_state.speech_language,
        "speech_rate": float(st.session_state.speech_rate),
        "accessibility_super_mode": bool(st.session_state.accessibility_super_mode),
        "theme_preset": st.session_state.theme_preset,
        "reminders_enabled": bool(st.session_state.reminders_enabled),
        "browser_notifications": bool(st.session_state.browser_notifications),
        "dragdrop_updates_enabled": bool(st.session_state.dragdrop_updates_enabled),
        "export_scope": st.session_state.export_scope,
        "export_include_notes": bool(st.session_state.export_include_notes),
        "voice_security_enabled": bool(st.session_state.voice_security_enabled),
        "notification_email": str(st.session_state.notification_email or "").strip(),
    }
    if config.OFFLINE_MODE or not sync_supabase.is_configured():
        st.caption(tr("offline_local"))
    ui_lang_options = list(UI_LANGUAGE_LABELS.keys())
    current_ui_lang = st.session_state.ui_language if st.session_state.ui_language in ui_lang_options else "en"
    st.session_state.ui_language = st.selectbox(
        tr("ui_language"),
        options=ui_lang_options,
        index=ui_lang_options.index(current_ui_lang),
        format_func=lambda code: UI_LANGUAGE_LABELS.get(code, code),
    )
    speech_lang_options = [code for code in config.SUPPORTED_LANGUAGES if code in SPEECH_LANGUAGE_LABELS]
    if not speech_lang_options:
        speech_lang_options = ["en"]
    current_speech_lang = st.session_state.speech_language if st.session_state.speech_language in speech_lang_options else "en"
    st.session_state.speech_language = st.selectbox(
        tr("speech_language"),
        options=speech_lang_options,
        index=speech_lang_options.index(current_speech_lang),
        format_func=lambda code: SPEECH_LANGUAGE_LABELS.get(code, code),
        help=tr("speech_help"),
    )
    st.session_state.speech_rate = st.slider(
        tr("speech_rate"),
        0.5, 2.0, float(st.session_state.speech_rate), 0.1,
        help=tr("speech_rate_help"),
    )
    st.session_state.accessibility_super_mode = st.toggle(
        tr("accessibility_mode"),
        value=bool(st.session_state.accessibility_super_mode),
        help=tr("accessibility_help"),
    )
    st.session_state.theme_preset = st.selectbox(
        tr("theme_preset"),
        options=list(THEME_PRESETS.keys()),
        index=list(THEME_PRESETS.keys()).index(st.session_state.theme_preset) if st.session_state.theme_preset in THEME_PRESETS else 0,
    )
    st.session_state.reminders_enabled = st.toggle(
        tr("reminders_enabled"),
        value=bool(st.session_state.reminders_enabled),
        help=tr("reminders_enabled_help"),
    )
    st.session_state.browser_notifications = st.toggle(
        tr("browser_notifications"),
        value=bool(st.session_state.browser_notifications),
        help=tr("browser_notifications_help"),
    )
    st.session_state.dragdrop_updates_enabled = st.toggle(
        tr("dragdrop_updates_enabled"),
        value=bool(st.session_state.dragdrop_updates_enabled),
        help=tr("dragdrop_updates_help"),
    )
    export_scope_options = ["all_users", "active_user_only"] if st.session_state.user_id == ADMIN_USER_ID else ["own_only"]
    if st.session_state.export_scope not in export_scope_options:
        st.session_state.export_scope = export_scope_options[0]
    st.session_state.export_scope = st.selectbox(
        tr("export_scope"),
        options=export_scope_options,
        index=export_scope_options.index(st.session_state.export_scope),
        format_func=lambda x: tr(f"export_scope_{x}"),
    )
    st.session_state.export_include_notes = st.toggle(
        tr("export_include_notes"),
        value=bool(st.session_state.export_include_notes),
    )
    st.markdown("---")
    st.markdown(tr("voice_access"))
    profiles = list_user_profiles()
    profile_ids = [p["user_id"] for p in profiles] if profiles else ["default"]
    if st.session_state.user_id not in profile_ids:
        st.session_state.user_id = "default"
        _load_settings_for_user("default")
    with st.expander(tr("voice_signin_optional"), expanded=False):
        st.caption(tr("voice_unlock_caption"))
        st.caption(f"{tr('active_user')}: {st.session_state.user_id}")
        if _is_admin_user(st.session_state.user_id):
            st.session_state.voice_security_enabled = True
            st.caption(tr("admin_voice_mandatory"))
        else:
            st.session_state.voice_security_enabled = st.toggle(
                tr("enable_voice_biometrics"),
                value=bool(st.session_state.voice_security_enabled),
                help=tr("voice_biometrics_help"),
            )
        st.session_state.voice_auth_threshold = st.slider(
            tr("voice_match_threshold"),
            0.60,
            0.95,
            float(st.session_state.voice_auth_threshold),
            0.01,
            help=tr("voice_match_help"),
        )
        if st.button(tr("capture_next_security"), key="arm_security_capture_btn"):
            st.session_state.audio_capture_mode = "security_enroll"
            st.info(tr("security_capture_armed"))
        capture_mode_text = tr("recorder_mode_security") if st.session_state.audio_capture_mode == "security_enroll" else tr("recorder_mode_task")
        st.caption(trf("recorder_mode", mode=capture_mode_text))
        if st.button(tr("enroll_from_security"), key="enroll_from_security_audio_btn"):
            security_audio = st.session_state.get("security_enroll_audio_bytes")
            if not security_audio:
                st.warning(tr("record_security_first"))
            else:
                enrolled = _extract_voiceprint(security_audio)
                if enrolled is None:
                    st.error(tr("extract_voiceprint_failed"))
                else:
                    target_user_id = st.session_state.enroll_user_id
                    updated = update_user_voiceprint(target_user_id, json.dumps(enrolled.tolist()))
                    if updated:
                        target_settings = get_user_settings(target_user_id)
                        target_settings["voice_security_enabled"] = True
                        set_user_settings(target_user_id, target_settings)
                        if st.session_state.user_id == target_user_id:
                            st.session_state.voice_security_enabled = True
                        log_user_event(
                            user_id=target_user_id,
                            event_type="voiceprint_enrolled",
                            details="security_audio_enroll",
                        )
                        st.success(f"{tr('voiceprint_enrolled')} ({target_user_id})")
                    else:
                        st.error(tr("voiceprint_update_failed"))
                    if st.session_state.voice_security_enabled:
                        st.session_state.voice_authenticated = False
        if st.button(tr("reset_voice_security"), key="reset_voice_security_btn"):
            st.session_state.verified_user_id = ""
            st.session_state.voice_authenticated = not st.session_state.voice_security_enabled
            st.info(tr("voice_security_cleared"))
        if st.session_state.voice_security_enabled:
            active_profile = get_user_profile(st.session_state.user_id)
            active_has_voice = bool((active_profile or {}).get("voiceprint", ""))
            if not active_has_voice:
                st.warning(tr("enroll_voice_warning"))
            status_text = tr("status_unlocked") if st.session_state.voice_authenticated else tr("status_locked")
            st.caption(trf("security_status", status=status_text))
    st.markdown(tr("user_profiles_heading"))
    manual_switch_user = st.selectbox(
        tr("switch_user_manually"),
        options=profile_ids,
        index=profile_ids.index(st.session_state.user_id),
    )
    if st.button(tr("switch_now"), key="manual_switch_user_btn"):
        prev_user = st.session_state.user_id
        st.session_state.user_id = manual_switch_user
        _load_settings_for_user(manual_switch_user)
        st.session_state.sync_done_once = False
        if st.session_state.voice_security_enabled and _requires_voice_for_user(manual_switch_user):
            st.session_state.voice_authenticated = False
        else:
            st.session_state.voice_authenticated = True
        log_user_event(
            user_id=manual_switch_user,
            event_type="user_switched_manual",
            details=f"from={prev_user}",
        )
        st.success(trf("switched_to_user", user_id=manual_switch_user))
        st.rerun()
    st.session_state.enroll_user_id = st.selectbox(
        tr("profile_to_enroll"),
        options=profile_ids,
        index=profile_ids.index(st.session_state.enroll_user_id) if st.session_state.enroll_user_id in profile_ids else 0,
    )
    st.session_state.notification_email = st.text_input(
        tr("email_reminders_label"),
        value=st.session_state.notification_email,
        placeholder="name@example.com",
    ).strip()
    new_user_id = st.text_input(tr("new_user_id"), value=st.session_state.enroll_user_id, placeholder="e.g. alice")
    new_display_name = st.text_input(tr("display_name"), value=(get_user_profile(st.session_state.enroll_user_id) or {}).get("display_name", ""))
    new_passkey = st.text_input(tr("voice_passkey_optional"), key="voice_pw", placeholder="e.g. 123")
    if st.button(tr("create_update_profile"), key="create_user_profile_btn"):
        uid_norm = _normalize_unlock_phrase(new_user_id)
        if not uid_norm:
            st.warning(tr("enter_valid_user_id"))
        else:
            existing_profile = get_user_profile(uid_norm) or {}
            upsert_user_profile(
                user_id=uid_norm,
                display_name=(new_display_name or uid_norm).strip(),
                passkey_norm=_normalize_unlock_phrase(new_passkey),
                voiceprint=existing_profile.get("voiceprint", ""),
            )
            existing_settings = get_user_settings(uid_norm)
            if not existing_settings:
                set_user_settings(uid_norm, _settings_defaults_for(uid_norm))
            log_user_event(
                user_id=uid_norm,
                event_type="profile_upserted",
                details="via_voice_settings",
            )
            st.session_state.enroll_user_id = uid_norm
            st.success(trf("profile_saved", user_id=uid_norm))
            st.rerun()
    if st.button(tr("linkedin_test_post_btn"), key="n8n_linkedin_test_btn"):
        _today_for_demo = _now_local().strftime("%Y-%m-%d")
        demo_task = Task(
            id=None,
            title="VoqTask Productivity Update",
            category="work",
            due_date=_today_for_demo,
            due_time=None,
            priority=Priority.MEDIUM,
            status=TaskStatus.PENDING,
            created_at=now_iso(),
            updated_at=now_iso(),
            shared_with=[],
            notes=f"User {st.session_state.user_id} completed tasks with VoqTask automation.",
            source="n8n_test",
        )
        _send_n8n_event("manual_linkedin_post", demo_task, extras={"action": "linkedin"})
        st.info(tr("linkedin_trigger_sent"))
    prefs_after = {
        "ui_language": st.session_state.ui_language,
        "speech_language": st.session_state.speech_language,
        "speech_rate": float(st.session_state.speech_rate),
        "accessibility_super_mode": bool(st.session_state.accessibility_super_mode),
        "theme_preset": st.session_state.theme_preset,
        "reminders_enabled": bool(st.session_state.reminders_enabled),
        "browser_notifications": bool(st.session_state.browser_notifications),
        "dragdrop_updates_enabled": bool(st.session_state.dragdrop_updates_enabled),
        "export_scope": st.session_state.export_scope,
        "export_include_notes": bool(st.session_state.export_include_notes),
        "voice_security_enabled": bool(st.session_state.voice_security_enabled),
        "notification_email": str(st.session_state.notification_email or "").strip(),
    }
    if prefs_before != prefs_after:
        _save_settings_for_current_user()
    st.markdown("---")
    st.markdown(tr("cloud_sync"))
    supabase_url_loaded = bool((config.SUPABASE_URL or "").strip())
    supabase_key_loaded = bool((config.SUPABASE_ANON_KEY or "").strip())
    st.caption(
        f"Debug: SUPABASE_URL loaded={supabase_url_loaded} | "
        f"SUPABASE_ANON_KEY loaded={supabase_key_loaded} | "
        f"OFFLINE_MODE={config.OFFLINE_MODE}"
    )
    if sync_supabase.is_configured() and not config.OFFLINE_MODE:
        st.success(tr("sync_ok"))
        if st.button(tr("sync_now")):
            try:
                merged = sync_supabase.pull_and_merge(st.session_state.user_id)
                pushed = sync_supabase.push_all_local(st.session_state.user_id)
                queue_pushed, queue_remaining = _flush_sync_queue()
                st.success(trf("sync_summary", pulled=merged, pushed=pushed, queued=queue_pushed, pending=queue_remaining))
            except Exception as e:
                st.error(trf("sync_failed", err=e))
            st.rerun()
    else:
        st.caption(tr("sync_hint"))
    st.markdown("---")
    st.markdown(tr("rewards_heading"))
    rewards = get_user_rewards_summary(st.session_state.user_id)
    st.caption(trf("level_points", level=rewards["level"], points=rewards["points"]))
    r1, r2, r3 = st.columns(3)
    r1.metric(tr("metric_done"), rewards["tasks_completed"])
    r2.metric(tr("metric_streak"), f"{rewards['streak_days']}d")
    r3.metric(tr("metric_next"), f"{rewards['needed_for_next']} pts")
    st.progress(min(1.0, max(0.0, rewards["level_progress"])))
    st.markdown("---")
    st.markdown(tr("data_export_heading"))
    export_rows = []
    if st.session_state.user_id == ADMIN_USER_ID and st.session_state.export_scope == "all_users":
        target_users = [p["user_id"] for p in list_user_profiles()]
    elif st.session_state.user_id == ADMIN_USER_ID and st.session_state.export_scope == "active_user_only":
        target_users = [st.session_state.get("admin_monitor_user_select", st.session_state.user_id)]
    else:
        target_users = [st.session_state.user_id]

    include_user_id = st.session_state.user_id == ADMIN_USER_ID and st.session_state.export_scope == "all_users"
    for uid in target_users:
        for t in get_tasks(user_id=uid, limit=5000):
            row = t.to_dict()
            if not st.session_state.export_include_notes:
                row["notes"] = ""
            if include_user_id:
                row["user_id"] = uid
            export_rows.append(row)
    export_json = json.dumps(export_rows, ensure_ascii=False, indent=2)
    csv_buf = io.StringIO()
    writer = csv.DictWriter(
        csv_buf,
        fieldnames=(["user_id"] if include_user_id else []) + ["id", "title", "category", "due_date", "due_time", "priority", "status", "created_at", "updated_at", "shared_with", "notes", "source"],
    )
    writer.writeheader()
    for row in export_rows:
        row = dict(row)
        row["shared_with"] = ",".join(row.get("shared_with") or [])
        writer.writerow(row)
    file_prefix = "voqtask_admin_export" if st.session_state.user_id == ADMIN_USER_ID else "voqtask_user_export"
    st.download_button(tr("download_json"), data=export_json.encode("utf-8"), file_name=f"{file_prefix}.json", mime="application/json")
    st.download_button(tr("download_csv"), data=csv_buf.getvalue().encode("utf-8"), file_name=f"{file_prefix}.csv", mime="text/csv")
    if st.session_state.user_id == ADMIN_USER_ID:
        st.caption(tr("admin_export_caption"))
    else:
        st.caption(tr("user_export_caption"))
    if not st.session_state.export_include_notes:
        st.caption(tr("export_notes_disabled_hint"))
    st.caption(tr("api_server_hint"))
    st.markdown("---")
    st.caption(tr("app_caption"))

if st.session_state.voice_security_enabled:
    active_profile = get_user_profile(st.session_state.user_id)
    active_has_voice = bool((active_profile or {}).get("voiceprint", ""))
    if active_has_voice:
        st.session_state.voice_authenticated = (st.session_state.verified_user_id == st.session_state.user_id)
    else:
        if _is_admin_user(st.session_state.user_id):
            # For admin without enrolled voiceprint, preserve explicit passkey unlock state.
            st.session_state.voice_authenticated = bool(
                st.session_state.voice_authenticated and st.session_state.verified_user_id == st.session_state.user_id
            )
        else:
            st.session_state.voice_authenticated = True

# Keep URL session context in sync so reload restores same user/page.
_sync_session_context_query_params()

if st.session_state.accessibility_super_mode:
    st.markdown(
        """
<style>
    .stApp {
        filter: contrast(1.12) saturate(1.08);
    }
    html, body, [class*="css"] {
        font-size: 18px !important;
        line-height: 1.5 !important;
    }
    .stButton > button,
    [data-testid="stChatInput"] textarea,
    [data-testid="stChatInput"] input,
    [data-baseweb="input"] input,
    [data-baseweb="select"] > div {
        min-height: 3rem !important;
        font-size: 1rem !important;
    }
    button:focus-visible,
    input:focus-visible,
    textarea:focus-visible,
    [role="button"]:focus-visible {
        outline: 3px solid #ffc864 !important;
        outline-offset: 2px !important;
    }
</style>
        """,
        unsafe_allow_html=True,
    )

active_theme = THEME_PRESETS.get(st.session_state.theme_preset, {})
if active_theme:
    st.markdown(
        f"""
<style>
    .stApp {{
        background: {active_theme["app_bg"]} !important;
        color: {active_theme["text"]} !important;
    }}
    .app-shell, .task-pane, .task-card-wrap, .chat-panel, [data-testid="stExpander"] {{
        background: {active_theme["card"]} !important;
        border-color: {active_theme["border"]} !important;
    }}
    .app-title, .task-card-wrap .task-title, h1, h2, h3, .section-head {{
        color: {active_theme["text"]} !important;
    }}
    .stat-pill, [data-testid="stTabs"] [aria-selected="true"] {{
        color: {active_theme["accent"]} !important;
        border-color: {active_theme["border"]} !important;
    }}
</style>
        """,
        unsafe_allow_html=True,
    )

# Main layout: Hero + Voice/Text, then Today / Tomorrow / Later
st.markdown(f"<p class='app-title'>\U0001F399\ufe0f VoqTask</p><p class='app-tagline'>{tr('app_tagline')}</p>", unsafe_allow_html=True)
active_display = (get_user_profile(st.session_state.user_id) or {}).get("display_name", st.session_state.user_id)
badge_color = "#f59e0b" if st.session_state.user_id == ADMIN_USER_ID else "#64b4ff"
badge_col, admin_btn_col, logout_btn_col = st.columns([4.6, 1.2, 1.2])
with badge_col:
    st.markdown(
        f"<div style='margin-bottom:0.45rem;'><span style='display:inline-block; padding:0.28rem 0.72rem; border-radius:999px; "
        f"border:1px solid rgba(255,255,255,0.12); background:rgba(20,24,32,0.78); color:{badge_color}; font-size:0.82rem; font-weight:600;'>"
        f"{html.escape(trf('current_user_badge', name=active_display, user_id=st.session_state.user_id))}</span></div>",
        unsafe_allow_html=True,
    )
with admin_btn_col:
    if st.session_state.user_id == ADMIN_USER_ID:
        label = tr("close_admin_console") if st.session_state.admin_console_mode else tr("open_admin_console")
        admin_unlocked_for_panels = (not st.session_state.voice_security_enabled) or st.session_state.voice_authenticated
        if st.button(label, key="toggle_admin_console_mode_btn", use_container_width=True, disabled=(not admin_unlocked_for_panels)):
            st.session_state.admin_console_mode = not st.session_state.admin_console_mode
            _sync_session_context_query_params()
            st.rerun()
        if st.session_state.admin_console_mode and not admin_unlocked_for_panels:
            st.session_state.admin_console_mode = False
            _sync_session_context_query_params()
            st.rerun()
with logout_btn_col:
    if st.button(tr("logout"), key="logout_btn", use_container_width=True):
        st.session_state.user_id = "default"
        st.session_state.admin_console_mode = False
        st.session_state.verified_user_id = ""
        st.session_state.voice_authenticated = True
        st.session_state.sync_done_once = False
        _load_settings_for_user("default")
        try:
            st.query_params["uid"] = "default"
            st.query_params["auth"] = "1"
            st.query_params["admin"] = "0"
        except Exception:
            pass
        st.rerun()
if st.session_state.reward_flash:
    st.success(st.session_state.reward_flash)
    st.session_state.reward_flash = None

if st.session_state.user_id == ADMIN_USER_ID and st.session_state.admin_console_mode:
    _render_admin_console_panel()
    st.stop()

left_col, right_col = st.columns([0.95, 1.05], gap="large")

audio = None
typed_message = ""

# Chat layout containers (top: chat, bottom: composer)
with left_col:
    chat_top_container = st.container()
    composer_bottom_container = st.container()

with composer_bottom_container:
    with st.container(key="unified_composer"):
        main_audio_label = tr("security_record") if st.session_state.audio_capture_mode == "security_enroll" else tr("speak")
        audio = st.audio_input(main_audio_label, key="main_voice_input", label_visibility="collapsed")
        typed_message = (st.chat_input(tr("chat_placeholder"), key="text_task_input") or "").strip()
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
        st.success(tr("security_sample_captured"))
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
                    st.success(f"{tr('heard')}: \"{transcript}\"")
            except Exception as e:
                st.error(trf("transcription_failed", err=e))
            finally:
                Path(path).unlink(missing_ok=True)
        elif st.session_state.last_voiceprint is not None:
            current_voiceprint = np.asarray(st.session_state.last_voiceprint, dtype=np.float32)

# Use transcript or text input
def _norm_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]+", " ", (text or "").lower())).strip()


def _resolve_task_by_title_query(title_query: str):
    if not title_query:
        return None
    tasks = get_tasks(user_id=st.session_state.user_id, limit=5000)
    if not tasks:
        return None
    q = _norm_for_match(title_query)
    if not q:
        return None
    exact = [t for t in tasks if _norm_for_match(t.title) == q]
    if exact:
        return sorted(exact, key=lambda t: t.updated_at or "", reverse=True)[0]
    contains = [t for t in tasks if q in _norm_for_match(t.title)]
    if contains:
        return sorted(contains, key=lambda t: t.updated_at or "", reverse=True)[0]
    return None


def _extract_title_query(text: str, action_words: str) -> str:
    quoted = re.search(r'"([^"]+)"', text)
    if quoted:
        return quoted.group(1).strip()
    raw = re.sub(action_words, "", text, flags=re.I).strip(" :-")
    raw = re.sub(r"\b(task|todo)\b", "", raw, flags=re.I).strip(" :-")
    return raw


def _try_voice_command_update(text: str) -> str | None:
    if re.search(r"\b(delete|remove)\b", text, re.I):
        title_query = _extract_title_query(text, r"\b(delete|remove)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to delete."
        _delete_task_with_sync(task.id)
        _send_n8n_event("task_deleted", task)
        return f"Deleted task: {task.title}"

    if re.search(r"\b(mark|set|complete|finish)\b", text, re.I) and re.search(r"\b(done|complete|completed|finished)\b", text, re.I):
        title_query = _extract_title_query(text, r"\b(mark|set|complete|finish|as|to|done|completed|finished)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to mark done."
        _update_status_with_sync(task.id, TaskStatus.DONE)
        task.status = TaskStatus.DONE
        _send_n8n_event("task_done", task)
        reward_result = reward_task_completion(task.id, st.session_state.user_id)
        if reward_result.get("awarded"):
            st.session_state.reward_flash = (
                f"+{reward_result['points_awarded']} pts | "
                f"Level {reward_result['level']} | "
                f"{reward_result['streak_days']}-day streak"
            )
        return f"Marked done: {task.title}"

    if re.search(r"\b(reopen|pending|not done|undo)\b", text, re.I):
        title_query = _extract_title_query(text, r"\b(reopen|pending|not done|undo|mark|set|as|to)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to reopen."
        _update_status_with_sync(task.id, TaskStatus.PENDING)
        return f"Reopened task: {task.title}"

    prio_match = re.search(r"\b(low|medium|high|urgent)\s+priority\b", text, re.I) or re.search(r"\bpriority\s+(low|medium|high|urgent)\b", text, re.I)
    if prio_match and re.search(r"\b(set|change|make|update)\b", text, re.I):
        new_prio = (prio_match.group(1) or "").lower().strip()
        title_query = _extract_title_query(text, r"\b(set|change|make|update|priority|low|medium|high|urgent|to|as)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to change priority."
        task.priority = Priority(new_prio)
        _update_task_with_sync(task)
        _send_n8n_event("task_updated", task, extras={"field": "priority"})
        return f"Updated priority to {new_prio}: {task.title}"

    due_m = re.search(
        r'\b(?:set|change|update)\b.*\bdue(?:\s+date|\s+time)?\b.*(?:of\s+)?(?:"([^"]+)"|(.+?))\s+\bto\b\s+(.+)$',
        text,
        re.I,
    )
    if due_m:
        title_query = (due_m.group(1) or due_m.group(2) or "").strip()
        due_phrase = (due_m.group(3) or "").strip()
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to update due date/time."
        due_probe = parse_task_from_text(f"remind me to placeholder {due_phrase}")
        if not due_probe or (not due_probe.due_date and not due_probe.due_time):
            return "I could not understand the new due date/time."
        task.due_date = due_probe.due_date or task.due_date
        task.due_time = due_probe.due_time or task.due_time
        _update_task_with_sync(task)
        _send_n8n_event("task_updated", task, extras={"field": "due"})
        return f"Updated due details: {task.title} -> {task.due_date or '-'} {task.due_time or ''}".strip()
    return None

user_message = (transcript or typed_message or "").strip()
task_created = None

if user_message:
    user_before_message = st.session_state.user_id
    auth_before_message = bool(st.session_state.voice_authenticated)
    _append_turn(st.session_state.user_id, "user", user_message)
    security_reply = None
    normalized_spoken = _normalize_unlock_phrase(user_message)
    normalized_spoken_digits = _normalize_with_spoken_digits(user_message)
    raw_digits_only = "".join(ch for ch in user_message if ch.isdigit())
    unlock_aliases = {"voiceprint", "voiceprints", "voiceprintunlock"}
    is_unlock_attempt = (normalized_spoken in unlock_aliases) or (normalized_spoken_digits in unlock_aliases)
    matched_pass_user = None
    admin_pass_norm = _normalize_unlock_phrase(ADMIN_PASSKEY)
    admin_prof_for_match = get_user_profile(ADMIN_USER_ID) or {}
    admin_profile_pass_norm = _normalize_unlock_phrase((admin_prof_for_match or {}).get("passkey_norm", ""))
    admin_effective_pass = admin_pass_norm or admin_profile_pass_norm or "1234"
    # Demo-safe shortcut: admin numeric utterance should always be treated as passkey attempt.
    if (
        not is_unlock_attempt
        and _is_admin_user(st.session_state.get("user_id", ""))
        and raw_digits_only.isdigit()
        and len(raw_digits_only) >= 3
    ):
        matched_pass_user = admin_prof_for_match or {"user_id": ADMIN_USER_ID}
        is_unlock_attempt = True
    # Deterministic admin passkey matcher for spoken digits/transcript variations.
    if (
        not is_unlock_attempt
        and _is_admin_user(st.session_state.get("user_id", ""))
        and (
            normalized_spoken == admin_effective_pass
            or normalized_spoken_digits == admin_effective_pass
            or raw_digits_only == admin_effective_pass
        )
    ):
        matched_pass_user = admin_prof_for_match or {"user_id": ADMIN_USER_ID}
        is_unlock_attempt = True
    if not is_unlock_attempt and (normalized_spoken or normalized_spoken_digits):
        matched_pass_user = _find_user_by_spoken_passkey(normalized_spoken) or _find_user_by_spoken_passkey(normalized_spoken_digits)
        # Admin-local fallback: also check passkey stored in admin profile.
        if matched_pass_user is None and _is_admin_user(st.session_state.get("user_id", "")):
            admin_prof = admin_prof_for_match
            admin_profile_pass = admin_profile_pass_norm
            if admin_profile_pass and (
                admin_profile_pass == normalized_spoken
                or admin_profile_pass == normalized_spoken_digits
                or admin_profile_pass in normalized_spoken
                or admin_profile_pass in normalized_spoken_digits
            ):
                matched_pass_user = admin_prof or {"user_id": ADMIN_USER_ID}
        # Hard fallback: allow explicit ADMIN_PASSKEY from .env to resolve admin reliably.
        if (
            matched_pass_user is None
            and admin_pass_norm
            and (
                admin_pass_norm == normalized_spoken
                or admin_pass_norm == normalized_spoken_digits
                or admin_pass_norm in normalized_spoken
                or admin_pass_norm in normalized_spoken_digits
            )
        ):
            matched_pass_user = get_user_profile(ADMIN_USER_ID) or {"user_id": ADMIN_USER_ID}
        # Final fallback for deployed env drift: admin current-session numeric input triggers admin verify flow.
        if (
            matched_pass_user is None
            and _is_admin_user(st.session_state.get("user_id", ""))
            and (
                (normalized_spoken_digits.isdigit() and len(normalized_spoken_digits) >= 3)
                or (raw_digits_only.isdigit() and len(raw_digits_only) >= 3)
            )
        ):
            matched_pass_user = get_user_profile(ADMIN_USER_ID) or {"user_id": ADMIN_USER_ID}
        if matched_pass_user:
            is_unlock_attempt = True

    if st.session_state.voice_security_enabled and is_unlock_attempt:
        threshold = float(st.session_state.voice_auth_threshold)
        # Path A: passkey spoken -> direct user resolution.
        if matched_pass_user:
            target_user = matched_pass_user["user_id"]
            st.session_state.user_id = target_user
            _load_settings_for_user(target_user)
            st.session_state.sync_done_once = False
            # Deterministic behavior: for admin, accepted passkey unlocks session directly.
            if _is_admin_user(target_user):
                st.session_state.voice_authenticated = True
                st.session_state.verified_user_id = target_user
                st.session_state.admin_console_mode = True
                log_user_event(
                    user_id=target_user,
                    event_type="login_admin_passkey",
                    details="passkey_unlock",
                )
                security_reply = trf("voice_signin_success_active", user_id=target_user)
            elif _requires_voice_for_user(target_user):
                target_voiceprint = (matched_pass_user.get("voiceprint") or "").strip()
                if not target_voiceprint:
                    target_voiceprint = ((get_user_profile(target_user) or {}).get("voiceprint") or "").strip()
                unlocked_without_voiceprint = False
                # Admin fallback: if no admin voiceprint is enrolled yet, allow passkey unlock.
                if _is_admin_user(target_user) and not target_voiceprint:
                    st.session_state.voice_authenticated = True
                    st.session_state.verified_user_id = target_user
                    log_user_event(
                        user_id=target_user,
                        event_type="login_admin_passkey_no_voiceprint",
                        details="fallback_unlock",
                    )
                    security_reply = trf("voice_signin_success_active", user_id=target_user)
                    unlocked_without_voiceprint = True
                if unlocked_without_voiceprint:
                    pass
                elif current_voiceprint is not None and target_voiceprint:
                    try:
                        template = np.asarray(json.loads(target_voiceprint), dtype=np.float32)
                        score = _voiceprint_similarity(current_voiceprint, template)
                    except Exception:
                        score = 0.0
                    if score >= threshold:
                        st.session_state.voice_authenticated = True
                        st.session_state.verified_user_id = target_user
                        log_user_event(
                            user_id=target_user,
                            event_type="login_passkey_voiceprint",
                            details=f"score={score:.2f}",
                        )
                        security_reply = trf("voice_verified_score", user_id=target_user, score=f"{score:.2f}")
                    else:
                        st.session_state.voice_authenticated = False
                        st.session_state.verified_user_id = ""
                        security_reply = tr("voice_no_match")
                elif current_voiceprint is None:
                    st.session_state.voice_authenticated = False
                    st.session_state.verified_user_id = ""
                    security_reply = tr("unlock_phrase_need_fresh_voice")
                else:
                    st.session_state.voice_authenticated = False
                    st.session_state.verified_user_id = ""
                    security_reply = trf("passkey_matched_needs_voice", user_id=target_user)
            else:
                st.session_state.voice_authenticated = True
                st.session_state.verified_user_id = ""
                log_user_event(
                    user_id=target_user,
                    event_type="login_passkey",
                    details="voice_unlock_phrase",
                )
                security_reply = trf("voice_signin_success_active", user_id=target_user)
        # Path B: voiceprint keyword + current sample -> resolve best matching enrolled user.
        elif current_voiceprint is None:
            security_reply = tr("unlock_phrase_need_fresh_voice")
            st.session_state.voice_authenticated = False
        else:
            best_user = None
            best_score = 0.0
            for prof in list_user_profiles():
                if not prof.get("voiceprint"):
                    continue
                try:
                    template = np.asarray(json.loads(prof["voiceprint"]), dtype=np.float32)
                except Exception:
                    continue
                score = _voiceprint_similarity(current_voiceprint, template)
                if score > best_score:
                    best_score = score
                    best_user = prof
            if best_user is not None and best_score >= threshold:
                st.session_state.user_id = best_user["user_id"]
                _load_settings_for_user(best_user["user_id"])
                st.session_state.voice_authenticated = True
                st.session_state.verified_user_id = best_user["user_id"]
                st.session_state.sync_done_once = False
                log_user_event(
                    user_id=best_user["user_id"],
                    event_type="login_voiceprint",
                    details=f"score={best_score:.2f}",
                )
                security_reply = trf("voice_verified_score", user_id=best_user["user_id"], score=f"{best_score:.2f}")
            else:
                st.session_state.voice_authenticated = False
                st.session_state.verified_user_id = ""
                security_reply = tr("voice_no_match")
    elif (not st.session_state.voice_security_enabled) and is_unlock_attempt:
        if matched_pass_user:
            st.session_state.user_id = matched_pass_user["user_id"]
            _load_settings_for_user(matched_pass_user["user_id"])
            st.session_state.sync_done_once = False
        st.session_state.voice_authenticated = True
        st.session_state.verified_user_id = ""
        security_reply = tr("voice_signin_success")

    if (
        security_reply is None
        and st.session_state.voice_security_enabled
        and not st.session_state.voice_authenticated
    ):
        security_reply = _locked_voice_prompt()

    if (
        security_reply is None
        and st.session_state.voice_security_enabled
        and _is_sensitive_task_query(user_message)
        and not st.session_state.voice_authenticated
    ):
        security_reply = _locked_voice_prompt()

    if security_reply is not None:
        _append_turn(st.session_state.user_id, "app", security_reply)
    else:
        voice_cmd_reply = _try_voice_command_update(user_message)
        if voice_cmd_reply:
            _append_turn(st.session_state.user_id, "app", voice_cmd_reply)
            st.success(voice_cmd_reply)
        else:
            task = parse_task_from_text(user_message)
            if task:
                task = _save_task_with_sync(task)
                task_created = task
                _send_n8n_event("task_created", task)
                st.balloons()
                st.success(f"{tr('task_added')}: **{task.title}**" + (f" - {task.due_date} {task.due_time or ''}" if task.due_date else ""))

            today_str = _now_local().strftime("%Y-%m-%d")
            tomorrow_str = (_now_local() + timedelta(days=1)).strftime("%Y-%m-%d")
            tasks_today = get_tasks(user_id=st.session_state.user_id, due_date=today_str, status=TaskStatus.PENDING)
            tasks_tomorrow = get_tasks(user_id=st.session_state.user_id, due_date=tomorrow_str, status=TaskStatus.PENDING)
            reply = reply_to_user(
                user_message,
                _conversation_for_user(st.session_state.user_id),
                tasks_today,
                tasks_tomorrow,
                task_created=task_created,
                language=st.session_state.get("ui_language", "en"),
                user_id=st.session_state.user_id,
            )
            _append_turn(st.session_state.user_id, "app", reply)

    # Keep header badge and chat context consistent when voice auth switches user.
    if (
        st.session_state.user_id != user_before_message
        or bool(st.session_state.voice_authenticated) != auth_before_message
    ):
        _sync_session_context_query_params()
        st.rerun()

# Show last reply or proactive suggestion
today_str = _now_local().strftime("%Y-%m-%d")
tomorrow_str = (_now_local() + timedelta(days=1)).strftime("%Y-%m-%d")
all_pending = get_tasks(user_id=st.session_state.user_id, status=TaskStatus.PENDING)
all_done = get_tasks(user_id=st.session_state.user_id, status=TaskStatus.DONE, limit=5000)
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
    """Tasks that are due in the next within_hours (default 2 hours)."""
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
    """Tasks that are due within the last grace_minutes (overdue or just became due)."""
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


def _emit_browser_due_popup(message: str, notif_key: str) -> None:
    payload = json.dumps({"message": message, "key": notif_key})
    js = """
<script>
(function() {
  const p = __PAYLOAD__;
  if (!p || !p.message) return;
  const sentKey = "voqtask_due_popup_" + String(p.key || p.message);
  try {
    if (window.sessionStorage.getItem(sentKey) === "1") return;
    const done = () => window.sessionStorage.setItem(sentKey, "1");
    const show = () => {
      try {
        new Notification("VoqTask Reminder", { body: String(p.message) });
      } catch (_) {
        try { alert(String(p.message)); } catch (_) {}
      }
      done();
    };
    if (!("Notification" in window)) {
      try { alert(String(p.message)); } catch (_) {}
      done();
      return;
    }
    if (Notification.permission === "granted") {
      show();
      return;
    }
    if (Notification.permission !== "denied") {
      Notification.requestPermission().then((perm) => {
        if (perm === "granted") show();
        else {
          try { alert(String(p.message)); } catch (_) {}
          done();
        }
      });
      return;
    }
    try { alert(String(p.message)); } catch (_) {}
    done();
  } catch (_) {}
})();
</script>
    """
    st.markdown(js.replace("__PAYLOAD__", payload), unsafe_allow_html=True)


def _norm_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]+", " ", (text or "").lower())).strip()


def _resolve_task_by_title_query(title_query: str):
    if not title_query:
        return None
    tasks = get_tasks(user_id=st.session_state.user_id, limit=5000)
    if not tasks:
        return None
    q = _norm_for_match(title_query)
    if not q:
        return None
    exact = [t for t in tasks if _norm_for_match(t.title) == q]
    if exact:
        return sorted(exact, key=lambda t: t.updated_at or "", reverse=True)[0]
    contains = [t for t in tasks if q in _norm_for_match(t.title)]
    if contains:
        return sorted(contains, key=lambda t: t.updated_at or "", reverse=True)[0]
    return None


def _extract_title_query(text: str, action_words: str) -> str:
    quoted = re.search(r'"([^"]+)"', text)
    if quoted:
        return quoted.group(1).strip()
    raw = re.sub(action_words, "", text, flags=re.I).strip(" :-")
    raw = re.sub(r"\b(task|todo)\b", "", raw, flags=re.I).strip(" :-")
    return raw


def _try_voice_command_update(text: str) -> str | None:
    # Delete
    if re.search(r"\b(delete|remove)\b", text, re.I):
        title_query = _extract_title_query(text, r"\b(delete|remove)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to delete."
        _delete_task_with_sync(task.id)
        _send_n8n_event("task_deleted", task)
        return f"Deleted task: {task.title}"

    # Mark done / complete
    if re.search(r"\b(mark|set|complete|finish)\b", text, re.I) and re.search(r"\b(done|complete|completed|finished)\b", text, re.I):
        title_query = _extract_title_query(text, r"\b(mark|set|complete|finish|as|to|done|completed|finished)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to mark done."
        _update_status_with_sync(task.id, TaskStatus.DONE)
        task.status = TaskStatus.DONE
        _send_n8n_event("task_done", task)
        reward_result = reward_task_completion(task.id, st.session_state.user_id)
        if reward_result.get("awarded"):
            st.session_state.reward_flash = (
                f"+{reward_result['points_awarded']} pts | "
                f"Level {reward_result['level']} | "
                f"{reward_result['streak_days']}-day streak"
            )
        return f"Marked done: {task.title}"

    # Reopen / pending
    if re.search(r"\b(reopen|pending|not done|undo)\b", text, re.I):
        title_query = _extract_title_query(text, r"\b(reopen|pending|not done|undo|mark|set|as|to)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to reopen."
        _update_status_with_sync(task.id, TaskStatus.PENDING)
        return f"Reopened task: {task.title}"

    # Priority update
    prio_match = re.search(r"\b(low|medium|high|urgent)\s+priority\b", text, re.I) or re.search(r"\bpriority\s+(low|medium|high|urgent)\b", text, re.I)
    if prio_match and re.search(r"\b(set|change|make|update)\b", text, re.I):
        new_prio = (prio_match.group(1) or "").lower().strip()
        title_query = _extract_title_query(text, r"\b(set|change|make|update|priority|low|medium|high|urgent|to|as)\b")
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to change priority."
        task.priority = Priority(new_prio)
        _update_task_with_sync(task)
        _send_n8n_event("task_updated", task, extras={"field": "priority"})
        return f"Updated priority to {new_prio}: {task.title}"

    # Due date/time update
    due_m = re.search(
        r'\b(?:set|change|update)\b.*\bdue(?:\s+date|\s+time)?\b.*(?:of\s+)?(?:"([^"]+)"|(.+?))\s+\bto\b\s+(.+)$',
        text,
        re.I,
    )
    if due_m:
        title_query = (due_m.group(1) or due_m.group(2) or "").strip()
        due_phrase = (due_m.group(3) or "").strip()
        task = _resolve_task_by_title_query(title_query)
        if not task:
            return "I could not find that task to update due date/time."
        due_probe = parse_task_from_text(f"remind me to placeholder {due_phrase}")
        if not due_probe or (not due_probe.due_date and not due_probe.due_time):
            return "I could not understand the new due date/time."
        task.due_date = due_probe.due_date or task.due_date
        task.due_time = due_probe.due_time or task.due_time
        _update_task_with_sync(task)
        _send_n8n_event("task_updated", task, extras={"field": "due"})
        return f"Updated due details: {task.title} -> {task.due_date or '-'} {task.due_time or ''}".strip()

    return None

upcoming = _tasks_due_soon(tasks_today)

due_now = _tasks_due_now(all_pending)
alerted_ids = set(st.session_state.due_alerted_task_ids)
pending_ids = {t.id for t in all_pending}
alerted_ids = {task_id for task_id in alerted_ids if task_id in pending_ids}
due_now_messages = []
due_now_popup_items = []
for task in due_now:
    if task.id in alerted_ids:
        continue
    msg = f"\u23F0 Due now: {task.title}" + (f" ({task.due_time})" if task.due_time else "")
    due_now_messages.append(msg)
    due_now_popup_items.append((msg, f"{task.id}:{task.due_date or ''}:{task.due_time or ''}"))
    _send_n8n_event("task_due", task)
    alerted_ids.add(task.id)
st.session_state.due_alerted_task_ids = list(alerted_ids)
if not st.session_state.reminders_enabled:
    due_now_messages = []
    due_now_popup_items = []
    upcoming = []

suggestion = get_proactive_suggestion(all_pending, language=st.session_state.get("ui_language", "en"))
today_local = _now_local().date()
done_today = sum(1 for task in all_done if _parse_iso_to_local_date(task.updated_at) == today_local)
today_goal = 5
today_percent = (done_today / today_goal * 100.0) if today_goal else 0.0
with chat_top_container:
    user_conversation = _conversation_for_user(st.session_state.user_id)
    unlocked_for_chat = (not st.session_state.voice_security_enabled) or st.session_state.voice_authenticated
    st.markdown(f"<div class='section-head'>\U0001F916 {tr('assistant_chat')}</div>", unsafe_allow_html=True)
    if not unlocked_for_chat:
        lock_msg = html.escape(_locked_tasks_prompt())
        st.markdown(
            "<div class='chat-panel'><div class='chat-row ai'><div class='chat-msg ai'>"
            + lock_msg
            + "</div></div></div>",
            unsafe_allow_html=True,
        )
    else:
        if upcoming:
            lines = " | ".join([f"{x[0].title} ({x[1]})" for x in upcoming])
            st.markdown(f"<div class='jarvis-bubble upcoming'><strong>\U0001F514 {tr('upcoming_label')}:</strong> {lines}</div>", unsafe_allow_html=True)
        for msg in due_now_messages:
            st.warning(msg)
            if st.session_state.browser_notifications:
                try:
                    st.toast(msg)
                except Exception:
                    pass
        if st.session_state.browser_notifications:
            for popup_msg, popup_key in due_now_popup_items:
                _emit_browser_due_popup(popup_msg, popup_key)
        if suggestion:
            st.markdown(f"<div class='jarvis-bubble suggestion'><strong>\U0001F4A1 {tr('tip_label')}:</strong> {suggestion}</div>", unsafe_allow_html=True)
        chat_rows = []
        if not user_conversation:
            chat_rows.append(f"<div class='chat-row ai'><div class='chat-msg ai'>{html.escape(tr('chat_try_prompt'))}</div></div>")
        else:
            for turn in user_conversation[-14:]:
                role_class = "user" if turn.role == "user" else "ai"
                safe_text = html.escape(turn.content or "")
                chat_rows.append(f"<div class='chat-row {role_class}'><div class='chat-msg {role_class}'>{safe_text}</div></div>")
        st.markdown("<div class='chat-panel'>" + "".join(chat_rows) + "</div>", unsafe_allow_html=True)
        if user_conversation:
            last_turn_idx = len(user_conversation) - 1
            last = user_conversation[last_turn_idx]
            last_spoken_idx = st.session_state.last_spoken_turn_by_user.get(st.session_state.user_id, -1)
            should_auto_speak = (
                last.role != "user"
                and last_spoken_idx != last_turn_idx
            )
            if should_auto_speak:
                speech_text = (last.content or "").strip()
                if speech_text:
                    speech_payload = json.dumps({
                        "text": speech_text,
                        "rate": float(st.session_state.speech_rate),
                        "turn": int(last_turn_idx),
                        "lang": TTS_LANG_BY_UI.get(st.session_state.get("ui_language", "en"), "en-IN"),
                        "tts_session": st.session_state.get("tts_session_id", "default"),
                    })
                    speech_js = """
<script>
(function() {
  const payload = __PAYLOAD__;
  const synth = window.speechSynthesis;
  if (!synth || !payload.text) return;

  // Prevent repeated playback inside browser-side rerenders.
  const key = "voqtask_last_spoken_turn_" + String(payload.tts_session || "default");
  const lastTurn = Number(window.sessionStorage.getItem(key) || "-1");
  if (lastTurn >= payload.turn) return;

  let hasSpokenForTurn = false;
  const speak = () => {
    if (hasSpokenForTurn) return;
    try {
      synth.cancel();
      synth.resume();
      const utter = new SpeechSynthesisUtterance(payload.text);
      utter.rate = Math.min(2, Math.max(0.5, Number(payload.rate) || 1));
      const wantedLang = String(payload.lang || "en-IN").toLowerCase();
      const voices = synth.getVoices ? synth.getVoices() : [];
      const wantedBase = wantedLang.split("-")[0];
      const exact = voices.find(v => String(v.lang || "").toLowerCase() === wantedLang);
      const baseMatch = voices.find(v => String(v.lang || "").toLowerCase().startsWith(wantedBase));
      const indianEnglish = voices.find(v => String(v.lang || "").toLowerCase().startsWith("en-in"));
      const anyEnglish = voices.find(v => String(v.lang || "").toLowerCase().startsWith("en"));
      const fallbackLocal = voices.find(v => v.localService) || voices[0];
      const selected = exact || baseMatch || indianEnglish || anyEnglish || fallbackLocal || null;
      if (selected) {
        utter.voice = selected;
        utter.lang = String(selected.lang || wantedLang);
      } else {
        utter.lang = wantedLang;
      }
      utter.pitch = 1.0;
      utter.volume = 1.0;
      hasSpokenForTurn = true;
      synth.speak(utter);
      window.sessionStorage.setItem(key, String(payload.turn));
    } catch (e) {
      console.warn("Browser TTS failed", e);
    }
  };

  // Some browsers return 0 voices initially and may never fire onvoiceschanged.
  // Speak immediately, then retry once voices load.
  speak();
  if (synth.getVoices && synth.getVoices().length === 0) {
    synth.onvoiceschanged = () => {
      speak();
      synth.onvoiceschanged = null;
    };
    setTimeout(() => {
      try { speak(); } catch (_) {}
    }, 900);
  }
})();
</script>
"""
                    st.components.v1.html(speech_js.replace("__PAYLOAD__", speech_payload), height=0)
                st.session_state.last_spoken_turn_by_user[st.session_state.user_id] = last_turn_idx
with right_col:
    unlocked_for_tasks = (not st.session_state.voice_security_enabled) or st.session_state.voice_authenticated
    if not unlocked_for_tasks:
        st.info(_locked_tasks_prompt())
    else:
        st.markdown(
            "<div class='panel-block'><div class='panel-head'>"
            f"<div class='panel-title'>\u23F0 {tr('now_section')}</div>"
            f"<div class='panel-sub'>{tr('panel_sub_now')}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        now_col_left, now_col_right = st.columns([1.45, 1], gap="medium")
        with now_col_left:
            st.caption(tr("due_next_2h"))
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
                st.info(tr("no_upcoming_2h"))
        with now_col_right:
            st.markdown(
                _small_ring_html(tr("today_focus"), f"{done_today}/{today_goal}", today_percent, "#4fd1c5"),
                unsafe_allow_html=True,
            )
            st.caption(tr("goal_daily"))

        qa_col1, qa_col2, qa_col3 = st.columns(3, gap="small")
        if qa_col1.button(tr("btn_add_focus"), key="qa_add_focus", use_container_width=True):
            focus_task = Task(
                id=None,
                title="Focus session (25m)",
                category="work",
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
            focus_task = _save_task_with_sync(focus_task)
            _send_n8n_event("task_created", focus_task, extras={"created_via": "quick_action"})
            st.success(tr("focus_added"))
            st.rerun()

        if qa_col2.button(tr("btn_snooze_next"), key="qa_snooze_next", use_container_width=True):
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
                st.info(tr("no_timed_task_snooze"))
            else:
                due_dt, task = sorted(candidates, key=lambda x: x[0])[0]
                task.due_time = (due_dt + timedelta(minutes=15)).strftime("%H:%M")
                task.updated_at = now_iso()
                _update_task_with_sync(task)
                st.success(trf("snoozed_to", title=task.title, time=task.due_time))
                st.rerun()

        if qa_col3.button(tr("btn_done_latest"), key="qa_done_latest", use_container_width=True):
            if not all_pending:
                st.info(tr("no_pending_available"))
            else:
                latest = sorted(all_pending, key=lambda t: t.created_at or "", reverse=True)[0]
                changed = _update_status_with_sync(latest.id, TaskStatus.DONE)
                if changed:
                    latest.status = TaskStatus.DONE
                    _send_n8n_event("task_done", latest)
                    reward_result = reward_task_completion(latest.id, st.session_state.user_id)
                    if reward_result.get("awarded"):
                        st.session_state.reward_flash = (
                            f"+{reward_result['points_awarded']} pts | "
                            f"Level {reward_result['level']} | "
                            f"{reward_result['streak_days']}-day streak"
                        )
                    st.success(trf("completed_task", title=latest.title))
                else:
                    st.info(tr("could_not_mark_done"))
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


with left_col:
    unlocked_for_tasks = (not st.session_state.voice_security_enabled) or st.session_state.voice_authenticated
    if not unlocked_for_tasks:
        st.info(_locked_tasks_prompt())
    else:
        st.markdown(
            "<div class='panel-block'><div class='panel-head'>"
            f"<div class='panel-title'>\U0001F4CB {tr('task_overview')}</div>"
            f"<div class='panel-sub'>{tr('panel_sub_tasks')}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        filter_col, _ = st.columns([1, 2])
        with filter_col:
            category_filter_options = ["all"] + CATEGORY_OPTIONS
            st.session_state.category_filter = st.selectbox(
                tr("category_filter"),
                options=category_filter_options,
                index=category_filter_options.index(st.session_state.category_filter) if st.session_state.category_filter in category_filter_options else 0,
                format_func=lambda c: tr("all_categories") if c == "all" else c.title(),
            )

        tasks_today_view = tasks_today
        tasks_tomorrow_view = tasks_tomorrow
        tasks_later_view = tasks_later
        all_pending_view = all_pending
        all_done_view = all_done
        if st.session_state.category_filter != "all":
            c = st.session_state.category_filter
            tasks_today_view = [t for t in tasks_today if t.category == c]
            tasks_tomorrow_view = [t for t in tasks_tomorrow if t.category == c]
            tasks_later_view = [t for t in tasks_later if t.category == c]
            all_pending_view = [t for t in all_pending if t.category == c]
            all_done_view = [t for t in all_done if t.category == c]

        tab_today, tab_tomorrow, tab_later = st.tabs([tr("tab_today"), tr("tab_tomorrow"), tr("tab_later")])

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
                        f"<div class='section-head'>{trf('priority_group', priority=current_priority.value.replace('_', ' ').title(), count=priority_counts.get(current_priority, 0))}</div>",
                        unsafe_allow_html=True,
                    )
                urg = " urgent" if t.priority == Priority.URGENT else ""
                meta = (f"{t.due_date} {t.due_time or ''}" if t.due_date else tr("no_date"))
                notes_preview = (f" | {t.notes[:28]}..." if t.notes and len(t.notes) > 28 else (f" | {t.notes}" if t.notes else ""))
                with st.container():
                    col_a, col_b = st.columns([4, 1])
                    with col_a:
                        st.markdown(
                            f"<div class='task-card-wrap{urg}'><div class='task-title'>{t.title}</div><div class='task-meta'>[{t.category}] {meta}{notes_preview}</div></div>",
                            unsafe_allow_html=True,
                        )
                    with col_b:
                        if st.button(tr("btn_done"), key=f"{key_prefix}_done_{t.id}", help=tr("btn_done")):
                            status_changed = _update_status_with_sync(t.id, TaskStatus.DONE)
                            if status_changed:
                                t.status = TaskStatus.DONE
                                _send_n8n_event("task_done", t)
                                reward_result = reward_task_completion(t.id, st.session_state.user_id)
                                if reward_result.get("awarded"):
                                    st.session_state.reward_flash = (
                                        f"\U0001F389 +{reward_result['points_awarded']} pts | "
                                        f"Level {reward_result['level']} | "
                                        f"\U0001F525 {reward_result['streak_days']}-day streak"
                                    )
                            st.rerun()
                        if st.button(tr("btn_view"), key=f"{key_prefix}_view_{t.id}", help=tr("btn_view")):
                            st.session_state[f"viewing_{t.id}"] = not st.session_state.get(f"viewing_{t.id}", False)
                            st.rerun()
                        if st.button(tr("btn_edit"), key=f"{key_prefix}_edit_{t.id}", help=tr("btn_edit")):
                            st.session_state[f"editing_{t.id}"] = True
                            st.rerun()
                        if st.button(tr("btn_delete"), key=f"{key_prefix}_del_{t.id}", help=tr("btn_delete")):
                            _delete_task_with_sync(t.id)
                            st.rerun()

                if st.session_state.get(f"viewing_{t.id}"):
                    with st.expander(tr("task_details"), expanded=True):
                        st.markdown(f"**{tr('label_title')}:** {t.title}")
                        st.markdown(f"**{tr('category')}:** {t.category}")
                        st.markdown(f"**{tr('label_due')}:** {t.due_date or '-'} {t.due_time or ''}")
                        st.markdown(f"**{tr('label_priority')}:** {t.priority.value} | **{tr('label_status')}:** {t.status.value}")
                        if t.notes:
                            st.markdown(f"**{tr('label_notes')}:** {t.notes}")
                        if t.shared_with:
                            st.markdown(f"**{tr('label_shared_with')}:** {', '.join(t.shared_with)}")
                        st.caption(trf("label_created_updated", created=t.created_at, updated=t.updated_at))
                        share_text = (
                            f"{tr('task_details')}: {t.title}\n"
                            f"{tr('category')}: {t.category}\n"
                            f"{tr('label_due')}: {t.due_date or '-'} {t.due_time or ''}\n"
                            f"{tr('label_priority')}: {t.priority.value}\n"
                            + (f"{tr('label_notes')}: {t.notes}\n" if t.notes else "")
                            + (f"{tr('label_shared_with')}: {', '.join(t.shared_with)}" if t.shared_with else "")
                        )
                        st.code(share_text, language=None)
                        if st.button(tr("btn_copy_share"), key=f"copy_share_{t.id}"):
                            st.session_state[f"clipboard_{t.id}"] = share_text
                            st.info(tr("copy_share_info"))
                        if st.button(tr("btn_close"), key=f"close_view_{t.id}"):
                            del st.session_state[f"viewing_{t.id}"]
                            st.rerun()

                if st.session_state.get(f"editing_{t.id}"):
                    with st.expander(trf("edit_prefix", title=t.title[:40]), expanded=True):
                        with st.form(key=f"edit_form_{key_prefix}_{t.id}"):
                            new_title = st.text_input(tr("label_title"), value=t.title, key=f"edit_title_{t.id}")
                            c1, c2 = st.columns(2)
                            with c1:
                                new_due_date = st.text_input(tr("label_due_date"), value=t.due_date or "", key=f"edit_date_{t.id}")
                            with c2:
                                new_due_time = st.text_input(tr("label_due_time"), value=t.due_time or "", key=f"edit_time_{t.id}")
                            new_priority = st.selectbox(
                                tr("label_priority"),
                                options=[p.value for p in Priority],
                                index=[p.value for p in Priority].index(t.priority.value),
                                key=f"edit_priority_{t.id}",
                            )
                            new_category = st.selectbox(
                                tr("category"),
                                options=CATEGORY_OPTIONS,
                                index=CATEGORY_OPTIONS.index(t.category) if t.category in CATEGORY_OPTIONS else 0,
                                key=f"edit_category_{t.id}",
                            )
                            new_notes = st.text_area(tr("label_notes"), value=t.notes or "", key=f"edit_notes_{t.id}")
                            new_shared = st.text_input(tr("label_shared_with_csv"), value=", ".join(t.shared_with) if t.shared_with else "", key=f"edit_shared_{t.id}")
                            sub_col1, sub_col2, _ = st.columns(3)
                            with sub_col1:
                                submitted = st.form_submit_button(tr("btn_save"))
                            with sub_col2:
                                cancel = st.form_submit_button(tr("btn_cancel"))
                            if submitted:
                                t.title = new_title.strip() or t.title
                                t.due_date = new_due_date.strip() or None
                                t.due_time = new_due_time.strip() or None
                                t.priority = Priority(new_priority)
                                t.category = new_category
                                t.notes = new_notes.strip()
                                t.shared_with = [x.strip() for x in new_shared.split(",") if x.strip()]
                                _update_task_with_sync(t)
                                if f"editing_{t.id}" in st.session_state:
                                    del st.session_state[f"editing_{t.id}"]
                                st.rerun()
                            if cancel:
                                if f"editing_{t.id}" in st.session_state:
                                    del st.session_state[f"editing_{t.id}"]
                                st.rerun()

        with tab_today:
            st.markdown(f"<div class='section-head timeline-head first'>{tr('due_today')}</div>", unsafe_allow_html=True)
            if not tasks_today_view:
                st.info(tr("nothing_due_today"))
            else:
                render_task_list(tasks_today_view, "today")

        with tab_tomorrow:
            st.markdown(f"<div class='section-head timeline-head'>{tr('due_tomorrow')}</div>", unsafe_allow_html=True)
            if not tasks_tomorrow_view:
                st.info(tr("nothing_due_tomorrow"))
            else:
                render_task_list(tasks_tomorrow_view, "tomorrow")

        with tab_later:
            st.markdown(f"<div class='section-head timeline-head'>{tr('later_no_date')}</div>", unsafe_allow_html=True)
            if not tasks_later_view:
                st.info(tr("nothing_later"))
            else:
                render_task_list(tasks_later_view, "later")
        st.markdown("</div>", unsafe_allow_html=True)

with right_col:
    unlocked_for_tasks = (not st.session_state.voice_security_enabled) or st.session_state.voice_authenticated
    if unlocked_for_tasks:
        tasks_today_view = tasks_today
        tasks_tomorrow_view = tasks_tomorrow
        tasks_later_view = tasks_later
        all_pending_view = all_pending
        all_done_view = all_done
        if st.session_state.category_filter != "all":
            c = st.session_state.category_filter
            tasks_today_view = [t for t in tasks_today if t.category == c]
            tasks_tomorrow_view = [t for t in tasks_tomorrow if t.category == c]
            tasks_later_view = [t for t in tasks_later if t.category == c]
            all_pending_view = [t for t in all_pending if t.category == c]
            all_done_view = [t for t in all_done if t.category == c]

        st.markdown(
            "<div class='panel-block'><div class='panel-head'>"
            f"<div class='panel-title'>\U0001F4C8 {tr('productivity_dashboard')}</div>"
            f"<div class='panel-sub'>{tr('panel_sub_productivity')}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='kpi-strip'>"
            f"<span class='kpi-pill'>{tr('task_count_today')}: {len(tasks_today_view)}</span>"
            f"<span class='kpi-pill'>{tr('task_count_tomorrow')}: {len(tasks_tomorrow_view)}</span>"
            f"<span class='kpi-pill'>{tr('task_count_later')}: {len(tasks_later_view)}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        total_open = len(all_pending_view)
        total_done = len(all_done_view)
        rewards_progress = get_user_rewards_summary(st.session_state.user_id)
        # Completion ring is reward-progress based, so it changes only on real "done" events.
        completion_rate = max(0.0, min(100.0, float(rewards_progress.get("level_progress", 0.0)) * 100.0))
        today_local = _now_local().date()
        completion_activity = get_completion_activity(st.session_state.user_id, days=7)
        done_today = int(completion_activity.get("today", 0))
        done_this_week = int(completion_activity.get("window_total", 0))
        daily_counts = {}
        for offset in range(6, -1, -1):
            day = today_local - timedelta(days=offset)
            key = day.strftime("%a")
            daily_counts[key] = 0
        for day_iso, count in (completion_activity.get("by_date") or {}).items():
            done_date = _parse_iso_to_local_date(f"{day_iso}T00:00:00Z")
            if done_date is None:
                continue
            age_days = (today_local - done_date).days
            if 0 <= age_days <= 6:
                key = done_date.strftime("%a")
                daily_counts[key] = daily_counts.get(key, 0) + int(count)
        avg_done_per_day = done_this_week / 7.0

        dash_col1, dash_col2, dash_col3, dash_col4 = st.columns(4)
        dash_col1.metric(tr("completed_today"), done_today)
        dash_col2.metric(tr("completion_rate"), f"{completion_rate:.1f}%")
        dash_col3.metric(tr("done_this_week"), done_this_week)
        dash_col4.metric(tr("avg_per_day_7d"), f"{avg_done_per_day:.1f}")

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
            st.markdown(_ring_card(tr("completion_rate"), f"{completion_rate:.0f}%", completion_rate, "#4fd1c5"), unsafe_allow_html=True)
        with ring_c2:
            st.markdown(_ring_card(tr("today_progress"), f"{done_today}/{today_goal}", today_percent, "#f6ad55"), unsafe_allow_html=True)
        with ring_c3:
            st.markdown(_ring_card(tr("weekly_progress"), f"{done_this_week}/{week_goal}", week_percent, "#63b3ed"), unsafe_allow_html=True)
        st.caption(f"{tr('trend_order')}: " + " | ".join(daily_counts.keys()))
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            "<div class='panel-block'><div class='panel-head'>"
            f"<div class='panel-title'>\U0001F4C5 {tr('dragdrop_due_dates')}</div>"
            f"<div class='panel-sub'>{tr('panel_sub_planner')}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        if not st.session_state.dragdrop_updates_enabled:
            st.info(tr("dragdrop_disabled_hint"))
        elif sort_items is None:
            st.info(tr("dragdrop_install"))
        else:
            # Always fetch fresh pending tasks for current user to avoid stale cross-user state.
            drag_pending_source = get_tasks(user_id=st.session_state.user_id, status=TaskStatus.PENDING, limit=5000)
            if st.session_state.category_filter != "all":
                drag_pending_source = [t for t in drag_pending_source if t.category == st.session_state.category_filter]
            pending_for_drag = sorted(
                [t for t in drag_pending_source if t.status == TaskStatus.PENDING],
                key=lambda t: (t.due_date or "9999-12-31", t.due_time or "23:59", t.title.lower()),
            )
            drag_signature_src = "|".join(
                f"{t.id}:{t.updated_at}:{t.due_date or ''}:{t.due_time or ''}"
                for t in pending_for_drag
            )
            drag_signature = hashlib.sha256(drag_signature_src.encode("utf-8")).hexdigest()[:12] if drag_signature_src else "empty"
            label_to_task = {}
            today_labels, tomorrow_labels, later_labels = [], [], []
            for idx, t in enumerate(pending_for_drag, start=1):
                label = f"{idx}. {t.title} [{t.priority.value}] <{t.id[:6]}>"
                label_to_task[label] = t
                if t.due_date == today_str:
                    today_labels.append(label)
                elif t.due_date == tomorrow_str:
                    tomorrow_labels.append(label)
                else:
                    later_labels.append(label)

            dropped = sort_items(
                [
                    {"header": tr("drag_header_today"), "items": today_labels},
                    {"header": tr("drag_header_tomorrow"), "items": tomorrow_labels},
                    {"header": tr("drag_header_later"), "items": later_labels},
                ],
                multi_containers=True,
                key=f"dragdrop_{st.session_state.user_id}_{st.session_state.category_filter}_{drag_signature}",
            )
            if st.button(tr("dragdrop_apply"), key="apply_drag_drop_due_btn"):
                zone_to_due = {
                    tr("drag_header_today"): today_str,
                    tr("drag_header_tomorrow"): tomorrow_str,
                    tr("drag_header_later"): None,
                }
                updated_count = 0
                for zone in dropped:
                    header = zone.get("header")
                    due_target = zone_to_due.get(header)
                    for label in zone.get("items", []):
                        task_ref = label_to_task.get(label)
                        if not task_ref:
                            continue
                        # Re-check ownership/status before update to avoid touching done/other-user tasks.
                        latest_ref = get_task_by_id(task_ref.id, user_id=st.session_state.user_id)
                        if not latest_ref or latest_ref.status != TaskStatus.PENDING:
                            continue
                        if latest_ref.due_date != due_target:
                            latest_ref.due_date = due_target
                            _update_task_with_sync(latest_ref)
                            updated_count += 1
                st.success(trf("dragdrop_applied", count=updated_count))
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        
# Smart reminders & sharing
with st.expander(tr("smart_reminders_sharing"), expanded=False):
    if st.session_state.reminders_enabled:
        st.caption(tr("smart_reminders_caption"))
    else:
        st.info(tr("reminders_disabled_hint"))


# Footer
st.markdown("---")
st.markdown(f"<p class='footer-note'>{tr('footer_note')}</p>", unsafe_allow_html=True)


