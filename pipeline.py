"""
D&D Scribe - Core processing pipeline.

Extracted from scribe.py for reuse by both the CLI and web interfaces.
"""

import os
import json
import yaml
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        return {}
    with open(config_file) as f:
        return yaml.safe_load(f)


def transcribe_audio(audio_path: str, config: dict, progress_callback=None) -> dict:
    """
    Transcribe audio file with speaker diarization using whisperX.

    Args:
        audio_path: Path to audio file.
        config: Full config dict.
        progress_callback: Optional callable(stage: str, message: str, percent: int).

    Returns:
        Transcript dict with segments, words, and speaker labels.
    """
    import whisperx
    import torch

    def progress(stage, message, percent):
        if progress_callback:
            progress_callback(stage, message, percent)

    whisper_config = config.get("whisper", {})
    diarization_config = config.get("diarization", {})

    device = whisper_config.get("device", "auto")
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    compute_type = whisper_config.get("compute_type", "float16")
    if device == "cpu" and compute_type == "float16":
        compute_type = "int8"

    model_name = whisper_config.get("model", "large-v3")
    language = whisper_config.get("language", "en")

    # Build initial_prompt from vocabulary list to bias Whisper toward D&D terms
    vocabulary = config.get("vocabulary") or whisper_config.get("vocabulary", [])
    initial_prompt = ", ".join(vocabulary) if vocabulary else None

    asr_options = {}
    if initial_prompt:
        asr_options["initial_prompt"] = initial_prompt

    progress("loading_model", f"Loading Whisper model: {model_name} ({device}, {compute_type})", 2)
    model = whisperx.load_model(
        model_name, device, compute_type=compute_type,
        asr_options=asr_options if asr_options else None,
    )

    progress("loading_audio", f"Loading audio: {audio_path}", 5)
    audio = whisperx.load_audio(audio_path)

    vocab_note = f" (vocabulary: {len(vocabulary)} terms)" if vocabulary else ""
    progress("transcribing", f"Transcribing audio...{vocab_note} (this may take a while)", 10)
    batch_size = whisper_config.get("batch_size", 4)
    result = model.transcribe(
        audio,
        batch_size=batch_size,
        language=language if language != "auto" else None,
    )

    progress("aligning", "Aligning transcript...", 72)
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)

    hf_token = diarization_config.get("hf_token") or os.environ.get("HUGGINGFACE_TOKEN")

    if hf_token:
        progress("diarizing", "Running speaker diarization...", 82)
        from whisperx.diarize import DiarizationPipeline
        diarize_model = DiarizationPipeline(token=hf_token, device=device)

        diarize_kwargs = {}
        if diarization_config.get("min_speakers"):
            diarize_kwargs["min_speakers"] = diarization_config["min_speakers"]
        if diarization_config.get("max_speakers"):
            diarize_kwargs["max_speakers"] = diarization_config["max_speakers"]

        diarize_segments = diarize_model(audio, **diarize_kwargs)
        result = whisperx.assign_word_speakers(diarize_segments, result)
    else:
        progress("diarizing", "No HuggingFace token - skipping speaker diarization", 95)

    progress("done_transcription", "Transcription complete", 95)
    return result


def get_speaker_samples(transcript: dict, num_samples: int = 8) -> dict:
    """
    Extract representative sample lines for each speaker.

    Returns dict keyed by speaker ID:
        {
            "SPEAKER_00": {
                "count": 618,
                "samples": [{"start": 41.2, "text": "Roll initiative."}, ...]
            }
        }
    Samples are spread across the session. Very short utterances are skipped.
    """
    speaker_segments = defaultdict(list)
    speaker_total_count = defaultdict(int)

    for seg in transcript.get("segments", []):
        speaker_id = seg.get("speaker", "UNKNOWN")
        speaker_total_count[speaker_id] += 1
        text = seg.get("text", "").strip()
        if len(text) > 15:
            speaker_segments[speaker_id].append(seg)

    result = {}
    for speaker_id in speaker_total_count:
        segments = speaker_segments.get(speaker_id, [])
        if not segments:
            result[speaker_id] = {"count": speaker_total_count[speaker_id], "samples": []}
            continue

        if len(segments) <= num_samples:
            indices = list(range(len(segments)))
        else:
            step = len(segments) / num_samples
            indices = [int(i * step) for i in range(num_samples)]

        result[speaker_id] = {
            "count": speaker_total_count[speaker_id],
            "samples": [
                {"start": segments[i].get("start", 0), "text": segments[i].get("text", "").strip()}
                for i in indices
            ],
        }

    # Sort by segment count descending (most talkative first - likely the DM)
    result = dict(sorted(result.items(), key=lambda x: x[1]["count"], reverse=True))
    return result


