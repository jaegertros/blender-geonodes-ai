"""
Property Variation Explorer (runs inside Blender)
==================================================
Tests nodes with their enum property variations to discover how
different modes/operations affect geometry.

For example, tests Extrude Mesh in FACES/EDGES/VERTICES modes,
or Math node with ADD/SUBTRACT/MULTIPLY/etc operations.

Usage:
    blender --background --factory-startup --python explorer/explore_properties.py -- \
        --catalog discovery/node_catalog.json \
        --nodes GeometryNodeExtrudeMesh,GeometryNodeMeshBoolean \
        --output explorer/results/prop_variations.json \
        --mesh-type cube
"""

import bpy
import sys
import os
import json
import argparse
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from eval_engine import test_node_with_property_variations


# Properties to skip (generic, on every node, not interesting)
SKIP_PROPS = {"color_tag", "warning_propagation"}


def parse_args():
    try:
        idx = sys.argv.index("--")
        args = sys.argv[idx + 1:]
    except ValueError:
        args = []

    parser = argparse.ArgumentParser(description="Explore node property variations")
    parser.add_argument("--catalog", required=True, help="Path to node_catalog.json")
    parser.add_argument("--nodes", required=True, help="Comma-separated node type IDs to test")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--mesh-type", default="cube", help="Base mesh type")

    return parser.parse_args(args)


def filter_catalog_enums(catalog_entry):
    """Filter catalog entry to only include non-generic enum properties."""
    filtered_props = {}
    for pname, pinfo in catalog_entry.get("properties", {}).items():
        if pname in SKIP_PROPS:
            continue
        if isinstance(pinfo, dict) and "enum_items" in pinfo:
            filtered_props[pname] = pinfo

    # Return a modified copy with only interesting enum properties
    entry = dict(catalog_entry)
    entry["properties"] = filtered_props
    return entry


def main():
    args = parse_args()

    with open(args.catalog, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    node_ids = [n.strip() for n in args.nodes.split(",") if n.strip()]

    results = {
        "blender_version": bpy.app.version_string,
        "exploration_date": datetime.now().isoformat(),
        "base_mesh": args.mesh_type,
        "type": "property_variations",
        "nodes": {},
    }

    total_tests = 0

    for i, node_id in enumerate(node_ids):
        if node_id not in catalog["nodes"]:
            print(f"  [{i+1}/{len(node_ids)}] {node_id}: NOT IN CATALOG, skipping")
            continue

        entry = catalog["nodes"][node_id]
        filtered_entry = filter_catalog_enums(entry)
        name = entry.get("name", node_id)

        # Count expected variations
        enum_count = sum(
            len(pinfo.get("enum_items", []))
            for pinfo in filtered_entry.get("properties", {}).values()
        )
        if enum_count == 0:
            print(f"  [{i+1}/{len(node_ids)}] {name}: no enum properties, testing default only")

        print(f"  [{i+1}/{len(node_ids)}] {name} ({node_id}) - {enum_count} variations...",
              flush=True)

        variation_results = test_node_with_property_variations(
            node_id, filtered_entry, args.mesh_type
        )

        # Compact results
        compact_variations = []
        for vr in variation_results:
            compact = {
                "variation": vr.get("property_variation", "default"),
                "category": vr["category"],
                "details": vr.get("details", {}),
            }
            # Include vertex counts for MODIFIED
            if "snapshot_before" in vr and "snapshot_after" in vr:
                b_v = vr["snapshot_before"].get("mesh", {}).get("vertices", 0)
                a_v = vr["snapshot_after"].get("mesh", {}).get("vertices", 0)
                if b_v != a_v:
                    compact["vertex_delta"] = a_v - b_v
                    compact["before_verts"] = b_v
                    compact["after_verts"] = a_v
            compact_variations.append(compact)

        results["nodes"][node_id] = {
            "name": name,
            "variations_tested": len(compact_variations),
            "results": compact_variations,
        }

        total_tests += len(compact_variations)

        # Quick summary for this node
        cats = {}
        for cv in compact_variations:
            c = cv["category"]
            cats[c] = cats.get(c, 0) + 1
        cat_str = ", ".join(f"{c}:{n}" for c, n in sorted(cats.items()))
        print(f"    -> {len(compact_variations)} tested: {cat_str}")

    # Write output
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print()
    print(f"Total property variation tests: {total_tests}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
