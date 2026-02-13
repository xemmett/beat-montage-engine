from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from typing import Optional

from src.audio.structure_analyzer import StructureAnalysis
from src.db.query import ClipQuery
from src.planning.timeline import TimelineSlot


@dataclass
class MontageSlot:
    timeline_slot: TimelineSlot
    query: ClipQuery  # Query parameters for clip selection
    section_type: Optional[str] = None  # 'intro', 'drop', etc.


def create_montage_plan(
    timeline_slots: list[TimelineSlot],
    structure: StructureAnalysis,
    *,
    config: Optional[dict] = None,
) -> list[MontageSlot]:
    """
    Augment timeline with aesthetic intent based on musical structure.
    
    Args:
        timeline_slots: Timeline slots from beat analysis
        structure: Musical structure analysis
        config: Optional full config dict (style, min_tag_score, min_entity_confidence)
    
    Returns:
        List of montage slots with query parameters
    """
    style_config = config.get("style") if config else None
    if style_config is None:
        style_config = {
            "intro": {"tags": ["religious", "low motion"], "max_motion": 0.3, "max_silence": 0.8},
            "drop": {"tags": ["night vision", "authority"], "min_motion": 0.6},
            "breakdown": {"tags": ["surveillance"], "max_silence": 0.5},
            "outro": {"tags": ["low motion"], "max_motion": 0.4},
        }
    
    min_tag_score = 0.3 if config is None else config.get("min_tag_score", 0.3)
    min_entity_confidence = 0.3 if config is None else config.get("min_entity_confidence", 0.3)
    
    # Map timeline slots to sections
    section_map = {}
    for section in structure.sections:
        for slot in timeline_slots:
            slot_mid = slot.start + (slot.duration / 2)
            if section.start <= slot_mid <= section.end:
                section_map[slot.beat_index] = section.type
    
    # Create montage plan
    montage_slots: list[MontageSlot] = []
    for slot in timeline_slots:
        section_type = section_map.get(slot.beat_index)
        
        # Get style config for this section
        if section_type and section_type in style_config:
            style = style_config[section_type]
        else:
            # Default style
            style = {"tags": [], "entities": [], "min_motion": None, "max_motion": None, "max_silence": None}

        # Only include fields that are defined in style. Omit = no filter for that dimension.
        # This lets users define just description, just tags, or any combination.
        tags = style.get("tags") or []
        entities = style.get("entities") or []
        description = (style.get("description") or "").strip() or None
        min_motion = style.get("min_motion") if "min_motion" in style else None
        max_motion = style.get("max_motion") if "max_motion" in style else None
        max_silence = style.get("max_silence") if "max_silence" in style else None

        query = ClipQuery(
            tags=tags,
            entities=entities,
            semantic_query=description,
            min_tag_score=style.get("min_tag_score", min_tag_score),
            min_entity_confidence=style.get("min_entity_confidence", min_entity_confidence),
            min_motion=min_motion,
            max_motion=max_motion,
            max_silence=max_silence,
        )
        
        montage_slots.append(
            MontageSlot(
                timeline_slot=slot,
                query=query,
                section_type=section_type,
            )
        )
    
    return montage_slots

