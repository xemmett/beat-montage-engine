from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.db.query import ClipQuery, query_clips


@dataclass
class SelectedClip:
    clip_id: str
    filepath: str
    duration: float
    source: str
    year: Optional[int]
    start_time: float
    end_time: float
    trim_start: float = 0.0  # Where to start in the clip (for trimming)
    trim_duration: float = 0.0  # How much of the clip to use


def _fallback_query_any(query: ClipQuery) -> ClipQuery:
    """
    Create a relaxed query that prioritizes returning *some* clip.
    Keeps coarse constraints like source/year, but removes tags, entities, and signal limits.
    """
    return ClipQuery(
        tags=[],
        entities=[],
        min_tag_score=0.0,
        min_entity_confidence=0.0,
        min_motion=None,
        max_motion=None,
        max_silence=None,
        min_brightness=None,
        semantic_query=None,
        year_min=query.year_min,
        year_max=query.year_max,
        source=query.source,
        exclude_clip_ids=[],
    )


def select_clip_for_slot(
    query: ClipQuery,
    target_duration: float,
    *,
    exclude_clip_ids: Optional[list[str]] = None,
    random_seed: Optional[int] = None,
) -> Optional[SelectedClip]:
    """
    Select a clip from the database that matches the query and fits the target duration.
    
    Args:
        query: Query parameters for clip selection
        target_duration: Target duration for the clip slot
        exclude_clip_ids: Clip IDs to exclude (avoid repetition)
        random_seed: Optional seed for deterministic randomness
    
    Returns:
        SelectedClip or None if no suitable clip found
    """
    if random_seed is not None:
        random.seed(random_seed)
    
    # Add exclude list to query
    if exclude_clip_ids:
        query.exclude_clip_ids = exclude_clip_ids
    
    # Query database
    candidates = query_clips(query, limit=100, randomize=True)
    
    if not candidates:
        # Fallback: if query is too strict, grab any clip (still respects source/year if set).
        candidates = query_clips(_fallback_query_any(query), limit=200, randomize=True)
        if not candidates:
            return None
    
    # Prefer candidates that can fully cover the slot, so we can trim down (no gaps).
    suitable = [c for c in candidates if c["duration"] >= target_duration]
    
    if not suitable:
        # Fall back to something close (best effort). Renderer will fill remaining audio if needed.
        suitable = candidates[:50]
    
    # Select random clip from suitable candidates
    selected = random.choice(suitable)
    
    # Calculate trim parameters
    clip_duration = selected["duration"]
    if clip_duration > target_duration:
        # Clip is longer than needed - trim from start
        trim_start = random.uniform(0.0, max(0.0, clip_duration - target_duration))
        trim_duration = target_duration
    else:
        # Clip is shorter - use entire clip
        trim_start = 0.0
        trim_duration = clip_duration
    
    # Verify file exists
    filepath = Path(selected["filepath"])
    if not filepath.exists():
        # Try relative to data directory
        from src.db.query import get_data_dir
        data_dir = get_data_dir()
        # If filepath is already relative, use it as-is
        if not Path(selected["filepath"]).is_absolute():
            filepath = data_dir / "clips" / selected["filepath"]
        else:
            # Try just the filename relative to clips directory
            filepath = data_dir / "clips" / Path(selected["filepath"]).name
        if not filepath.exists():
            return None
    
    return SelectedClip(
        clip_id=selected["clip_id"],
        filepath=str(filepath),
        duration=clip_duration,
        source=selected["source"],
        year=selected.get("year"),
        start_time=selected["start_time"],
        end_time=selected["end_time"],
        trim_start=trim_start,
        trim_duration=trim_duration,
    )


def select_clips_for_montage(
    montage_slots: list,  # list[MontageSlot]
    *,
    random_seed: Optional[int] = None,
    avoid_repetition: bool = True,
) -> list[Optional[SelectedClip]]:
    """
    Select clips for all montage slots, avoiding repetition.
    
    Args:
        montage_slots: List of MontageSlot objects
        random_seed: Optional seed for deterministic randomness
        avoid_repetition: If True, avoid using the same clip multiple times
    
    Returns:
        List of SelectedClip objects (or None if no clip found for a slot)
    """
    if random_seed is not None:
        random.seed(random_seed)
    
    selected_clips: list[Optional[SelectedClip]] = []
    used_clip_ids: list[str] = []
    
    for slot in montage_slots:
        exclude_ids = used_clip_ids if avoid_repetition else None
        clip = select_clip_for_slot(
            slot.query,
            slot.timeline_slot.duration,
            exclude_clip_ids=exclude_ids,
            random_seed=None,  # Don't reset seed for each selection
        )

        # If we couldn't find a clip while avoiding repetition, allow repetition rather than leaving a hole.
        if clip is None and avoid_repetition:
            clip = select_clip_for_slot(
                slot.query,
                slot.timeline_slot.duration,
                exclude_clip_ids=None,
                random_seed=None,
            )
        
        selected_clips.append(clip)
        if clip and avoid_repetition:
            used_clip_ids.append(clip.clip_id)
    
    return selected_clips

