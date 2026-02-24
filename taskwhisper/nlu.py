# Natural language understanding for task creation (no rigid commands)
import re
from datetime import datetime, timedelta
from typing import Tuple, Optional
from .models import Task, Priority, TaskStatus, now_iso


# Patterns for date/time and priority
TOMORROW = re.compile(r"\b(tomorrow|tmrw|tmr)\b", re.I)
TODAY = re.compile(r"\b(today|tonight|this evening)\b", re.I)
NEXT_WEEK = re.compile(r"\b(next week|next monday|next tuesday|next wednesday|next thursday|next friday|next saturday|next sunday)\b", re.I)
NEXT_WEEKDAY = re.compile(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
ON_WEEKDAY = re.compile(r"\b(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
TIME = re.compile(r"\b(at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.?)?(?=\s|$|[,.!?])", re.I)
IN_N_HOURS = re.compile(r"\bin\s+(\d+)\s*(hour|hr)s?\b", re.I)
IN_N_DAYS = re.compile(r"\bin\s+(\d+)\s*days?\b", re.I)
URGENT = re.compile(r"\b(urgent|asap|as soon as possible|critical|important)\b", re.I)
HIGH_PRIO = re.compile(r"\b(high priority|high-priority|priority high|top priority)\b", re.I)
MEDIUM_PRIO = re.compile(r"\b(medium priority|normal priority|priority medium)\b", re.I)
LOW_PRIO = re.compile(r"\b(whenever|low priority|no rush|someday)\b", re.I)
REMIND = re.compile(r"\b(remind me to|reminder to|don't forget to|remember to|add task|task:|todo:?)\s*", re.I)
SHARE_WITH = re.compile(r"\bshare\s+with\s+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9.-]+|\w+)\b", re.I)
CATEGORY_HINT = re.compile(
    r"\b(?:in|under|for)\s+(finance|financial|work|office|personal|home|health|medical|study|learning|shopping|groceries|family|fitness|travel)\b",
    re.I,
)
LIST_INTENT = re.compile(
    r"\b(list|show|display|what(?:'s| is| are)|which)\b.*\b(task|tasks|todo|to do)\b",
    re.I,
)
LEADING_TASK_FILLER = re.compile(
    r"^\s*(?:please\s+)?(?:can you|could you|would you|i need you to|i want you to|hey jarvis|jarvis)?\s*"
    r"(?:add\s+to\s+(?:the\s+)?task|add(?:\s+this)?(?:\s+task)?|create(?:\s+a)?(?:\s+new)?\s+task|"
    r"set(?:\s+a)?\s+reminder|remind me to|make(?:\s+a)?\s+todo|task(?:\s+is)?(?:\s+to)?|"
    r"the\s+task(?:\s+is)?(?:\s+to)?|todo(?:\s+is)?(?:\s+to)?|i need to|i have to|i must|"
    r"don't forget to|remember to)\s*(?::|-)?\s*",
    re.I,
)
TRAILING_TASK_FILLER = re.compile(r"\b(please|thanks|thank you)\b\s*$", re.I)
MERIDIEM_ONLY = re.compile(r"\b(a\.?m\.?|p\.?m\.?)\b\.?", re.I)
WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
CATEGORY_ALIAS = {
    "financial": "finance",
    "office": "work",
    "medical": "health",
    "learning": "study",
    "groceries": "shopping",
}
AUTO_CATEGORY_KEYWORDS = {
    "finance": [
        "bill",
        "electricity bill",
        "current bill",
        "emi",
        "loan",
        "credit card",
        "rent",
        "insurance premium",
        "subscription renewal",
        "payment",
    ],
}


def _parse_time(match) -> Optional[str]:
    hour = int(match.group(2))
    minute = int(match.group(3)) if match.group(3) else 0
    ampm = (match.group(4) or "").lower()
    if "p" in ampm and hour < 12:
        hour += 12
    if "a" in ampm and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _date_for_tomorrow() -> str:
    return (datetime.now().astimezone() + timedelta(days=1)).strftime("%Y-%m-%d")


def _date_for_today() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _date_for_next_week() -> Optional[str]:
    today = datetime.now().astimezone().date()
    for _ in range(8):
        today += timedelta(days=1)
        if today.weekday() == 0:  # next Monday
            return today.strftime("%Y-%m-%d")
    return None


def _date_for_next_weekday(name: str) -> Optional[str]:
    target = WEEKDAY_INDEX.get((name or "").lower())
    if target is None:
        return None
    today = datetime.now().astimezone().date()
    delta = (target - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return (today + timedelta(days=delta)).strftime("%Y-%m-%d")


def _extract_category(text: str) -> Optional[str]:
    source = (text or "").lower()
    m = CATEGORY_HINT.search(source)
    if not m:
        for category, keywords in AUTO_CATEGORY_KEYWORDS.items():
            if any(keyword in source for keyword in keywords):
                return category
        return None
    raw = m.group(1).lower().strip()
    return CATEGORY_ALIAS.get(raw, raw)


def _clean_task_title(raw: str) -> str:
    title = re.sub(r"^\s*[:,-]+\s*", "", raw.strip())
    # Users often say command wrappers twice; remove repeatedly from the start.
    for _ in range(3):
        next_title = LEADING_TASK_FILLER.sub("", title, count=1).strip()
        if next_title == title:
            break
        title = next_title
    title = TRAILING_TASK_FILLER.sub("", title).strip()
    return title


def parse_task_from_text(text: str) -> Optional[Task]:
    """Parse natural language into a Task. Returns None if not task-like."""
    if not text or len(text.strip()) < 2:
        return None
    if LIST_INTENT.search(text):
        return None
    raw = text.strip()
    # Strip common prefixes
    raw = REMIND.sub("", raw, count=1).strip()
    raw = _clean_task_title(raw)
    if not raw:
        return None

    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority = Priority.MEDIUM

    if TOMORROW.search(text):
        due_date = _date_for_tomorrow()
    elif TODAY.search(text):
        due_date = _date_for_today()
    elif NEXT_WEEKDAY.search(text):
        weekday_match = NEXT_WEEKDAY.search(text)
        due_date = _date_for_next_weekday(weekday_match.group(1)) if weekday_match else None
    elif NEXT_WEEK.search(text):
        due_date = _date_for_next_week()
    else:
        weekday_match = ON_WEEKDAY.search(text)
        if weekday_match:
            due_date = _date_for_next_weekday(weekday_match.group(1))

    time_match = TIME.search(text)
    if time_match:
        due_time = _parse_time(time_match)
        if due_date is None and (TODAY.search(text) or "tonight" in text.lower() or "evening" in text.lower()):
            due_date = _date_for_today()
        elif due_date is None:
            due_date = _date_for_today()

    in_hrs = IN_N_HOURS.search(text)
    if in_hrs and due_date is None:
        delta = timedelta(hours=int(in_hrs.group(1)))
        dt = datetime.now().astimezone() + delta
        due_date = dt.strftime("%Y-%m-%d")
        due_time = dt.strftime("%H:%M")

    in_days = IN_N_DAYS.search(text)
    if in_days and due_date is None:
        delta = timedelta(days=int(in_days.group(1)))
        due_date = (datetime.now().astimezone() + delta).strftime("%Y-%m-%d")

    if URGENT.search(text):
        priority = Priority.URGENT
    elif HIGH_PRIO.search(text):
        priority = Priority.HIGH
    elif MEDIUM_PRIO.search(text):
        priority = Priority.MEDIUM
    elif LOW_PRIO.search(text):
        priority = Priority.LOW

    category = _extract_category(text)

    # Clean title: remove date/time phrases for display
    title = raw
    for pat in [
        TOMORROW,
        TODAY,
        NEXT_WEEKDAY,
        ON_WEEKDAY,
        NEXT_WEEK,
        TIME,
        IN_N_HOURS,
        IN_N_DAYS,
        URGENT,
        HIGH_PRIO,
        MEDIUM_PRIO,
        LOW_PRIO,
        CATEGORY_HINT,
    ]:
        title = pat.sub("", title)
    title = MERIDIEM_ONLY.sub("", title)
    title = re.sub(r"\s*[,;:.!?-]+\s*$", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        title = raw[:80]

    shared = []
    share_m = SHARE_WITH.search(text)
    if share_m:
        shared.append(share_m.group(1).strip())

    now = now_iso()
    return Task(
        id=None,
        title=title,
        category=(category or "general"),
        due_date=due_date,
        due_time=due_time,
        priority=priority,
        status=TaskStatus.PENDING,
        created_at=now,
        updated_at=now,
        shared_with=shared,
        notes="",
        source="voice",
    )


def is_task_creation(text: str) -> bool:
    """Heuristic: does this look like creating a task?"""
    lower = text.lower().strip()
    if len(lower) < 3:
        return False
    if LIST_INTENT.search(text):
        return False
    triggers = [
        "remind", "remember", "don't forget", "add", "task", "todo",
        "schedule", "set", "create", "need to", "have to", "got to",
        "i need", "i must", "i should", "put on", "add to my",
    ]
    return any(t in lower for t in triggers) or parse_task_from_text(text) is not None