def apply_speaker_names(transcript: dict, speaker_map: dict) -> dict:
    """Replace speaker IDs with names from the provided mapping."""
    for segment in transcript.get("segments", []):
        speaker_id = segment.get("speaker", "UNKNOWN")
        segment["speaker_name"] = speaker_map.get(speaker_id, speaker_id)
    return transcript


def save_transcript(transcript: dict, output_dir: Path, config: dict):
    """Save transcript in configured formats. Returns list of saved file paths."""
    output_config = config.get("output", {})
    formats = output_config.get("formats", ["json", "txt"])
    include_timestamps = output_config.get("timestamps", True)

    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    # JSON output (always save)
    json_path = output_dir / "transcript.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2)
    saved.append(json_path)

    if "txt" in formats:
        txt_path = output_dir / "transcript.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            for segment in transcript.get("segments", []):
                speaker = segment.get("speaker_name", segment.get("speaker", "UNKNOWN"))
                text = segment.get("text", "").strip()
                if include_timestamps:
                    start = segment.get("start", 0)
                    timestamp = f"[{int(start // 60):02d}:{int(start % 60):02d}]"
                    f.write(f"{timestamp} {speaker}: {text}\n")
                else:
                    f.write(f"{speaker}: {text}\n")
        saved.append(txt_path)

    if "srt" in formats:
        srt_path = output_dir / "transcript.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(transcript.get("segments", []), 1):
                start = segment.get("start", 0)
                end = segment.get("end", start + 1)
                speaker = segment.get("speaker_name", segment.get("speaker", ""))
                text = segment.get("text", "").strip()
                start_srt = f"{int(start // 3600):02d}:{int((start % 3600) // 60):02d}:{int(start % 60):02d},{int((start % 1) * 1000):03d}"
                end_srt = f"{int(end // 3600):02d}:{int((end % 3600) // 60):02d}:{int(end % 60):02d},{int((end % 1) * 1000):03d}"
                f.write(f"{i}\n")
                f.write(f"{start_srt} --> {end_srt}\n")
                f.write(f"[{speaker}] {text}\n\n")
        saved.append(srt_path)

    return saved


def generate_recap(transcript_path: str, config: dict, output_dir: Path) -> str:
    """Generate session recap using configured LLM. Returns recap text."""
    recap_config = config.get("recap", {})
    provider = recap_config.get("provider", "clawdbot")

    with open(transcript_path) as f:
        transcript = json.load(f)

    formatted = []
    for segment in transcript.get("segments", []):
        speaker = segment.get("speaker_name", segment.get("speaker", "UNKNOWN"))
        text = segment.get("text", "").strip()
        if text:
            formatted.append(f"{speaker}: {text}")

    transcript_text = "\n".join(formatted)
    system_prompt = recap_config.get("system_prompt", "Summarize this D&D session transcript.")

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=recap_config.get("model", "gpt-4o"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the session transcript:\n\n{transcript_text}"},
            ],
        )
        recap = response.choices[0].message.content

    elif provider == "clawdbot":
        import requests
        clawdbot_url = recap_config.get("clawdbot_url", "http://localhost:18789")
        api_key = recap_config.get("api_key") or os.environ.get("CLAWDBOT_API_KEY", "")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = requests.post(
            f"{clawdbot_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": recap_config.get("model", "default"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here is the session transcript:\n\n{transcript_text}"},
                ],
            },
        )
        response.raise_for_status()
        recap = response.json()["choices"][0]["message"]["content"]

    else:
        return ""

    output_dir.mkdir(parents=True, exist_ok=True)
    recap_path = output_dir / "recap.md"
    with open(recap_path, "w", encoding="utf-8") as f:
        f.write("# Session Recap\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write(recap)

    return recap


def save_session_meta(output_dir: Path, session_name: str, audio_file: str,
                      speaker_map: dict, status: str = "completed"):
    """Save session metadata to session.yaml in the output directory."""
    meta = {
        "name": session_name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "audio_file": audio_file,
        "speakers": speaker_map,
        "status": status,
        "created_at": datetime.now().isoformat(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "session.yaml", "w", encoding="utf-8") as f:
        yaml.dump(meta, f, default_flow_style=False)
    return meta


def load_session_meta(session_dir: Path) -> dict:
    """Load session metadata from session.yaml, or infer from files."""
    meta_path = session_dir / "session.yaml"
    if meta_path.exists():
        with open(meta_path) as f:
            return yaml.safe_load(f)
    # Fallback: infer from directory name
    name = session_dir.name
    return {
        "name": name,
        "date": name[:10] if len(name) >= 10 else "",
        "status": "completed" if (session_dir / "transcript.json").exists() else "unknown",
        "speakers": {},
    }
