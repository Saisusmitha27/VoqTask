import sqlite3
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta, UTC
from .models import Task, TaskStatus, Priority, now_iso
from . import config


def get_conn():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(config.DB_PATH))


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'default',
            title TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            due_date TEXT,
            due_time TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            shared_with TEXT,
            notes TEXT,
            source TEXT DEFAULT 'voice'
        )
    """)
    # Backward-compatible migration for existing DBs created before category support.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
    if "category" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN category TEXT DEFAULT 'general'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            points INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, task_id, reason)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rewards_user_created ON rewards(user_id, created_at DESC);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            passkey_norm TEXT,
            voiceprint TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_passkey ON users(passkey_norm);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            task_id TEXT,
            task_title TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_events_user_created ON user_events(user_id, created_at DESC);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_events_created ON user_events(created_at DESC);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            settings_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("INSERT OR IGNORE INTO users (user_id, display_name, passkey_norm, voiceprint, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (
        "default", "Default User", "", "", now_iso(), now_iso()
    ))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_progress (
            user_id TEXT PRIMARY KEY,
            points INTEGER NOT NULL DEFAULT 0,
            tasks_completed INTEGER NOT NULL DEFAULT 0,
            streak_days INTEGER NOT NULL DEFAULT 0,
            last_completion_date TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_task(task: Task, user_id: str = "default") -> Task:
    import uuid
    if not task.id:
        task.id = str(uuid.uuid4())
    task.updated_at = now_iso()
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO tasks (id, user_id, title, category, due_date, due_time, priority, status, created_at, updated_at, shared_with, notes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task.id, user_id, task.title, task.category, task.due_date, task.due_time, task.priority.value, task.status.value,
        task.created_at, task.updated_at, ",".join(task.shared_with), task.notes, task.source
    ))
    conn.commit()
    conn.close()
    return task


def get_tasks(
    user_id: str = "default",
    due_date: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    category: Optional[str] = None,
    limit: int = 500,
) -> List[Task]:
    conn = get_conn()
    q = "SELECT id, title, category, due_date, due_time, priority, status, created_at, updated_at, shared_with, notes, source FROM tasks WHERE user_id = ?"
    params = [user_id]
    if due_date is not None:
        q += " AND due_date = ?"
        params.append(due_date)
    if status is not None:
        q += " AND status = ?"
        params.append(status.value)
    if category is not None:
        q += " AND category = ?"
        params.append(category)
    q += " ORDER BY due_date ASC, due_time ASC, created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append(Task(
            id=r[0], title=r[1], category=r[2] or "general", due_date=r[3], due_time=r[4],
            priority=Priority(r[5]), status=TaskStatus(r[6]),
            created_at=r[7], updated_at=r[8],
            shared_with=(r[9] or "").split(",") if r[9] else [],
            notes=r[10] or "", source=r[11] or "voice",
        ))
    return out


def get_task_by_id(task_id: str, user_id: str = "default") -> Optional[Task]:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, title, category, due_date, due_time, priority, status, created_at, updated_at, shared_with, notes, source FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, user_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return Task(
        id=row[0], title=row[1], category=row[2] or "general", due_date=row[3], due_time=row[4],
        priority=Priority(row[5]), status=TaskStatus(row[6]),
        created_at=row[7], updated_at=row[8],
        shared_with=row[9].split(",") if row[9] else [],
        notes=row[10] or "", source=row[11] or "voice",
    )


def update_task_status(task_id: str, status: TaskStatus, user_id: str = "default") -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND user_id = ? AND status != ?",
        (status.value, now_iso(), task_id, user_id, status.value),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def update_task(task: Task, user_id: str = "default") -> Task:
    """Full update of an existing task (by id). Preserves created_at."""
    existing = get_task_by_id(task.id, user_id=user_id)
    if not existing:
        return save_task(task, user_id=user_id)
    task.created_at = existing.created_at
    return save_task(task, user_id=user_id)


def delete_task(task_id: str, user_id: str = "default") -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def clear_user_runtime_data(user_id: str = "default") -> None:
    """Clear user runtime data while keeping the profile row."""
    conn = get_conn()
    conn.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM rewards WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM user_events WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def _compute_level(points: int) -> int:
    return max(1, (points // 100) + 1)


def get_user_rewards_summary(user_id: str = "default") -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT points, tasks_completed, streak_days FROM user_progress WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        points = 0
        tasks_completed = 0
        streak_days = 0
    else:
        points = int(row[0] or 0)
        tasks_completed = int(row[1] or 0)
        streak_days = int(row[2] or 0)
    level = _compute_level(points)
    level_floor = (level - 1) * 100
    level_ceiling = level * 100
    points_in_level = points - level_floor
    needed_for_next = level_ceiling - points
    return {
        "points": points,
        "tasks_completed": tasks_completed,
        "streak_days": streak_days,
        "level": level,
        "points_in_level": points_in_level,
        "needed_for_next": needed_for_next,
        "level_progress": (points_in_level / 100.0) if points > 0 else 0.0,
    }


def get_completion_activity(user_id: str = "default", days: int = 7) -> dict:
    """Return completion counts from immutable rewards history (delete-safe)."""
    safe_days = max(1, min(int(days or 7), 90))
    today = datetime.now(UTC).date()
    start_date = (today - timedelta(days=safe_days - 1)).strftime("%Y-%m-%d")

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(DISTINCT task_id) AS completed_count
        FROM rewards
        WHERE user_id = ? AND reason = 'task_complete' AND substr(created_at, 1, 10) >= ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (user_id, start_date),
    ).fetchall()
    conn.close()

    by_date = {str(r[0]): int(r[1] or 0) for r in rows}
    today_key = today.strftime("%Y-%m-%d")
    window_total = sum(by_date.values())
    return {
        "today": int(by_date.get(today_key, 0)),
        "window_total": int(window_total),
        "by_date": by_date,
    }


def reward_task_completion(task_id: str, user_id: str = "default") -> dict:
    """Award completion points once per task and update user progress."""
    task = get_task_by_id(task_id, user_id=user_id)
    if not task or task.status != TaskStatus.DONE:
        return {"awarded": False, "points_awarded": 0, **get_user_rewards_summary(user_id)}

    reward_items = [("task_complete", 10)]
    if task.priority == Priority.URGENT:
        reward_items.append(("urgent_complete", 5))

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).strftime("%Y-%m-%d")
    awarded_points = 0
    now = now_iso()

    conn = get_conn()
    try:
        for reason, pts in reward_items:
            try:
                conn.execute(
                    "INSERT INTO rewards (user_id, task_id, reason, points, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, task_id, reason, pts, now),
                )
                awarded_points += pts
            except sqlite3.IntegrityError:
                pass

        if awarded_points == 0:
            conn.commit()
            conn.close()
            return {"awarded": False, "points_awarded": 0, **get_user_rewards_summary(user_id)}

        row = conn.execute(
            "SELECT points, tasks_completed, streak_days, last_completion_date FROM user_progress WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            new_points = awarded_points
            new_tasks_completed = 1
            new_streak = 1
            conn.execute(
                """
                INSERT INTO user_progress (user_id, points, tasks_completed, streak_days, last_completion_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, new_points, new_tasks_completed, new_streak, today, now),
            )
        else:
            prev_points = int(row[0] or 0)
            prev_tasks_completed = int(row[1] or 0)
            prev_streak = int(row[2] or 0)
            prev_date = row[3]

            if prev_date == today:
                new_streak = prev_streak
            elif prev_date == yesterday:
                new_streak = prev_streak + 1
            else:
                new_streak = 1

            new_points = prev_points + awarded_points
            new_tasks_completed = prev_tasks_completed + 1
            conn.execute(
                """
                UPDATE user_progress
                SET points = ?, tasks_completed = ?, streak_days = ?, last_completion_date = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (new_points, new_tasks_completed, new_streak, today, now, user_id),
            )

        conn.commit()
    finally:
        conn.close()

    summary = get_user_rewards_summary(user_id)
    return {"awarded": True, "points_awarded": awarded_points, **summary}


def upsert_user_profile(
    user_id: str,
    display_name: str = "",
    passkey_norm: str = "",
    voiceprint: str = "",
) -> None:
    now = now_iso()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO users (user_id, display_name, passkey_norm, voiceprint, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            display_name = excluded.display_name,
            passkey_norm = excluded.passkey_norm,
            voiceprint = excluded.voiceprint,
            updated_at = excluded.updated_at
        """,
        (user_id, display_name, passkey_norm, voiceprint, now, now),
    )
    conn.commit()
    conn.close()


