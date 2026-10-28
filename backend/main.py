
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4
from urllib.parse import urlparse
from pathlib import Path
import subprocess
import tempfile
import shutil
import re
import os

import imageio_ffmpeg
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="LEAF OS Backend",
    description="API central para agentes y generación de clips",
    version="0.3.0",
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
CLIP_JOBS = {}

ALLOWED_HOSTS = {
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "kick.com",
}

# Directorio temporal. Los archivos pueden desaparecer al reiniciarse
# el servicio; todavía no es almacenamiento permanente.
CLIP_ROOT = Path(tempfile.gettempdir()) / "leaf-os-clips"
CLIP_ROOT.mkdir(parents=True, exist_ok=True)

MAX_SOURCE_BYTES = 500 * 1024 * 1024
DOWNLOAD_TIMEOUT = 300
CLIP_TIMEOUT = 120


class TaskInput(BaseModel):
    agent_id: str
    description: str = Field(min_length=1, max_length=500)
    priority: str = "Normal"
    video_url: str | None = Field(default=None, max_length=1000)


class TaskUpdate(BaseModel):
    status: str


class ClipRequest(BaseModel):
    video_url: str = Field(min_length=8, max_length=1000)
    count: int = Field(default=5, ge=1, le=10)
    duration: int = Field(default=60, ge=60, le=120)


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

    if parsed.username or parsed.password:
        raise HTTPException(422, "El enlace no puede incluir credenciales")

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


def run_command(command, timeout):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


