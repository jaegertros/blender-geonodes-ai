"""
Knowledge Base Builder
======================
Assembles all discovery, pattern, and exploration data into a unified
knowledge base that an AI can use to understand and generate geometry
node trees.

Data sources:
  - discovery/node_catalog.json       (what nodes exist, sockets, defaults)
  - discovery/connection_matrix.json   (what socket types can connect)
  - discovery/node_classification.json (domain groupings)
  - discovery/axioms.json             (hardcoded rules and pitfalls)
  - patterns/pattern_catalog.json     (verified working patterns)
  - explorer/results/*_combined.json  (single-node behavior observations)

Output:
  - knowledge/blender_geonodes_kb.json

Usage:
  python knowledge/build_kb.py
"""

import json
import os
from datetime import datetime


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_node_profiles(catalog, classification, exploration_results):
    """Build a per-node profile combining catalog info + classification + observed behavior."""
    profiles = {}

    for node_id, cat_entry in catalog.get("nodes", {}).items():
        profile = {
            "name": cat_entry.get("name", node_id),
            "type_id": node_id,
            "inputs": cat_entry.get("inputs", []),
            "outputs": cat_entry.get("outputs", []),
            "properties": cat_entry.get("properties", {}),
        }

        # Add classification
        class_info = classification.get("nodes", {}).get(node_id, {})
        profile["domain"] = class_info.get("domain", "unknown")
        profile["purpose"] = class_info.get("purpose", "unknown")

        # Derive socket signature
        input_types = [s["type"] for s in profile["inputs"]]
        output_types = [s["type"] for s in profile["outputs"]]
        profile["has_geometry_input"] = "GEOMETRY" in input_types
        profile["has_geometry_output"] = "GEOMETRY" in output_types
        profile["input_socket_types"] = sorted(set(input_types))
        profile["output_socket_types"] = sorted(set(output_types))

        # Classify node role based on sockets
        if profile["has_geometry_input"] and profile["has_geometry_output"]:
            profile["role"] = "processor"  # Takes geo, outputs geo
        elif profile["has_geometry_output"] and not profile["has_geometry_input"]:
            profile["role"] = "generator"  # Creates geo from nothing
        elif profile["has_geometry_input"] and not profile["has_geometry_output"]:
            profile["role"] = "consumer"   # Takes geo, no geo output (viewer, etc.)
        else:
            profile["role"] = "field"      # No geo sockets (math, utility)

        # Add exploration results
        if node_id in exploration_results:
            obs = exploration_results[node_id]
            profile["observed_behavior"] = obs["category"]
            profile["observation_details"] = obs.get("details", {})
            if "before_verts" in obs:
                profile["observed_vertex_delta"] = obs.get("after_verts", 0) - obs["before_verts"]
        else:
            profile["observed_behavior"] = "NOT_TESTED"

        profiles[node_id] = profile

    return profiles


def build_connection_rules(connection_matrix):
    """Extract socket compatibility rules from the connection matrix."""
    rules = {
        "valid_connections": [],
        "invalid_connections": [],
        "type_groups": {},
    }

    # connection_matrix.json stores data under "connections" key as a dict
    # Keys are "TYPE_A -> TYPE_B" format
    connections_data = connection_matrix.get("connections", connection_matrix.get("compatibility", {}))

    for key, info in connections_data.items():
        # Handle multiple key formats: "A -> B", "A→B", etc.
        for sep in [" -> ", "→", "->"]:
            if sep in key:
                parts = key.split(sep)
                break
        else:
            continue
        if len(parts) != 2:
            continue
        from_type, to_type = parts[0].strip(), parts[1].strip()

        entry = {
            "from": from_type,
            "to": to_type,
            "valid": info.get("valid", False),
        }

        if info.get("valid"):
            rules["valid_connections"].append(entry)
        else:
            rules["invalid_connections"].append(entry)

    # Build type groups (types that can freely interconnect)
    valid_pairs = set()
    all_types = set()
    for conn in rules["valid_connections"]:
        f, t = conn["from"], conn["to"]
        valid_pairs.add((f, t))
        all_types.add(f)
        all_types.add(t)

    # Find groups of mutually compatible types
    # A group = set of types where every pair (a->b and b->a) is valid
    numeric_types = {"BOOLEAN", "INT", "VALUE", "RGBA", "VECTOR"}
    spatial_types = {"ROTATION", "MATRIX"}
    resource_types = {"GEOMETRY", "OBJECT", "COLLECTION", "IMAGE", "MATERIAL"}

    rules["type_groups"] = {
        "numeric": {
            "types": sorted(numeric_types & all_types),
            "note": "Freely interconvertible (bool<->int<->float<->vector<->color)",
        },
        "spatial": {
            "types": sorted(spatial_types & all_types),
            "note": "Rotation and Matrix can convert between each other",
        },
        "resource": {
            "types": sorted(resource_types & all_types),
            "note": "Resource types are isolated - only connect to same type",
        },
    }

    rules["total_valid"] = len(rules["valid_connections"])
    rules["total_invalid"] = len(rules["invalid_connections"])

    return rules


