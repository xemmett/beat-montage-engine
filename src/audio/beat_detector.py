from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np


@dataclass
class BeatAnalysis:
    bpm: float
    beats: list[float]  # Beat timestamps in seconds
    downbeats: Optional[list[float]] = None  # Downbeat timestamps (if detectable)


def detect_beats(audio_path: Path, *, hop_length: int = 512) -> BeatAnalysis:
    """
    Extract BPM and beat timestamps from audio file.
    
    Args:
        audio_path: Path to audio file (MP3, WAV, etc.)
        hop_length: Hop length for librosa analysis
    
    Returns:
        BeatAnalysis with BPM and beat timestamps
    """
    # Load audio
    y, sr = librosa.load(str(audio_path), sr=None)
    
    # Detect tempo and beats
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length, units="time")
    
    # Try to detect downbeats (bar boundaries)
    # This is heuristic-based and may not work for all tracks
    downbeats = None
    try:
        # Use onset detection to find strong beats
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
        
        # Simple heuristic: downbeats are often the first beat in a group
        # This is a simplified approach
        if len(beats) > 4:
            # Assume 4/4 time, so every 4th beat is a downbeat
            downbeats = beats[::4].tolist()
    except Exception:
        # Downbeat detection failed, continue without it
        pass
    
    return BeatAnalysis(
        bpm=float(tempo),
        beats=beats.tolist(),
        downbeats=downbeats,
    )

