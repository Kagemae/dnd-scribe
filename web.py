"""
D&D Scribe - Web interface.

Run with: python web.py
"""

import json
import re
import asyncio
import shutil
import yaml
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv

import pipeline
import wiki_push
from jobs import JobManager

load_dotenv()

app = FastAPI(title="D&D Scribe")

BASE_DIR = Path(__file__).parent
SESSIONS_DIR = BASE_DIR / "sessions"
RECORDINGS_DIR = BASE_DIR / "recordings"
CONFIG_PATH = BASE_DIR / "config.yaml"

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

config = pipeline.load_config()
job_manager = JobManager()


# --- Jinja2 filters ---

def format_timestamp(seconds):
    """Format seconds as MM:SS."""
    if seconds is None:
        return "00:00"
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"

templates.env.filters["timestamp"] = format_timestamp
templates.env.filters["basename"] = lambda p: Path(p).name if p else ""


# --- Helper functions ---

def list_sessions() -> list[dict]:
    """Scan sessions/ directory and return metadata for each."""
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions
    for d in sorted(SESSIONS_DIR.iterdir(), reverse=True):
        if d.is_dir():
            meta = pipeline.load_session_meta(d)
            meta["id"] = d.name
            meta["dir"] = str(d)
            meta["has_recap"] = (d / "recap.md").exists()
            meta["has_transcript"] = (d / "transcript.json").exists()
            sessions.append(meta)
    return sessions


def list_recordings() -> list[str]:
    """List audio files in recordings/ directory."""
    if not RECORDINGS_DIR.exists():
        return []
    exts = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
    return sorted(
        f.name for f in RECORDINGS_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in exts
    )


def make_session_dir(session_name: str) -> Path:
    """Create a unique session directory name."""
    date = datetime.now().strftime("%Y-%m-%d")
    slug = session_name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    base = SESSIONS_DIR / f"{date}-{slug}"
    # Avoid collisions
    result = base
    counter = 2
    while result.exists():
        result = Path(f"{base}-{counter}")
        counter += 1
    return result


