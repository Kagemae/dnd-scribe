"""
Async job manager for long-running transcription tasks.

Runs transcription in a background thread, tracks progress, and supports
a two-phase flow: transcribe -> pause for speaker names -> save/recap.
"""

import threading
import uuid
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime
from pathlib import Path

import pipeline


class JobStatus(str, Enum):
    QUEUED = "queued"
    LOADING_MODEL = "loading_model"
    LOADING_AUDIO = "loading_audio"
    TRANSCRIBING = "transcribing"
    ALIGNING = "aligning"
    DIARIZING = "diarizing"
    AWAITING_SPEAKERS = "awaiting_speakers"
    SAVING = "saving"
    GENERATING_RECAP = "generating_recap"
    COMPLETED = "completed"
    FAILED = "failed"


# Map pipeline stage names to JobStatus
_STAGE_MAP = {
    "loading_model": JobStatus.LOADING_MODEL,
    "loading_audio": JobStatus.LOADING_AUDIO,
    "transcribing": JobStatus.TRANSCRIBING,
    "aligning": JobStatus.ALIGNING,
    "diarizing": JobStatus.DIARIZING,
    "done_transcription": JobStatus.AWAITING_SPEAKERS,
}


@dataclass
class Job:
    id: str
    audio_path: str
    session_dir: str
    session_name: str
    config: dict
    skip_recap: bool = False
    status: JobStatus = JobStatus.QUEUED
    progress_message: str = ""
    progress_percent: int = 0
    error: Optional[str] = None
    transcript: Optional[dict] = None
    speaker_samples: Optional[dict] = None
    created_at: datetime = field(default_factory=datetime.now)


class JobManager:
    """Thread-safe job manager. One job at a time (GPU constraint)."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._speaker_events: dict[str, threading.Event] = {}
        self._speaker_maps: dict[str, dict] = {}

    def create_job(self, audio_path: str, session_name: str, session_dir: str,
                   config: dict, skip_recap: bool = False) -> str:
        """Create and start a new transcription job. Returns job ID."""
        with self._lock:
            # Check if any job is currently running
            for job in self._jobs.values():
                if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
                    raise RuntimeError("A job is already running. Only one transcription at a time.")

        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            audio_path=audio_path,
            session_dir=session_dir,
            session_name=session_name,
            config=config,
            skip_recap=skip_recap,
        )

        with self._lock:
            self._jobs[job_id] = job
            self._speaker_events[job_id] = threading.Event()

        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_speaker_names(self, job_id: str, speaker_map: dict, skip_recap: bool = False):
        """Provide speaker names for a job awaiting them."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != JobStatus.AWAITING_SPEAKERS:
                raise ValueError(f"Job {job_id} is not awaiting speaker names")
            self._speaker_maps[job_id] = speaker_map
            job.skip_recap = skip_recap
        self._speaker_events[job_id].set()

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def _run(self, job: Job):
        """Background worker: transcribe, wait for names, save, recap."""
        try:
            def progress_cb(stage, message, percent):
                with self._lock:
                    job.status = _STAGE_MAP.get(stage, job.status)
                    job.progress_message = message
                    job.progress_percent = percent

            # Phase 1: Transcription + diarization
            transcript = pipeline.transcribe_audio(
                job.audio_path, job.config, progress_callback=progress_cb
            )

            # Extract speaker samples and pause
            samples = pipeline.get_speaker_samples(transcript)
            with self._lock:
                job.transcript = transcript
                job.speaker_samples = samples
                job.status = JobStatus.AWAITING_SPEAKERS
                job.progress_message = "Waiting for speaker identification..."
                job.progress_percent = 95

            # Wait for speaker names (blocks until set_speaker_names is called)
            self._speaker_events[job.id].wait()

            # Phase 2: Apply names, save, recap
            speaker_map = self._speaker_maps.get(job.id, {})
            output_dir = Path(job.session_dir)

            with self._lock:
                job.status = JobStatus.SAVING
                job.progress_message = "Saving transcript..."
                job.progress_percent = 96

            transcript = pipeline.apply_speaker_names(transcript, speaker_map)
            pipeline.save_transcript(transcript, output_dir, job.config)
            pipeline.save_session_meta(
                output_dir, job.session_name, job.audio_path, speaker_map
            )

            if not job.skip_recap:
                with self._lock:
                    job.status = JobStatus.GENERATING_RECAP
                    job.progress_message = "Generating recap..."
                    job.progress_percent = 97

                transcript_json = str(output_dir / "transcript.json")
                pipeline.generate_recap(transcript_json, job.config, output_dir)

            with self._lock:
                job.status = JobStatus.COMPLETED
                job.progress_message = "Done!"
                job.progress_percent = 100
                job.transcript = None  # Free memory

        except Exception as e:
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                job.progress_message = f"Failed: {e}"
