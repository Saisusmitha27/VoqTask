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
            title TEXT NOT NULL,
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
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


def save_task(task: Task) -> Task:
    import uuid
    if not task.id:
        task.id = str(uuid.uuid4())
    task.updated_at = now_iso()
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO tasks (id, title, due_date, due_time, priority, status, created_at, updated_at, shared_with, notes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task.id, task.title, task.due_date, task.due_time, task.priority.value, task.status.value,
        task.created_at, task.updated_at, ",".join(task.shared_with), task.notes, task.source
    ))
    conn.commit()
    conn.close()
    return task


def get_tasks(due_date: Optional[str] = None, status: Optional[TaskStatus] = None, limit: int = 500) -> List[Task]:
    conn = get_conn()
    q = "SELECT id, title, due_date, due_time, priority, status, created_at, updated_at, shared_with, notes, source FROM tasks WHERE 1=1"
    params = []
    if due_date is not None:
        q += " AND due_date = ?"
        params.append(due_date)
    if status is not None:
        q += " AND status = ?"
        params.append(status.value)
    q += " ORDER BY due_date ASC, due_time ASC, created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append(Task(
            id=r[0], title=r[1], due_date=r[2], due_time=r[3],
            priority=Priority(r[4]), status=TaskStatus(r[5]),
            created_at=r[6], updated_at=r[7],
            shared_with=(r[8] or "").split(",") if r[8] else [],
            notes=r[9] or "", source=r[10] or "voice",
        ))
    return out


def get_task_by_id(task_id: str) -> Optional[Task]:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, title, due_date, due_time, priority, status, created_at, updated_at, shared_with, notes, source FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return Task(
        id=row[0], title=row[1], due_date=row[2], due_time=row[3],
        priority=Priority(row[4]), status=TaskStatus(row[5]),
        created_at=row[6], updated_at=row[7],
        shared_with=row[8].split(",") if row[8] else [],
        notes=row[9] or "", source=row[10] or "voice",
    )


def update_task_status(task_id: str, status: TaskStatus) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND status != ?",
        (status.value, now_iso(), task_id, status.value),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def update_task(task: Task) -> Task:
    """Full update of an existing task (by id). Preserves created_at."""
    existing = get_task_by_id(task.id)
    if not existing:
        return save_task(task)
    task.created_at = existing.created_at
    return save_task(task)


def delete_task(task_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


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


def reward_task_completion(task_id: str, user_id: str = "default") -> dict:
    """Award completion points once per task and update user progress."""
    task = get_task_by_id(task_id)
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
