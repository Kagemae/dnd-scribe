"""
Push completed sessions to the dnd-session-wiki API.

Reads session files (session.yaml, transcript.json) from a session
directory, builds a payload, and POSTs it to the wiki's ingest endpoint.
"""

import json
import copy
import logging
import yaml
import requests
from pathlib import Path

log = logging.getLogger(__name__)

INTERFACE_VERSION = "1.0"


def build_payload(session_dir: Path) -> dict:
    """
    Assemble the push payload from a completed session directory.

    Reads session.yaml and transcript.json, strips word-level data
    to reduce payload size, and returns a dict ready to POST.
    """
    session_dir = Path(session_dir)

    # Load session metadata
    session_yaml = session_dir / "session.yaml"
    if not session_yaml.exists():
        raise FileNotFoundError(f"No session.yaml in {session_dir}")
    with open(session_yaml) as f:
        meta = yaml.safe_load(f)

    # Load transcript
    transcript_json = session_dir / "transcript.json"
    if not transcript_json.exists():
        raise FileNotFoundError(f"No transcript.json in {session_dir}")
    with open(transcript_json) as f:
        transcript = json.load(f)

    # Strip word-level data to reduce payload (~5MB -> ~1MB)
    segments = copy.deepcopy(transcript.get("segments", []))
    for seg in segments:
        seg.pop("words", None)

    # Compute duration from last segment
    duration = segments[-1]["end"] if segments else 0

    return {
        "interface_version": INTERFACE_VERSION,
        "session": {
            "name": meta.get("name", ""),
            "date": meta.get("date", ""),
            "speakers": meta.get("speakers", {}),
            "status": meta.get("status", "completed"),
            "created_at": meta.get("created_at", ""),
        },
        "transcript": {
            "segments": segments,
            "duration": duration,
            "segment_count": len(segments),
        },
    }


def push_to_wiki(session_dir: Path, wiki_url: str, api_key: str = "") -> dict:
    """
    POST a completed session to the wiki API.

    Args:
        session_dir: Path to the session directory containing session.yaml and transcript.json
        wiki_url: Base URL of the wiki (e.g. http://host:port)
        api_key: Optional Bearer token for authentication

    Returns:
        Response JSON from the wiki API.

    Raises:
        requests.HTTPError: If the wiki returns an error status.
        FileNotFoundError: If required session files are missing.
    """
    payload = build_payload(session_dir)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    endpoint = f"{wiki_url.rstrip('/')}/api/sessions/ingest"
    log.info("Pushing session '%s' to %s", payload["session"]["name"], endpoint)

    response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()
