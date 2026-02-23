# Optional cloud sync via Supabase (free tier)
from typing import List
from .models import Task
from . import config
from . import storage


def is_configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_ANON_KEY)


def pull_tasks(user_id: str = "default") -> List[Task]:
    if not is_configured():
        return []
    try:
        from supabase import create_client
        client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        r = client.table("tasks").select("*").eq("user_id", user_id).execute()
        rows = r.data or []
        out = []
        for row in rows:
            d = {**row, "id": row.get("id")}
            if "user_id" in d:
                del d["user_id"]
            out.append(Task.from_dict(d))
        return out
    except Exception:
        return []


def push_task(task: Task, user_id: str = "default") -> bool:
    if not is_configured():
        return False
    try:
        from supabase import create_client
        client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        payload = {**task.to_dict(), "user_id": user_id}
        client.table("tasks").upsert(payload).execute()
        return True
    except Exception:
        return False


def delete_remote(task_id: str, user_id: str = "default") -> bool:
    if not is_configured():
        return False
    try:
        from supabase import create_client
        client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        client.table("tasks").delete().eq("id", task_id).eq("user_id", user_id).execute()
        return True
    except Exception:
        return False


def pull_and_merge(user_id: str = "default") -> int:
    """Pull from Supabase and merge into local DB (newer updated_at wins). Returns count merged."""
    if not is_configured() or config.OFFLINE_MODE:
        return 0
    pulled = pull_tasks(user_id)
    merged = 0
    for remote in pulled:
        local = storage.get_task_by_id(remote.id)
        if local is None or (remote.updated_at and local.updated_at and remote.updated_at > local.updated_at):
            storage.save_task(remote)
            merged += 1
    return merged


def push_all_local(user_id: str = "default") -> int:
    """Push all local tasks to Supabase. Returns count pushed."""
    if not is_configured() or config.OFFLINE_MODE:
        return 0
    tasks = storage.get_tasks(limit=2000)
    count = 0
    for t in tasks:
        if push_task(t, user_id):
            count += 1
    return count
