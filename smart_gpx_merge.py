#!/usr/bin/env python3
"""
Merge multiple GPX files into one continuous route:
1. Deduplicate overlapping segments
2. Bridge gaps by retracing existing trail (no straight lines)
3. Output a single continuous trkseg

Usage:
  python3 merge_gpx.py input1.gpx input2.gpx ...          # specific files
  python3 merge_gpx.py ./my_tracks/                        # all .gpx in a directory
  python3 merge_gpx.py *.gpx -o merged.gpx                # custom output name
  python3 merge_gpx.py *.gpx --dup-radius 20 --gap 150    # custom thresholds
"""

import argparse
import glob
import xml.etree.ElementTree as ET
import math
import os
import sys
import heapq
from collections import defaultdict

# ── Defaults ───────────────────────────────────────────────────
DEFAULT_OUTPUT = "merged_all_routes.gpx"
DEFAULT_DUP_RADIUS = 15
DEFAULT_STRAIGHT_LINE = 100
DEFAULT_JUNCTION_RADIUS = 25
DEFAULT_MIN_SEGMENT_PTS = 5
DEFAULT_DOWNSAMPLE_SPACING = 8

GPX_NS = "http://www.topografix.com/GPX/1/1"
ET.register_namespace("", GPX_NS)
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge multiple GPX files into one continuous route, "
                    "removing duplicates and straight-line artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s track1.gpx track2.gpx track3.gpx
  %(prog)s ./gpx_folder/
  %(prog)s *.gpx -o my_merged_route.gpx
  %(prog)s *.gpx --dup-radius 20 --gap-threshold 150
