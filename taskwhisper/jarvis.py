# Conversational helpers: multi-turn context, proactive suggestions, replies
from datetime import datetime, timedelta, UTC
from typing import List, Optional
from .models import Task, TaskStatus, ConversationTurn, now_iso
from . import storage


def get_proactive_suggestion(tasks: List[Task]) -> Optional[str]:
    """Proactive suggestion based on current task state."""
    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    today_tasks = [t for t in pending if t.due_date == today]
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_tasks = [t for t in pending if t.due_date == tomorrow]

    if len(today_tasks) >= 6:
        return "I noticed you have a lot scheduled today. Want me to suggest moving something to tomorrow?"
    if tomorrow_tasks and not today_tasks:
        return "You're all set for today. Tomorrow you have " + str(len(tomorrow_tasks)) + " task(s). Want a reminder in the morning?"
    if len(pending) >= 10:
        return "You have " + str(len(pending)) + " open tasks. Want me to list the top 3 by priority?"
    return None


def reply_to_user(
    user_message: str,
    conversation_history: List[ConversationTurn],
    tasks_today: List[Task],
    tasks_tomorrow: List[Task],
    task_created: Optional[Task] = None,
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
            return f"{title}: none."
        ordered = sorted(tasks, key=_task_sort_key)[:limit]
        lines = []
        for i, task in enumerate(ordered, start=1):
            when = ""
            if task.due_date:
                when = f" ({task.due_date}" + (f" {task.due_time}" if task.due_time else "") + ")"
            lines.append(f"{i}. {task.title} [{task.priority.value}]{when}")
        suffix = ""
        if len(tasks) > limit:
            suffix = f" Showing {limit} of {len(tasks)}."
        return title + ":\n" + "\n".join(lines) + suffix
    # Acknowledge task creation
    if task_created:
        parts = [f"Done. I've added \"{task_created.title}\"."]
        if task_created.due_date:
            parts.append(f" Due {task_created.due_date}" + (f" at {task_created.due_time}" if task_created.due_time else "") + ".")
        if task_created.priority.value == "urgent":
            parts.append(" Marked as urgent.")
        return "".join(parts).strip()

    # Greetings
    if any(lower.startswith(x) for x in ["hi", "hey", "hello", "good morning", "good evening"]):
        return "Hello. What would you like to do? You can add a task by voice or ask what's due today or tomorrow."

    # What's due
    if "today" in lower and ("what" in lower or "due" in lower or "schedule" in lower):
        if not tasks_today:
            return "Nothing due today. Want to add something?"
        return f"You have {len(tasks_today)} task(s) today. Check your Today list below."

    if "tomorrow" in lower and ("what" in lower or "due" in lower):
        if not tasks_tomorrow:
            return "Nothing scheduled for tomorrow yet."
        return f"You have {len(tasks_tomorrow)} task(s) tomorrow. See the Tomorrow section."

    # List tasks on request
    wants_list = any(k in lower for k in ["list", "show", "what are", "display"])
    mentions_tasks = any(k in lower for k in ["task", "tasks", "to do", "todo"])
    asks_necessary = any(k in lower for k in ["necessary", "important", "priority", "urgent"])
    if wants_list and (mentions_tasks or asks_necessary):
        pending_tasks = storage.get_tasks(status=TaskStatus.PENDING, limit=500)
        if asks_necessary:
            necessary = [t for t in pending_tasks if t.priority.value in ("urgent", "high")]
            if not necessary:
                return "You have no urgent/high-priority pending tasks right now."
            return _format_tasks(necessary, "Necessary tasks", limit=8)
        if not pending_tasks:
            return "You have no pending tasks."
        return _format_tasks(pending_tasks, "Pending tasks", limit=10)

    # Thanks
    if "thank" in lower or "thanks" in lower:
        return "You're welcome. Anything else?"

    # Default
    return "You can say something like: \"Remind me to buy milk tomorrow at 5pm\" or \"What do I have today?\""
