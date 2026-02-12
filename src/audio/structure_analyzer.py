from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
from scipy import signal


@dataclass
class Section:
    type: str  # 'intro', 'drop', 'breakdown', 'outro', etc.
    start: float  # Start time in seconds
    end: float  # End time in seconds


@dataclass
class StructureAnalysis:
    sections: list[Section]
    energy: list[float]  # RMS energy over time (normalized)
    duration: float  # Total audio duration


def analyze_structure(
    audio_path: Path,
    *,
    hop_length: int = 512,
    frame_length: int = 2048,
    window_size: int = 20,  # frames for smoothing
) -> StructureAnalysis:
    """
    Detect musical structure (intro, drop, breakdown, outro) using energy analysis.
    
    This is heuristic-based and works best for electronic/dance music.
    """
    # Load audio
    y, sr = librosa.load(str(audio_path), sr=None)
    duration = len(y) / sr
    
    # Compute RMS energy over time
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    
    # Smooth the energy curve
    if window_size > 1:
        window = np.ones(window_size) / window_size
        rms_smooth = np.convolve(rms, window, mode="same")
    else:
        rms_smooth = rms
    
    # Normalize energy to 0-1
    if rms_smooth.max() > 0:
        energy = (rms_smooth / rms_smooth.max()).tolist()
    else:
        energy = [0.0] * len(rms_smooth)
    
    # Convert frame indices to time
    times = librosa.frames_to_time(np.arange(len(energy)), sr=sr, hop_length=hop_length)
    
    # Heuristic section detection
    sections = _detect_sections(energy, times, duration)
    
    return StructureAnalysis(
        sections=sections,
        energy=energy,
        duration=float(duration),
    )


def _detect_sections(
    energy: list[float],
    times: np.ndarray,
    duration: float,
) -> list[Section]:
    """
    Heuristic-based section detection.
    
    Rules:
    - Intro: First 10-20% with low/rising energy
    - Drop: First major energy peak after intro
    - Breakdown: Low energy section after drop
    - Outro: Last 10-20% with falling energy
    """
    sections: list[Section] = []
    
    if len(energy) == 0:
        return sections
    
    energy_array = np.array(energy)
    mean_energy = np.mean(energy_array)
    
    # Intro: first 15% or until energy rises above threshold
    intro_end = min(duration * 0.15, duration * 0.25)
    for i, t in enumerate(times):
        if t >= intro_end or (i > 10 and energy[i] > mean_energy * 0.7):
            intro_end = t
            break
    
    if intro_end > 0:
        sections.append(Section(type="intro", start=0.0, end=float(intro_end)))
    
    # Find drop (first major peak after intro)
    drop_start = intro_end
    drop_end = duration * 0.4
    
    # Find peak energy in first half
    first_half_end = int(len(energy) * 0.5)
    if first_half_end > 0:
        peak_idx = int(np.argmax(energy_array[:first_half_end]))
        if peak_idx < len(times):
            drop_start = float(times[peak_idx])
            # Drop typically lasts 30-60 seconds or until energy drops
            drop_duration = min(60.0, duration * 0.3)
            drop_end = min(drop_start + drop_duration, duration * 0.7)
            
            # Find where energy actually drops
            for i in range(peak_idx, min(peak_idx + int(len(energy) * 0.3), len(energy))):
                if i < len(times) and energy[i] < mean_energy * 0.6:
                    drop_end = float(times[i])
                    break
    
    if drop_start < drop_end:
        sections.append(Section(type="drop", start=float(drop_start), end=float(drop_end)))
    
    # Breakdown: low energy section after drop
    breakdown_start = drop_end
    breakdown_end = min(breakdown_start + duration * 0.2, duration * 0.85)
    
    # Find low energy region
    breakdown_idx = int(np.argmin(energy_array[int(len(energy) * 0.5):]))
    if breakdown_idx > 0:
        breakdown_idx += int(len(energy) * 0.5)
        if breakdown_idx < len(times):
            breakdown_start = float(times[breakdown_idx])
            breakdown_end = min(breakdown_start + duration * 0.15, duration * 0.9)
    
    if breakdown_start < breakdown_end and breakdown_start > drop_end:
        sections.append(
            Section(type="breakdown", start=float(breakdown_start), end=float(breakdown_end))
        )
    
    # Outro: last 15% with falling energy
    outro_start = max(duration * 0.85, breakdown_end if sections else drop_end)
    if outro_start < duration:
        sections.append(Section(type="outro", start=float(outro_start), end=float(duration)))
    
    return sections