# --- Page routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sessions": list_sessions(),
        "recordings": list_recordings(),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    vocabulary = config.get("vocabulary") or config.get("whisper", {}).get("vocabulary", [])
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "vocabulary": vocabulary,
    })


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, session_id: str):
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    meta = pipeline.load_session_meta(session_dir)
    meta["id"] = session_id

    transcript_lines = []
    txt_path = session_dir / "transcript.txt"
    if txt_path.exists():
        transcript_lines = txt_path.read_text(encoding="utf-8").splitlines()

    recap_html = ""
    recap_path = session_dir / "recap.md"
    if recap_path.exists():
        import markdown
        recap_html = markdown.markdown(
            recap_path.read_text(encoding="utf-8"),
            extensions=["tables", "fenced_code"],
        )

    files = [f.name for f in session_dir.iterdir() if f.is_file()]

    # Extract current speaker mapping from transcript
    speaker_map = {}
    transcript_json = session_dir / "transcript.json"
    if transcript_json.exists():
        with open(transcript_json) as f:
            transcript_data = json.load(f)
        seen = {}
        for seg in transcript_data.get("segments", []):
            sid = seg.get("speaker", "UNKNOWN")
            if sid not in seen:
                seen[sid] = seg.get("speaker_name", sid)
        speaker_map = seen

    return templates.TemplateResponse("session.html", {
        "request": request,
        "session": meta,
        "session_id": session_id,
        "transcript_lines": transcript_lines,
        "recap_html": recap_html,
        "files": files,
        "speaker_map": speaker_map,
    })


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_progress_page(request: Request, job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse("progress.html", {
        "request": request,
        "job_id": job_id,
        "job": job,
    })


@app.get("/jobs/{job_id}/speakers", response_class=HTMLResponse)
async def speakers_page(request: Request, job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Load default speaker names from config as suggestions
    default_names = config.get("speakers", {})

    return templates.TemplateResponse("speakers.html", {
        "request": request,
        "job_id": job_id,
        "job": job,
        "speaker_samples": job.speaker_samples or {},
        "default_names": default_names,
    })


# --- API routes ---

@app.get("/api/vocabulary")
async def get_vocabulary():
    return {"vocabulary": config.get("vocabulary") or config.get("whisper", {}).get("vocabulary", [])}


@app.post("/api/vocabulary")
async def update_vocabulary(request: Request):
    """Update the vocabulary list in config.yaml and reload."""
    global config
    body = await request.json()
    words = body.get("vocabulary", [])
    # Clean: strip whitespace, remove empties, deduplicate preserving order
    seen = set()
    cleaned = []
    for w in words:
        w = w.strip()
        if w and w not in seen:
            cleaned.append(w)
            seen.add(w)

    # Read, update, and write config.yaml
    with open(CONFIG_PATH) as f:
        raw = yaml.safe_load(f)
    raw["vocabulary"] = cleaned
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    # Reload in-memory config
    config = pipeline.load_config()
    return {"status": "ok", "count": len(cleaned)}


@app.post("/api/jobs")
async def create_job(
    session_name: str = Form(...),
    source: str = Form("upload"),
    recording: str = Form(""),
    file: UploadFile = None,
):
    """Start a new transcription job."""
    if source == "upload" and file and file.filename:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        dest = RECORDINGS_DIR / file.filename
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        audio_path = str(dest)
    elif source == "recording" and recording:
        audio_path = str(RECORDINGS_DIR / recording)
        if not Path(audio_path).exists():
            raise HTTPException(status_code=400, detail=f"Recording not found: {recording}")
    else:
        raise HTTPException(status_code=400, detail="No audio file provided")

    session_dir = make_session_dir(session_name)

    try:
        job_id = job_manager.create_job(
            audio_path=audio_path,
            session_name=session_name,
            session_dir=str(session_dir),
            config=config,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    """SSE stream of job progress updates."""

    async def event_generator():
        last_msg = None
        last_status = None
        while True:
            job = job_manager.get_job(job_id)
            if not job:
                yield {"event": "error", "data": json.dumps({"error": "Job not found"})}
                break

            current = (job.status.value, job.progress_message, job.progress_percent)
            if current != (last_status, last_msg, None):  # always send if changed
                data = {
                    "status": job.status.value,
                    "message": job.progress_message,
                    "percent": job.progress_percent,
                }
                if job.status.value == "awaiting_speakers":
                    data["speakers_url"] = f"/jobs/{job_id}/speakers"
                yield {"event": "progress", "data": json.dumps(data)}
                last_status = job.status.value
                last_msg = job.progress_message

            if job.status.value == "completed":
                yield {
                    "event": "completed",
                    "data": json.dumps({"session_url": f"/sessions/{Path(job.session_dir).name}"}),
                }
                break
            if job.status.value == "failed":
                yield {"event": "failed", "data": json.dumps({"error": job.error or "Unknown error"})}
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get current job status as JSON."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status.value,
        "message": job.progress_message,
        "percent": job.progress_percent,
        "error": job.error,
        "session_name": job.session_name,
    }


@app.post("/api/jobs/{job_id}/speakers")
async def submit_speaker_names(job_id: str, request: Request):
    """Submit speaker names for a job awaiting identification."""
    body = await request.json()
    speaker_map = body.get("speakers", {})
    skip_recap = body.get("skip_recap", False)

    try:
        job_manager.set_speaker_names(job_id, speaker_map, skip_recap=skip_recap)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "continuing"}


@app.get("/api/sessions")
async def api_list_sessions():
    return list_sessions()


@app.get("/api/recordings")
async def api_list_recordings():
    return list_recordings()


@app.post("/api/sessions/{session_id}/speakers")
async def update_session_speakers(session_id: str, request: Request):
    """Update speaker names for an existing session and re-save transcript files."""
    session_dir = SESSIONS_DIR / session_id
    transcript_json = session_dir / "transcript.json"
    if not transcript_json.exists():
        raise HTTPException(status_code=404, detail="No transcript found for this session")

    body = await request.json()
    speaker_map = body.get("speakers", {})

    # Load raw transcript, apply new names, re-save
    with open(transcript_json) as f:
        transcript = json.load(f)

    # Strip old speaker_name values before re-applying
    for seg in transcript.get("segments", []):
        seg.pop("speaker_name", None)

    transcript = pipeline.apply_speaker_names(transcript, speaker_map)
    pipeline.save_transcript(transcript, session_dir, config)

    # Update session.yaml with new speaker map
    meta = pipeline.load_session_meta(session_dir)
    meta["speakers"] = speaker_map
    pipeline.save_session_meta(
        session_dir,
        meta.get("name", session_id),
        meta.get("audio_file", ""),
        speaker_map,
    )

    # Return updated transcript lines for the viewer
    txt_path = session_dir / "transcript.txt"
    lines = txt_path.read_text(encoding="utf-8").splitlines() if txt_path.exists() else []
    return {"status": "ok", "transcript_lines": lines}


@app.post("/api/sessions/{session_id}/recap")
async def regenerate_recap(session_id: str):
    """Regenerate recap for an existing session."""
    session_dir = SESSIONS_DIR / session_id
    transcript_json = session_dir / "transcript.json"
    if not transcript_json.exists():
        raise HTTPException(status_code=404, detail="No transcript found for this session")

    recap_text = pipeline.generate_recap(str(transcript_json), config, session_dir)
    if not recap_text:
        raise HTTPException(status_code=500, detail="Recap generation failed")

    import markdown
    recap_html = markdown.markdown(recap_text, extensions=["tables", "fenced_code"])
    return {"html": recap_html, "text": recap_text}


@app.post("/api/sessions/{session_id}/push")
async def push_to_wiki(session_id: str):
    """Push a completed session to the dnd-session-wiki."""
    session_dir = SESSIONS_DIR / session_id
    if not (session_dir / "transcript.json").exists():
        raise HTTPException(status_code=404, detail="No transcript found for this session")

    wiki_cfg = config.get("wiki", {})
    wiki_url = wiki_cfg.get("url", "")
    if not wiki_url:
        raise HTTPException(status_code=400, detail="No wiki URL configured in config.yaml")

    try:
        result = wiki_push.push_to_wiki(
            session_dir, wiki_url, wiki_cfg.get("api_key", "")
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wiki push failed: {e}")


@app.get("/sessions/{session_id}/download/{filename}")
async def download_file(session_id: str, filename: str):
    """Download a session file."""
    from fastapi.responses import FileResponse
    file_path = SESSIONS_DIR / session_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    # Prevent directory traversal
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return FileResponse(file_path, filename=filename)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web:app", host="0.0.0.0", port=8000, reload=True)
