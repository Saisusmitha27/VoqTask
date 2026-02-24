# VoqTask

Voice-first to-do management with an AI-style chat experience.

## Hackathon pitch

People lose tasks because capture is slow and context-switching is expensive.  
VoqTask lets users speak naturally, instantly turns speech into structured tasks, and provides an assistant-like interface to list, prioritize, and manage work in one place.

## Why this is different

- Voice-first input with natural language parsing
- AI-style chat interface on the left, actionable task board on the right
- Smart reminders (upcoming and due-now)
- Priority grouping and assistant task listing (`list all tasks`, `show necessary tasks`)
- Productivity analytics with circular progress visuals
- Rewards system (points, streaks, levels)
- Works offline first (SQLite), optional cloud sync (Supabase)

## Core features

- Create tasks by voice or text
- Parse due date/time and priority from natural language
- Structured task categories (with filter in UI)
- Task CRUD across Today / Tomorrow / Later tabs
- Group and sort by priority for clarity
- In-app sharing text export per task
- Full data export (JSON and CSV)
- Reminder alerts when task time is reached
- Assistant replies and read-aloud support
- Theme presets and accessibility mode

## Tech stack

- Frontend + app runtime: Streamlit
- Language: Python
- Storage: SQLite
- Speech-to-text: Whisper (with fallback option)
- Optional cloud: Supabase
- API: Flask (REST CRUD endpoints)

## System flow

1. User speaks or types task/request.
2. NLU decides intent:
   - task creation intent -> parse and save task
   - assistant intent -> generate response/list tasks
3. Storage persists tasks and reward progress.
4. UI updates chat panel, reminders, and task dashboard.

## 2-3 minute live demo script

### 0:00 - 0:20 Problem

"People capture tasks late or forget context because typing is slow during real life moments."

### 0:20 - 1:00 Voice capture + parsing

Say:  
`Remind me to submit hackathon report tomorrow at 9 am high priority`

Show:

- task created automatically
- parsed date/time/priority
- task appears in the right-side board

### 1:00 - 1:40 Assistant behavior

Say:

- `list all tasks`
- `show necessary tasks`

Show:

- assistant lists pending tasks
- urgent/high-priority filtering works

### 1:40 - 2:10 Productivity + rewards

Mark one task done and show:

- points earned
- streak/level updates
- circular productivity dashboard metrics

### 2:10 - 2:40 Reminder behavior

Create a task due in the next minute and show:

- upcoming reminder
- due-now alert when time is reached

### 2:40 - 3:00 Close

"VoqTask combines instant voice capture, assistant-style control, and measurable productivity in one lightweight app."

## Setup

```bash
cd "d:\Desktop Files\Jarvis_Voice"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Configuration

- Local data dir: `TASKWHISPER_DATA`
- Whisper model: `WHISPER_MODEL`
- Optional cloud sync:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`

## CRUD API

Run the API server:

```bash
python -m taskwhisper.api_server
```

Base URL: `http://localhost:8000`

- `GET /health`
- `GET /tasks?status=pending&category=finance&limit=100`
- `GET /tasks/<task_id>`
- `POST /tasks`
- `PUT /tasks/<task_id>`
- `DELETE /tasks/<task_id>`

## Judging-ready checklist

- Demo path rehearsed with exact commands/phrases
- Stable microphone and internet fallback plan
- One clear target user segment
- One sentence metric claim (speed, completion rate, or missed-task reduction)
- Backup video of the full demo flow

## License

Use and modify freely.
