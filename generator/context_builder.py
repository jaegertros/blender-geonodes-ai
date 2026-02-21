"""
KB Context Builder for Geometry Node Generation
=================================================
Extracts a relevant slice of the knowledge base for a given generation
task. This context slice is small enough to include in an LLM prompt
while containing all the information needed to generate a valid node tree.

The context builder:
  1. Searches the KB for relevant nodes based on the task description
  2. Includes full socket specs for matched nodes
  3. Includes connection rules for the socket types involved
  4. Includes matching verified patterns as examples
  5. Includes relevant pitfalls and structural rules

Output: a structured dict or formatted text that can be injected into a prompt.
"""

import json
import os
import re


def load_kb(kb_path=None):
    """Load the knowledge base."""
    if kb_path is None:
        kb_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge", "blender_geonodes_kb.json"
        )
    with open(kb_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────
# Keyword extraction and node matching
# ──────────────────────────────────────────────────────────────────────

# Map common user terms to KB node search terms
TERM_MAP = {
    "scatter": ["distribute", "instance", "points"],
    "rocks": ["instance", "ico sphere", "cube"],
    "trees": ["instance", "collection"],
    "random": ["random", "noise", "distribute"],
    "smooth": ["shade smooth", "subdivide", "subdivision"],
    "subdivide": ["subdivide", "subdivision"],
    "boolean": ["boolean", "intersect", "difference", "union"],
    "subtract": ["boolean", "difference"],
    "cut": ["boolean", "difference"],
    "merge": ["join", "merge", "boolean union"],
    "deform": ["set position", "noise", "displacement"],
    "displace": ["set position", "noise texture", "displacement"],
    "noise": ["noise", "random"],
    "extrude": ["extrude"],
    "array": ["instance", "duplicate"],
    "duplicate": ["duplicate", "instance"],
    "curve": ["curve", "bezier", "spline"],
    "sweep": ["curve to mesh", "profile"],
    "pipe": ["curve to mesh", "curve circle"],
    "text": ["string to curves"],
    "particles": ["distribute", "instance", "points"],
    "hair": ["distribute", "curve", "interpolate"],
    "color": ["material", "color", "rgba"],
    "material": ["material", "set material"],
    "volume": ["volume", "mesh to volume"],
    "grid": ["grid", "mesh grid"],
    "sphere": ["uv sphere", "ico sphere"],
    "cylinder": ["cylinder"],
    "cone": ["cone"],
    "circle": ["circle"],
    "triangulate": ["triangulate"],
    "flip": ["flip faces"],
    "scale": ["scale", "transform"],
    "rotate": ["rotate", "transform"],
    "move": ["translate", "set position", "transform"],
    "join": ["join geometry"],
    "separate": ["separate", "delete"],
    "delete": ["delete geometry"],
    "proximity": ["proximity"],
    "raycast": ["raycast"],
    "fill": ["fill curve"],
    "convex": ["convex hull"],
    "bounding": ["bounding box"],
}


def extract_search_terms(description):
    """Extract search terms from a natural language description."""
    terms = set()
    desc_lower = description.lower()

    # Direct keyword matches
    words = re.findall(r'[a-z]+', desc_lower)
    for word in words:
        if word in TERM_MAP:
            terms.update(TERM_MAP[word])
        terms.add(word)

    # Multi-word phrase matches
    for phrase, mapped in TERM_MAP.items():
        if phrase in desc_lower:
            terms.update(mapped)

    return terms


def search_nodes(kb, terms, max_results=20):
    """Search KB nodes matching the given terms. Returns (node_id, score, profile)."""
    results = []

    for nid, profile in kb["nodes"].items():
        score = 0
        name_lower = profile.get("name", "").lower()
        type_lower = nid.lower()

        for term in terms:
            term_lower = term.lower()
            # Name match (highest weight)
            if term_lower in name_lower:
                score += 10
            # Type ID match
            if term_lower.replace(" ", "") in type_lower.lower():
                score += 5
            # Socket name match
            for s in profile.get("inputs", []) + profile.get("outputs", []):
                if term_lower in s.get("name", "").lower():
                    score += 2
            # Domain match
            if term_lower in profile.get("domain", ""):
                score += 3

        if score > 0:
            results.append((nid, score, profile))

    results.sort(key=lambda x: -x[1])
    return results[:max_results]


def search_patterns(kb, terms, max_results=5):
    """Search verified patterns matching the terms."""
    results = []

    for pattern in kb.get("patterns", []):
        score = 0
        desc_lower = pattern.get("description", "").lower()
        name_lower = pattern.get("name", "").lower()

        for term in terms:
            term_lower = term.lower()
            if term_lower in desc_lower:
                score += 5
            if term_lower in name_lower:
                score += 10
            # Check if pattern uses relevant node types
            for node in pattern.get("nodes_used", []):
                if term_lower in node.get("type", "").lower():
                    score += 3
                if term_lower in node.get("name", "").lower():
                    score += 3

        if score > 0:
            results.append((score, pattern))

    results.sort(key=lambda x: -x[0])
    return [p for _, p in results[:max_results]]


# ──────────────────────────────────────────────────────────────────────
# Context building
# ──────────────────────────────────────────────────────────────────────

def build_context(kb, description, max_nodes=15):
    """Build a context slice from the KB for the given task description.

    Returns a dict with:
      - matched_nodes: relevant node profiles with full specs
      - connection_rules: socket type compatibility for involved types
      - example_patterns: matching verified patterns
      - structural_rules: key rules and pitfalls
      - property_variations: enum options for matched nodes (if available)
    """
    terms = extract_search_terms(description)
    node_matches = search_nodes(kb, terms, max_results=max_nodes)
    pattern_matches = search_patterns(kb, terms)

    # Collect socket types involved
    socket_types_used = set()
    for _, _, profile in node_matches:
        for s in profile.get("inputs", []):
            socket_types_used.add(s["type"])
        for s in profile.get("outputs", []):
            socket_types_used.add(s["type"])

    # Always include GEOMETRY
    socket_types_used.add("GEOMETRY")

    # Get relevant connection rules
    relevant_connections = []
    for conn in kb.get("connections", {}).get("valid_connections", []):
        if conn["from"] in socket_types_used or conn["to"] in socket_types_used:
            relevant_connections.append(conn)

    # Build node specs
    matched_nodes = {}
    for nid, score, profile in node_matches:
        spec = {
            "name": profile["name"],
            "type_id": nid,
            "role": profile.get("role", "unknown"),
            "domain": profile.get("domain", "unknown"),
            "observed_behavior": profile.get("observed_behavior", "NOT_TESTED"),
            "inputs": profile.get("inputs", []),
            "outputs": profile.get("outputs", []),
        }

        # Include key enum properties (not all properties, just enums)
        enum_props = {}
        for pname, pinfo in profile.get("properties", {}).items():
            if isinstance(pinfo, dict) and "enum_items" in pinfo:
                if pname not in ("color_tag", "warning_propagation"):
                    items = [
                        i["identifier"] if isinstance(i, dict) else i
                        for i in pinfo["enum_items"]
                    ]
                    enum_props[pname] = items
        if enum_props:
            spec["enum_properties"] = enum_props

        # Include property variation results if available
        prop_vars = profile.get("property_variations")
        if prop_vars:
            spec["property_variations"] = prop_vars

        matched_nodes[nid] = spec

    # Always include essential utility nodes if they're not already matched
    essential_nodes = [
        "GeometryNodeJoinGeometry",
        "GeometryNodeRealizeInstances",
        "GeometryNodeSetPosition",
    ]
    for eid in essential_nodes:
        if eid not in matched_nodes and eid in kb["nodes"]:
            profile = kb["nodes"][eid]
            matched_nodes[eid] = {
                "name": profile["name"],
                "type_id": eid,
                "role": profile.get("role", "unknown"),
                "inputs": profile.get("inputs", []),
                "outputs": profile.get("outputs", []),
                "note": "Essential utility node (auto-included)",
            }

    context = {
        "task_description": description,
        "search_terms": sorted(terms),
        "matched_nodes": matched_nodes,
        "connection_rules": {
            "valid": relevant_connections,
            "type_groups": kb.get("connections", {}).get("type_groups", {}),
        },
        "example_patterns": pattern_matches,
        "structural_rules": {
            "tree_creation": kb.get("rules", {}).get("tree_creation", {}),
            "pitfalls": kb.get("rules", {}).get("pitfalls", []),
        },
    }

    return context


def format_context_for_prompt(context):
    """Format the context dict into a human-readable text block for LLM prompts."""
    lines = []

    lines.append("## Available Geometry Nodes")
    lines.append("")
    for nid, spec in sorted(context["matched_nodes"].items()):
        lines.append(f"### {spec['name']} ({nid})")
        lines.append(f"Role: {spec.get('role', '?')}, Domain: {spec.get('domain', '?')}")
        if spec.get("observed_behavior"):
            lines.append(f"Tested behavior: {spec['observed_behavior']}")

        if spec.get("inputs"):
            lines.append("Inputs:")
            for s in spec["inputs"]:
                default = f" (default: {s.get('default', '')})" if "default" in s else ""
                lines.append(f"  - {s['name']}: {s['type']}{default}")

        if spec.get("outputs"):
            lines.append("Outputs:")
            for s in spec["outputs"]:
                lines.append(f"  - {s['name']}: {s['type']}")

        if spec.get("enum_properties"):
            lines.append("Mode/Operation properties:")
            for pname, items in spec["enum_properties"].items():
                items_str = ", ".join(items[:10])
                if len(items) > 10:
                    items_str += f" (+{len(items)-10} more)"
                lines.append(f"  - {pname}: [{items_str}]")

        lines.append("")

    if context.get("example_patterns"):
        lines.append("## Example Verified Patterns")
        lines.append("")
        for pat in context["example_patterns"]:
            lines.append(f"### Pattern: {pat['name']}")
            lines.append(f"Description: {pat['description']}")
            lines.append("Nodes used:")
            for node in pat["nodes_used"]:
                defaults_str = ""
                if node.get("input_defaults"):
                    defaults_str = " " + json.dumps(node["input_defaults"])
                lines.append(f"  - {node['type']}{defaults_str}")
            lines.append("Connections:")
            for link in pat["links"]:
                lines.append(f"  - {link['from_node']}.{link['from_socket']} -> {link['to_node']}.{link['to_socket']}")
            lines.append("")

    lines.append("## Connection Rules")
    type_groups = context.get("connection_rules", {}).get("type_groups", {})
    if type_groups:
        for group_name, group_info in type_groups.items():
            types = group_info.get("types", [])
            note = group_info.get("note", "")
            lines.append(f"- {group_name}: {', '.join(types)} ({note})")
    lines.append("")

    pitfalls = context.get("structural_rules", {}).get("pitfalls", [])
    if pitfalls:
        lines.append("## Critical Pitfalls")
        for p in pitfalls[:5]:
            if isinstance(p, dict):
                lines.append(f"- {p.get('pitfall', '')}")
                lines.append(f"  Fix: {p.get('fix', '')}")
            else:
                lines.append(f"- {p}")
        lines.append("")

    tree_rules = context.get("structural_rules", {}).get("tree_creation", {})
    if tree_rules:
        lines.append("## Tree Creation Rules")
        setup = tree_rules.get("minimal_modifier_setup", {})
        if setup:
            for step in setup.get("steps", []):
                if isinstance(step, dict):
                    lines.append(f"- {step.get('step', '')}: {step.get('code', '')}")
                else:
                    lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Build KB context for generation")
    parser.add_argument("description", help="Natural language description of desired geometry")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted text")
    parser.add_argument("--max-nodes", type=int, default=15, help="Max nodes to include")
    args = parser.parse_args()

    kb = load_kb()
    context = build_context(kb, args.description, max_nodes=args.max_nodes)

    if args.json:
        print(json.dumps(context, indent=2, default=str))
    else:
        print(format_context_for_prompt(context))
