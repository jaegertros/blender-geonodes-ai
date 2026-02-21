"""
Node Exploration Script (runs inside Blender)
===============================================
Tests a batch of nodes by inserting each into a simple passthrough
tree and evaluating the result using the multi-tier eval engine.

Usage:
    blender --background --factory-startup --python explorer/explore_nodes.py -- \
        --catalog discovery/node_catalog.json \
        --classification discovery/node_classification.json \
        --domain mesh \
        --output explorer/results/mesh_results.json \
        --batch-start 0 \
        --batch-size 50

Arguments after -- are passed to the script.
"""

import bpy
import sys
import os
import json
import argparse
from datetime import datetime

# Add explorer dir to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from eval_engine import test_node_insertion


def parse_args():
    """Parse command line args (after Blender's --)."""
    # Find '--' separator
    try:
        idx = sys.argv.index("--")
        args = sys.argv[idx + 1:]
    except ValueError:
        args = []

    parser = argparse.ArgumentParser(description="Explore geometry nodes")
    parser.add_argument("--catalog", required=True, help="Path to node_catalog.json")
    parser.add_argument("--classification", required=True, help="Path to node_classification.json")
    parser.add_argument("--domain", default=None, help="Filter to specific domain (mesh, curve, etc.) or 'all'")
    parser.add_argument("--nodes", default=None, help="Comma-separated list of specific node type IDs to test")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--batch-start", type=int, default=0, help="Start index in filtered node list")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of nodes per batch")
    parser.add_argument("--mesh-type", default="cube", help="Base mesh type (cube, plane, sphere)")

    return parser.parse_args(args)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_nodes_to_test(catalog, classification, domain=None, specific_nodes=None):
    """Get the list of nodes to test, filtered by domain or explicit list."""
    if specific_nodes:
        node_ids = [n.strip() for n in specific_nodes.split(",")]
        return [(nid, catalog["nodes"][nid]) for nid in node_ids if nid in catalog["nodes"]]

    if domain and domain != "all":
        # Filter by classification domain
        class_nodes = classification.get("nodes", {})
        return [
            (nid, catalog["nodes"][nid])
            for nid, info in sorted(class_nodes.items())
            if info.get("domain") == domain and nid in catalog["nodes"]
        ]

    # All nodes
    return [(nid, catalog["nodes"][nid]) for nid in sorted(catalog["nodes"])]


# Skip list: nodes that are known to crash or require special handling
SKIP_NODES = {
    # Base classes / non-instantiable
    "FunctionNode", "GeometryNode", "GeometryNodeCustomGroup", "GeometryNodeTree",
    # Zone nodes (need input+output pair)
    "GeometryNodeSimulationInput", "GeometryNodeSimulationOutput",
    "GeometryNodeRepeatInput", "GeometryNodeRepeatOutput",
    "GeometryNodeBake",
    "GeometryNodeForeachGeometryElementInput", "GeometryNodeForeachGeometryElementOutput",
    "GeometryNodeForeachElementInput", "GeometryNodeForeachElementOutput",
    # Closure/Bundle (internal)
    "GeometryNodeClosureInput", "GeometryNodeClosureOutput",
    "GeometryNodeEvaluateClosure",
    "GeometryNodeCombineBundle", "GeometryNodeSeparateBundle",
    # Gizmo nodes (need UI context)
    "GeometryNodeGizmoLinear", "GeometryNodeGizmoDial", "GeometryNodeGizmoTransform",
    # Shader nodes that can't be in geonodes tree
    "ShaderNodeCombineColor", "ShaderNodeSeparateColor",
}


def main():
    args = parse_args()

    catalog = load_json(args.catalog)
    classification = load_json(args.classification)

    all_nodes = get_nodes_to_test(catalog, classification, args.domain, args.nodes)

    # Apply batch window
    batch = all_nodes[args.batch_start:args.batch_start + args.batch_size]

    # Filter out skip list
    batch = [(nid, entry) for nid, entry in batch if nid not in SKIP_NODES]

    print(f"Exploring {len(batch)} nodes (batch {args.batch_start}-{args.batch_start + len(batch)})")
    print(f"Domain: {args.domain or 'all'}")
    print(f"Base mesh: {args.mesh_type}")
    print()

    results = {
        "blender_version": bpy.app.version_string,
        "exploration_date": datetime.now().isoformat(),
        "domain": args.domain,
        "base_mesh": args.mesh_type,
        "batch_start": args.batch_start,
        "batch_size": len(batch),
        "summary": {
            "MODIFIED": 0,
            "PASSTHROUGH": 0,
            "TYPE_CONVERTED": 0,
            "EMPTY_OUTPUT": 0,
            "GENERATED": 0,
            "ERROR": 0,
            "LINK_INVALID": 0,
        },
        "nodes": [],
    }

    for i, (node_id, catalog_entry) in enumerate(batch):
        name = catalog_entry.get("name", node_id)
        print(f"  [{i+1}/{len(batch)}] {name} ({node_id})...", end=" ", flush=True)

        r = test_node_insertion(node_id, catalog_entry, args.mesh_type)

        # Compact the result (remove bulky snapshots for summary, keep category)
        compact = {
            "node_type": r["node_type"],
            "node_name": r["node_name"],
            "category": r["category"],
            "details": r.get("details", {}),
            "links_valid": r.get("links_valid", True),
        }

        # Keep snapshot deltas for MODIFIED
        if r["category"] == "MODIFIED" and "snapshot_before" in r and "snapshot_after" in r:
            compact["before_verts"] = r["snapshot_before"].get("mesh", {}).get("vertices", 0)
            compact["after_verts"] = r["snapshot_after"].get("mesh", {}).get("vertices", 0)

        results["nodes"].append(compact)
        results["summary"][r["category"]] = results["summary"].get(r["category"], 0) + 1

        print(r["category"])

    # Write results
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print()
    print("=" * 60)
    print("Summary:")
    for cat, count in sorted(results["summary"].items()):
        if count > 0:
            print(f"  {cat:<20} {count}")
    print(f"Output: {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
