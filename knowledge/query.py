"""
Knowledge Base Query Interface
===============================
Simple query functions for the Blender Geometry Nodes knowledge base.

Usage:
  python knowledge/query.py "what nodes can subdivide a mesh"
  python knowledge/query.py --generators
  python knowledge/query.py --domain mesh
  python knowledge/query.py --can-connect FLOAT VECTOR
  python knowledge/query.py --node GeometryNodeSubdivideMesh
  python knowledge/query.py --role processor
  python knowledge/query.py --modified
"""

import json
import os
import sys
import argparse


def load_kb():
    kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_geonodes_kb.json")
    with open(kb_path, "r", encoding="utf-8") as f:
        return json.load(f)


def query_node(kb, node_type_id):
    """Get full profile for a specific node."""
    profile = kb["nodes"].get(node_type_id)
    if not profile:
        # Try fuzzy match
        matches = [
            nid for nid in kb["nodes"]
            if node_type_id.lower() in nid.lower()
        ]
        if matches:
            print(f"Node '{node_type_id}' not found. Did you mean:")
            for m in matches:
                print(f"  - {m} ({kb['nodes'][m]['name']})")
            return None
        print(f"Node '{node_type_id}' not found.")
        return None
    return profile


def query_domain(kb, domain):
    """List all nodes in a domain."""
    nodes = kb["lookups"]["nodes_by_domain"].get(domain, [])
    if not nodes:
        print(f"Domain '{domain}' not found. Available domains:")
        for d in sorted(kb["lookups"]["nodes_by_domain"].keys()):
            print(f"  - {d} ({len(kb['lookups']['nodes_by_domain'][d])} nodes)")
        return []
    return [(nid, kb["nodes"][nid]) for nid in nodes]


def query_role(kb, role):
    """List all nodes with a specific role."""
    nodes = kb["lookups"]["nodes_by_role"].get(role, [])
    return [(nid, kb["nodes"][nid]) for nid in nodes]


def query_generators(kb):
    """List all generator nodes (create geometry from nothing)."""
    return [(nid, kb["nodes"][nid]) for nid in kb["lookups"]["generators"]]


def query_mesh_modifiers(kb):
    """List all nodes that observably modify mesh geometry."""
    return [(nid, kb["nodes"][nid]) for nid in kb["lookups"]["mesh_modifiers"]]


def query_can_connect(kb, from_type, to_type):
    """Check if two socket types can connect."""
    for conn in kb["connections"]["valid_connections"]:
        if conn["from"] == from_type and conn["to"] == to_type:
            return True, conn
    for conn in kb["connections"]["invalid_connections"]:
        if conn["from"] == from_type and conn["to"] == to_type:
            return False, conn
    return None, None  # Not tested


def query_compatible_outputs(kb, target_type):
    """Find all socket types that can connect to target_type."""
    compatible = []
    for conn in kb["connections"]["valid_connections"]:
        if conn["to"] == target_type:
            compatible.append(conn["from"])
    return sorted(set(compatible))


def query_compatible_inputs(kb, source_type):
    """Find all socket types that accept source_type."""
    compatible = []
    for conn in kb["connections"]["valid_connections"]:
        if conn["from"] == source_type:
            compatible.append(conn["to"])
    return sorted(set(compatible))


def query_text(kb, text):
    """Simple text search across node names and descriptions."""
    text_lower = text.lower()
    matches = []
    for nid, profile in kb["nodes"].items():
        score = 0
        name = profile.get("name", "").lower()
        if text_lower in name:
            score += 10
        if text_lower in nid.lower():
            score += 5
        # Check input/output socket names
        for s in profile.get("inputs", []):
            if text_lower in s.get("name", "").lower():
                score += 2
        for s in profile.get("outputs", []):
            if text_lower in s.get("name", "").lower():
                score += 2
        # Check domain
        if text_lower in profile.get("domain", ""):
            score += 3
        if score > 0:
            matches.append((score, nid, profile))

    matches.sort(key=lambda x: -x[0])
    return [(nid, profile) for _, nid, profile in matches[:20]]


def format_node_brief(nid, profile):
    """Format a node for brief display."""
    behavior = profile.get("observed_behavior", "?")
    role = profile.get("role", "?")
    domain = profile.get("domain", "?")
    name = profile.get("name", nid)
    return f"  {name:40s} [{domain:12s}] [{role:10s}] [{behavior}]"


