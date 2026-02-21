# D&D Scribe

Audio transcription pipeline for tabletop RPG sessions.

Records audio, identifies speakers via diarization, and transcribes the session using Whisper — all locally on GPU. Completed transcripts are pushed to [dnd-session-wiki](https://github.com/Kagemae/dnd-session-wiki) for review, cleanup, and recap generation.

## Architecture

```
                        dnd-scribe (this repo)                    dnd-session-wiki
                        ~~~~~~~~~~~~~~~~~~~~~~                    ~~~~~~~~~~~~~~~~

Audio File ──> [whisperX] ──> Transcription + Diarization
                                      |
                              Speaker Identification
                                (local web UI)
                                      |
                              transcript.json + session.yaml
                                      |
                                 API Push ──────────────────> POST /api/sessions/ingest
                                                                      |
                                                              DM reviews & cleans
                                                              up wording/speakers
                                                                      |
                                                              [LLM] ──> Recap
                                                                      |
                                                               Campaign Wiki
```

## Features

- **Speaker Diarization** — Automatically identifies and labels different speakers
- **High-Quality Transcription** — Powered by Whisper (large-v3 on GPU)
- **Local Web UI** — Browser-based interface for running transcription jobs and identifying speakers
- **Wiki Integration** — Push completed transcripts to dnd-session-wiki via API
- **Batch Processing** — Designed for post-session processing (no real-time requirements)
- **Fully Local** — Runs on your own hardware, no cloud dependencies

## Requirements

- Python 3.10+
- ffmpeg
- **GPU (optional but recommended):** CUDA-capable NVIDIA GPU with 8GB+ VRAM
- **CPU-only:** Works fine, just slower. Expect ~1-2x realtime (4hr session = 4-8hr processing)

### Hardware Recommendations

| Setup | Model | Processing Time (4hr session) |
|-------|-------|------------------------------|
| RTX 5070 Ti | large-v3 | ~15-20 minutes |
| RTX 3060 (12GB) | large-v3 | ~30-45 minutes |
| CPU (i5-12400) | medium | ~4-6 hours |
| CPU (i5-8257U) | medium | ~6-10 hours |

---

## Installation (Windows with NVIDIA GPU)

### Prerequisites

1. **NVIDIA Drivers** — Make sure you have the latest drivers for your GPU
   - Download from: https://www.nvidia.com/Download/index.aspx

2. **CUDA Toolkit 12.8+** — Required for GPU acceleration
   - Download from: https://developer.nvidia.com/cuda-downloads
   - Select: Windows > x86_64 > 11 > exe (local)
   - Run installer, default options are fine
   - Verify: `nvcc --version` in a new terminal

3. **Python 3.10+** — Get from Microsoft Store or python.org
   - Verify: `python --version`

4. **ffmpeg** — Required for audio processing
   ```powershell
   # Option 1: winget (easiest)
   winget install ffmpeg

   # Option 2: Download manually from https://ffmpeg.org/download.html
   # Extract and add bin folder to PATH
   ```
   - Verify: `ffmpeg -version`

5. **Git** — For cloning the repo
   ```powershell
   winget install Git.Git
   ```

### Setup

```powershell
# Clone the repo
git clone https://github.com/Kagemae/dnd-scribe.git
cd dnd-scribe

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install PyTorch with CUDA 12.8 support FIRST (important!)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# Verify CUDA is available
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

# Install remaining dependencies
pip install -r requirements.txt
```

### Configure for GPU

Edit `config.yaml`:

```yaml
whisper:
  model: large-v3       # Best quality on GPU
  compute_type: float16 # GPU-optimized
  device: cuda          # Use GPU
```

### HuggingFace Token (Required for Speaker Diarization)

Speaker diarization uses pyannote models which require a HuggingFace token:

1. Create account at https://huggingface.co
2. Accept the pyannote model licenses:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0
3. Create a token at https://huggingface.co/settings/tokens
4. Add to your `.env` file:
   ```
   HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
   ```

### Quick Test

```powershell
# Test with a short audio clip
python scribe.py process test.wav --output ./test-output/
```

---

## Installation (Linux/macOS)

```bash
# Clone the repo
git clone https://github.com/Kagemae/dnd-scribe.git
cd dnd-scribe

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# For GPU on Linux, install PyTorch with CUDA first:
# pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

## Usage

### Web UI (recommended)

```bash
python web.py
# Browse to http://localhost:8000
```

The web interface lets you:
- Start transcription jobs from uploaded or local audio files
- Track progress in real-time via SSE
- Identify speakers by reviewing sample quotes
- View transcripts and push completed sessions to the wiki

### CLI

```bash
# Transcribe an audio file
python scribe.py process /path/to/session.wav --output ./sessions/2026-02-05/

# Transcribe and push to wiki in one step
python scribe.py process /path/to/session.wav --push

# Push an existing session to the wiki
python scribe.py push ./sessions/2026-02-20-witchlight/

# Regenerate a recap locally
python scribe.py recap ./sessions/2026-02-05/transcript.json
```

## Wiki Integration

Completed transcripts are pushed to [dnd-session-wiki](https://github.com/Kagemae/dnd-session-wiki) where the DM can review speaker assignments, clean up wording, and generate recaps.

### Configuration

Add the wiki URL to `config.yaml`:

```yaml
wiki:
  url: "http://your-wiki-host:port"
  api_key: ""        # optional
  auto_push: true    # push automatically when jobs complete
```

Or use environment variables: `WIKI_URL`, `WIKI_API_KEY`.

### Push methods

1. **Auto-push** — When `wiki.auto_push` is `true` and a URL is configured, transcripts are pushed automatically after each job completes.
2. **Web UI button** — Click "Push to Wiki" on any session page.
3. **CLI** — `python scribe.py push ./sessions/<session-dir>/`

### Interface contract

The push payload format is documented in [`interface/INTERFACE.md`](interface/INTERFACE.md). dnd-scribe owns this spec as the producer. The wiki validates incoming payloads against it.

## Output

Each processed session creates a directory under `sessions/` containing:
- `session.yaml` — Session metadata (name, date, speakers)
- `transcript.json` — Full transcript with timestamps, speaker labels, and word-level timing
- `transcript.txt` — Human-readable transcript
- `transcript.srt` — Subtitle file
- `recap.md` — AI-generated session summary (if generated locally)

## Configuration

Edit `config.yaml` to customize:
- Whisper model size (tiny/base/small/medium/large-v3)
- Speaker diarization settings (min/max speakers)
- Vocabulary list for D&D-specific term recognition
- Wiki push settings
- Recap prompts and LLM provider (for local recap generation)
- Output formats

## License

MIT

---

*"Roll for initiative... and don't forget to hit record."*
