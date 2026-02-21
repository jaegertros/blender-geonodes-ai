"""
Property Variation Scan Runner (standalone Python)
====================================================
Launches Blender subprocesses to scan property variations on key nodes.
Groups nodes into small batches to avoid crashes.

Usage:
    python explorer/run_property_scan.py [--batch-size 5]
"""

import subprocess
import sys
import os
import json
import argparse
from datetime import datetime


DEFAULT_BLENDER = r"C:\Tools\Blender\stable\blender-4.5.6-lts.a78963ed6435\blender.exe"

# Properties to skip
SKIP_PROPS = {"color_tag", "warning_propagation"}


def find_blender():
    if os.path.isfile(DEFAULT_BLENDER):
        return DEFAULT_BLENDER
    print("ERROR: Blender not found.")
    sys.exit(1)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_priority_nodes(catalog):
    """Identify nodes with meaningful enum properties, prioritized by impact."""
    priority_nodes = []

    for nid, entry in catalog["nodes"].items():
        inputs = entry.get("inputs", [])
        outputs = entry.get("outputs", [])
        has_geo_in = any(s["type"] == "GEOMETRY" for s in inputs)
        has_geo_out = any(s["type"] == "GEOMETRY" for s in outputs)

        props = entry.get("properties", {})
        enum_props = {}
        for pname, pinfo in props.items():
            if isinstance(pinfo, dict) and "enum_items" in pinfo:
                if pname not in SKIP_PROPS:
                    items = pinfo["enum_items"]
                    enum_props[pname] = len(items)

        if not enum_props:
            continue

        total_variations = sum(enum_props.values())

        # Classify priority
        if has_geo_in and has_geo_out:
            priority = 2  # Processor with modes
        elif has_geo_out and not has_geo_in:
            priority = 2  # Generator with options
        elif nid in ("ShaderNodeMath", "ShaderNodeVectorMath", "ShaderNodeMix",
                     "ShaderNodeMapRange", "ShaderNodeMixRGB"):
            priority = 1  # Key math/utility nodes
        else:
            priority = 0

        if priority >= 1:
            priority_nodes.append((priority, total_variations, nid))

    # Sort: highest priority first, then most variations
    priority_nodes.sort(key=lambda x: (-x[0], -x[1]))
    return [nid for _, _, nid in priority_nodes]


def run_batch(blender_path, project_dir, node_ids, mesh_type, output_path):
    """Run property variation scan on a batch of nodes."""
    script = os.path.join(project_dir, "explorer", "explore_properties.py")
    catalog = os.path.join(project_dir, "discovery", "node_catalog.json")

    cmd = [
        blender_path,
        "--background",
        "--factory-startup",
        "--python", script,
        "--",
        "--catalog", catalog,
        "--nodes", ",".join(node_ids),
        "--output", output_path,
        "--mesh-type", mesh_type,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min per batch (property scanning takes longer)
        )

        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Blender ") or line.startswith("Read ") or not line.strip():
                    continue
                print(f"    {line}")

        if result.returncode != 0:
            print(f"    WARNING: Blender exited with code {result.returncode}")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[:5]:
                    print(f"    STDERR: {line}")

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT: Batch timed out after 600s")
        return False
    except Exception as e:
        print(f"    ERROR: {e}")
        return False


def combine_results(result_dir):
    """Merge all property scan batch results."""
    combined = {
        "exploration_date": datetime.now().isoformat(),
        "type": "property_variations",
        "nodes": {},
    }

    batch_files = sorted([
        f for f in os.listdir(result_dir)
        if f.startswith("prop_batch_") and f.endswith(".json")
    ])

    for fname in batch_files:
        path = os.path.join(result_dir, fname)
        try:
            data = load_json(path)
            combined["blender_version"] = data.get("blender_version", "unknown")
            combined["nodes"].update(data.get("nodes", {}))
        except Exception as e:
            print(f"  Warning: Could not read {fname}: {e}")

    combined["total_nodes"] = len(combined["nodes"])
    combined["total_variations"] = sum(
        n["variations_tested"] for n in combined["nodes"].values()
    )

    output_path = os.path.join(result_dir, "property_variations_combined.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False, default=str)

    return output_path, combined


def main():
    parser = argparse.ArgumentParser(description="Run property variation scanning")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Nodes per Blender batch (keep small, property scanning is heavier)")
    parser.add_argument("--mesh-type", default="cube", help="Base mesh type")
    args = parser.parse_args()

    blender = find_blender()
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result_dir = os.path.join(project_dir, "explorer", "results")
    os.makedirs(result_dir, exist_ok=True)

    catalog = load_json(os.path.join(project_dir, "discovery", "node_catalog.json"))
    node_ids = get_priority_nodes(catalog)

    num_batches = (len(node_ids) + args.batch_size - 1) // args.batch_size

    print("=" * 60)
    print("Property Variation Scanner")
    print("=" * 60)
    print(f"Priority nodes: {len(node_ids)}")
    print(f"Batch size: {args.batch_size}")
    print(f"Batches: {num_batches}")
    print(f"Base mesh: {args.mesh_type}")
    print()

    for batch_idx in range(num_batches):
        start = batch_idx * args.batch_size
        batch = node_ids[start:start + args.batch_size]
        output_path = os.path.join(result_dir, f"prop_batch_{batch_idx:03d}.json")

        names = [catalog["nodes"][nid].get("name", nid) for nid in batch]
        print(f"Batch {batch_idx + 1}/{num_batches}: {', '.join(names)}")

        success = run_batch(blender, project_dir, batch, args.mesh_type, output_path)
        if not success:
            print(f"  Batch {batch_idx + 1} had issues, continuing...")
        print()

    # Combine results
    print("Combining results...")
    combined_path, combined = combine_results(result_dir)

    print()
    print("=" * 60)
    print("Property Variation Scan Complete")
    print(f"  Nodes scanned:     {combined.get('total_nodes', 0)}")
    print(f"  Total variations:  {combined.get('total_variations', 0)}")
    print(f"  Output: {combined_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