def build_pattern_library(pattern_catalog):
    """Structure the verified patterns into a queryable format."""
    patterns = []

    for entry in pattern_catalog.get("patterns", []):
        if not entry.get("verified"):
            continue

        pattern = {
            "name": entry.get("pattern_name", ""),
            "description": entry.get("description", ""),
            "blender_version": entry.get("blender_version", ""),
            "nodes_used": [],
            "links": [],
        }

        tree = entry.get("tree_structure", {})
        for node in tree.get("nodes", []):
            if node["type"] in ("NodeGroupInput", "NodeGroupOutput"):
                continue
            pattern["nodes_used"].append({
                "type": node["type"],
                "name": node["name"],
                "input_defaults": node.get("input_defaults", {}),
                "properties": node.get("properties", {}),
            })

        for link in tree.get("links", []):
            pattern["links"].append({
                "from_node": link["from_node"],
                "from_socket": link["from_socket"],
                "to_node": link["to_node"],
                "to_socket": link["to_socket"],
            })

        # Stats
        stats = entry.get("stats_after", {})
        pattern["result_stats"] = stats

        patterns.append(pattern)

    return patterns


def build_exploration_summary(exploration_results):
    """Summarize exploration findings by behavior category."""
    summary = {
        "total_tested": 0,
        "by_category": {},
        "interesting_findings": [],
    }

    for node_id, obs in exploration_results.items():
        cat = obs["category"]
        summary["total_tested"] += 1
        if cat not in summary["by_category"]:
            summary["by_category"][cat] = {"count": 0, "nodes": []}
        summary["by_category"][cat]["count"] += 1
        summary["by_category"][cat]["nodes"].append({
            "type": node_id,
            "name": obs.get("node_name", ""),
            "details": obs.get("details", {}),
        })

    # Highlight interesting findings
    for node_id, obs in exploration_results.items():
        if obs["category"] == "MODIFIED":
            details = obs.get("details", {})
            vd = details.get("vertex_delta", 0)
            if vd != 0:
                summary["interesting_findings"].append({
                    "node": node_id,
                    "name": obs.get("node_name", ""),
                    "finding": f"Changed vertex count by {vd:+d}",
                    "category": "MODIFIED",
                })
        elif obs["category"] == "TYPE_CONVERTED":
            summary["interesting_findings"].append({
                "node": node_id,
                "name": obs.get("node_name", ""),
                "finding": obs.get("details", {}).get("reason", "Type conversion"),
                "category": "TYPE_CONVERTED",
            })

    return summary


