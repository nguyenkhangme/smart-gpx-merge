# smart-gpx-merge

Merges multiple GPX files into a single continuous route. Deduplicates overlapping segments, removes straight-line GPS artifacts, and bridges gaps by retracing existing trail.

## Installation

```bash
uv tool install smart-gpx-merge    # from PyPI (recommended)
pip install smart-gpx-merge        # or using pip
```

## CLI usage

```bash
smart-gpx-merge <inputs> [options]
```

### Common patterns

```bash
# Merge all GPX files in a directory
smart-gpx-merge ./tracks/ -o merged.gpx

# Merge specific files
smart-gpx-merge a.gpx b.gpx c.gpx

# Custom output and track name
smart-gpx-merge *.gpx -o merged.gpx --name "My Trail Map"

# Crop to bounding box and drop unreachable segments
smart-gpx-merge *.gpx --bbox south,west,north,east --drop-isolated

# Tune thresholds
smart-gpx-merge *.gpx --dup-radius 20 --gap-threshold 150 --junction-radius 30
```

## Key flags

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | `merged_all_routes.gpx` | Output file path |
| `--name` | `Merged Mountain Routes` | Track name in output GPX |
| `--dup-radius` | `15` | Meters to consider points as duplicates |
| `--gap-threshold` | `100` | Max gap (m) before splitting a segment |
| `--junction-radius` | `25` | Meters to connect junctions across segments |
| `--min-points` | `5` | Min points for a segment to be kept |
| `--downsample` | `8` | Min spacing (m) between points |
| `--bbox` | none | Crop to `south,west,north,east` |
| `--drop-isolated` | off | Drop segments that can't be bridged |

## Programmatic usage

```python
from smart_gpx_merge import parse_trackpoints, build_gpx_single, SpatialGrid, TrailGraph
```

## Architecture

Single module (`smart_gpx_merge.py`). Zero dependencies (stdlib only).

Key classes:
- `SpatialGrid` — spatial indexing for deduplication
- `TrailGraph` — Dijkstra-based gap bridging through existing trail points

Pipeline: parse → crop bbox → split artifacts → downsample → deduplicate → build graph → stitch → output
