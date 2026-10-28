
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4
from urllib.parse import urlparse
import subprocess

import imageio_ffmpeg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="LEAF OS Backend",
    description="API central para administrar los agentes de LEAF OS",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://jr7408979-cpu.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

lock = Lock()

AGENTS = {
    "clip-agent": {
        "id": "clip-agent",
        "name": "Clip Agent",
        "role": "Preparar clips de video",
        "status": "idle",
        "current_task": None,
    },
    "trend-agent": {
        "id": "trend-agent",
        "name": "Trend Agent",
        "role": "Analizar tendencias",
        "status": "idle",
        "current_task": None,
    },
    "monitor-agent": {
        "id": "monitor-agent",
        "name": "Monitor Agent",
        "role": "Supervisar redes sociales",
        "status": "idle",
        "current_task": None,
    },
    "quality-agent": {
        "id": "quality-agent",
        "name": "Quality Agent",
        "role": "Revisar la calidad del contenido",
        "status": "idle",
        "current_task": None,
    },
}

TASKS = {}
ACTIVITY = []

ALLOWED_HOSTS = {
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "kick.com",
}


class TaskInput(BaseModel):
    agent_id: str
    description: str = Field(min_length=1, max_length=500)
    priority: str = "Normal"
    video_url: str | None = Field(default=None, max_length=1000)


class TaskUpdate(BaseModel):
    status: str


def validate_video_url(video_url: str | None):
    if not video_url:
        return None

    video_url = video_url.strip()

    try:
        parsed = urlparse(video_url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        raise HTTPException(422, "Enlace de video no válido")

    allowed = any(
        host == domain or host.endswith("." + domain)
        for domain in ALLOWED_HOSTS
    )

    if parsed.scheme != "https" or not allowed:
        raise HTTPException(
            422,
            "Usa un enlace HTTPS válido de YouTube, TikTok o Kick",
        )

    return video_url


def record_event(message: str, event_type: str = "info"):
    ACTIVITY.insert(
        0,
        {
            "id": str(uuid4()),
            "message": message,
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    del ACTIVITY[100:]


def task_copy(task):
    return dict(task)


@app.get("/")
def root():
    return {
        "name": "LEAF OS",
        "version": "0.2.0",
        "status": "online",
        "message": "Backend iniciado correctamente",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/tools/ffmpeg")
def check_ffmpeg():
    try:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )

        first_line = result.stdout.splitlines()[0]

        return {
            "available": True,
            "version": first_line,
        }

    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
        }


@app.get("/api/status")
def system_status():
    with lock:
        tasks = list(TASKS.values())
        return {
            "name": "LEAF OS",
            "version": "0.2.0",
            "agents_total": len(AGENTS),
            "agents_working": sum(
                agent["status"] == "working"
                for agent in AGENTS.values()
            ),
            "tasks_total": len(tasks),
            "tasks_pending": sum(
                task["status"] == "pending" for task in tasks
            ),
            "tasks_completed": sum(
                task["status"] == "completed" for task in tasks
            ),
            "tasks_error": sum(
                task["status"] == "error" for task in tasks
            ),
        }


@app.get("/api/agents")
def get_agents():
    with lock:
        return [dict(agent) for agent in AGENTS.values()]


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str):
    with lock:
        agent = AGENTS.get(agent_id)
        if not agent:
            raise HTTPException(404, "Agente no encontrado")
        return dict(agent)


@app.get("/api/tasks")
def get_tasks():
    with lock:
        return [task_copy(task) for task in TASKS.values()]


@app.post("/api/tasks", status_code=201)
def create_task(data: TaskInput):
    description = data.description.strip()

    if not description:
        raise HTTPException(
            422,
            "La descripción no puede estar vacía",
        )

    if data.priority not in ("Normal", "Alta", "Urgente"):
        raise HTTPException(422, "Prioridad no válida")

    video_url = validate_video_url(data.video_url)

    with lock:
        agent = AGENTS.get(data.agent_id)
        if not agent:
            raise HTTPException(404, "Agente no encontrado")

        task_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        task = {
            "id": task_id,
            "agent_id": data.agent_id,
            "description": description,
            "priority": data.priority,
            "video_url": video_url,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }

        TASKS[task_id] = task

        message = f"Tarea creada para {agent['name']}: {description}"
        if video_url:
            message += " (incluye enlace de video)"

        record_event(message, "success")
        return task_copy(task)


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, data: TaskUpdate):
    allowed = {"pending", "working", "completed", "error"}

    if data.status not in allowed:
        raise HTTPException(422, "Estado de tarea no válido")

    with lock:
        task = TASKS.get(task_id)
        if not task:
            raise HTTPException(404, "Tarea no encontrada")

        agent = AGENTS[task["agent_id"]]
        task["status"] = data.status
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        if data.status == "working":
            agent["status"] = "working"
            agent["current_task"] = task_id
        elif agent["current_task"] == task_id:
            agent["current_task"] = None
            agent["status"] = (
                "error" if data.status == "error" else "idle"
            )

        record_event(
            f"{agent['name']}: tarea {task_id} -> {data.status}",
            "error" if data.status == "error" else "success",
        )

        return task_copy(task)


@app.get("/api/activity")
def get_activity(limit: int = 30):
    limit = max(1, min(limit, 100))
    with lock:
        return ACTIVITY[:limit]