def main():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Load all data sources
    print("Loading data sources...")

    catalog = load_json(os.path.join(project_dir, "discovery", "node_catalog.json"))
    print(f"  Node catalog: {len(catalog.get('nodes', {}))} nodes")

    connection_matrix = load_json(os.path.join(project_dir, "discovery", "connection_matrix.json"))
    conn_count = len(connection_matrix.get("connections", connection_matrix.get("compatibility", {})))
    print(f"  Connection matrix: {conn_count} type pairs tested")

    classification = load_json(os.path.join(project_dir, "discovery", "node_classification.json"))
    print(f"  Classification: {classification.get('total_nodes', 0)} nodes classified")

    axioms = load_json(os.path.join(project_dir, "discovery", "axioms.json"))
    structural = axioms.get("structural_rules", {})
    pitfalls = axioms.get("common_pitfalls", {}).get("items", [])
    print(f"  Axioms: {len(structural)} structural rule categories, "
          f"{len(pitfalls)} discovered pitfalls")

    pattern_catalog = load_json(os.path.join(project_dir, "patterns", "pattern_catalog.json"))
    print(f"  Pattern catalog: {len(pattern_catalog.get('patterns', []))} verified patterns")

    # Load exploration results
    results_dir = os.path.join(project_dir, "explorer", "results")
    exploration_results = {}
    explored_files = 0
    for fname in sorted(os.listdir(results_dir)):
        if fname.endswith("_combined.json"):
            data = load_json(os.path.join(results_dir, fname))
            for node_obs in data.get("nodes", []):
                exploration_results[node_obs["node_type"]] = node_obs
            explored_files += 1
    print(f"  Exploration results: {len(exploration_results)} nodes from {explored_files} domain files")

    # Build knowledge base sections
    print("\nBuilding knowledge base...")

    kb = {
        "metadata": {
            "version": "1.0.0",
            "blender_version": catalog.get("blender_version", "unknown"),
            "build_date": datetime.now().isoformat(),
            "description": "Empirically-generated knowledge base for Blender Geometry Nodes",
            "data_sources": [
                "discovery/node_catalog.json",
                "discovery/connection_matrix.json",
                "discovery/node_classification.json",
                "discovery/axioms.json",
                "patterns/pattern_catalog.json",
                "explorer/results/*_combined.json",
            ],
        },

        # Section 1: Rules and axioms (things that are always true)
        "rules": {
            "structural": axioms.get("structural_rules", {}),
            "socket_types": axioms.get("socket_type_system", {}),
            "geometry_domains": axioms.get("geometry_domains", {}),
            "tree_creation": axioms.get("node_tree_creation", {}),
            "pitfalls": axioms.get("common_pitfalls", {}).get("items", []),
        },

        # Section 2: Socket connection compatibility
        "connections": build_connection_rules(connection_matrix),

        # Section 3: Per-node profiles (catalog + classification + observations)
        "nodes": build_node_profiles(catalog, classification, exploration_results),

        # Section 4: Verified patterns (known-good recipes)
        "patterns": build_pattern_library(pattern_catalog),

        # Section 5: Exploration summary (what we learned)
        "exploration": build_exploration_summary(exploration_results),

        # Section 6: Quick-reference lookups
        "lookups": {},
    }

    # Build lookup tables
    print("  Building lookup tables...")

    # Nodes by role
    by_role = {}
    for nid, profile in kb["nodes"].items():
        role = profile["role"]
        if role not in by_role:
            by_role[role] = []
        by_role[role].append(nid)
    kb["lookups"]["nodes_by_role"] = {k: sorted(v) for k, v in by_role.items()}

    # Nodes by domain
    by_domain = {}
    for nid, profile in kb["nodes"].items():
        domain = profile["domain"]
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(nid)
    kb["lookups"]["nodes_by_domain"] = {k: sorted(v) for k, v in by_domain.items()}

    # Generator nodes (create geometry from nothing)
    kb["lookups"]["generators"] = sorted([
        nid for nid, p in kb["nodes"].items()
        if p["role"] == "generator"
    ])

    # Nodes that modify mesh topology
    kb["lookups"]["mesh_modifiers"] = sorted([
        nid for nid, p in kb["nodes"].items()
        if p.get("observed_behavior") == "MODIFIED"
    ])

    # Type converter nodes
    kb["lookups"]["type_converters"] = sorted([
        nid for nid, p in kb["nodes"].items()
        if p.get("observed_behavior") == "TYPE_CONVERTED"
    ])

    # Nodes by output socket type
    by_output_type = {}
    for nid, profile in kb["nodes"].items():
        for stype in profile["output_socket_types"]:
            if stype not in by_output_type:
                by_output_type[stype] = []
            by_output_type[stype].append(nid)
    kb["lookups"]["nodes_by_output_type"] = {k: sorted(v) for k, v in by_output_type.items()}

    # Stats
    kb["stats"] = {
        "total_nodes": len(kb["nodes"]),
        "total_patterns": len(kb["patterns"]),
        "nodes_explored": len(exploration_results),
        "connection_types_tested": conn_count,
        "nodes_by_role": {k: len(v) for k, v in kb["lookups"]["nodes_by_role"].items()},
        "nodes_by_behavior": {
            cat: info["count"]
            for cat, info in kb["exploration"]["by_category"].items()
        },
    }

    # Write output
    output_dir = os.path.join(project_dir, "knowledge")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "blender_geonodes_kb.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2, ensure_ascii=False, default=str)

    file_size = os.path.getsize(output_path)
    print(f"\nKnowledge base written to: {output_path}")
    print(f"Size: {file_size / 1024:.1f} KB")
    print()
    print("=" * 60)
    print("Knowledge Base Stats:")
    print(f"  Nodes:               {kb['stats']['total_nodes']}")
    print(f"  Nodes explored:      {kb['stats']['nodes_explored']}")
    print(f"  Verified patterns:   {kb['stats']['total_patterns']}")
    print(f"  Connection types:    {kb['stats']['connection_types_tested']}")
    print(f"  Node roles:          {kb['stats']['nodes_by_role']}")
    print(f"  Observed behaviors:  {kb['stats']['nodes_by_behavior']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