def format_node_detail(nid, profile):
    """Format a node with full details."""
    lines = []
    lines.append(f"Node: {profile.get('name', nid)}")
    lines.append(f"  Type ID: {nid}")
    lines.append(f"  Domain:  {profile.get('domain', '?')}")
    lines.append(f"  Role:    {profile.get('role', '?')}")
    lines.append(f"  Behavior: {profile.get('observed_behavior', 'NOT_TESTED')}")

    if profile.get("inputs"):
        lines.append("  Inputs:")
        for s in profile["inputs"]:
            default = f" = {s.get('default', '')}" if "default" in s else ""
            lines.append(f"    - {s['name']} ({s['type']}){default}")

    if profile.get("outputs"):
        lines.append("  Outputs:")
        for s in profile["outputs"]:
            lines.append(f"    - {s['name']} ({s['type']})")

    if profile.get("properties"):
        lines.append("  Properties:")
        for pname, pinfo in profile["properties"].items():
            if isinstance(pinfo, dict) and "enum_items" in pinfo:
                items = [i["identifier"] if isinstance(i, dict) else i for i in pinfo["enum_items"]]
                lines.append(f"    - {pname}: enum [{', '.join(items[:8])}{'...' if len(items) > 8 else ''}]")
            else:
                lines.append(f"    - {pname}: {pinfo}")

    obs = profile.get("observation_details", {})
    if obs:
        lines.append(f"  Observation: {json.dumps(obs, default=str)}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Query Blender Geometry Nodes KB")
    parser.add_argument("text", nargs="?", help="Text search query")
    parser.add_argument("--node", help="Get details for specific node type ID")
    parser.add_argument("--domain", help="List nodes in a domain")
    parser.add_argument("--role", help="List nodes by role (processor, generator, consumer, field)")
    parser.add_argument("--generators", action="store_true", help="List generator nodes")
    parser.add_argument("--modified", action="store_true", help="List nodes that modify mesh")
    parser.add_argument("--can-connect", nargs=2, metavar=("FROM", "TO"), help="Check socket type compatibility")
    parser.add_argument("--accepts", help="Find types that connect to this type")
    parser.add_argument("--outputs-to", help="Find types this type can connect to")
    parser.add_argument("--patterns", action="store_true", help="List verified patterns")
    parser.add_argument("--stats", action="store_true", help="Show KB statistics")

    args = parser.parse_args()
    kb = load_kb()

    if args.stats:
        print("Knowledge Base Statistics:")
        print(json.dumps(kb["stats"], indent=2))
        return

    if args.node:
        profile = query_node(kb, args.node)
        if profile:
            print(format_node_detail(args.node, profile))
        return

    if args.domain:
        results = query_domain(kb, args.domain)
        print(f"Domain '{args.domain}': {len(results)} nodes")
        for nid, profile in results:
            print(format_node_brief(nid, profile))
        return

    if args.role:
        results = query_role(kb, args.role)
        print(f"Role '{args.role}': {len(results)} nodes")
        for nid, profile in results:
            print(format_node_brief(nid, profile))
        return

    if args.generators:
        results = query_generators(kb)
        print(f"Generator nodes: {len(results)}")
        for nid, profile in results:
            print(format_node_brief(nid, profile))
        return

    if args.modified:
        results = query_mesh_modifiers(kb)
        print(f"Mesh-modifying nodes: {len(results)}")
        for nid, profile in results:
            details = profile.get("observation_details", {})
            vd = details.get("vertex_delta", 0)
            name = profile.get("name", nid)
            print(f"  {name:40s} vertex_delta={vd:+d}" if vd else f"  {name:40s}")
        return

    if args.can_connect:
        from_type, to_type = args.can_connect
        valid, conn = query_can_connect(kb, from_type.upper(), to_type.upper())
        if valid is None:
            print(f"{from_type} -> {to_type}: NOT TESTED")
        elif valid:
            print(f"{from_type} -> {to_type}: VALID (yes)")
        else:
            print(f"{from_type} -> {to_type}: INVALID (no)")
        return

    if args.accepts:
        compatible = query_compatible_outputs(kb, args.accepts.upper())
        print(f"Types that can connect TO {args.accepts.upper()}:")
        for t in compatible:
            print(f"  - {t}")
        return

    if args.outputs_to:
        compatible = query_compatible_inputs(kb, args.outputs_to.upper())
        print(f"Types that {args.outputs_to.upper()} can connect TO:")
        for t in compatible:
            print(f"  - {t}")
        return

    if args.patterns:
        print(f"Verified patterns: {len(kb['patterns'])}")
        for p in kb["patterns"]:
            nodes = [n["type"] for n in p["nodes_used"]]
            print(f"  {p['name']:40s} {p['description']}")
            print(f"    Nodes: {', '.join(nodes)}")
        return

    if args.text:
        results = query_text(kb, args.text)
        if results:
            print(f"Search '{args.text}': {len(results)} matches")
            for nid, profile in results:
                print(format_node_brief(nid, profile))
        else:
            print(f"No matches for '{args.text}'")
        return

    # Default: show summary
    print("Blender Geometry Nodes Knowledge Base")
    print("=" * 50)
    print(json.dumps(kb["stats"], indent=2))
    print()
    print("Usage examples:")
    print('  python knowledge/query.py "subdivide"')
    print("  python knowledge/query.py --node GeometryNodeSubdivideMesh")
    print("  python knowledge/query.py --domain mesh")
    print("  python knowledge/query.py --generators")
    print("  python knowledge/query.py --modified")
    print("  python knowledge/query.py --can-connect FLOAT VECTOR")
    print("  python knowledge/query.py --patterns")


if __name__ == "__main__":
    main()
