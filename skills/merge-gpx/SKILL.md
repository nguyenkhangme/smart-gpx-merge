---
name: merge-gpx
description: Merge multiple GPX files into one continuous route, removing duplicates and bridging gaps
allowed-tools: Bash(python3 *)
---

Merge GPX files using the bundled smart_gpx_merge.py script.

Run the script from the skill directory:

```bash
python3 ${CLAUDE_SKILL_DIR}/smart_gpx_merge.py <inputs> [options]
```

Key flags:
- `-o, --output` — output file (default: merged_all_routes.gpx)
- `--dup-radius` — dedup radius in meters (default: 15)
- `--gap-threshold` — max gap before splitting (default: 100)
- `--bbox south,west,north,east` — crop to area
- `--drop-isolated` — remove unbridgeable segments
- `--name` — track name in output

Available GPX files in current directory: !`find . -name "*.gpx" -type f 2>/dev/null`

Merge instructions: $ARGUMENTS
