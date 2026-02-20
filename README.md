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

---

## Installation (Windows with NVIDIA GPU)

### Prerequisites

1. **NVIDIA Drivers** — Make sure you have the latest drivers for your GPU
   - Download from: https://www.nvidia.com/Download/index.aspx

2. **CUDA Toolkit 12.8+** — Required for GPU acceleration
   - Download from: https://developer.nvidia.com/cuda-downloads
   - Select: Windows → x86_64 → 11 → exe (local)
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
git clone https://github.com/kagemae/dnd-scribe.git
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
git clone https://github.com/kagemae/dnd-scribe.git
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
