from __future__ import annotations

import json
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


def _ffprobe_duration_seconds(path: Path) -> float:
    """
    Best-effort duration probe (seconds).
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return 0.0
    try:
        data = json.loads(proc.stdout)
        return float(data.get("format", {}).get("duration") or 0.0)
    except Exception:
        return 0.0


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
    
    # IMPORTANT:
    # Stream-copy trimming ("-c copy") frequently produces odd timestamps / VFR segments,
    # especially when cuts don't land on keyframes. When concatenated, many players
    # interpret the resulting non-monotonic timestamps as pauses/speedups/freezes.
    #
    # We intentionally normalize each segment here:
    # - reset timestamps to start at 0 (setpts)
    # - force constant frame rate (fps)
    # - scale+crop to a consistent output size
    # - re-encode video (H.264) so segments concatenate cleanly
    #
    # Audio is dropped per-clip; the montage muxes the main audio later.
    TARGET_W = 1920
    TARGET_H = 1080
    TARGET_FPS = 30

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start_time:.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        str(input_path),
        "-an",
        "-vf",
        (
            f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_W}:{TARGET_H},"
            f"setsar=1,"
            f"fps={TARGET_FPS},"
            f"setpts=PTS-STARTPTS"
        ),
        "-vsync",
        "cfr",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
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

    # If we couldn't fill the song (due to missing clips / short segments), extend video by appending
    # additional trimmed segments from *any* available clips. This prevents muxing with -shortest
    # from trimming the end of the audio.
    audio_duration = _ffprobe_duration_seconds(audio_path)
    if audio_duration > 0:
        planned_video_duration = sum(float(c.trim_duration) for c in valid_clips if c is not None and c.trim_duration)
        remaining = audio_duration - planned_video_duration
        if remaining > 0.05:
            i = len(trimmed_clips)
            j = 0
            while remaining > 0.05:
                filler = valid_clips[j % len(valid_clips)]
                # Prefer to trim from the filler clip (no speed changes), and clamp to remaining.
                seg_dur = min(float(filler.trim_duration or filler.duration or 1.0), remaining)
                trimmed_path = temp_dir / f"clip_{i:04d}.mp4"
                try:
                    trim_clip(
                        Path(filler.filepath),
                        trimmed_path,
                        float(filler.trim_start or 0.0),
                        float(seg_dur),
                    )
                    trimmed_clips.append(trimmed_path)
                    remaining -= seg_dur
                    i += 1
                    j += 1
                except Exception as e:
                    print(f"Warning: Failed to extend montage with fallback clip: {e}")
                    break
    
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
        # Even though clips are normalized above, re-encoding here makes the final
        # output more robust across players and avoids edge-case timestamp issues.
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
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