def update_user_voiceprint(user_id: str, voiceprint: str) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE users SET voiceprint = ?, updated_at = ? WHERE user_id = ?",
        (voiceprint, now_iso(), user_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def list_user_profiles() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, display_name, passkey_norm, voiceprint, created_at, updated_at FROM users ORDER BY user_id ASC"
    ).fetchall()
    conn.close()
    return [
        {
            "user_id": r[0],
            "display_name": r[1] or r[0],
            "passkey_norm": r[2] or "",
            "voiceprint": r[3] or "",
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]


def get_user_profile(user_id: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, display_name, passkey_norm, voiceprint, created_at, updated_at FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "user_id": row[0],
        "display_name": row[1] or row[0],
        "passkey_norm": row[2] or "",
        "voiceprint": row[3] or "",
        "created_at": row[4],
        "updated_at": row[5],
    }


def find_user_by_passkey(passkey_norm: str) -> Optional[dict]:
    if not passkey_norm:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, display_name, passkey_norm, voiceprint, created_at, updated_at FROM users WHERE passkey_norm = ?",
        (passkey_norm,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "user_id": row[0],
        "display_name": row[1] or row[0],
        "passkey_norm": row[2] or "",
        "voiceprint": row[3] or "",
        "created_at": row[4],
        "updated_at": row[5],
    }


def log_user_event(
    user_id: str,
    event_type: str,
    task_id: str = "",
    task_title: str = "",
    details: str = "",
) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO user_events (user_id, event_type, task_id, task_title, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id or "default",
            (event_type or "event").strip(),
            task_id or "",
            task_title or "",
            details or "",
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()


def get_user_events(user_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    conn = get_conn()
    q = "SELECT id, user_id, event_type, task_id, task_title, details, created_at FROM user_events"
    params: list = []
    if user_id:
        q += " WHERE user_id = ?"
        params.append(user_id)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 2000)))
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "event_type": r[2],
            "task_id": r[3] or "",
            "task_title": r[4] or "",
            "details": r[5] or "",
            "created_at": r[6],
        }
        for r in rows
    ]


def get_user_settings(user_id: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT settings_json FROM user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row or not row[0]:
        return {}
    try:
        import json
        parsed = json.loads(row[0])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def set_user_settings(user_id: str, settings: dict) -> None:
    import json
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO user_settings (user_id, settings_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            settings_json = excluded.settings_json,
            updated_at = excluded.updated_at
        """,
        (user_id, json.dumps(settings, ensure_ascii=False), now_iso()),
    )
    conn.commit()
    conn.close()
