# Conversational helpers: multi-turn context, proactive suggestions, replies
from datetime import datetime, timedelta, UTC
from typing import List, Optional
from .models import Task, TaskStatus, ConversationTurn, now_iso
from . import storage


def _repair_mojibake(text: str) -> str:
    """Best-effort fix for UTF-8 text that was decoded as latin-1/cp1252."""
    if not text:
        return text
    # Fast path: likely already fine.
    if "à" not in text and "â" not in text:
        return text
    try:
        repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if repaired and repaired != text:
            return repaired
    except Exception:
        pass
    return text


LANG_TEXT = {
    "en": {
        "suggest_busy": "I noticed you have a lot scheduled today. Want me to suggest moving something to tomorrow?",
        "suggest_tomorrow": "You're all set for today. Tomorrow you have {count} task(s). Want a reminder in the morning?",
        "suggest_open": "You have {count} open tasks. Want me to list the top 3 by priority?",
        "none": "{title}: none.",
        "showing": " Showing {limit} of {count}.",
        "done_added": "Done. I've added \"{title}\".",
        "due": " Due {date}{time}.",
        "at": " at {time}",
        "marked_urgent": " Marked as urgent.",
        "hello": "Hello. What would you like to do? You can add a task by voice or ask what's due today or tomorrow.",
        "nothing_today": "Nothing due today. Want to add something?",
        "have_today": "You have {count} task(s) today. Check your Today list below.",
        "nothing_tomorrow": "Nothing scheduled for tomorrow yet.",
        "have_tomorrow": "You have {count} task(s) tomorrow. See the Tomorrow section.",
        "no_necessary": "You have no urgent/high-priority pending tasks right now.",
        "necessary_tasks": "Necessary tasks",
        "no_pending": "You have no pending tasks.",
        "pending_tasks": "Pending tasks",
        "welcome": "You're welcome. Anything else?",
        "default": "You can say something like: \"Remind me to buy milk tomorrow at 5pm\" or \"What do I have today?\"",
    },
    "ta": {
        "suggest_busy": "இன்று உங்களுக்கு நிறைய பணிகள் உள்ளன. சிலவற்றை நாளைக்கு மாற்ற பரிந்துரைக்கவா?",
        "suggest_tomorrow": "இன்றைக்கு நீங்கள் முடித்துவிட்டீர்கள். நாளைக்கு {count} பணி உள்ளது. காலை நினைவூட்டலா?",
        "suggest_open": "உங்களிடம் {count} நிலுவைப் பணிகள் உள்ளன. முன்னுரிமை 3 பணிகளை காட்டவா?",
        "none": "{title}: எதுவும் இல்லை.",
        "showing": " {count} இல் {limit} மட்டும் காட்டப்படுகிறது.",
        "done_added": "சரி. \"{title}\" பணியை சேர்த்துவிட்டேன்.",
        "due": " கடைசி நாள் {date}{time}.",
        "at": " {time} மணிக்கு",
        "marked_urgent": " அவசரமாக குறிக்கப்பட்டது.",
        "hello": "வணக்கம். என்ன செய்ய விரும்புகிறீர்கள்? குரலில் பணி சேர்க்கலாம் அல்லது இன்று/நாளை பணிகளை கேட்கலாம்.",
        "nothing_today": "இன்றைக்கு செய்ய வேண்டிய பணி இல்லை. புதிய பணி சேர்க்கவா?",
        "have_today": "இன்று உங்களுக்கு {count} பணி உள்ளது. கீழே Today பட்டியலை பார்க்கவும்.",
        "nothing_tomorrow": "நாளைக்கு இன்னும் பணி திட்டமிடப்படவில்லை.",
        "have_tomorrow": "நாளைக்கு உங்களுக்கு {count} பணி உள்ளது. Tomorrow பகுதியைப் பார்க்கவும்.",
        "no_necessary": "தற்போது அவசர/உயர் முன்னுரிமை நிலுவைப் பணிகள் இல்லை.",
        "necessary_tasks": "முக்கிய பணிகள்",
        "no_pending": "நிலுவைப் பணிகள் இல்லை.",
        "pending_tasks": "நிலுவைப் பணிகள்",
        "welcome": "நன்றி. இன்னும் ஏதேனும் வேண்டுமா?",
        "default": "\"நாளை மாலை 5 மணிக்கு பால் வாங்க நினைவூட்டு\" என்று சொல்லலாம்.",
    },
    "te": {
        "suggest_busy": "ఈ రోజు మీకు చాలా టాస్కులు ఉన్నాయి. కొన్ని రేపటికి మార్చమంటారా?",
        "suggest_tomorrow": "ఈ రోజు పనులు పూర్తయ్యాయి. రేపటికి {count} టాస్క్(లు) ఉన్నాయి. ఉదయం రిమైండర్ ఇవ్వాలా?",
        "suggest_open": "మీ వద్ద {count} ఓపెన్ టాస్కులు ఉన్నాయి. టాప్ 3 ప్రాధాన్యత టాస్కులు చూపాలా?",
        "none": "{title}: ఏవి లేవు.",
        "showing": " {count} లో {limit} మాత్రమే చూపిస్తున్నాం.",
        "done_added": "సరే. \"{title}\" టాస్క్ జోడించాను.",
        "due": " గడువు {date}{time}.",
        "at": " {time} కు",
        "marked_urgent": " అత్యవసరంగా గుర్తించబడింది.",
        "hello": "హలో. ఏమి చేయాలి? వాయిస్‌తో టాస్క్ జోడించండి లేదా ఈరోజు/రేపటి టాస్కులు అడగండి.",
        "nothing_today": "ఈ రోజుకి డ్యూ టాస్కులు లేవు. కొత్తది జోడించాలా?",
        "have_today": "ఈ రోజు మీకు {count} టాస్క్(లు) ఉన్నాయి. దిగువ Today జాబితా చూడండి.",
        "nothing_tomorrow": "రేపటికి ఇంకా టాస్కులు లేవు.",
        "have_tomorrow": "రేపటికి మీకు {count} టాస్క్(లు) ఉన్నాయి. Tomorrow విభాగం చూడండి.",
        "no_necessary": "ఇప్పుడే అత్యవసర/హై ప్రాధాన్యత పెండింగ్ టాస్కులు లేవు.",
        "necessary_tasks": "ముఖ్య టాస్కులు",
        "no_pending": "పెండింగ్ టాస్కులు లేవు.",
        "pending_tasks": "పెండింగ్ టాస్కులు",
        "welcome": "స్వాగతం. ఇంకేమైనా?",
        "default": "\"రేపు సాయంత్రం 5కి పాలు కొనమని గుర్తు చేయి\" అని చెప్పండి.",
    },
    "hi": {
        "suggest_busy": "आज आपके पास बहुत सारे काम हैं। क्या कुछ कल पर शिफ्ट कर दूं?",
        "suggest_tomorrow": "आज के लिए सब सेट है। कल आपके {count} टास्क हैं। सुबह रिमाइंडर चाहिए?",
        "suggest_open": "आपके पास {count} ओपन टास्क हैं। टॉप 3 प्रायोरिटी दिखाऊं?",
        "none": "{title}: कोई नहीं।",
        "showing": " {count} में से {limit} दिखा रहे हैं।",
        "done_added": "ठीक है। \"{title}\" टास्क जोड़ दिया है।",
        "due": " ड्यू {date}{time}.",
        "at": " {time} बजे",
        "marked_urgent": " इसे अर्जेंट मार्क किया गया है।",
        "hello": "नमस्ते। क्या करना है? आप आवाज़ से टास्क जोड़ सकते हैं या आज/कल के टास्क पूछ सकते हैं।",
        "nothing_today": "आज के लिए कोई टास्क ड्यू नहीं है। नया जोड़ें?",
        "have_today": "आज आपके {count} टास्क हैं। नीचे Today सूची देखें।",
        "nothing_tomorrow": "कल के लिए अभी कोई टास्क नहीं है।",
        "have_tomorrow": "कल आपके {count} टास्क हैं। Tomorrow सेक्शन देखें।",
        "no_necessary": "अभी कोई अर्जेंट/हाई-प्रायोरिटी पेंडिंग टास्क नहीं है।",
        "necessary_tasks": "ज़रूरी टास्क",
        "no_pending": "कोई पेंडिंग टास्क नहीं है।",
        "pending_tasks": "पेंडिंग टास्क",
        "welcome": "स्वागत है। और कुछ?",
        "default": "\"कल शाम 5 बजे दूध खरीदने की याद दिलाओ\" जैसा बोल सकते हैं।",
    },
}


