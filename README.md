# Beat Montage Engine

Generate beat-synchronized video montages from audio files using clips from the aesthetic-indexer database.

## Overview

This system takes an MP3 audio file and creates a video montage where:
- Clips are cut on musical beats
- Clip selection is based on aesthetic similarity and musical structure
- The final video is synchronized with the original audio

## Requirements

- Python **3.11+**
- **FFmpeg** available on PATH
- **PostgreSQL 15** with `pgvector` extension
- Access to a database with the clip schema (compatible with aesthetic-indexer schema)

## Setup

1. Install the package:

```bash
cd beat-montage-engine
python -m venv .venv
. .venv/bin/activate  # Windows: .\\.venv\\Scripts\\activate
pip install -U pip
pip install -e .
```

2. Configure environment:

```bash
cp .env.example .env
```

Edit `.env` and set:
- `DATABASE_URL` - PostgreSQL connection string (same as aesthetic-indexer)

## Usage

### Basic Usage

```bash
python -m src.pipeline.run \
  --audio inputs/audio/track.mp3 \
  --output outputs/renders/montage.mp4
```

### With Configuration

Create a `config.yaml`:

```yaml
beats_per_clip: 1
style:
  intro:
    tags: ["religious", "low motion"]
    max_motion: 0.3
    max_silence: 0.8
  drop:
    tags: ["night vision", "authority"]
    min_motion: 0.6
  breakdown:
    tags: ["surveillance"]
    max_silence: 0.5
  outro:
    tags: ["low motion"]
    max_motion: 0.4
```

Then run:

```bash
python -m src.pipeline.run \
  --audio "C:\Users\mmttl\Music\ItsNotMeAnymore\mp3\Under Surveillance.mp3" \
  --output montage.mp4 \
  --config config.yaml \
  --beats-per-clip 1 \
  --seed 42
```

## Options

- `--audio` / `-a`: Input audio file (required)
- `--output` / `-o`: Output video file (required)
- `--config` / `-c`: Optional YAML configuration file
- `--beats-per-clip`: Number of beats per clip (default: 1)
- `--seed`: Random seed for deterministic output
- `--avoid-repetition` / `--allow-repetition`: Control clip repetition (default: avoid)

## How It Works

1. **Beat Detection**: Analyzes audio to find BPM and beat timestamps
2. **Structure Analysis**: Detects musical sections (intro, drop, breakdown, outro)
3. **Timeline Creation**: Converts beats into clip slots
4. **Montage Planning**: Maps sections to aesthetic queries (tags, motion, silence)
5. **Clip Retrieval**: Queries database for matching clips
6. **Video Assembly**: Trims and concatenates clips, muxes with audio

## Output

- **Video file**: Final montage MP4
- **JSON log**: Details about selected clips and structure analysis

## Notes

- This is a standalone project with no dependencies on aesthetic-indexer
- The database schema is compatible with aesthetic-indexer (same table structure)
- Clips are selected based on tags, motion scores, and silence ratios
- The montage is deterministic if you provide a `--seed`
- Clips are automatically trimmed to fit beat durations
- Set `DATA_DIR` environment variable to point to your clips directory, or it will look for clips in a sibling `aesthetic-indexer/data` directory

