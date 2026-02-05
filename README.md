# D&D Scribe 🎲📜

Automated transcription and session notes for tabletop RPG sessions.

Records audio, identifies speakers, transcribes the session, and generates recap notes — all locally, with no ongoing API costs.

## Features

- **Speaker Diarization** — Automatically identifies and labels different speakers
- **High-Quality Transcription** — Powered by Whisper
- **Smart Recaps** — LLM-generated session summaries with key events, combat highlights, and plot developments
- **Batch Processing** — Designed for post-session processing (no real-time requirements)
- **Fully Local** — Runs on your own hardware, no cloud dependencies

## Requirements

- Python 3.10+
- ffmpeg
- **GPU (optional but recommended):** CUDA-capable NVIDIA GPU with 8GB+ VRAM
- **CPU-only:** Works fine, just slower. Expect ~1-2x realtime (4hr session ≈ 4-8hr processing)

### Hardware Recommendations

| Setup | Model | Processing Time (4hr session) |
|-------|-------|------------------------------|
| RTX 5070 Ti | large-v3 | ~15-20 minutes |
| RTX 3060 (12GB) | large-v3 | ~30-45 minutes |
| CPU (i5-12400) | medium | ~4-6 hours |
| CPU (i5-8257U) | medium | ~6-10 hours |

## Installation

```bash
# Clone the repo
git clone https://github.com/kagemae/dnd-scribe.git
cd dnd-scribe

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### 1. Record Your Session

Record your D&D session as a WAV or MP3 file. Any decent recording setup works — a USB mic in the center of the table, a phone, etc.

### 2. Process the Recording

```bash
python scribe.py process /path/to/session.wav --output ./sessions/2026-02-05/
```

### 3. Configure Speaker Names

On first run, the tool will identify speakers as "Speaker 1", "Speaker 2", etc. Edit `speakers.json` to map these to actual names:

```json
{
  "SPEAKER_00": "Jason (DM)",
  "SPEAKER_01": "Michael",
  "SPEAKER_02": "Rhys",
  "SPEAKER_03": "Alisha"
}
```

### 4. Generate Session Recap

```bash
python scribe.py recap ./sessions/2026-02-05/transcript.json
```

## Output

Each processed session creates:
- `transcript.json` — Full transcript with timestamps and speaker labels
- `transcript.txt` — Human-readable transcript
- `recap.md` — AI-generated session summary

## Configuration

Edit `config.yaml` to customize:
- Whisper model size (tiny/base/small/medium/large)
- Speaker diarization sensitivity
- Recap prompts and style
- Output formats

## Architecture

```
Audio File
    ↓
[whisperX] → Transcription + Diarization
    ↓
Speaker-labeled transcript
    ↓
[LLM] → Session recap & notes
```

## License

MIT

---

*"Roll for initiative... and don't forget to hit record."*
