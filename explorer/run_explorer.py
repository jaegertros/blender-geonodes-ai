"""
Explorer Runner (standalone Python, launches Blender subprocesses)
===================================================================
Orchestrates the exploration by launching batched Blender subprocesses.
Each batch gets its own fresh Blender instance to avoid crashes.

Usage:
    python explorer/run_explorer.py [--domain mesh] [--batch-size 30]

Output:
    explorer/results/<domain>_batch_<N>.json  (per batch)
    explorer/results/<domain>_combined.json   (merged)
"""

import subprocess
import sys
import os
import json
import argparse
from datetime import datetime


DEFAULT_BLENDER = r"C:\Tools\Blender\stable\blender-4.5.6-lts.a78963ed6435\blender.exe"


def find_blender():
    if os.path.isfile(DEFAULT_BLENDER):
        return DEFAULT_BLENDER
    print("ERROR: Blender not found at default path. Set DEFAULT_BLENDER.")
    sys.exit(1)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def count_nodes_for_domain(classification_path, domain):
    """Count how many nodes are in a domain."""
    classification = load_json(classification_path)
    if domain == "all":
        return len(classification.get("nodes", {}))
    return sum(
        1 for info in classification.get("nodes", {}).values()
        if info.get("domain") == domain
    )


def run_batch(blender_path, project_dir, domain, batch_start, batch_size, mesh_type, output_path):
    """Run one exploration batch in a Blender subprocess."""
    script = os.path.join(project_dir, "explorer", "explore_nodes.py")
    catalog = os.path.join(project_dir, "discovery", "node_catalog.json")
    classification = os.path.join(project_dir, "discovery", "node_classification.json")

    cmd = [
        blender_path,
        "--background",
        "--factory-startup",
        "--python", script,
        "--",
        "--catalog", catalog,
        "--classification", classification,
        "--domain", domain,
        "--output", output_path,
        "--batch-start", str(batch_start),
        "--batch-size", str(batch_size),
        "--mesh-type", mesh_type,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min per batch
        )

        # Print Blender's stdout (our progress output)
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                # Filter out Blender boilerplate
                if line.startswith("Blender ") or line.startswith("Read ") or not line.strip():
                    continue
                print(f"    {line}")

        if result.returncode != 0:
            print(f"    WARNING: Blender exited with code {result.returncode}")
            if result.stderr:
                stderr_lines = result.stderr.strip().split("\n")[:5]
                for line in stderr_lines:
                    print(f"    STDERR: {line}")

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT: Batch timed out after 300s")
        return False
    except Exception as e:
        print(f"    ERROR: {e}")
        return False


def combine_results(result_dir, domain):
    """Merge all batch result files into one combined file."""
    combined = {
        "exploration_date": datetime.now().isoformat(),
        "domain": domain,
        "summary": {},
        "nodes": [],
    }

    batch_files = sorted([
        f for f in os.listdir(result_dir)
        if f.startswith(f"{domain}_batch_") and f.endswith(".json")
    ])

    for fname in batch_files:
        path = os.path.join(result_dir, fname)
        try:
            data = load_json(path)
            combined["blender_version"] = data.get("blender_version", "unknown")
            combined["nodes"].extend(data.get("nodes", []))

            for cat, count in data.get("summary", {}).items():
                combined["summary"][cat] = combined["summary"].get(cat, 0) + count
        except Exception as e:
            print(f"  Warning: Could not read {fname}: {e}")

    combined["total_nodes"] = len(combined["nodes"])

    output_path = os.path.join(result_dir, f"{domain}_combined.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False, default=str)

    return output_path, combined


def main():
    parser = argparse.ArgumentParser(description="Run geometry node exploration")
    parser.add_argument("--domain", default="mesh", help="Domain to explore (mesh, curve, geometry, math, input, etc. or 'all')")
    parser.add_argument("--batch-size", type=int, default=30, help="Nodes per Blender batch")
    parser.add_argument("--mesh-type", default="cube", help="Base mesh type")
    args = parser.parse_args()

    blender = find_blender()
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result_dir = os.path.join(project_dir, "explorer", "results")
    os.makedirs(result_dir, exist_ok=True)

    classification_path = os.path.join(project_dir, "discovery", "node_classification.json")

    total_nodes = count_nodes_for_domain(classification_path, args.domain)
    num_batches = (total_nodes + args.batch_size - 1) // args.batch_size

    print("=" * 60)
    print(f"Geometry Node Explorer")
    print("=" * 60)
    print(f"Domain: {args.domain}")
    print(f"Total nodes: {total_nodes}")
    print(f"Batch size: {args.batch_size}")
    print(f"Batches: {num_batches}")
    print(f"Base mesh: {args.mesh_type}")
    print(f"Blender: {blender}")
    print()

    for batch_idx in range(num_batches):
        batch_start = batch_idx * args.batch_size
        output_path = os.path.join(result_dir, f"{args.domain}_batch_{batch_idx:03d}.json")

        print(f"Batch {batch_idx + 1}/{num_batches} (nodes {batch_start}-{batch_start + args.batch_size}):")
        success = run_batch(
            blender, project_dir, args.domain,
            batch_start, args.batch_size, args.mesh_type, output_path
        )
        if not success:
            print(f"  Batch {batch_idx + 1} had issues, continuing...")
        print()

    # Combine results
    print("Combining results...")
    combined_path, combined = combine_results(result_dir, args.domain)

    print()
    print("=" * 60)
    print("Final Summary:")
    for cat, count in sorted(combined.get("summary", {}).items()):
        if count > 0:
            print(f"  {cat:<20} {count}")
    print(f"Total explored: {combined.get('total_nodes', 0)}")
    print(f"Combined output: {combined_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
