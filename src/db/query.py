from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Optional

import os
import random
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

# Import local database models and session
from src.db.models import Clip, ClipEmbedding, ClipEntity, ClipSignals, ClipTag
from src.db.session import get_session_factory


def get_data_dir() -> Path:
    """Get the data directory for clips."""
    data_dir = os.getenv("DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser().resolve()
    # Default: assume clips are in a 'data' directory relative to project root
    # or in a sibling 'aesthetic-indexer/data' directory
    project_root = Path(__file__).resolve().parents[2]
    # Try sibling aesthetic-indexer first (common setup)
    sibling_data = project_root.parent / "aesthetic-indexer" / "data"
    if sibling_data.exists():
        return sibling_data
    # Fallback to local data directory
    return project_root / "data"


class ClipQuery:
    """Query parameters for clip selection."""
    
    def __init__(
        self,
        tags: Optional[list[str]] = None,
        entities: Optional[list[str]] = None,
        min_tag_score: float = 0.3,
        min_entity_confidence: float = 0.3,
        min_motion: Optional[float] = None,
        max_motion: Optional[float] = None,
        max_silence: Optional[float] = None,
        min_brightness: Optional[float] = None,
        semantic_query: Optional[str] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        source: Optional[str] = None,
        exclude_clip_ids: Optional[list[str]] = None,
    ):
        self.tags = tags or []
        self.entities = entities or []
        self.min_tag_score = min_tag_score
        self.min_entity_confidence = min_entity_confidence
        self.min_motion = min_motion
        self.max_motion = max_motion
        self.max_silence = max_silence
        self.min_brightness = min_brightness
        self.semantic_query = semantic_query
        self.year_min = year_min
        self.year_max = year_max
        self.source = source
        self.exclude_clip_ids = exclude_clip_ids or []


def query_clips(
    query: ClipQuery,
    limit: int = 50,
    randomize: bool = True,
) -> list[dict]:
    """
    Query clips from the database based on query parameters.
    Returns list of clip dicts with: id, filepath, duration, source, year, etc.
    """
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        # Start with base query
        base_query = select(Clip)
        
        # Apply filters
        if query.source:
            base_query = base_query.where(Clip.source == query.source)
        
        if query.year_min is not None:
            base_query = base_query.where(Clip.year >= query.year_min)
        
        if query.year_max is not None:
            base_query = base_query.where(Clip.year <= query.year_max)
        
        if query.exclude_clip_ids:
            import uuid
            exclude_uuids = [uuid.UUID(id) for id in query.exclude_clip_ids if id]
            if exclude_uuids:
                base_query = base_query.where(~Clip.id.in_(exclude_uuids))
        
        # Join with signals if needed
        needs_signals = any([
            query.min_motion is not None,
            query.max_motion is not None,
            query.max_silence is not None,
            query.min_brightness is not None,
        ])
        
        if needs_signals:
            base_query = base_query.join(ClipSignals, Clip.id == ClipSignals.clip_id)
            if query.min_motion is not None:
                base_query = base_query.where(ClipSignals.motion_score >= query.min_motion)
            if query.max_motion is not None:
                base_query = base_query.where(ClipSignals.motion_score <= query.max_motion)
            if query.max_silence is not None:
                base_query = base_query.where(ClipSignals.silence_ratio <= query.max_silence)
            if query.min_brightness is not None:
                base_query = base_query.where(ClipSignals.brightness_entropy >= query.min_brightness)
        
        # Handle tag filtering
        if query.tags:
            base_query = base_query.join(ClipTag, Clip.id == ClipTag.clip_id)
            base_query = base_query.where(ClipTag.tag.in_(query.tags))
            base_query = base_query.where(ClipTag.similarity_score >= query.min_tag_score)
        
        # Handle entity filtering
        if query.entities:
            base_query = base_query.join(ClipEntity, Clip.id == ClipEntity.clip_id)
            base_query = base_query.where(ClipEntity.entity.in_(query.entities))
            base_query = base_query.where(ClipEntity.confidence >= query.min_entity_confidence)
        
        # Handle semantic search
        if query.semantic_query:
            # This would require CLIP model - for now, we'll use tag-based fallback
            # In production, you'd encode the query and use pgvector
            pass
        
        # Get results
        if randomize:
            base_query = base_query.order_by(func.random())
        else:
            base_query = base_query.order_by(Clip.created_at.desc())
        
        base_query = base_query.limit(limit)
        clips = session.scalars(base_query).all()
        
        # Load related data
        clip_ids = [c.id for c in clips]
        
        # Load tags
        tags_map = {}
        if clip_ids:
            tags_query = select(ClipTag).where(ClipTag.clip_id.in_(clip_ids))
            for tag in session.scalars(tags_query):
                if str(tag.clip_id) not in tags_map:
                    tags_map[str(tag.clip_id)] = []
                tags_map[str(tag.clip_id)].append({tag.tag: tag.similarity_score})
        
        # Load entities
        entities_map = {}
        if clip_ids:
            entities_query = select(ClipEntity).where(ClipEntity.clip_id.in_(clip_ids))
            for ent in session.scalars(entities_query):
                if str(ent.clip_id) not in entities_map:
                    entities_map[str(ent.clip_id)] = []
                entities_map[str(ent.clip_id)].append({ent.entity: ent.confidence})
        
        # Load signals
        signals_map = {}
        if clip_ids and needs_signals:
            signals_query = select(ClipSignals).where(ClipSignals.clip_id.in_(clip_ids))
            for s in session.scalars(signals_query):
                signals_map[str(s.clip_id)] = s
        
        # Build result dicts
        data_dir = get_data_dir()
        results = []
        for clip in clips:
            clip_id_str = str(clip.id)
            
            # Resolve filepath
            filepath = Path(clip.filepath)
            if not filepath.is_absolute():
                filepath = data_dir / "clips" / filepath
            
            results.append({
                "clip_id": clip_id_str,
                "filepath": str(filepath),
                "duration": clip.duration,
                "source": clip.source,
                "video_id": clip.video_id,
                "year": clip.year,
                "start_time": clip.start_time,
                "end_time": clip.end_time,
                "tags": tags_map.get(clip_id_str, []),
                "entities": entities_map.get(clip_id_str, []),
                "signals": {
                    "motion_score": signals_map[clip_id_str].motion_score if clip_id_str in signals_map else None,
                    "silence_ratio": signals_map[clip_id_str].silence_ratio if clip_id_str in signals_map else None,
                    "brightness_entropy": signals_map[clip_id_str].brightness_entropy if clip_id_str in signals_map else None,
                } if clip_id_str in signals_map else None,
            })
        
        return results

