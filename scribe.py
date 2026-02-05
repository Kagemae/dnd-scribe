#!/usr/bin/env python3
"""
D&D Scribe - Automated session transcription and recap generation.
"""

import os
import json
import click
import yaml
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[yellow]Config file not found at {config_path}, using defaults[/yellow]")
        return {}
    
    with open(config_file) as f:
        return yaml.safe_load(f)


def transcribe_audio(audio_path: str, config: dict, output_dir: Path) -> dict:
    """
    Transcribe audio file with speaker diarization using whisperX.
    
    Returns transcript data with speaker labels and timestamps.
    """
    import whisperx
    import torch
    
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
    
    console.print(f"[cyan]Loading Whisper model: {model_name}[/cyan]")
    console.print(f"[dim]Device: {device}, Compute: {compute_type}[/dim]")
    
    # Load model
    model = whisperx.load_model(model_name, device, compute_type=compute_type)
    
    # Load audio
    console.print(f"[cyan]Loading audio: {audio_path}[/cyan]")
    audio = whisperx.load_audio(audio_path)
    
    # Transcribe
    console.print("[cyan]Transcribing... (this may take a while for long sessions)[/cyan]")
    result = model.transcribe(audio, batch_size=16, language=language if language != "auto" else None)
    
    # Align whisper output
    console.print("[cyan]Aligning transcript...[/cyan]")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
    
    # Speaker diarization
    hf_token = diarization_config.get("hf_token") or os.environ.get("HUGGINGFACE_TOKEN")
    
    if hf_token:
        console.print("[cyan]Running speaker diarization...[/cyan]")
        diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
        
        diarize_kwargs = {}
        if diarization_config.get("min_speakers"):
            diarize_kwargs["min_speakers"] = diarization_config["min_speakers"]
        if diarization_config.get("max_speakers"):
            diarize_kwargs["max_speakers"] = diarization_config["max_speakers"]
        
        diarize_segments = diarize_model(audio, **diarize_kwargs)
        result = whisperx.assign_word_speakers(diarize_segments, result)
    else:
        console.print("[yellow]No HuggingFace token found - skipping speaker diarization[/yellow]")
        console.print("[dim]Set HUGGINGFACE_TOKEN env var or hf_token in config.yaml[/dim]")
    
    return result


def apply_speaker_names(transcript: dict, config: dict) -> dict:
    """Replace speaker IDs with configured names."""
    speaker_map = config.get("speakers", {})
    
    for segment in transcript.get("segments", []):
        speaker_id = segment.get("speaker", "UNKNOWN")
        segment["speaker_name"] = speaker_map.get(speaker_id, speaker_id)
    
    return transcript


def save_transcript(transcript: dict, output_dir: Path, config: dict):
    """Save transcript in configured formats."""
    output_config = config.get("output", {})
    formats = output_config.get("formats", ["json", "txt"])
    include_timestamps = output_config.get("timestamps", True)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # JSON output (always save for recap generation)
    json_path = output_dir / "transcript.json"
    with open(json_path, "w") as f:
        json.dump(transcript, f, indent=2)
    console.print(f"[green]Saved:[/green] {json_path}")
    
    # Text output
    if "txt" in formats:
        txt_path = output_dir / "transcript.txt"
        with open(txt_path, "w") as f:
            for segment in transcript.get("segments", []):
                speaker = segment.get("speaker_name", segment.get("speaker", "UNKNOWN"))
                text = segment.get("text", "").strip()
                
                if include_timestamps:
                    start = segment.get("start", 0)
                    timestamp = f"[{int(start//60):02d}:{int(start%60):02d}]"
                    f.write(f"{timestamp} {speaker}: {text}\n")
                else:
                    f.write(f"{speaker}: {text}\n")
        console.print(f"[green]Saved:[/green] {txt_path}")
    
    # SRT output (subtitles)
    if "srt" in formats:
        srt_path = output_dir / "transcript.srt"
        with open(srt_path, "w") as f:
            for i, segment in enumerate(transcript.get("segments", []), 1):
                start = segment.get("start", 0)
                end = segment.get("end", start + 1)
                speaker = segment.get("speaker_name", segment.get("speaker", ""))
                text = segment.get("text", "").strip()
                
                start_srt = f"{int(start//3600):02d}:{int((start%3600)//60):02d}:{int(start%60):02d},{int((start%1)*1000):03d}"
                end_srt = f"{int(end//3600):02d}:{int((end%3600)//60):02d}:{int(end%60):02d},{int((end%1)*1000):03d}"
                
                f.write(f"{i}\n")
                f.write(f"{start_srt} --> {end_srt}\n")
                f.write(f"[{speaker}] {text}\n\n")
        console.print(f"[green]Saved:[/green] {srt_path}")


