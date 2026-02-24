from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional, List
from enum import Enum


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: Optional[str]
    title: str
    category: str
    due_date: Optional[str]
    due_time: Optional[str]
    priority: Priority
    status: TaskStatus
    created_at: str
    updated_at: str
    shared_with: List[str]
    notes: str
    source: str

    def __post_init__(self):
        if self.shared_with is None:
            self.shared_with = []
        if not self.category:
            self.category = "general"
        if self.notes is None:
            self.notes = ""
        if self.source is None:
            self.source = "voice"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "due_date": self.due_date,
            "due_time": self.due_time,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "shared_with": self.shared_with,
            "notes": self.notes,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        sh = d.get("shared_with")
        if isinstance(sh, list):
            shared_with = sh
        elif isinstance(sh, str):
            shared_with = [x.strip() for x in sh.split(",") if x.strip()]
        else:
            shared_with = []
        return cls(
            id=d.get("id"),
            title=d.get("title") or "(No title)",
            category=(d.get("category") or "general"),
            due_date=d.get("due_date"),
            due_time=d.get("due_time"),
            priority=Priority(d.get("priority", "medium")),
            status=TaskStatus(d.get("status", "pending")),
            created_at=d.get("created_at") or now_iso(),
            updated_at=d.get("updated_at") or now_iso(),
            shared_with=shared_with,
            notes=d.get("notes", ""),
            source=d.get("source", "voice"),
        )


def now_iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ConversationTurn:
    """Represents a single turn in the app conversation."""
    role: str  # "user" or "app"
    content: str
    timestamp: str
    
    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "ConversationTurn":
        return cls(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            timestamp=d.get("timestamp", now_iso()),
        )
