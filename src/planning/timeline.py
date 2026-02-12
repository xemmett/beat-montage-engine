from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.audio.beat_detector import BeatAnalysis


@dataclass
class TimelineSlot:
    start: float  # Start time in montage (seconds)
    duration: float  # Duration of this slot (seconds)
    beat_index: int  # Which beat this corresponds to


def create_timeline(
    beat_analysis: BeatAnalysis,
    *,
    beats_per_clip: int = 1,
    duration_variation: float = 0.1,  # ±10% variation
) -> list[TimelineSlot]:
    """
    Convert beat timestamps into timeline slots for clips.
    
    Args:
        beat_analysis: Beat detection results
        beats_per_clip: Number of beats per clip (1 = cut on every beat, 2 = every 2 beats)
        duration_variation: Allowable duration variation (±10% = 0.1)
    
    Returns:
        List of timeline slots
    """
    slots: list[TimelineSlot] = []
    beats = beat_analysis.beats
    
    if len(beats) < 2:
        # Not enough beats, create a single slot
        if len(beats) == 1:
            slots.append(TimelineSlot(start=beats[0], duration=1.0, beat_index=0))
        return slots
    
    # Group beats
    for i in range(0, len(beats) - beats_per_clip + 1, beats_per_clip):
        start_beat = beats[i]
        
        # Calculate end beat
        if i + beats_per_clip < len(beats):
            end_beat = beats[i + beats_per_clip]
        else:
            # Last slot - use average beat interval
            avg_interval = (beats[-1] - beats[0]) / max(1, len(beats) - 1)
            end_beat = start_beat + (avg_interval * beats_per_clip)
        
        duration = end_beat - start_beat
        
        # Apply micro-variation (±duration_variation)
        variation = duration * duration_variation
        import random
        duration_adjusted = duration + random.uniform(-variation, variation)
        duration_adjusted = max(0.1, duration_adjusted)  # Minimum 0.1 seconds
        
        slots.append(
            TimelineSlot(
                start=float(start_beat),
                duration=float(duration_adjusted),
                beat_index=i,
            )
        )
    
    return slots









