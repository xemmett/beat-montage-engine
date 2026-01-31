from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from src.retrieval.clip_selector import SelectedClip


class FFmpegError(RuntimeError):
    pass


def _run_ffmpeg(cmd: list[str]) -> None:
    """Run FFmpeg command and raise error if it fails."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(
            f"FFmpeg command failed ({proc.returncode}): {' '.join(cmd)}\n\nSTDERR:\n{proc.stderr}"
        )


def trim_clip(
    input_path: Path,
    output_path: Path,
    start_time: float,
    duration: float,
) -> Path:
    """
    Trim a clip to specified start time and duration.
    
    Args:
        input_path: Input video file
        output_path: Output trimmed video file
        start_time: Start time in seconds
        duration: Duration in seconds
    
    Returns:
        Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{start_time:.6f}",
        "-i", str(input_path),
        "-t", f"{duration:.6f}",
        "-c", "copy",  # Stream copy for speed
        str(output_path),
    ]
    
    _run_ffmpeg(cmd)
    return output_path


def render_montage(
    selected_clips: list[SelectedClip],
    audio_path: Path,
    output_path: Path,
    *,
    temp_dir: Optional[Path] = None,
    crossfade_duration: float = 0.0,  # Crossfade duration in seconds (0 = hard cuts)
) -> Path:
    """
    Assemble clips into final montage video with audio.
    
    Args:
        selected_clips: List of selected clips (None entries are skipped)
        audio_path: Original audio file (MP3)
        output_path: Final output video path
        temp_dir: Temporary directory for intermediate files
        crossfade_duration: Crossfade duration between clips (0 = hard cuts)
    
    Returns:
        Path to final video
    """
    if temp_dir is None:
        temp_dir = output_path.parent / ".temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Filter out None clips
    valid_clips = [c for c in selected_clips if c is not None]
    if not valid_clips:
        raise ValueError("No valid clips provided for montage")
    
    # Step 1: Trim all clips
    trimmed_clips: list[Path] = []
    for i, clip in enumerate(valid_clips):
        trimmed_path = temp_dir / f"clip_{i:04d}.mp4"
        try:
            trim_clip(
                Path(clip.filepath),
                trimmed_path,
                clip.trim_start,
                clip.trim_duration,
            )
            trimmed_clips.append(trimmed_path)
        except Exception as e:
            print(f"Warning: Failed to trim clip {clip.clip_id}: {e}")
            continue
    
    if not trimmed_clips:
        raise ValueError("No clips could be trimmed successfully")
    
    # Step 2: Create concat file
    concat_file = temp_dir / "concat.txt"
    with open(concat_file, "w") as f:
        for clip_path in trimmed_clips:
            f.write(f"file '{clip_path.absolute()}'\n")
    
    # Step 3: Concatenate video clips
    video_only = temp_dir / "video_only.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(video_only),
    ]
    _run_ffmpeg(cmd)
    
    # Step 4: Mux video with audio
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_only),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",  # End when shortest stream ends
        str(output_path),
    ]
    _run_ffmpeg(cmd)
    
    # Cleanup temp files
    try:
        for f in trimmed_clips:
            if f.exists():
                f.unlink()
        if video_only.exists():
            video_only.unlink()
        if concat_file.exists():
            concat_file.unlink()
    except Exception:
        pass  # Best effort cleanup
    
    return output_path



