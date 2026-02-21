#!/usr/bin/env python3
"""
D&D Scribe - CLI interface for session transcription and recap generation.
"""

import click
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console

import pipeline

load_dotenv()
console = Console()


@click.group()
def cli():
    """D&D Scribe - Automated session transcription and recap generation."""
    pass


@cli.command()
@click.argument("audio_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option("--config", "-c", type=click.Path(), default="config.yaml", help="Config file path")
@click.option("--skip-recap", is_flag=True, help="Skip recap generation")
@click.option("--push", is_flag=True, help="Push to wiki after processing")
def process(audio_path: str, output: str, config: str, skip_recap: bool, push: bool):
    """Process an audio recording: transcribe, diarize, and generate recap."""
    cfg = pipeline.load_config(config)

    if output:
        output_dir = Path(output)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d")
        output_dir = Path("sessions") / timestamp

    console.print(f"\n[bold]D&D Scribe[/bold]")
    console.print(f"[dim]Processing: {audio_path}[/dim]")
    console.print(f"[dim]Output: {output_dir}[/dim]\n")

    def cli_progress(stage, message, percent):
        console.print(f"[cyan]{message}[/cyan]")

    transcript = pipeline.transcribe_audio(audio_path, cfg, progress_callback=cli_progress)

    speaker_map = cfg.get("speakers", {})
    transcript = pipeline.apply_speaker_names(transcript, speaker_map)

    pipeline.save_transcript(transcript, output_dir, cfg)
    for p in [output_dir / "transcript.json", output_dir / "transcript.txt", output_dir / "transcript.srt"]:
        if p.exists():
            console.print(f"[green]Saved:[/green] {p}")

    if not skip_recap:
        transcript_json = output_dir / "transcript.json"
        pipeline.generate_recap(str(transcript_json), cfg, output_dir)
        console.print(f"[green]Saved:[/green] {output_dir / 'recap.md'}")

    if push:
        import wiki_push
        url = cfg.get("wiki", {}).get("url", "")
        key = cfg.get("wiki", {}).get("api_key", "")
        if url:
            console.print(f"[cyan]Pushing to wiki...[/cyan]")
            try:
                wiki_push.push_to_wiki(output_dir, url, key)
                console.print(f"[green]Pushed to wiki.[/green]")
            except Exception as e:
                console.print(f"[red]Wiki push failed: {e}[/red]")
        else:
            console.print("[yellow]--push specified but no wiki.url configured[/yellow]")

    console.print(f"\n[bold green]Processing complete![/bold green]")
    console.print(f"[dim]Check {output_dir} for outputs[/dim]\n")


@cli.command()
@click.argument("transcript_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output directory (defaults to transcript directory)")
@click.option("--config", "-c", type=click.Path(), default="config.yaml", help="Config file path")
def recap(transcript_path: str, output: str, config: str):
    """Generate or regenerate a session recap from an existing transcript."""
    cfg = pipeline.load_config(config)
    transcript_file = Path(transcript_path)
    output_dir = Path(output) if output else transcript_file.parent

    console.print(f"\n[bold]D&D Scribe - Recap Generation[/bold]")
    console.print(f"[dim]Transcript: {transcript_path}[/dim]\n")

    pipeline.generate_recap(transcript_path, cfg, output_dir)

    console.print(f"\n[bold green]Recap generated![/bold green]\n")


@cli.command()
@click.argument("session_dir", type=click.Path(exists=True))
@click.option("--wiki-url", envvar="WIKI_URL", default=None, help="Wiki API base URL")
@click.option("--api-key", envvar="WIKI_API_KEY", default="", help="Wiki API key")
@click.option("--config", "-c", type=click.Path(), default="config.yaml", help="Config file path")
def push(session_dir: str, wiki_url: str, api_key: str, config: str):
    """Push a completed session to the dnd-session-wiki."""
    import wiki_push

    cfg = pipeline.load_config(config)
    url = wiki_url or cfg.get("wiki", {}).get("url", "")
    key = api_key or cfg.get("wiki", {}).get("api_key", "")

    if not url:
        console.print("[red]No wiki URL configured.[/red]")
        console.print("[dim]Set wiki.url in config.yaml or pass --wiki-url[/dim]")
        raise SystemExit(1)

    console.print(f"\n[bold]D&D Scribe - Push to Wiki[/bold]")
    console.print(f"[dim]Session: {session_dir}[/dim]")
    console.print(f"[dim]Wiki: {url}[/dim]\n")

    try:
        result = wiki_push.push_to_wiki(Path(session_dir), url, key)
        console.print(f"[bold green]Pushed successfully![/bold green]")
        console.print(f"[dim]{result}[/dim]\n")
    except Exception as e:
        console.print(f"[red]Push failed: {e}[/red]\n")
        raise SystemExit(1)


@cli.command()
@click.option("--config", "-c", type=click.Path(), default="config.yaml", help="Config file path")
def list_speakers(config: str):
    """List configured speaker mappings."""
    cfg = pipeline.load_config(config)
    speakers = cfg.get("speakers", {})

    console.print(f"\n[bold]Speaker Mappings[/bold]\n")
    for speaker_id, name in speakers.items():
        console.print(f"  {speaker_id} -> {name}")
    console.print()


if __name__ == "__main__":
    cli()
