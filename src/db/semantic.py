"""Semantic search via CLIP embeddings + pgvector."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db.query import ClipQuery

_model_cache: Optional[tuple] = None


def _encode_text_query(query: str):
    """Encode text to CLIP embedding."""
    import open_clip
    import torch

    global _model_cache
    if _model_cache is None:
        dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        model = model.to(dev)
        model.eval()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        _model_cache = (model, tokenizer, dev)
    model, tokenizer, dev = _model_cache
    with torch.no_grad():
        tokens = tokenizer([query]).to(dev)
        features = model.encode_text(tokens)
        features = features / features.norm(dim=-1, keepdim=True)
        return features[0].detach().cpu().numpy().astype("float32")


def run_semantic_search(
    session: Session,
    query: ClipQuery,
    limit: int,
) -> list[tuple]:
    """
    Run pgvector semantic search with optional filters.
    Returns list of (clip_id, source, video_id, filepath, start_time, end_time,
                     duration, year, created_at, similarity_score).
    """
    embedding = _encode_text_query(query.semantic_query.strip())
    emb_str = "[" + ",".join(str(x) for x in embedding.tolist()) + "]"
    params: dict = {"limit": limit}

    where_parts: list[str] = []
    if query.source:
        where_parts.append("c.source = :source")
        params["source"] = query.source
    if query.year_min is not None:
        where_parts.append("c.year >= :year_min")
        params["year_min"] = query.year_min
    if query.year_max is not None:
        where_parts.append("c.year <= :year_max")
        params["year_max"] = query.year_max
    if query.exclude_clip_ids:
        from uuid import UUID
        uuids = [str(UUID(id)) for id in query.exclude_clip_ids if id]
        if uuids:
            where_parts.append("c.id != ALL(ARRAY[" + ",".join(f"'{u}'::uuid" for u in uuids) + "])")

    if query.tags:
        where_parts.append(
            "EXISTS (SELECT 1 FROM clip_tags ct WHERE ct.clip_id = c.id "
            "AND ct.tag = ANY(:tags) AND ct.similarity_score >= :min_tag_score)"
        )
        params["tags"] = query.tags
        params["min_tag_score"] = query.min_tag_score
    if query.entities:
        where_parts.append(
            "EXISTS (SELECT 1 FROM clip_entities ce WHERE ce.clip_id = c.id "
            "AND ce.entity = ANY(:entities) AND ce.confidence >= :min_entity_conf)"
        )
        params["entities"] = query.entities
        params["min_entity_conf"] = query.min_entity_confidence

    needs_signals = any([
        query.min_motion is not None,
        query.max_motion is not None,
        query.max_silence is not None,
        query.min_brightness is not None,
    ])
    if needs_signals:
        sig_parts = ["ss.clip_id = c.id"]
        if query.min_motion is not None:
            sig_parts.append("ss.motion_score >= :min_motion")
            params["min_motion"] = query.min_motion
        if query.max_motion is not None:
            sig_parts.append("ss.motion_score <= :max_motion")
            params["max_motion"] = query.max_motion
        if query.max_silence is not None:
            sig_parts.append("ss.silence_ratio <= :max_silence")
            params["max_silence"] = query.max_silence
        if query.min_brightness is not None:
            sig_parts.append("ss.brightness_entropy >= :min_brightness")
            params["min_brightness"] = query.min_brightness
        where_parts.append(
            f"EXISTS (SELECT 1 FROM clip_signals ss WHERE {' AND '.join(sig_parts)})"
        )

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    sql = text(
        f"""
        SELECT c.id, c.source, c.video_id, c.filepath, c.start_time, c.end_time,
               c.duration, c.year, c.created_at,
               (1 - (e.embedding <=> '{emb_str}'::vector)) AS similarity_score
        FROM clip_embeddings e
        JOIN clips c ON c.id = e.clip_id
        {where_sql}
        ORDER BY e.embedding <=> '{emb_str}'::vector
        LIMIT :limit
        """
    )

    return list(session.execute(sql, params).all())