def generate_recap(transcript_path: str, config: dict, output_dir: Path) -> str:
    """Generate session recap using configured LLM."""
    recap_config = config.get("recap", {})
    provider = recap_config.get("provider", "clawdbot")
    
    # Load transcript
    with open(transcript_path) as f:
        transcript = json.load(f)
    
    # Format transcript for LLM
    formatted = []
    for segment in transcript.get("segments", []):
        speaker = segment.get("speaker_name", segment.get("speaker", "UNKNOWN"))
        text = segment.get("text", "").strip()
        if text:
            formatted.append(f"{speaker}: {text}")
    
    transcript_text = "\n".join(formatted)
    system_prompt = recap_config.get("system_prompt", "Summarize this D&D session transcript.")
    
    console.print(f"[cyan]Generating recap via {provider}...[/cyan]")
    
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=recap_config.get("model", "gpt-4o"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the session transcript:\n\n{transcript_text}"}
            ]
        )
        recap = response.choices[0].message.content
        
    elif provider == "clawdbot":
        import requests
        clawdbot_url = recap_config.get("clawdbot_url", "http://localhost:18789")
        response = requests.post(
            f"{clawdbot_url}/v1/chat/completions",
            json={
                "model": recap_config.get("model", "default"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here is the session transcript:\n\n{transcript_text}"}
                ]
            }
        )
        response.raise_for_status()
        recap = response.json()["choices"][0]["message"]["content"]
        
    else:
        console.print(f"[red]Unknown recap provider: {provider}[/red]")
        return ""
    
    # Save recap
    recap_path = output_dir / "recap.md"
    with open(recap_path, "w") as f:
        f.write(f"# Session Recap\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write(recap)
    
    console.print(f"[green]Saved:[/green] {recap_path}")
    return recap


@click.group()
def cli():
    """D&D Scribe - Automated session transcription and recap generation."""
    pass


@cli.command()
@click.argument("audio_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option("--config", "-c", type=click.Path(), default="config.yaml", help="Config file path")
@click.option("--skip-recap", is_flag=True, help="Skip recap generation")
def process(audio_path: str, output: str, config: str, skip_recap: bool):
    """Process an audio recording: transcribe, diarize, and generate recap."""
    
    cfg = load_config(config)
    
    # Determine output directory
    if output:
        output_dir = Path(output)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d")
        output_dir = Path("sessions") / timestamp
    
    console.print(f"\n[bold]🎲 D&D Scribe[/bold]")
    console.print(f"[dim]Processing: {audio_path}[/dim]")
    console.print(f"[dim]Output: {output_dir}[/dim]\n")
    
    # Transcribe
    transcript = transcribe_audio(audio_path, cfg, output_dir)
    
    # Apply speaker names
    transcript = apply_speaker_names(transcript, cfg)
    
    # Save outputs
    save_transcript(transcript, output_dir, cfg)
    
    # Generate recap
    if not skip_recap:
        transcript_json = output_dir / "transcript.json"
        generate_recap(str(transcript_json), cfg, output_dir)
    
    console.print(f"\n[bold green]✓ Processing complete![/bold green]")
    console.print(f"[dim]Check {output_dir} for outputs[/dim]\n")


@cli.command()
@click.argument("transcript_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output directory (defaults to transcript directory)")
@click.option("--config", "-c", type=click.Path(), default="config.yaml", help="Config file path")
def recap(transcript_path: str, output: str, config: str):
    """Generate or regenerate a session recap from an existing transcript."""
    
    cfg = load_config(config)
    
    transcript_file = Path(transcript_path)
    output_dir = Path(output) if output else transcript_file.parent
    
    console.print(f"\n[bold]🎲 D&D Scribe - Recap Generation[/bold]")
    console.print(f"[dim]Transcript: {transcript_path}[/dim]\n")
    
    generate_recap(transcript_path, cfg, output_dir)
    
    console.print(f"\n[bold green]✓ Recap generated![/bold green]\n")


@cli.command()
@click.option("--config", "-c", type=click.Path(), default="config.yaml", help="Config file path")
def list_speakers(config: str):
    """List configured speaker mappings."""
    
    cfg = load_config(config)
    speakers = cfg.get("speakers", {})
    
    console.print(f"\n[bold]Speaker Mappings[/bold]\n")
    for speaker_id, name in speakers.items():
        console.print(f"  {speaker_id} → {name}")
    console.print()


if __name__ == "__main__":
    cli()