def get_video_duration(ffmpeg_path, video_path):
    result = subprocess.run(
        [ffmpeg_path, "-i", str(video_path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    output = result.stderr or ""
    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        output,
    )

    if not match:
        raise RuntimeError(
            "No se pudo determinar la duración del video."
        )

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def process_clip_job(job_id, video_url, count, duration):
    job_dir = CLIP_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with lock:
        job = CLIP_JOBS.get(job_id)
        if not job:
            return
        job["status"] = "working"
        job["progress"] = 5
        job["message"] = "Preparando descarga..."
        job["updated_at"] = datetime.now(timezone.utc).isoformat()

        AGENTS["clip-agent"]["status"] = "working"
        AGENTS["clip-agent"]["current_task"] = job_id

    try:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        source_path = job_dir / "source.mp4"

        with lock:
            CLIP_JOBS[job_id]["message"] = "Descargando el video autorizado..."
            CLIP_JOBS[job_id]["progress"] = 10

        # Requiere yt-dlp instalado en requirements.txt.
        # No descarga listas de reproducción ni archivos mayores al límite.
        run_command(
            [
                "python",
                "-m",
                "yt_dlp",
                "--no-playlist",
                "--max-filesize",
                "500M",
                "--format",
                "best[ext=mp4]/best",
                "--merge-output-format",
                "mp4",
                "--socket-timeout",
                "20",
                "--retries",
                "2",
                "--output",
                str(source_path),
                video_url,
            ],
            DOWNLOAD_TIMEOUT,
        )

        if not source_path.exists():
            candidates = list(job_dir.glob("source.*"))
            candidates = [
                path for path in candidates
                if path.is_file() and path.name != "source.mp4"
            ]
            if candidates:
                source_path = candidates[0]

        if not source_path.exists():
            raise RuntimeError(
                "La descarga terminó, pero no se encontró el archivo."
            )

        if source_path.stat().st_size > MAX_SOURCE_BYTES:
            raise RuntimeError("El video supera el límite de 500 MB.")

        with lock:
            CLIP_JOBS[job_id]["message"] = "Analizando duración..."
            CLIP_JOBS[job_id]["progress"] = 30

        total_duration = get_video_duration(ffmpeg_path, source_path)

        if total_duration < duration:
            raise RuntimeError(
                f"El video dura {int(total_duration)} segundos; "
                f"necesitas al menos {duration} segundos."
            )

        # Distribuye los puntos de inicio a lo largo del video.
        # Los clips pueden solaparse si el video es corto.
        max_start = max(0, total_duration - duration)
        if count == 1:
            starts = [max_start / 2]
        else:
            starts = [
                max_start * index / (count - 1)
                for index in range(count)
            ]

        clips = []

        for index, start in enumerate(starts, start=1):
            filename = f"clip_{index:02d}.mp4"
            output_path = job_dir / filename

            with lock:
                CLIP_JOBS[job_id]["message"] = (
                    f"Creando clip {index} de {count}..."
                )
                CLIP_JOBS[job_id]["progress"] = (
                    35 + int(60 * (index - 1) / count)
                )

            run_command(
                [
                    ffmpeg_path,
                    "-y",
                    "-ss",
                    str(start),
                    "-i",
                    str(source_path),
                    "-t",
                    str(duration),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "24",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    str(output_path),
                ],
                CLIP_TIMEOUT,
            )

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError(f"No se pudo crear {filename}.")

            clips.append({
                "number": index,
                "filename": filename,
                "duration": duration,
                "start_seconds": round(start, 2),
                "size_bytes": output_path.stat().st_size,
                "url": f"/api/clips/{job_id}/{filename}",
            })

        # El original ocupa espacio y ya no se necesita para reproducir.
        try:
            source_path.unlink(missing_ok=True)
        except OSError:
            pass

        with lock:
            job = CLIP_JOBS[job_id]
            job["status"] = "completed"
            job["progress"] = 100
            job["message"] = f"Se crearon {len(clips)} clips."
            job["clips"] = clips
            job["updated_at"] = datetime.now(timezone.utc).isoformat()

            AGENTS["clip-agent"]["status"] = "idle"
            AGENTS["clip-agent"]["current_task"] = None

            record_event(
                f"Clip Agent creó {len(clips)} clips ({job_id}).",
                "success",
            )

    except Exception as exc:
        error_message = str(exc)
        if len(error_message) > 400:
            error_message = error_message[:400]

        with lock:
            job = CLIP_JOBS.get(job_id)
            if job:
                job["status"] = "error"
                job["message"] = (
                    "No se pudieron crear los clips: " + error_message
                )
                job["updated_at"] = datetime.now(timezone.utc).isoformat()

            AGENTS["clip-agent"]["status"] = "error"
            AGENTS["clip-agent"]["current_task"] = None

            record_event(
                f"Falló la generación de clips ({job_id}): {error_message}",
                "error",
            )
    finally:
        pass
@app.get("/")
def root():
    return {
        "name": "LEAF OS",
        "version": "0.3.0",
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
        result = run_command([ffmpeg_path, "-version"], 10)

        return {
            "available": True,
            "version": result.stdout.splitlines()[0],
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


@app.get("/api/status")
def system_status():
    with lock:
        tasks = list(TASKS.values())
        return {
            "name": "LEAF OS",
            "version": "0.3.0",
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
        raise HTTPException(422, "La descripción no puede estar vacía")

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


@app.post("/api/clips", status_code=202)
def create_clip_job(data: ClipRequest, background_tasks: BackgroundTasks):
    video_url = validate_video_url(data.video_url)

    if not video_url:
        raise HTTPException(422, "Debes introducir un enlace de video.")

    with lock:
        if AGENTS["clip-agent"]["status"] == "working":
            raise HTTPException(
                409,
                "Clip Agent ya está procesando un video. Espera a que termine.",
            )

        job_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        CLIP_JOBS[job_id] = {
            "id": job_id,
            "status": "pending",
            "progress": 0,
            "message": "Trabajo creado.",
            "video_url": video_url,
            "count": data.count,
            "duration": data.duration,
            "clips": [],
            "created_at": now,
            "updated_at": now,
        }

        record_event(
            f"Solicitud de {data.count} clips de {data.duration} segundos.",
            "info",
        )

    background_tasks.add_task(
        process_clip_job,
        job_id,
        video_url,
        data.count,
        data.duration,
    )

    return {
        "id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Generación iniciada.",
        "status_url": f"/api/clips/{job_id}",
    }


@app.get("/api/clips/{job_id}")
def get_clip_job(job_id: str):
    with lock:
        job = CLIP_JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "Trabajo no encontrado")

        result = dict(job)
        result["clips"] = [dict(clip) for clip in job["clips"]]
        return result


@app.get("/api/clips/{job_id}/{filename}")
def download_clip(job_id: str, filename: str):
    if not re.fullmatch(r"clip_\d{2}\.mp4", filename):
        raise HTTPException(400, "Nombre de archivo no válido.")

    with lock:
        job = CLIP_JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "Trabajo no encontrado")

        if job["status"] != "completed":
            raise HTTPException(409, "El clip todavía no está listo.")

        allowed = any(
            clip["filename"] == filename for clip in job["clips"]
        )
        if not allowed:
            raise HTTPException(404, "Clip no encontrado.")

    path = CLIP_ROOT / job_id / filename
    if not path.is_file():
        raise HTTPException(
            410,
            "El archivo temporal ya no está disponible. Genera los clips otra vez.",
        )

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename,
    )


@app.get("/api/activity")
def get_activity(limit: int = 30):
    limit = max(1, min(limit, 100))
    with lock:
        return ACTIVITY[:limit]