def _t(lang: str, key: str, **kwargs) -> str:
    table = LANG_TEXT.get(lang, LANG_TEXT["en"])
    text = table.get(key, LANG_TEXT["en"].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return _repair_mojibake(text)


def get_proactive_suggestion(tasks: List[Task], language: str = "en") -> Optional[str]:
    """Proactive suggestion based on current task state."""
    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    today_tasks = [t for t in pending if t.due_date == today]
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_tasks = [t for t in pending if t.due_date == tomorrow]

    if len(today_tasks) >= 6:
        return _t(language, "suggest_busy")
    if tomorrow_tasks and not today_tasks:
        return _t(language, "suggest_tomorrow", count=len(tomorrow_tasks))
    if len(pending) >= 10:
        return _t(language, "suggest_open", count=len(pending))
    return None


def reply_to_user(
    user_message: str,
    conversation_history: List[ConversationTurn],
    tasks_today: List[Task],
    tasks_tomorrow: List[Task],
    task_created: Optional[Task] = None,
    language: str = "en",
    user_id: str = "default",
) -> str:
    """Generate a short, conversational reply (rule-based, no API)."""
    lower = user_message.lower().strip()

    def _task_sort_key(task: Task):
        priority_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        due_date = task.due_date or "9999-12-31"
        due_time = task.due_time or "23:59"
        created_at = task.created_at or ""
        return (priority_rank.get(task.priority.value, 99), due_date, due_time, created_at)

    def _format_tasks(tasks: List[Task], title: str, limit: int = 8) -> str:
        if not tasks:
            return _t(language, "none", title=title)
        ordered = sorted(tasks, key=_task_sort_key)[:limit]
        lines = []
        for i, task in enumerate(ordered, start=1):
            when = ""
            if task.due_date:
                when = f" ({task.due_date}" + (f" {task.due_time}" if task.due_time else "") + ")"
            lines.append(f"{i}. {task.title} [{task.priority.value}]{when}")
        suffix = ""
        if len(tasks) > limit:
            suffix = _t(language, "showing", limit=limit, count=len(tasks))
        return title + ":\n" + "\n".join(lines) + suffix
    # Acknowledge task creation
    if task_created:
        parts = [_t(language, "done_added", title=task_created.title)]
        if task_created.due_date:
            time_text = _t(language, "at", time=task_created.due_time) if task_created.due_time else ""
            parts.append(_t(language, "due", date=task_created.due_date, time=time_text))
        if task_created.priority.value == "urgent":
            parts.append(_t(language, "marked_urgent"))
        return "".join(parts).strip()

    # Greetings
    if any(lower.startswith(x) for x in ["hi", "hey", "hello", "good morning", "good evening"]):
        return _t(language, "hello")

    # What's due
    if "today" in lower and ("what" in lower or "due" in lower or "schedule" in lower):
        if not tasks_today:
            return _t(language, "nothing_today")
        return _t(language, "have_today", count=len(tasks_today))

    if "tomorrow" in lower and ("what" in lower or "due" in lower):
        if not tasks_tomorrow:
            return _t(language, "nothing_tomorrow")
        return _t(language, "have_tomorrow", count=len(tasks_tomorrow))

    # List tasks on request
    wants_list = any(k in lower for k in ["list", "show", "what are", "display"])
    mentions_tasks = any(k in lower for k in ["task", "tasks", "to do", "todo"])
    asks_necessary = any(k in lower for k in ["necessary", "important", "priority", "urgent"])
    if wants_list and (mentions_tasks or asks_necessary):
        pending_tasks = storage.get_tasks(user_id=user_id, status=TaskStatus.PENDING, limit=500)
        if asks_necessary:
            necessary = [t for t in pending_tasks if t.priority.value in ("urgent", "high")]
            if not necessary:
                return _t(language, "no_necessary")
            return _format_tasks(necessary, _t(language, "necessary_tasks"), limit=8)
        if not pending_tasks:
            return _t(language, "no_pending")
        return _format_tasks(pending_tasks, _t(language, "pending_tasks"), limit=10)

    # Thanks
    if "thank" in lower or "thanks" in lower:
        return _t(language, "welcome")

    # Default
    return _t(language, "default")
