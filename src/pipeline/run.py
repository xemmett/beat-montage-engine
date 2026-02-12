from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.audio.beat_detector import detect_beats
from src.audio.structure_analyzer import analyze_structure
from src.assembly.ffmpeg_renderer import render_montage
from src.planning.montage_plan import create_montage_plan
from src.planning.timeline import create_timeline
from src.retrieval.clip_selector import select_clips_for_montage

app = typer.Typer(add_completion=False, help="Beat-synchronized video montage generator")
console = Console()


@app.command()
def run(
    audio: Path = typer.Option(..., "--audio", "-a", help="Input audio file (MP3, WAV, etc.)"),
    output: Path = typer.Option(..., "--output", "-o", help="Output video file (MP4)"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Optional YAML config file"),
    beats_per_clip: int = typer.Option(1, "--beats-per-clip", help="Number of beats per clip"),
    random_seed: Optional[int] = typer.Option(None, "--seed", help="Random seed for deterministic output"),
    avoid_repetition: bool = typer.Option(True, "--avoid-repetition/--allow-repetition", help="Avoid using same clip multiple times"),
):
    """
    Generate a beat-synchronized video montage from an audio file.
    
    Example:
        python -m src.pipeline.run --audio track.mp3 --output montage.mp4
    """
    if not audio.exists():
        console.print(f"[red]Error: Audio file not found: {audio}[/red]")
        raise typer.Exit(1)
    
    # Load config if provided
    config_data = None
    if config and config.exists():
        import yaml
        with open(config) as f:
            config_data = yaml.safe_load(f)
    
    console.print(f"[bold]Beat Montage Generator[/bold]")
    console.print(f"Audio: {audio}")
    console.print(f"Output: {output}")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Stage 1: Audio Analysis
        task1 = progress.add_task("Analyzing beats...", total=None)
        beat_analysis = detect_beats(audio)
        progress.update(task1, description=f"Detected {len(beat_analysis.beats)} beats at {beat_analysis.bpm:.1f} BPM")
        
        task2 = progress.add_task("Analyzing structure...", total=None)
        structure = analyze_structure(audio)
        progress.update(task2, description=f"Detected {len(structure.sections)} sections")
        
        # Stage 2: Timeline Planning
        task3 = progress.add_task("Creating timeline...", total=None)
        timeline_slots = create_timeline(beat_analysis, beats_per_clip=beats_per_clip)
        progress.update(task3, description=f"Created {len(timeline_slots)} timeline slots")
        
        # Stage 3: Montage Planning
        task4 = progress.add_task("Planning montage...", total=None)
        montage_slots = create_montage_plan(timeline_slots, structure, config=config_data)
        progress.update(task4, description=f"Planned {len(montage_slots)} montage slots")
        
        # Stage 4: Clip Retrieval
        task5 = progress.add_task("Selecting clips from database...", total=len(montage_slots))
        selected_clips = select_clips_for_montage(
            montage_slots,
            random_seed=random_seed,
            avoid_repetition=avoid_repetition,
        )
        for _ in range(len(montage_slots)):
            progress.advance(task5)
        
        found_count = sum(1 for c in selected_clips if c is not None)
        progress.update(task5, description=f"Selected {found_count}/{len(montage_slots)} clips")
        
        if found_count == 0:
            console.print("[red]Error: No clips found in database matching queries[/red]")
            raise typer.Exit(1)
        
        # Stage 5: Video Assembly
        task6 = progress.add_task("Rendering montage...", total=None)
        render_montage(selected_clips, audio, output)
        progress.update(task6, description="Montage rendered successfully")
    
    # Log selected clips
    log_file = output.with_suffix(".json")
    log_data = {
        "audio_file": str(audio),
        "output_file": str(output),
        "bpm": beat_analysis.bpm,
        "beats_count": len(beat_analysis.beats),
        "sections": [
            {"type": s.type, "start": s.start, "end": s.end}
            for s in structure.sections
        ],
        "selected_clips": [
            {
                "clip_id": c.clip_id,
                "filepath": c.filepath,
                "duration": c.duration,
                "trim_start": c.trim_start,
                "trim_duration": c.trim_duration,
                "section_type": montage_slots[i].section_type,
            }
            for i, c in enumerate(selected_clips)
            if c is not None
        ],
    }
    
    with open(log_file, "w") as f:
        json.dump(log_data, f, indent=2)
    
    console.print(f"\n[green]✓ Montage complete![/green]")
    console.print(f"  Video: {output}")
    console.print(f"  Log: {log_file}")
    console.print(f"  Clips used: {found_count}/{len(montage_slots)}")


if __name__ == "__main__":
    app()