""",
    )
    parser.add_argument(
        "inputs", nargs="+",
        help="GPX files or a directory containing GPX files",
    )
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT,
        help=f"Output GPX file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dup-radius", type=float, default=DEFAULT_DUP_RADIUS,
        help=f"Radius (m) to consider two points as the same location (default: {DEFAULT_DUP_RADIUS})",
    )
    parser.add_argument(
        "--gap-threshold", type=float, default=DEFAULT_STRAIGHT_LINE,
        help=f"Max gap (m) between consecutive points before splitting (default: {DEFAULT_STRAIGHT_LINE})",
    )
    parser.add_argument(
        "--junction-radius", type=float, default=DEFAULT_JUNCTION_RADIUS,
        help=f"Radius (m) to connect trail junctions across segments (default: {DEFAULT_JUNCTION_RADIUS})",
    )
    parser.add_argument(
        "--min-points", type=int, default=DEFAULT_MIN_SEGMENT_PTS,
        help=f"Minimum points for a segment to be kept (default: {DEFAULT_MIN_SEGMENT_PTS})",
    )
    parser.add_argument(
        "--downsample", type=float, default=DEFAULT_DOWNSAMPLE_SPACING,
        help=f"Min spacing (m) between points after downsampling (default: {DEFAULT_DOWNSAMPLE_SPACING})",
    )
    parser.add_argument(
        "--name", default="Merged Mountain Routes",
        help="Track name in the output GPX (default: 'Merged Mountain Routes')",
    )
    return parser.parse_args()


def resolve_input_files(inputs, output_path):
    """Resolve input args to a list of .gpx file paths."""
    files = []
    output_basename = os.path.basename(os.path.abspath(output_path))
    for inp in inputs:
        if os.path.isdir(inp):
            files.extend(sorted(glob.glob(os.path.join(inp, "*.gpx"))))
        elif os.path.isfile(inp) and inp.endswith(".gpx"):
            files.append(inp)
        elif "*" in inp or "?" in inp:
            files.extend(sorted(glob.glob(inp)))
        else:
            print(f"  ⚠ Skipping {inp} (not a .gpx file or directory)")
    # Exclude the output file from inputs
    files = [f for f in files if os.path.basename(os.path.abspath(f)) != output_basename]
    return files


# ── Helpers ────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def grid_key(lat, lon, cell_size):
    return (round(lat / cell_size), round(lon / cell_size))


def parse_trackpoints(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    segments = []
    for trkseg in root.iter(f"{{{GPX_NS}}}trkseg"):
        pts = []
        for trkpt in trkseg.findall(f"{{{GPX_NS}}}trkpt"):
            lat = float(trkpt.get("lat"))
            lon = float(trkpt.get("lon"))
            ele_el = trkpt.find(f"{{{GPX_NS}}}ele")
            ele = float(ele_el.text) if ele_el is not None else 0.0
            pts.append((lat, lon, ele))
        if pts:
            segments.append(pts)
    return segments


def split_on_straight_lines(segment, threshold_m, min_points):
    if len(segment) < 2:
        return [segment]
    sub_segments = []
    current = [segment[0]]
    for i in range(1, len(segment)):
        dist = haversine(segment[i-1][0], segment[i-1][1], segment[i][0], segment[i][1])
        if dist > threshold_m:
            if len(current) >= min_points:
                sub_segments.append(current)
            current = [segment[i]]
        else:
            current.append(segment[i])
    if len(current) >= min_points:
        sub_segments.append(current)
    return sub_segments


def downsample_segment(segment, min_spacing_m):
    if len(segment) <= 2:
        return segment
    result = [segment[0]]
    for pt in segment[1:-1]:
        if haversine(result[-1][0], result[-1][1], pt[0], pt[1]) >= min_spacing_m:
            result.append(pt)
    result.append(segment[-1])
    return result


class SpatialGrid:
    def __init__(self, cell_size):
        self.grid = defaultdict(list)
        self.cell_size = cell_size

    def add_point(self, lat, lon):
        self.grid[grid_key(lat, lon, self.cell_size)].append((lat, lon))

    def has_nearby(self, lat, lon, radius_m):
        ci, cj = grid_key(lat, lon, self.cell_size)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for plat, plon in self.grid.get((ci + di, cj + dj), []):
                    if haversine(lat, lon, plat, plon) <= radius_m:
                        return True
        return False

    def coverage_ratio(self, segment, radius_m):
        if not segment:
            return 1.0
        step = max(1, len(segment) // 200)
        sampled = segment[::step]
        covered = sum(1 for lat, lon, _ in sampled if self.has_nearby(lat, lon, radius_m))
        return covered / len(sampled)

    def add_segment(self, segment):
        for lat, lon, _ in segment:
            self.add_point(lat, lon)


class TrailGraph:
    def __init__(self, cell_size):
        self.points = []
        self.adj = defaultdict(list)
        self.spatial = defaultdict(list)
        self.cell_size = cell_size

    def add_segment(self, segment):
        start_id = len(self.points)
        for pt in segment:
            node_id = len(self.points)
            self.points.append(pt)
            key = grid_key(pt[0], pt[1], self.cell_size)
            self.spatial[key].append(node_id)
        for i in range(len(segment) - 1):
            a, b = start_id + i, start_id + i + 1
            d = haversine(segment[i][0], segment[i][1], segment[i+1][0], segment[i+1][1])
            self.adj[a].append((b, d))
            self.adj[b].append((a, d))

    def connect_junctions(self, radius_m):
        print(f"  Building junction connections (radius={radius_m}m)...")
        connections = 0
        for key, nodes in self.spatial.items():
            ci, cj = key
            for node_a in nodes:
                pa = self.points[node_a]
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        for node_b in self.spatial.get((ci+di, cj+dj), []):
                            if node_b <= node_a:
                                continue
                            pb = self.points[node_b]
                            d = haversine(pa[0], pa[1], pb[0], pb[1])
                            if d <= radius_m:
                                existing = {n for n, _ in self.adj[node_a]}
                                if node_b not in existing:
                                    self.adj[node_a].append((node_b, d))
                                    self.adj[node_b].append((node_a, d))
                                    connections += 1
        print(f"  Junction connections added: {connections}")

    def find_nearest_node(self, lat, lon):
        best_id, best_dist = -1, float('inf')
        ci, cj = grid_key(lat, lon, self.cell_size)
        for r in range(0, 50):
            for di in range(-r, r+1):
                for dj in range(-r, r+1):
                    if abs(di) != r and abs(dj) != r:
                        continue
                    for nid in self.spatial.get((ci+di, cj+dj), []):
                        p = self.points[nid]
                        d = haversine(lat, lon, p[0], p[1])
                        if d < best_dist:
                            best_dist = d
                            best_id = nid
            if best_id >= 0 and r > 1:
                break
        return best_id, best_dist

    def shortest_path(self, start_id, end_id):
        if start_id == end_id:
            return [self.points[start_id]]
        dist = {start_id: 0}
        prev = {}
        pq = [(0, start_id)]
        max_iterations = len(self.points) * 2
        iterations = 0
        while pq and iterations < max_iterations:
            iterations += 1
            d, u = heapq.heappop(pq)
            if u == end_id:
                break
            if d > dist.get(u, float('inf')):
                continue
            for v, w in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, float('inf')):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        if end_id not in prev:
            return None
        path = []
        node = end_id
        while node != start_id:
            path.append(self.points[node])
            node = prev[node]
        path.append(self.points[start_id])
        path.reverse()
        return path


def order_segments_greedy(segments):
    if len(segments) <= 1:
        return segments
    remaining = list(range(len(segments)))
    ordered = [remaining.pop(0)]
    while remaining:
        last_seg = segments[ordered[-1]]
        end_pt = last_seg[-1]
        best_idx = None
        best_dist = float('inf')
        best_reverse = False
        for idx in remaining:
            seg = segments[idx]
            d_start = haversine(end_pt[0], end_pt[1], seg[0][0], seg[0][1])
            d_end = haversine(end_pt[0], end_pt[1], seg[-1][0], seg[-1][1])
            if d_start < best_dist:
                best_dist = d_start
                best_idx = idx
                best_reverse = False
            if d_end < best_dist:
                best_dist = d_end
                best_idx = idx
                best_reverse = True
        remaining.remove(best_idx)
        if best_reverse:
            segments[best_idx] = list(reversed(segments[best_idx]))
        ordered.append(best_idx)
    return [segments[i] for i in ordered]


def build_gpx_single(all_points, track_name):
    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "smart-gpx-merge",
        "xmlns": GPX_NS,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": (
            "http://www.topografix.com/GPX/1/1 "
            "http://www.topografix.com/GPX/1/1/gpx.xsd"
        ),
    })
    metadata = ET.SubElement(gpx, "metadata")
    name = ET.SubElement(metadata, "name")
    name.text = track_name
    trk = ET.SubElement(gpx, "trk")
    trk_name = ET.SubElement(trk, "name")
    trk_name.text = track_name
    trk_type = ET.SubElement(trk, "type")
    trk_type.text = "trail_running"
    trkseg = ET.SubElement(trk, "trkseg")
    for lat, lon, ele in all_points:
        trkpt = ET.SubElement(trkseg, "trkpt", {
            "lat": f"{lat:.7f}",
            "lon": f"{lon:.7f}",
        })
        ele_el = ET.SubElement(trkpt, "ele")
        ele_el.text = f"{ele:.1f}"
    return ET.ElementTree(gpx)


# ── Main ───────────────────────────────────────────────────────
def main():
    args = parse_args()
    cell_size = args.dup_radius / 111_000

    print("=" * 60)
    print("GPX Route Merger")
    print("=" * 60)

    # Resolve input files
    input_files = resolve_input_files(args.inputs, args.output)
    if not input_files:
        print("Error: No .gpx files found in the provided inputs.")
        sys.exit(1)

    # Step 1: Parse
    all_segments = []
    for fpath in input_files:
        segs = parse_trackpoints(fpath)
        total_pts = sum(len(s) for s in segs)
        print(f"  📂 {os.path.basename(fpath)}: {len(segs)} segment(s), {total_pts:,} points")
        all_segments.extend(segs)

    print(f"\nTotal raw segments: {len(all_segments)}")
    print(f"Total raw points: {sum(len(s) for s in all_segments):,}")

    # Step 2: Split on straight-line artifacts
    print(f"\n── Removing straight-line artifacts (>{args.gap_threshold}m gaps) ──")
    split_segments = []
    straight_lines_removed = 0
    for seg in all_segments:
        splits = split_on_straight_lines(seg, args.gap_threshold, args.min_points)
        if len(splits) > 1:
            straight_lines_removed += len(splits) - 1
        split_segments.extend(splits)
    print(f"  Breaks found: {straight_lines_removed}")
    print(f"  Segments after splitting: {len(split_segments)}")

    # Step 3: Downsample
    print("\n── Downsampling ──")
    downsampled = [downsample_segment(seg, args.downsample) for seg in split_segments]
    print(f"  Points after downsampling: {sum(len(s) for s in downsampled):,}")

    # Step 4: Sort by length, deduplicate
    downsampled.sort(key=len, reverse=True)
    print(f"\n── Deduplicating (radius={args.dup_radius}m) ──")
    grid = SpatialGrid(cell_size)
    kept_segments = []
    for i, seg in enumerate(downsampled):
        coverage = grid.coverage_ratio(seg, args.dup_radius)
        if coverage < 0.85:
            kept_segments.append(seg)
            grid.add_segment(seg)
            print(f"  ✅ Seg {i+1}: {len(seg)} pts, {(1-coverage)*100:.0f}% new → KEPT")

    print(f"  Kept: {len(kept_segments)}, Discarded: {len(downsampled) - len(kept_segments)}")

    if not kept_segments:
        print("Error: No segments remaining after deduplication.")
        sys.exit(1)

    # Step 5: Build trail graph
    print("\n── Building trail graph ──")
    graph = TrailGraph(cell_size)
    for seg in kept_segments:
        graph.add_segment(seg)
    print(f"  Total nodes: {len(graph.points)}")
    print(f"  Total edges: {sum(len(v) for v in graph.adj.values()) // 2}")
    graph.connect_junctions(args.junction_radius)

    # Step 6: Order segments
    print("\n── Ordering segments ──")
    kept_segments = order_segments_greedy(kept_segments)

    # Rebuild graph after reordering
    graph2 = TrailGraph(cell_size)
    for seg in kept_segments:
        graph2.add_segment(seg)
    graph2.connect_junctions(args.junction_radius)

    # Step 7: Stitch with trail bridges
    print("\n── Stitching segments with trail bridges ──")
    final_points = list(kept_segments[0])

    for i in range(1, len(kept_segments)):
        prev_end = kept_segments[i-1][-1]
        next_start = kept_segments[i][0]
        gap_dist = haversine(prev_end[0], prev_end[1], next_start[0], next_start[1])

        if gap_dist < args.junction_radius:
            print(f"  Gap {i}: {gap_dist:.0f}m — direct connection")
            final_points.extend(kept_segments[i])
        else:
            start_node, _ = graph2.find_nearest_node(prev_end[0], prev_end[1])
            end_node, _ = graph2.find_nearest_node(next_start[0], next_start[1])
            bridge = graph2.shortest_path(start_node, end_node)

            if bridge:
                print(f"  Gap {i}: {gap_dist:.0f}m — bridge via {len(bridge)} trail points")
                final_points.extend(bridge)
            else:
                print(f"  Gap {i}: {gap_dist:.0f}m — ⚠ no trail path found")

            final_points.extend(kept_segments[i])

    # Step 8: Write output
    print(f"\n── Writing output ──")
    print(f"  Total points: {len(final_points):,}")
    tree = build_gpx_single(final_points, args.name)
    ET.indent(tree, space="  ")
    tree.write(args.output, xml_declaration=True, encoding="UTF-8")
    print(f"  ✅ Saved to: {args.output}")
    print("\nDone!")


if __name__ == "__main__":
    main()
