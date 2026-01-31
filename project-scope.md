# Project: Beat-Synced Montage Generator

## Goal

Given:

* an **MP3 audio file**
* access to the **Aesthetic Indexer database**

Produce:

* a **beat-synchronised video montage**
* clips selected by **aesthetic similarity**
* cuts aligned to musical structure (beats / bars / sections)

This outputs a **final rendered video file** (e.g. MP4).

---

## Non-Goals (important)

* No AI “creative direction”
* No lyrics interpretation
* No UI in v1
* No copyright logic

This system **executes structure**, not taste.

---

## High-Level Architecture

```
[ MP3 Input ]
     ↓
[ Beat & Structure Analysis ]
     ↓
[ Montage Plan (Timeline) ]
     ↓
[ Clip Retrieval (DB) ]
     ↓
[ Clip-to-Beat Assignment ]
     ↓
[ FFmpeg Assembly ]
     ↓
[ Final Video ]
```

---

## Tech Stack

### Core

* **Python 3.11**
* **FFmpeg**
* **PostgreSQL + pgvector** (shared DB)

### Audio Analysis

* `librosa`
* `numpy`
* `scipy`

### Video Assembly

* FFmpeg (concat, trim, crossfade)
* Optional later: `moviepy` (FFmpeg-first preferred)

---

## Repo Structure

```
beat-montage-engine/
├── README.md
├── pyproject.toml
├── .env.example
├── inputs/
│   └── audio/
├── outputs/
│   └── renders/
├── src/
│   ├── audio/
│   │   ├── beat_detector.py
│   │   └── structure_analyzer.py
│   ├── planning/
│   │   ├── timeline.py
│   │   └── montage_plan.py
│   ├── retrieval/
│   │   └── clip_selector.py
│   ├── assembly/
│   │   └── ffmpeg_renderer.py
│   ├── db/
│   │   └── query.py
│   └── pipeline/
│       └── run.py
```

---

## Stage 1: Audio Analysis

### `beat_detector.py`

Extract:

* BPM
* Beat timestamps
* Downbeats (if detectable)

Using:

```python
librosa.beat.beat_track
```

Output:

```json
{
  "bpm": 132,
  "beats": [0.47, 0.94, 1.41, ...]
}
```

---

### `structure_analyzer.py`

Detect:

* Intro / drop / breakdown / outro (heuristic-based)
* Energy curve (RMS over time)

Output:

```json
{
  "sections": [
    {"type": "intro", "start": 0.0, "end": 18.2},
    {"type": "drop", "start": 18.2, "end": 48.7}
  ],
  "energy": [ ... ]
}
```

---

## Stage 2: Montage Planning

### `timeline.py`

Convert beats → **cut slots**

Rules:

* 1 clip per beat (or every 2 beats)
* Clip duration = beat interval
* Allow micro-variation (±5–10%)

Output:

```json
[
  {"start": 0.47, "duration": 0.47},
  {"start": 0.94, "duration": 0.47}
]
```

---

### `montage_plan.py`

Augment timeline with **aesthetic intent**:

Example mapping:

* Low energy → low motion, silence-heavy clips
* High energy → high motion, military / surveillance
* Drop → night vision / thermal / authority

This produces **queries**, not clips.

---

## Stage 3: Clip Retrieval

### `clip_selector.py`

For each timeline slot:

* Query aesthetic DB using:

  * tags
  * motion score
  * silence ratio
  * embedding similarity
* Randomised within constraints (avoid repetition)

Example query intent:

```
night vision
motion > 0.6
year > 1980
```

Output:

```json
{
  "clip_id": "...",
  "filepath": "...",
  "duration": 1.9
}
```

---

## Stage 4: Clip-to-Beat Alignment

Rules:

* Trim or loop clip to fit beat duration
* No stretching audio (audio is master)
* Hard cuts on beat by default
* Optional crossfades only on section boundaries

This is **mechanical**, not artistic.

---

## Stage 5: Video Assembly

### `ffmpeg_renderer.py`

* Trim clips
* Concatenate in order
* Mux with original MP3
* Export final MP4

FFmpeg primitives only:

* `-ss`, `-t`
* `concat` demuxer
* `-map 0:v -map 1:a`

---

## Configuration (v1)

YAML or JSON:

```yaml
beats_per_clip: 1
style:
  intro: ["religious", "low motion"]
  drop: ["night vision", "authority"]
  breakdown: ["surveillance", "silence"]
```

---

## Deliverables

* CLI:

```
python -m src.pipeline.run \
  --audio inputs/audio/track.mp3 \
  --output outputs/renders/video.mp4
```

* Deterministic runs with optional randomness seed
* Logs showing which clips were selected and why

---

## Milestones

1. Beat detection validated
2. Timeline generation stable
3. DB retrieval integrated
4. FFmpeg render produces synced output
5. End-to-end run on a 3–4 minute track

---

## Hard Truth (important)

This system will produce:

* **Striking, mechanical, cold montages**
* Not “human taste”

That’s exactly why this aesthetic works.