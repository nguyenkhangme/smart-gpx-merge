# smart-gpx-merge

Merge multiple overlapping GPX files into a single continuous route. Built for combining trail running / hiking GPS tracks from the same area (e.g., a mountain with many trails) into one unified map.

## Features

- **Duplicate removal** — detects overlapping trail segments using spatial proximity and keeps only unique coverage
- **Straight-line artifact removal** — splits segments where GPS jumped (large gaps between consecutive points)
- **Gap bridging** — connects disjoint segments by retracing existing trail instead of drawing straight lines
- **Downsampling** — reduces point density from high-frequency GPS recordings while preserving trail shape
- **Zero dependencies** — pure Python 3, uses only the standard library

## How It Works

```
Input: Multiple GPX files with overlapping routes
                    │
     1. Parse all track segments from all files
     2. Split segments at GPS jumps (straight-line artifacts)
     3. Downsample dense GPS recordings
     4. Deduplicate — keep segments that add new trail coverage
     5. Build a trail graph with junction connections
     6. Order segments to minimize gaps
     7. Bridge gaps via shortest path through existing trail
                    │
Output: One continuous GPX track covering all unique routes
```

## Usage

```bash
# Merge all .gpx files in a directory
python3 smart_gpx_merge.py ./my_tracks/

# Merge specific files
python3 smart_gpx_merge.py track1.gpx track2.gpx track3.gpx

# Custom output file and track name
python3 smart_gpx_merge.py *.gpx -o merged.gpx --name "My Trail Map"

# Tune thresholds
python3 smart_gpx_merge.py *.gpx --dup-radius 20 --gap-threshold 150

# Crop to a specific area and drop isolated segments
python3 smart_gpx_merge.py *.gpx --bbox 10.505,107.10,10.56,107.155 --drop-isolated
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | `merged_all_routes.gpx` | Output file path |
| `--name` | `Merged Mountain Routes` | Track name in the output GPX |
| `--dup-radius` | `15` | Radius (m) to consider two points as the same location |
| `--gap-threshold` | `100` | Max gap (m) between consecutive points before splitting a segment |
| `--junction-radius` | `25` | Radius (m) to connect trail junctions across different segments |
| `--min-points` | `5` | Minimum points for a segment to be kept |
| `--downsample` | `8` | Minimum spacing (m) between points after downsampling |
| `--bbox` | none | Crop to bounding box: `south,west,north,east` |
| `--drop-isolated` | off | Drop segments that can't be bridged through existing trail |

## Example

Merging 4 GPX files with overlapping trail runs on the same mountain:

```bash
python3 smart_gpx_merge.py ./tracks/ -o merged.gpx --name "Mountain Trails"
```

```
📂 route_a.gpx:          1 segment, 58,000 points
📂 route_b.gpx:          1 segment, 10,000 points
📂 route_c.gpx:          1 segment, 16,000 points
📂 previous_merged.gpx:  7 segments,  3,800 points

→ Deduplicated to 4 unique segments (6 discarded)
→ Bridged 2 gaps via existing trail
→ Output: 1 continuous track, ~7,200 points
```

## Tips

- **Duplicate radius** (`--dup-radius`): Increase if parallel trails are being kept as separate segments. Decrease if distinct nearby trails are being merged incorrectly.
- **Gap threshold** (`--gap-threshold`): Lower this if you see GPS jumps that aren't being caught. Raise if legitimate trail sections are being split.
- **Junction radius** (`--junction-radius`): Controls how far apart two points from different segments can be and still be considered the same trail junction. Affects gap bridging quality.

## Requirements

- Python 3.8+
- No external dependencies

## Acknowledgements

Built with [Claude Code](https://claude.ai/claude-code) by Anthropic.

## License

MIT
